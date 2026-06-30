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
import time
from pathlib import Path
from typing import Any

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
from modeldeck.cli.login_cmd import _ensure_account_in_config
from modeldeck.config.loader import ProviderAccount, load_config, slugify
from modeldeck.config.secrets_writer import write_account_secrets
from modeldeck.core.logging import get_logger

logger = get_logger(__name__)

# In-memory PKCE session store with TTL (5 minutes).
# Stores {session_key: {verifier, state, provider, account_id, label, expires}}
_OAUTH_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL = 300  # seconds

_PROVIDERS = ("codex", "claude", "cursor")


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
    """Paste a token or API key for Cursor or API-key modes."""

    token: str
    field: str = "access_token"  # access_token | session_token | api_key


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
        docs_url=None,  # disable Swagger UI in production
        redoc_url=None,
    )

    static_dir = Path(__file__).parent / "static"
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
    # POST /accounts — create a new account entry (config only, no token yet)
    # -----------------------------------------------------------------------

    @app.post("/accounts", response_model=AccountResponse, status_code=201)
    async def create_account(body: CreateAccountRequest) -> dict[str, Any]:
        """Create a new account in modeldeck.yaml."""
        if body.provider not in _PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
        try:
            config, _ = load_config()
            existing = getattr(config.providers, body.provider, [])
            existing_ids = {a.id for a in existing if isinstance(a, ProviderAccount)}
        except Exception:
            existing_ids = set()

        account_id = slugify(body.label or body.provider, existing_ids)
        _ensure_account_in_config(
            body.provider, account_id, body.label, auth_mode=body.auth_mode, enabled=False
        )
        return {
            "provider": body.provider,
            "id": account_id,
            "label": body.label,
            "enabled": False,
            "auth_mode": body.auth_mode,
        }

    # -----------------------------------------------------------------------
    # POST /accounts/{provider}/{account_id}/oauth/start
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

        # Load label from config.
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

        session_key = generate_state()  # random key to identify this flow
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
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/oauth/complete")
    async def oauth_complete(
        provider: str, account_id: str, body: OAuthCompleteRequest
    ) -> JSONResponse:
        """Complete OAuth: exchange pasted code for tokens and save."""
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
        _ensure_account_in_config(
            provider, account_id, session["label"], auth_mode="oauth", enabled=True
        )
        logger.info("OAuth complete for %s/%s", provider, account_id)
        return JSONResponse({"status": "ok", "account_id": account_id, "provider": provider})

    # -----------------------------------------------------------------------
    # POST /accounts/{provider}/{account_id}/token — paste-token (Cursor, api)
    # -----------------------------------------------------------------------

    @app.post("/accounts/{provider}/{account_id}/token")
    async def paste_token(
        provider: str, account_id: str, body: PasteTokenRequest
    ) -> JSONResponse:
        """Save a pasted token or API key for an account."""
        if body.field not in ("access_token", "session_token", "api_key", "refresh_token"):
            raise HTTPException(status_code=400, detail=f"Unknown field: {body.field}")
        if not body.token.strip():
            raise HTTPException(status_code=400, detail="Token must not be empty.")

        write_account_secrets(provider, account_id, {body.field: body.token.strip()})
        _ensure_account_in_config(provider, account_id, account_id, auth_mode="auto", enabled=True)
        return JSONResponse({"status": "ok"})

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
        import yaml

        from modeldeck.core.paths import config_path, secrets_path

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
        import yaml

        from modeldeck.core.paths import config_path

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
    # GET /providers — list OAuth-capable providers
    # -----------------------------------------------------------------------

    @app.get("/providers")
    async def list_providers() -> JSONResponse:
        """Return provider metadata for the UI."""
        return JSONResponse({
            "providers": [
                {
                    "id": "claude",
                    "name": "Claude",
                    "oauth": "claude" in supported_oauth_providers(),
                    "auth_modes": ["oauth", "cookie"],
                },
                {
                    "id": "codex",
                    "name": "OpenAI Codex",
                    "oauth": "codex" in supported_oauth_providers(),
                    "auth_modes": ["subscription", "api"],
                },
                {
                    "id": "cursor",
                    "name": "Cursor",
                    "oauth": False,
                    "auth_modes": ["personal", "enterprise"],
                },
            ]
        })

    return app


# ---------------------------------------------------------------------------
# Fallback HTML (when static/index.html not present)
# ---------------------------------------------------------------------------

