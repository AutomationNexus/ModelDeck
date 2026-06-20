"""Extended dual-auth collector coverage tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from modeldeck.collectors.auth_resolve import (
    pick_claude_mode,
    pick_codex_mode,
    pick_cursor_mode,
    resolve_codex_secrets,
    resolve_cursor_secrets,
)
from modeldeck.collectors.claude_oauth import ClaudeOAuthCollector
from modeldeck.collectors.codex_subscription import CodexSubscriptionCollector
from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage
from modeldeck.collectors.cursor_enterprise import CursorEnterpriseCollector
from modeldeck.collectors.cursor_personal_parser import (
    parse_cursor_period_usage,
    parse_cursor_usage_summary,
)
from modeldeck.config.loader import ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import CollectorStatus

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.asyncio
async def test_codex_subscription_success_path():
    """Subscription collector should parse a successful wham response."""
    payload = json.loads((FIXTURES / "codex_wham_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="token", account_id="acct")
    snap = await CodexSubscriptionCollector(secrets, "Codex", client).collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent_weekly == 24.0


@pytest.mark.asyncio
async def test_claude_oauth_auth_failure_after_refresh():
    """OAuth collector should return auth_error when refresh fails."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if "oauth/token" in str(request.url):
            return httpx.Response(400)
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="bad", refresh_token="refresh")
    snap = await ClaudeOAuthCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_claude_cookie_with_optional_cookies():
    """Cookie collector should send optional Cloudflare and device cookies."""
    payload = json.loads((FIXTURES / "claude_console_usage.json").read_text(encoding="utf-8"))
    seen_cookie = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_cookie
        seen_cookie = request.headers.get("cookie", "")
        return httpx.Response(200, json=payload)

    from modeldeck.collectors.claude_cookie import ClaudeCookieCollector

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(
        session_token="session",
        org_id="org-1",
        cf_clearance="cf",
        device_id="device",
    )
    snap = await ClaudeCookieCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.OK
    assert "cf_clearance=cf" in seen_cookie


def test_load_codex_oauth_default_path_missing(monkeypatch, tmp_path):
    """Default Codex auth path should return empty dict when missing."""
    from modeldeck.collectors.credentials import codex_auth

    monkeypatch.setattr(codex_auth, "default_codex_auth_path", lambda: tmp_path / "missing.json")
    assert codex_auth.load_codex_oauth() == {}


def test_load_cursor_token_from_sqlite(tmp_path):
    """Cursor SQLite store should yield access token."""
    import sqlite3

    from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token

    db_path = tmp_path / "state.vscdb"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
        ("cursorAuth/accessToken", "jwt-token"),
    )
    conn.commit()
    conn.close()
    assert load_cursor_access_token(db_path) == "jwt-token"


def test_pick_explicit_auth_modes():
    """Explicit auth_mode values should bypass auto detection."""
    assert pick_codex_mode(ProviderToggle(auth_mode="api"), ProviderSecrets()) == "api"
    assert pick_claude_mode(ProviderToggle(auth_mode="oauth"), ProviderSecrets()) == "oauth"
    assert (
        pick_cursor_mode(ProviderToggle(auth_mode="enterprise"), ProviderSecrets()) == "enterprise"
    )


def test_legacy_codex_parser_import():
    """Legacy codex_parser module should re-export billing parser."""
    from modeldeck.collectors.codex_parser import parse_codex_usage

    snap = parse_codex_usage({"usage_used": 5, "usage_limit": 10})
    assert snap.usage_percent == 50.0


@pytest.mark.asyncio
async def test_codex_subscription_refresh_success():
    """Subscription collector should retry after successful token refresh."""
    payload = json.loads((FIXTURES / "codex_wham_usage.json").read_text(encoding="utf-8"))
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2"})
        if len([c for c in calls if "wham" in c]) == 1:
            return httpx.Response(401)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="old", refresh_token="refresh")
    snap = await CodexSubscriptionCollector(secrets, "Codex", client).collect()
    assert snap.status == CollectorStatus.OK
    assert secrets.access_token == "new"


