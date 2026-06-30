"""ModelDeck Ingress web UI — FastAPI application.

Provides a browser-based interface for managing provider accounts:
- List accounts and live status
- Start OAuth login wizard (Claude/Codex): returns authorize URL
- Complete OAuth login: accept pasted code, exchange, save
- Paste token (Cursor, API keys): save directly
- Verify account credentials live
- Delete account and retire MQTT sensors
- Disable / enable accounts

Bound to Ingress port only — never exposed externally.
No secret values are returned in API responses.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modeldeck.auth.oauth_flow import (
    OAuthFlowError,
    build_authorize_url,
    exchange_code,
    extract_code_from_redirect,
    generate_state,
    generate_verifier,
)
from modeldeck.auth.provider_specs import get_spec, supported_oauth_providers
from modeldeck.config.loader import ProviderAccount, load_config, slugify
from modeldeck.config.secrets_writer import write_account_secrets
from modeldeck.core.logging import get_logger
from modeldeck.core.paths import config_path

logger = get_logger(__name__)

# In-memory PKCE session store with TTL (5 minutes).
# Stores {session_key: {verifier, state, provider, account_id, label, expires}}
_OAUTH_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL = 300  # seconds

_PROVIDERS = ("codex", "claude", "cursor")

# Per-provider auth modes and their required credential fields.
# Used by /providers endpoint so the UI renders the right inputs per mode.
_PROVIDER_META: dict[str, dict[str, Any]] = {
    "codex": {
        "name": "OpenAI Codex",
        "oauth": True,
        "auth_modes": [
            {
                "id": "subscription",
                "label": "Subscription (ChatGPT Plus/Pro)",
                "fields": [
                    {"id": "access_token", "label": "Access token", "type": "password", "hint": "eyJ… from ~/.codex/auth.json"},
                    {"id": "refresh_token", "label": "Refresh token", "type": "password", "hint": "rt_… from ~/.codex/auth.json"},
                    {"id": "account_id", "label": "Account ID", "type": "text", "hint": "user-… from ~/.codex/auth.json"},
                ],
                "oauth_capable": True,
            },
            {
                "id": "api",
                "label": "API billing (sk-admin key)",
                "fields": [
                    {"id": "api_key", "label": "Organization Admin API key", "type": "password", "hint": "sk-admin-…"},
                ],
                "oauth_capable": False,
            },
        ],
    },
    "claude": {
        "name": "Claude",
        "oauth": True,
        "auth_modes": [
            {
                "id": "oauth",
                "label": "OAuth (Claude Code)",
                "fields": [],
                "oauth_capable": True,
            },
            {
                "id": "cookie",
                "label": "Cookie (claude.ai Pro/Max web)",
                "fields": [
                    {"id": "session_token", "label": "sessionKey cookie", "type": "password", "hint": "sk-ant-sid01-…"},
                    {"id": "org_id", "label": "Organization ID", "type": "text", "hint": "org_…"},
                    {"id": "cf_clearance", "label": "cf_clearance cookie (if 403)", "type": "password", "hint": "optional"},
                    {"id": "device_id", "label": "Device ID cookie (if 403)", "type": "text", "hint": "optional"},
                ],
                "oauth_capable": False,
            },
        ],
    },
    "cursor": {
        "name": "Cursor",
        "oauth": False,
        "auth_modes": [
            {
                "id": "personal",
                "label": "Personal (Pro/Ultra)",
                "fields": [
                    {"id": "session_token", "label": "WorkosCursorSessionToken", "type": "password", "hint": "From cursor.com/dashboard/usage cookies"},
                    {"id": "access_token", "label": "App JWT (alternative)", "type": "password", "hint": "eyJ… from Cursor state.vscdb"},
                ],
                "oauth_capable": False,
            },
            {
                "id": "enterprise",
                "label": "Enterprise / Team",
                "fields": [
                    {"id": "admin_api_key", "label": "Team Admin API key", "type": "password", "hint": "crsr_…"},
                ],
                "oauth_capable": False,
            },
        ],
    },
}


def _prune_sessions() -> None:
    """Remove expired OAuth sessions."""
    now = time.time()
    expired = [k for k, v in _OAUTH_SESSIONS.items() if v.get("expires", 0) < now]
    for k in expired:
        del _OAUTH_SESSIONS[k]


def _load_accounts() -> list[dict[str, Any]]:
    """Load all configured accounts as safe dicts (no secret values)."""
    try:
        config, _ = load_config()
    except Exception:
        return []
    result = []
    for provider in _PROVIDERS:
        accounts = getattr(config.providers, provider, [])
        if not isinstance(accounts, list):
            continue
        for acct in accounts:
            if not isinstance(acct, ProviderAccount):
                continue
            result.append({
                "provider": provider,
                "id": acct.id,
                "label": acct.label,
                "enabled": acct.enabled,
                "auth_mode": acct.auth_mode,
            })
    return result


def upsert_account_in_config(
    provider: str,
    account_id: str,
    label: str,
    *,
    auth_mode: str,
    enabled: bool,
) -> None:
    """Add or update an account in modeldeck.yaml.

    Unlike the old append-only helper, this updates ``enabled``, ``auth_mode``,
    and ``label`` when an account with ``account_id`` already exists.
    """
    path = config_path()
    if not path.exists():
        return

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    providers = raw.setdefault("providers", {})
    accounts: list[dict[str, Any]] = providers.get(provider, [])
    if not isinstance(accounts, list):
        accounts = []

    existing_idx = next(
        (i for i, a in enumerate(accounts) if isinstance(a, dict) and a.get("id") == account_id),
        None,
    )
    if existing_idx is not None:
        accounts[existing_idx]["enabled"] = enabled
        accounts[existing_idx]["auth_mode"] = auth_mode
        if label:
            accounts[existing_idx]["label"] = label
    else:
        accounts.append({
            "id": account_id,
            "label": label,
            "enabled": enabled,
            "auth_mode": auth_mode,
        })

    providers[provider] = accounts
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    logger.info("Upserted account %s/%s (enabled=%s)", provider, account_id, enabled)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class CreateAccountRequest(BaseModel):
    """Create a new provider account."""

    provider: str
    label: str
    auth_mode: str = "auto"


class OAuthStartResponse(BaseModel):
    """Authorization URL and session key for the browser step."""

    authorize_url: str
    session_key: str
    provider: str
    account_id: str
    label: str


class OAuthCompleteRequest(BaseModel):
    """User pastes back the authorization code or redirect URL."""

    session_key: str
    code_or_redirect: str


class PasteTokenRequest(BaseModel):
    """Paste a credential field for a provider account."""

    field: str  # explicit field name; no prefix guessing
    value: str


class AccountResponse(BaseModel):
    """Safe account info (no secret values)."""

    provider: str
    id: str
    label: str
    enabled: bool
    auth_mode: str


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the ModelDeck web UI FastAPI application."""
    app = FastAPI(
        title="ModelDeck",
        description="AI quota monitor — account management UI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    # Allow CI / tests to override the static dir via env var so path
    # resolution is independent of editable-install layout.
    _static_env = os.environ.get("MODELDECK_STATIC_DIR")
    static_dir = Path(_static_env) if _static_env else Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # -----------------------------------------------------------------------
    # GET / — serve dashboard UI
    # -----------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> HTMLResponse:
        """Serve the single-page account management UI."""
        html_file = static_dir / "index.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))
        return HTMLResponse(_fallback_html(), status_code=200)

    # -----------------------------------------------------------------------
    # GET /accounts — list all accounts (no secrets)
    # -----------------------------------------------------------------------

    @app.get("/accounts", response_model=list[AccountResponse])
    async def list_accounts() -> list[dict[str, Any]]:
        """List all configured provider accounts."""
        return _load_accounts()

    # -----------------------------------------------------------------------
    # POST /accounts/{provider}/{account_id}/oauth/start
    # (Single-wizard: caller selects provider+label+mode first, then starts
    # OAuth; account is written to config only on successful credential step.)
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/oauth/start",
              response_model=OAuthStartResponse)
    async def oauth_start(provider: str, account_id: str) -> dict[str, Any]:
        """Start the OAuth PKCE login wizard. Returns authorize URL."""
        spec = get_spec(provider)
        if spec is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Provider '{provider}' does not support OAuth. "
                    f"Supported: {supported_oauth_providers()}"
                ),
            )

        _prune_sessions()
        verifier = generate_verifier()
        state = generate_state()
        url = build_authorize_url(spec, verifier, state)

        label = account_id
        try:
            config, _ = load_config()
            accounts = getattr(config.providers, provider, [])
            for acct in accounts:
                if isinstance(acct, ProviderAccount) and acct.id == account_id:
                    label = acct.label or account_id
                    break
        except Exception:
            pass

        session_key = generate_state()
        _OAUTH_SESSIONS[session_key] = {
            "verifier": verifier,
            "state": state,
            "provider": provider,
            "account_id": account_id,
            "label": label,
            "expires": time.time() + _SESSION_TTL,
        }
        return {
            "authorize_url": url,
            "session_key": session_key,
            "provider": provider,
            "account_id": account_id,
            "label": label,
        }

    # -----------------------------------------------------------------------
    # POST /accounts/{provider}/{account_id}/oauth/complete
    # On success: upsert account as enabled with auth_mode=oauth.
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/oauth/complete")
    async def oauth_complete(
        provider: str, account_id: str, body: OAuthCompleteRequest
    ) -> JSONResponse:
        """Complete OAuth: exchange pasted code for tokens, save, enable account."""
        _prune_sessions()
        session = _OAUTH_SESSIONS.pop(body.session_key, None)
        if session is None:
            raise HTTPException(status_code=400, detail="OAuth session expired or not found.")
        if session["provider"] != provider or session["account_id"] != account_id:
            raise HTTPException(status_code=400, detail="Session provider/account mismatch.")

        spec = get_spec(provider)
        if spec is None:
            raise HTTPException(status_code=400, detail="Provider not OAuth-capable.")

        try:
            code = extract_code_from_redirect(body.code_or_redirect)
            tokens = await exchange_code(spec, code, session["verifier"])
        except OAuthFlowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        fields: dict[str, str] = {}
        if isinstance(tokens.get("access_token"), str):
            fields["access_token"] = tokens["access_token"]
        if isinstance(tokens.get("refresh_token"), str):
            fields["refresh_token"] = tokens["refresh_token"]
        if not fields:
            raise HTTPException(status_code=502, detail="Token exchange returned no tokens.")

        write_account_secrets(provider, account_id, fields)
        # Upsert: create or enable existing account with oauth mode.
        upsert_account_in_config(
            provider, account_id, session["label"], auth_mode="oauth", enabled=True
        )
        logger.info("OAuth complete for %s/%s", provider, account_id)
        return JSONResponse({"status": "ok", "account_id": account_id, "provider": provider})

    # -----------------------------------------------------------------------
    # POST /accounts/{provider}/{account_id}/token — paste credential fields
    # On success: upsert account as enabled.
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/token")
    async def paste_token(
        provider: str, account_id: str, body: PasteTokenRequest
    ) -> JSONResponse:
        """Save a pasted credential field for an account and enable it."""
        valid_fields = {
            "access_token", "session_token", "api_key", "refresh_token",
            "account_id", "org_id", "cf_clearance", "device_id", "admin_api_key",
        }
        if body.field not in valid_fields:
            raise HTTPException(status_code=400, detail=f"Unknown field: {body.field}")
        if not body.value.strip():
            raise HTTPException(status_code=400, detail="Value must not be empty.")

        write_account_secrets(provider, account_id, {body.field: body.value.strip()})

        # Resolve auth_mode from existing config or default.
        auth_mode = "auto"
        try:
            config, _ = load_config()
            accts = getattr(config.providers, provider, [])
            for a in accts:
                if isinstance(a, ProviderAccount) and a.id == account_id:
                    auth_mode = a.auth_mode
                    break
        except Exception:
            pass

        # Upsert: create (with account_id as label) or enable existing account.
        upsert_account_in_config(provider, account_id, account_id, auth_mode=auth_mode, enabled=True)
        return JSONResponse({"status": "ok"})

    # -----------------------------------------------------------------------
    # POST /accounts — wizard: register label+mode, return account_id.
    # Credentials are saved by /token or /oauth/complete; account is NOT
    # written to config until credential step succeeds.
    # -----------------------------------------------------------------------

    @app.post("/accounts", response_model=AccountResponse, status_code=201)
    async def create_account(body: CreateAccountRequest) -> dict[str, Any]:
        """Reserve an account_id for the wizard flow (config written on credential step)."""
        if body.provider not in _PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
        try:
            config, _ = load_config()
            existing = getattr(config.providers, body.provider, [])
            existing_ids = {a.id for a in existing if isinstance(a, ProviderAccount)}
        except Exception:
            existing_ids = set()

        account_id = slugify(body.label or body.provider, existing_ids)
        # Return the reserved id; config is written only after credentials are confirmed.
        return {
            "provider": body.provider,
            "id": account_id,
            "label": body.label,
            "enabled": False,
            "auth_mode": body.auth_mode,
        }

    # -----------------------------------------------------------------------
    # POST /accounts/{provider}/{account_id}/verify
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/verify")
    async def verify_account(provider: str, account_id: str) -> JSONResponse:
        """Run a live credential check and return status (no secret values)."""
        from modeldeck.collectors.auth_resolve import (
            pick_claude_mode,
            pick_codex_mode,
            pick_cursor_mode,
            resolve_claude_secrets,
            resolve_codex_secrets,
            resolve_cursor_secrets,
        )
        from modeldeck.collectors.claude import ClaudeCollector
        from modeldeck.collectors.codex import CodexCollector
        from modeldeck.collectors.cursor import CursorCollector
        from modeldeck.config.loader import ProviderSecrets

        resolvers = {
            "codex": (CodexCollector, resolve_codex_secrets, pick_codex_mode),
            "claude": (ClaudeCollector, resolve_claude_secrets, pick_claude_mode),
            "cursor": (CursorCollector, resolve_cursor_secrets, pick_cursor_mode),
        }
        if provider not in resolvers:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

        try:
            config, secrets = load_config()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc

        accounts = getattr(config.providers, provider, [])
        account = next(
            (a for a in accounts if isinstance(a, ProviderAccount) and a.id == account_id),
            None,
        )
        if account is None:
            raise HTTPException(
                status_code=404, detail=f"Account {provider}/{account_id} not found."
            )

        acct_secrets = secrets.providers.get(provider, {}).get(account_id, ProviderSecrets())
        collector_cls, resolve_fn, _ = resolvers[provider]
        resolved = resolve_fn(account, acct_secrets)
        collector = collector_cls(config, acct_secrets, account, account_id)

        try:
            snapshot = await asyncio.wait_for(collector.collect(), timeout=30.0)
        except Exception as exc:
            detail = f"Collection error: {type(exc).__name__}"
            raise HTTPException(status_code=502, detail=detail) from exc

        return JSONResponse({
            "status": snapshot.status.value,
            "provider": provider,
            "account_id": account_id,
            "auth_mode": str(getattr(resolved, "auth_mode", "unknown")),
        })

    # -----------------------------------------------------------------------
    # DELETE /accounts/{provider}/{account_id}
    # -----------------------------------------------------------------------

    @app.delete("/accounts/{provider}/{account_id}")
    async def delete_account(provider: str, account_id: str) -> JSONResponse:
        """Remove account from config and secrets."""
        from modeldeck.core.paths import secrets_path

        cfg_path = config_path()
        if cfg_path.exists():
            raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            accounts: list[Any] = raw.get("providers", {}).get(provider, [])
            if isinstance(accounts, list):
                before = len(accounts)
                accounts = [
                    a for a in accounts
                    if not (isinstance(a, dict) and a.get("id") == account_id)
                ]
                if len(accounts) < before:
                    raw["providers"][provider] = accounts
                    cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        sec_path = secrets_path()
        if sec_path.exists():
            raw_sec: dict[str, Any] = yaml.safe_load(sec_path.read_text(encoding="utf-8")) or {}
            prov_sec = raw_sec.get("providers", {}).get(provider, {})
            if isinstance(prov_sec, dict) and account_id in prov_sec:
                del prov_sec[account_id]
                raw_sec["providers"][provider] = prov_sec
                sec_path.write_text(yaml.safe_dump(raw_sec, sort_keys=False), encoding="utf-8")

        logger.info("Deleted account %s/%s", provider, account_id)
        return JSONResponse({"status": "ok", "message": "Restart service to retire MQTT sensors."})

    # -----------------------------------------------------------------------
    # PATCH /accounts/{provider}/{account_id} — enable/disable
    # -----------------------------------------------------------------------

    @app.patch("/accounts/{provider}/{account_id}")
    async def patch_account(
        provider: str, account_id: str, request: Request
    ) -> JSONResponse:
        """Enable or disable an account."""
        body = await request.json()
        enabled = body.get("enabled")
        if enabled is None:
            raise HTTPException(status_code=400, detail="Body must contain 'enabled' bool.")

        cfg_path = config_path()
        if not cfg_path.exists():
            raise HTTPException(status_code=404, detail="Config not found.")

        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        accounts: list[Any] = raw.get("providers", {}).get(provider, [])
        changed = False
        for acct in accounts:
            if isinstance(acct, dict) and acct.get("id") == account_id:
                acct["enabled"] = bool(enabled)
                changed = True
        if not changed:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found.")
        raw["providers"][provider] = accounts
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        return JSONResponse({"status": "ok", "enabled": bool(enabled)})

    # -----------------------------------------------------------------------
    # GET /providers — provider metadata + per-mode credential field maps
    # -----------------------------------------------------------------------

    @app.get("/providers")
    async def list_providers() -> JSONResponse:
        """Return provider metadata including per-mode required credential fields."""
        return JSONResponse({"providers": list(_PROVIDER_META.values())})

    return app


# ---------------------------------------------------------------------------
# Fallback HTML (served when static/index.html not present — dev without build)
# ---------------------------------------------------------------------------

def _fallback_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ModelDeck</title>
<style>
  body{font-family:sans-serif;max-width:600px;margin:4rem auto;padding:1rem;background:#111;color:#eee;}
  h1{color:#38bdf8;}
  p{color:#94a3b8;}
  code{background:#1e293b;padding:2px 6px;border-radius:4px;font-size:.9em;}
</style>
</head>
<body>
<h1>ModelDeck</h1>
<p>The management UI requires a production build.</p>
<p>Run <code>cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</code> then restart the server.</p>
</body>
</html>"""