def _fallback_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ModelDeck</title>
<style>
  body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 1rem; }
  h1 { color: #1a56db; }
  .account { border: 1px solid #ddd; border-radius: 6px; padding: 1rem; margin: 0.5rem 0; }
  .ok { color: #16a34a; } .error { color: #dc2626; } .disabled { color: #6b7280; }
  button { background: #1a56db; color: white; border: none; padding: 0.4rem 1rem;
           border-radius: 4px; cursor: pointer; }
  button.danger { background: #dc2626; }
  input { border: 1px solid #ddd; padding: 0.3rem 0.5rem; border-radius: 4px; width: 100%; }
  .form { margin-top: 1rem; display: flex; flex-direction: column; gap: 0.5rem; }
  .wizard { background: #f0f9ff; border: 1px solid #0ea5e9; border-radius: 6px; padding: 1rem; }
  pre { background: #f5f5f5; padding: 0.5rem; border-radius: 4px; overflow-x: auto; }
</style>
</head>
<body>
<h1>ModelDeck</h1>
<p>AI usage quota bridge for Home Assistant.</p>
<div id="app"><p>Loading accounts...</p></div>
<h2>Add Account</h2>
<div class="form">
  <label>Provider:
    <select id="add-provider">
      <option value="claude">Claude</option>
      <option value="codex">OpenAI Codex</option>
      <option value="cursor">Cursor</option>
    </select>
  </label>
  <label>Label: <input id="add-label" placeholder="e.g. Personal Claude"></label>
  <label>Auth mode:
    <select id="add-auth-mode">
      <option value="auto">auto</option>
      <option value="oauth">oauth</option>
      <option value="cookie">cookie</option>
      <option value="subscription">subscription</option>
      <option value="api">api</option>
      <option value="personal">personal</option>
      <option value="enterprise">enterprise</option>
    </select>
  </label>
  <button onclick="addAccount()">Add Account</button>
</div>
<div id="wizard-area"></div>
<script>
const api = (method, path, body) => fetch(path, {
  method, headers: {'Content-Type': 'application/json'},
  body: body ? JSON.stringify(body) : undefined,
}).then(r => r.json());

async function load() {
  const accounts = await api('GET', '/accounts');
  const el = document.getElementById('app');
  if (!accounts.length) { el.innerHTML = '<p>No accounts configured.</p>'; return; }
  el.innerHTML = accounts.map(a => `
    <div class="account">
      <b>${a.provider}/${a.id}</b> — ${a.label || '(no label)'}
      <span class="${a.enabled ? 'ok' : 'disabled'}"> [${a.enabled ? 'enabled' : 'disabled'}]</span>
      <span> auth_mode: ${a.auth_mode}</span><br>
      <button onclick="verify('${a.provider}','${a.id}')">Verify</button>
      ${supportsOAuth(a.provider, a.auth_mode) ?
        `<button onclick="startOAuth('${a.provider}','${a.id}')">Re-login (OAuth)</button>` : ''}
      <button onclick="pasteToken('${a.provider}','${a.id}')">Paste Token</button>
      <button onclick="toggleAccount('${a.provider}','${a.id}',${!a.enabled})">${a.enabled ? 'Disable' : 'Enable'}</button>
      <button class="danger" onclick="deleteAccount('${a.provider}','${a.id}')">Delete</button>
      <span id="status-${a.provider}-${a.id}"></span>
    </div>`).join('');
}

function supportsOAuth(provider, mode) {
  return (provider === 'claude' || provider === 'codex') &&
         (mode === 'oauth' || mode === 'subscription' || mode === 'auto');
}

async function addAccount() {
  const provider = document.getElementById('add-provider').value;
  const label = document.getElementById('add-label').value;
  const auth_mode = document.getElementById('add-auth-mode').value;
  const acct = await api('POST', '/accounts', {provider, label, auth_mode});
  if (supportsOAuth(provider, auth_mode)) {
    await startOAuth(provider, acct.id);
  }
  load();
}

async function startOAuth(provider, accountId) {
  const res = await api('POST', `/accounts/${provider}/${accountId}/oauth/start`);
  const area = document.getElementById('wizard-area');
  area.innerHTML = `<div class="wizard">
    <h3>Login: ${provider}/${accountId}</h3>
    <p>1. Open this URL in your browser and log in:</p>
    <pre>${res.authorize_url}</pre>
    <p>2. After authorization, paste the code or redirect URL:</p>
    <input id="oauth-code" placeholder="Paste code or redirect URL">
    <button onclick="completeOAuth('${provider}','${accountId}','${res.session_key}')">Complete Login</button>
  </div>`;
}

async function completeOAuth(provider, accountId, sessionKey) {
  const code = document.getElementById('oauth-code').value;
  const res = await api('POST', `/accounts/${provider}/${accountId}/oauth/complete`,
    {session_key: sessionKey, code_or_redirect: code});
  document.getElementById('wizard-area').innerHTML =
    `<p class="${res.status === 'ok' ? 'ok' : 'error'}">
      ${res.status === 'ok' ? 'Login successful!' : 'Error: ' + JSON.stringify(res)}</p>`;
  load();
}

async function pasteToken(provider, accountId) {
  const token = prompt('Paste JWT, session cookie, or API key:');
  if (!token) return;
  const field = token.startsWith('sk-admin') ? 'api_key' :
                token.startsWith('eyJ') ? 'access_token' : 'session_token';
  await api('POST', `/accounts/${provider}/${accountId}/token`, {token, field});
  load();
}

async function verify(provider, accountId) {
  const el = document.getElementById(`status-${provider}-${accountId}`);
  el.textContent = ' checking...';
  const res = await api('POST', `/accounts/${provider}/${accountId}/verify`);
  el.textContent = ` → ${res.status}`;
  el.className = res.status === 'ok' ? 'ok' : 'error';
}

async function toggleAccount(provider, accountId, enabled) {
  await api('PATCH', `/accounts/${provider}/${accountId}`, {enabled});
  load();
}

async function deleteAccount(provider, accountId) {
  if (!confirm(`Delete ${provider}/${accountId}?`)) return;
  await api('DELETE', `/accounts/${provider}/${accountId}`);
  load();
}

load();
</script>
</body>
</html>"""
