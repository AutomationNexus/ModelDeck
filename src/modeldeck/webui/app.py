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
    extract_codex_account_id,
    generate_state,
    generate_verifier,
    parse_code_and_state,
)
from modeldeck.auth.provider_specs import get_spec, supported_oauth_providers
from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import (
    PROVIDER_DISPLAY_NAMES,
    ProviderAccount,
    load_config,
    next_account_id,
)
from modeldeck.config.secrets_writer import write_account_secrets
from modeldeck.core.logging import get_logger
from modeldeck.core.paths import config_path
from modeldeck.mqtt.discovery import (
    METRIC_META,
    bridge_status_topic,
    discovery_object_id,
    discovery_topic,
    homeassistant_entity_id,
    state_topic,
)

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
        "id": "codex",
        "name": PROVIDER_DISPLAY_NAMES["codex"],
        "oauth": True,
        # Default mode for the wizard — OAuth is recommended for independent sessions.
        "default_mode": "subscription",
        # paste_back_note: shown in the OAuth wizard for this provider.
        "oauth_paste_back_note": (
            "Open the authorization URL in your browser and sign in. "
            "The page at localhost:1455 will fail to load — that is expected. "
            "Copy the entire URL from your browser's address bar and paste it below. "
            "ModelDeck extracts the authorization code automatically."
        ),
        "auth_modes": [
            {
                "id": "subscription",
                "label": "Subscription (ChatGPT Plus/Pro) — OAuth",
                "fields": [
                    {"id": "access_token", "label": "Access token", "type": "password", "hint": "eyJ… from ~/.codex/auth.json (or use OAuth above)"},
                    {"id": "refresh_token", "label": "Refresh token", "type": "password", "hint": "Optional, from auth.json"},
                    {"id": "account_id", "label": "Account ID", "type": "text", "hint": "user-… from auth.json (filled automatically by OAuth)"},
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
        "id": "claude",
        "name": PROVIDER_DISPLAY_NAMES["claude"],
        "oauth": True,
        # Default mode for the wizard — OAuth gives an independent session.
        "default_mode": "oauth",
        "oauth_paste_back_note": (
            "Open the authorization URL in your browser and sign in to Claude. "
            "After authorizing, you will be redirected to console.anthropic.com where "
            "the authorization code is displayed. Copy the entire URL from your browser's "
            "address bar (or just the code shown on the page) and paste it below. "
            "ModelDeck extracts the authorization code automatically."
        ),
        "auth_modes": [
            {
                "id": "oauth",
                "label": "OAuth (Claude Code — independent session)",
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
        "id": "cursor",
        "name": PROVIDER_DISPLAY_NAMES["cursor"],
        "oauth": False,
        "default_mode": "personal",
        # no_oauth_note: shown on Cursor accounts in the UI.
        "no_oauth_note": (
            "Cursor has no public OAuth flow. This token shares your browser/app session "
            "and may be invalidated if you log out of Cursor on your device."
        ),
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
    """Create a new provider account.

    Labels are always server-generated ("{Provider Display Name} {n}") and
    are not user-customizable — there is no ``label`` field here by design.
    """

    provider: str
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
        # Mount /static for legacy references and /assets for Vite-built bundles
        # (Vite base:"./" makes asset URLs relative, so ./assets/x.js from page
        # at / becomes GET /assets/x.js — serve assets dir at /assets directly).
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
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

        # Default for a brand-new wizard account (not yet written to disk) is
        # the same server-generated "{Provider Display Name} {n}" label that
        # POST /accounts already returned as a preview — never the bare
        # account_id. If the account already exists on disk (e.g. re-login),
        # its stored label wins.
        label = f"{PROVIDER_DISPLAY_NAMES.get(provider, provider)} {account_id}"
        try:
            config, _ = load_config()
            accounts = getattr(config.providers, provider, [])
            for acct in accounts:
                if isinstance(acct, ProviderAccount) and acct.id == account_id:
                    label = acct.label or label
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
            code, state = parse_code_and_state(body.code_or_redirect)
            tokens = await exchange_code(spec, code, session["verifier"], state=state)
        except OAuthFlowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        fields: dict[str, str] = {}
        if isinstance(tokens.get("access_token"), str):
            fields["access_token"] = tokens["access_token"]
        if isinstance(tokens.get("refresh_token"), str):
            fields["refresh_token"] = tokens["refresh_token"]
        if not fields:
            raise HTTPException(status_code=502, detail="Token exchange returned no tokens.")

        # Codex: extract account_id from id_token and persist it.
        # The codex subscription collector sends ChatGPT-Account-Id header
        # using this value; without it some API calls may fail.
        if provider == "codex":
            id_token = tokens.get("id_token", "")
            if isinstance(id_token, str) and id_token:
                acct_id_val = extract_codex_account_id(id_token)
                if acct_id_val:
                    fields["account_id"] = acct_id_val

        write_account_secrets(provider, account_id, fields)

        # Determine the correct auth_mode for this provider's OAuth flow:
        # - Codex OAuth tokens are used in "subscription" mode by the collector
        # - Claude OAuth tokens are used in "oauth" mode
        oauth_auth_mode = "subscription" if provider == "codex" else "oauth"
        upsert_account_in_config(
            provider, account_id, session["label"], auth_mode=oauth_auth_mode, enabled=True
        )
        logger.info("OAuth complete for %s/%s (mode=%s)", provider, account_id, oauth_auth_mode)
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

        # Resolve auth_mode and label from existing config; default label for
        # a brand-new wizard account (not yet on disk) is the same
        # server-generated "{Provider Display Name} {n}" label POST /accounts
        # already returned as a preview — never the bare account_id.
        auth_mode = "auto"
        label = f"{PROVIDER_DISPLAY_NAMES.get(provider, provider)} {account_id}"
        try:
            config, _ = load_config()
            accts = getattr(config.providers, provider, [])
            for a in accts:
                if isinstance(a, ProviderAccount) and a.id == account_id:
                    auth_mode = a.auth_mode
                    label = a.label or label
                    break
        except Exception:
            pass

        # Upsert: create (with the generated/preserved label) or enable existing account.
        upsert_account_in_config(provider, account_id, label, auth_mode=auth_mode, enabled=True)
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

        account_id = next_account_id(existing_ids)
        label = f"{PROVIDER_DISPLAY_NAMES[body.provider]} {account_id}"
        # Return the reserved id; config is written only after credentials are confirmed.
        return {
            "provider": body.provider,
            "id": account_id,
            "label": label,
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
    # POST /accounts/{provider}/{account_id}/switch-oauth
    # Switch an existing account to OAuth mode and start the OAuth wizard.
    # Returns the same payload as oauth/start so the UI can immediately show
    # the authorize URL and paste box without a separate request.
    # 400 for Cursor (no OAuth support).
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/switch-oauth",
              response_model=OAuthStartResponse)
    async def switch_oauth(provider: str, account_id: str) -> dict[str, Any]:
        """Switch account to OAuth mode and return authorize URL (combined action)."""
        spec = get_spec(provider)
        if spec is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Provider '{provider}' does not support OAuth. "
                    "Cursor has no public OAuth/device flow — use Paste credentials instead."
                ),
            )

        # Determine the oauth auth_mode label for this provider.
        oauth_mode = "subscription" if provider == "codex" else "oauth"

        # Look up current label (preserve it); update auth_mode in config.
        # Fall back to the generated "{Provider Display Name} {n}" label
        # (never the bare account_id) if the account somehow has none.
        label = f"{PROVIDER_DISPLAY_NAMES.get(provider, provider)} {account_id}"
        try:
            cfg, _ = load_config()
            accts = getattr(cfg.providers, provider, [])
            for a in accts:
                if isinstance(a, ProviderAccount) and a.id == account_id:
                    label = a.label or label
                    break
        except Exception:
            pass

        upsert_account_in_config(
            provider, account_id, label, auth_mode=oauth_mode, enabled=False
        )

        # Start the OAuth session.
        _prune_sessions()
        verifier = generate_verifier()
        state = generate_state()
        url = build_authorize_url(spec, verifier, state)

        session_key = generate_state()
        _OAUTH_SESSIONS[session_key] = {
            "verifier": verifier,
            "state": state,
            "provider": provider,
            "account_id": account_id,
            "label": label,
            "expires": time.time() + _SESSION_TTL,
        }
        logger.info("Switch-to-OAuth started for %s/%s (mode=%s)", provider, account_id, oauth_mode)
        return {
            "authorize_url": url,
            "session_key": session_key,
            "provider": provider,
            "account_id": account_id,
            "label": label,
        }

    # -----------------------------------------------------------------------
    # GET /providers — provider metadata + per-mode credential field maps
    # -----------------------------------------------------------------------

    @app.get("/providers")
    async def list_providers() -> JSONResponse:
        """Return provider metadata including per-mode required credential fields."""
        return JSONResponse({"providers": list(_PROVIDER_META.values())})

    # -----------------------------------------------------------------------
    # GET /accounts/{provider}/{account_id}/entities
    # Return entity IDs and MQTT topics for an account (static derivation;
    # no network or MQTT connection needed).  Lists the candidate metric set
    # for the account's auth_mode — actual HA entities are the populated
    # subset (effective_metrics) which depends on the provider response.
    # -----------------------------------------------------------------------

    @app.get("/accounts/{provider}/{account_id}/entities")
    async def account_entities(provider: str, account_id: str) -> JSONResponse:
        """Return entity IDs and MQTT topics for an account."""
        if provider not in _PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

        try:
            config, _ = load_config()
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

        mqtt = config.mqtt
        auth_mode = account.auth_mode if account.auth_mode != "auto" else (
            "subscription" if provider == "codex" else
            "oauth" if provider == "claude" else
            "personal"
        )
        candidates = base_metrics(provider, auth_mode)

        entities = []
        for metric in candidates:
            meta = METRIC_META.get(metric, {})
            entities.append({
                "metric": metric.value,
                "name": meta.get("name_suffix", metric.value),
                "entity_id": homeassistant_entity_id(provider, account_id, metric),
                "object_id": discovery_object_id(provider, account_id, metric),
                "state_topic": state_topic(mqtt, provider, account_id, metric),
                "discovery_topic": discovery_topic(mqtt, provider, account_id, metric),
            })

        return JSONResponse({
            "provider": provider,
            "account_id": account_id,
            "label": account.label or account_id,
            "device_id": f"modeldeck_{provider}_{account_id}",
            "topic_prefix": mqtt.topic_prefix,
            "discovery_prefix": mqtt.discovery_prefix,
            "availability_topic": bridge_status_topic(mqtt),
            "entities": entities,
        })

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