@pytest.mark.asyncio
async def test_codex_subscription_live_client(monkeypatch):
    """Subscription collector without injected client should call httpx."""
    payload = json.loads((FIXTURES / "codex_wham_usage.json").read_text(encoding="utf-8"))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.codex_subscription.httpx.AsyncClient", lambda **k: FakeClient()
    )
    secrets = ProviderSecrets(access_token="token")
    snap = await CodexSubscriptionCollector(secrets, "Codex").collect()
    assert snap.status == CollectorStatus.OK


@pytest.mark.asyncio
async def test_claude_oauth_live_client_and_parse_error(monkeypatch):
    """OAuth collector live client branch and transport parse errors."""
    from modeldeck.collectors.claude_oauth import ClaudeOAuthCollector

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return json.loads((FIXTURES / "claude_oauth_usage.json").read_text(encoding="utf-8"))

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.claude_oauth.httpx.AsyncClient",
        lambda **k: FakeClient(),
    )
    snap = await ClaudeOAuthCollector(ProviderSecrets(access_token="t"), "Claude").collect()
    assert snap.status == CollectorStatus.OK
    monkeypatch.undo()

    async def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    err = await ClaudeOAuthCollector(ProviderSecrets(access_token="t"), "Claude", client).collect()
    assert err.status == CollectorStatus.UNAVAILABLE


def test_codex_wham_parser_edge_cases():
    """Wham parser should handle empty windows and unix resets."""
    snap = parse_codex_wham_usage({"rate_limit": {}})
    assert snap.usage_percent is None
    snap2 = parse_codex_wham_usage(
        {"rate_limit": {"primary_window": {"used_percent": 1, "reset_at": 1700000000}}}
    )
    assert snap2.reset_at is not None


def test_cursor_parser_edge_cases():
    """Cursor parsers should handle millis timestamps and computed percent."""
    snap = parse_cursor_period_usage(
        {
            "billingCycleEnd": "1771077734000",
            "planUsage": {"remaining": 100, "limit": 200},
        }
    )
    assert snap.usage_percent == 50.0
    snap2 = parse_cursor_usage_summary({"planUsage": {"totalPercentUsed": 12.5}})
    assert snap2.usage_percent == 12.5


def test_codex_auth_paths(monkeypatch, tmp_path):
    """Codex auth loader should honor CODEX_HOME and config path."""
    from modeldeck.collectors.credentials import codex_auth

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"access_token": "from-home"}}), encoding="utf-8")
    assert codex_auth.load_codex_oauth()["access_token"] == "from-home"

    config_auth = tmp_path / "config-auth.json"
    config_auth.write_text(json.dumps({"tokens": {}}), encoding="utf-8")
    assert codex_auth.load_codex_oauth(config_auth) == {}


def test_claude_auth_invalid_json(tmp_path):
    """Invalid Claude credentials JSON should return empty dict."""
    from modeldeck.collectors.credentials.claude_auth import load_claude_oauth

    bad = tmp_path / "bad.json"
    bad.write_text("not-json", encoding="utf-8")
    assert load_claude_oauth(bad) == {}


def test_resolve_cursor_with_access_token_short_circuit():
    """Cursor resolver should skip file lookup when access_token is set."""
    toggle = ProviderToggle(credential_path="/should/not/read")
    merged = resolve_cursor_secrets(toggle, ProviderSecrets(access_token="already"))
    assert merged.access_token == "already"


@pytest.mark.asyncio
async def test_claude_oauth_refresh_retry_success():
    """OAuth collector should retry usage fetch after refresh."""
    payload = json.loads((FIXTURES / "claude_oauth_usage.json").read_text(encoding="utf-8"))
    usage_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal usage_calls
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "new", "refresh_token": "r"})
        usage_calls += 1
        if usage_calls == 1:
            return httpx.Response(401)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="old", refresh_token="refresh")
    snap = await ClaudeOAuthCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.OK


@pytest.mark.asyncio
async def test_claude_oauth_missing_token():
    """OAuth collector without tokens should return auth_error."""
    snap = await ClaudeOAuthCollector(ProviderSecrets(), "Claude").collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_cursor_enterprise_live_client(monkeypatch):
    """Enterprise collector should use httpx when no client is injected."""
    payload = json.loads((FIXTURES / "cursor_enterprise_usage.json").read_text(encoding="utf-8"))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, json=None, auth=None):
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.cursor_enterprise.httpx.AsyncClient", lambda **k: FakeClient()
    )
    snap = await CursorEnterpriseCollector(ProviderSecrets(admin_api_key="k"), "Cursor").collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_used == 32.5


def test_auth_resolve_auto_defaults():
    """Auto mode without credentials should fall back to default modes."""
    empty = ProviderSecrets()
    assert pick_codex_mode(ProviderToggle(auth_mode="auto"), empty) == "subscription"
    assert pick_claude_mode(ProviderToggle(auth_mode="auto"), empty) == "cookie"
    assert pick_cursor_mode(ProviderToggle(auth_mode="auto"), empty) == "personal"


def test_credential_path_expansion(tmp_path):
    """Custom credential_path should expand user home segments."""
    path = tmp_path / "auth.json"
    path.write_text("{}", encoding="utf-8")
    toggle = ProviderToggle(credential_path=str(path))
    assert resolve_codex_secrets(toggle, ProviderSecrets()).access_token == ""


@pytest.mark.asyncio
async def test_codex_subscription_parse_error():
    """Transport errors in subscription collector should map to parse_error."""

    async def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    snap = await CodexSubscriptionCollector(
        ProviderSecrets(access_token="t"), "Codex", client
    ).collect()
    assert snap.status == CollectorStatus.PARSE_ERROR


@pytest.mark.asyncio
async def test_claude_oauth_refresh_retry_still_fails():
    """OAuth collector should surface auth_error when retry still fails."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "new"})
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="old", refresh_token="refresh")
    snap = await ClaudeOAuthCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


def test_codex_wham_string_and_invalid_reset():
    """Wham parser should accept string unix resets and ignore bad values."""
    snap = parse_codex_wham_usage(
        {
            "rate_limit": {
                "primary_window": {"used_percent": 1, "reset_at": "bad"},
                "secondary_window": {"used_percent": 2, "reset_at": 1700000000},
            }
        }
    )
    assert snap.reset_at is None
    assert snap.reset_at_weekly is not None


def test_cursor_parser_iso_reset_string():
    """Cursor parser should parse ISO reset timestamps."""
    snap = parse_cursor_usage_summary({"billingCycleEnd": "2026-07-01T00:00:00+00:00"})
    assert snap.reset_at is not None


def test_default_cursor_state_db_path_windows(monkeypatch):
    """Windows default Cursor DB path should use APPDATA."""
    from modeldeck.collectors.credentials import cursor_auth

    monkeypatch.setattr(cursor_auth.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    path = cursor_auth.default_cursor_state_db_path()
    assert "Cursor" in str(path)
    assert path.name == "state.vscdb"


@pytest.mark.asyncio
async def test_claude_oauth_connect_error():
    """OAuth collector should map transport failures to parse_error."""

    async def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    snap = await ClaudeOAuthCollector(ProviderSecrets(access_token="t"), "Claude", client).collect()
    assert snap.status == CollectorStatus.PARSE_ERROR


def test_load_codex_from_config_home(monkeypatch, tmp_path):
    """Codex auth loader should read ~/.config/codex/auth.json when present."""
    from modeldeck.collectors.credentials import codex_auth

    config_dir = tmp_path / ".config" / "codex"
    config_dir.mkdir(parents=True)
    auth_file = config_dir / "auth.json"
    auth_file.write_text(
        json.dumps({"tokens": {"access_token": "cfg"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(codex_auth.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    tokens = codex_auth.load_codex_oauth()
    assert tokens.get("access_token") == "cfg"
