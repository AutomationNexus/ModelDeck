"""Tests for the Codex OAuth fixes and related improvements.

Covers:
- CODEX_SPEC: correct endpoints, scopes, client_id, redirect, encoding, extra params
- CLAUDE_SPEC: unchanged behavior + encoding is still json
- build_authorize_url: Codex extra params included
- _post_token: form-encoding for Codex, JSON for Claude
- decode_id_token_claims / extract_codex_account_id
- oauth_complete Codex path: account_id extracted, auth_mode=subscription
- oauth_complete Claude path: auth_mode=oauth (unchanged)
- /switch-oauth endpoint: sets auth_mode + returns OAuth start payload
- /switch-oauth 400 for Cursor
"""
from __future__ import annotations

import base64
import json
import urllib.parse

import pytest

from modeldeck.auth.provider_specs import CLAUDE_SPEC, CODEX_SPEC

# ---------------------------------------------------------------------------
# A. CODEX_SPEC correctness
# ---------------------------------------------------------------------------

class TestCodexSpec:
    def test_authorize_url(self):
        assert CODEX_SPEC.effective_authorize_url == "https://auth.openai.com/oauth/authorize"

    def test_token_url(self):
        assert CODEX_SPEC.effective_token_url == "https://auth.openai.com/oauth/token"

    def test_client_id(self):
        assert CODEX_SPEC.effective_client_id == "app_EMoamEEZ73f0CkXaXp7hrann"

    def test_redirect_uri(self):
        assert CODEX_SPEC.effective_redirect_uri == "http://localhost:1455/auth/callback"

    def test_token_encoding_is_form(self):
        assert CODEX_SPEC.effective_token_encoding == "form"

    def test_scopes_include_required(self):
        scopes = CODEX_SPEC.effective_scopes
        for required in ("openid", "profile", "email", "offline_access",
                         "api.connectors.read", "api.connectors.invoke"):
            assert required in scopes

    def test_extra_params_include_originator(self):
        params = dict(CODEX_SPEC.effective_extra_authorize_params)
        assert "originator" in params
        assert params["originator"] == "codex_cli_rs"

    def test_extra_params_include_simplified_flow(self):
        params = dict(CODEX_SPEC.effective_extra_authorize_params)
        assert params.get("codex_cli_simplified_flow") == "true"
        assert params.get("id_token_add_organizations") == "true"

    def test_originator_env_override(self, monkeypatch):
        monkeypatch.setenv("MODELDECK_CODEX_OAUTH_ORIGINATOR", "my_custom_tool")
        params = dict(CODEX_SPEC.effective_extra_authorize_params)
        assert params["originator"] == "my_custom_tool"

    def test_client_id_env_override(self, monkeypatch):
        monkeypatch.setenv("MODELDECK_CODEX_OAUTH_CLIENT_ID", "test_client")
        assert CODEX_SPEC.effective_client_id == "test_client"


class TestClaudeSpec:
    def test_authorize_url(self):
        assert CLAUDE_SPEC.effective_authorize_url == "https://claude.ai/oauth/authorize"

    def test_token_encoding_is_json(self):
        assert CLAUDE_SPEC.effective_token_encoding == "json"

    def test_client_id_unchanged(self):
        assert CLAUDE_SPEC.effective_client_id == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

    def test_no_extra_params(self):
        assert CLAUDE_SPEC.effective_extra_authorize_params == ()


# ---------------------------------------------------------------------------
# B. build_authorize_url — Codex extra params in the URL
# ---------------------------------------------------------------------------

class TestBuildAuthorizeUrl:
    def test_codex_url_has_correct_host(self):
        from modeldeck.auth.oauth_flow import build_authorize_url, generate_state, generate_verifier
        url = build_authorize_url(CODEX_SPEC, generate_verifier(), generate_state())
        assert url.startswith("https://auth.openai.com/oauth/authorize?")

    def test_codex_url_has_extra_params(self):
        from modeldeck.auth.oauth_flow import build_authorize_url, generate_state, generate_verifier
        url = build_authorize_url(CODEX_SPEC, generate_verifier(), generate_state())
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert parsed.get("originator") == ["codex_cli_rs"]
        assert parsed.get("codex_cli_simplified_flow") == ["true"]
        assert parsed.get("id_token_add_organizations") == ["true"]

    def test_codex_url_has_s256_challenge(self):
        from modeldeck.auth.oauth_flow import build_authorize_url, generate_state, generate_verifier
        url = build_authorize_url(CODEX_SPEC, generate_verifier(), generate_state())
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert parsed.get("code_challenge_method") == ["S256"]
        assert "code_challenge" in parsed

    def test_codex_url_redirect_uri(self):
        from modeldeck.auth.oauth_flow import build_authorize_url, generate_state, generate_verifier
        url = build_authorize_url(CODEX_SPEC, generate_verifier(), generate_state())
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert parsed.get("redirect_uri") == ["http://localhost:1455/auth/callback"]

    def test_claude_url_has_no_extra_params(self):
        from modeldeck.auth.oauth_flow import build_authorize_url, generate_state, generate_verifier
        url = build_authorize_url(CLAUDE_SPEC, generate_verifier(), generate_state())
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert "originator" not in parsed
        assert "codex_cli_simplified_flow" not in parsed


# ---------------------------------------------------------------------------
# C. _post_token encoding — form vs JSON
# ---------------------------------------------------------------------------

class TestPostTokenEncoding:
    @pytest.mark.asyncio
    async def test_codex_sends_form_encoding(self, monkeypatch):
        """Codex token exchange must use application/x-www-form-urlencoded."""
        captured = {}

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"access_token": "at", "refresh_token": "rt"}

        class FakeClient:
            async def post(self, url, *, data=None, json=None, timeout=None):
                captured["data"] = data
                captured["json"] = json
                captured["url"] = url
                return FakeResponse()

        from modeldeck.auth.oauth_flow import _post_token
        await _post_token(CODEX_SPEC, {"grant_type": "authorization_code"}, client=FakeClient())
        assert captured["data"] is not None, "Codex must use data= (form)"
        assert captured["json"] is None, "Codex must NOT use json="
        assert "auth.openai.com" in captured["url"]

    @pytest.mark.asyncio
    async def test_claude_sends_json_encoding(self, monkeypatch):
        """Claude token exchange must use JSON body."""
        captured = {}

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"access_token": "at"}

        class FakeClient:
            async def post(self, url, *, data=None, json=None, timeout=None):
                captured["data"] = data
                captured["json"] = json
                return FakeResponse()

        from modeldeck.auth.oauth_flow import _post_token
        await _post_token(CLAUDE_SPEC, {"grant_type": "authorization_code"}, client=FakeClient())
        assert captured["json"] is not None, "Claude must use json="
        assert captured["data"] is None, "Claude must NOT use data= (form)"


# ---------------------------------------------------------------------------
# D. decode_id_token_claims / extract_codex_account_id
# ---------------------------------------------------------------------------

def _make_id_token(auth_block: dict) -> str:
    """Build a synthetic JWT id_token with the given auth block."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=")
    payload_data = {"https://api.openai.com/auth": auth_block}
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


class TestIdTokenDecode:
    def test_extract_account_id_present(self):
        from modeldeck.auth.oauth_flow import extract_codex_account_id
        token = _make_id_token({"chatgpt_account_id": "user-abc123", "other": "data"})
        assert extract_codex_account_id(token) == "user-abc123"

    def test_extract_account_id_missing(self):
        from modeldeck.auth.oauth_flow import extract_codex_account_id
        token = _make_id_token({"other": "data"})
        assert extract_codex_account_id(token) is None

    def test_extract_account_id_invalid_token(self):
        from modeldeck.auth.oauth_flow import extract_codex_account_id
        assert extract_codex_account_id("not.a.valid") is None
        assert extract_codex_account_id("") is None

    def test_decode_id_token_claims_returns_dict(self):
        from modeldeck.auth.oauth_flow import decode_id_token_claims
        token = _make_id_token({"chatgpt_account_id": "user-xyz"})
        claims = decode_id_token_claims(token)
        assert isinstance(claims, dict)
        assert "https://api.openai.com/auth" in claims

    def test_decode_id_token_claims_bad_token(self):
        from modeldeck.auth.oauth_flow import decode_id_token_claims
        assert decode_id_token_claims("bad") == {}
        assert decode_id_token_claims("") == {}


# ---------------------------------------------------------------------------
# E. oauth_complete — Codex path sets auth_mode=subscription + account_id
# ---------------------------------------------------------------------------

def _make_webui_client(monkeypatch, tmp_path, provider="codex"):
    from starlette.testclient import TestClient

    from modeldeck.config.loader import AppConfig, SecretsConfig
    from modeldeck.webui.app import create_app

    accounts = [{"id": "default", "label": "Test", "enabled": False, "auth_mode": "api"}]
    providers_cfg: dict = {"codex": [], "claude": [], "cursor": []}
    providers_cfg[provider] = accounts

    cfg = AppConfig.model_validate({"providers": providers_cfg})
    sec = SecretsConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, sec))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "modeldeck.yaml").write_text(
        f"providers:\n  {provider}:\n    - id: default\n      label: Test\n"
        "      enabled: false\n      auth_mode: api\n",
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")
    return TestClient(create_app(), raise_server_exceptions=False)


class TestOAuthCompleteCodex:
    def test_codex_oauth_complete_sets_subscription_mode(self, monkeypatch, tmp_path):
        """Codex OAuth complete upserts account with auth_mode=subscription."""
        from modeldeck.webui import app as webui_app

        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["auth_mode"] = auth_mode
            upserted["enabled"] = enabled

        client = _make_webui_client(monkeypatch, tmp_path, provider="codex")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)

        start = client.post("/accounts/codex/default/oauth/start").json()
        session_key = start["session_key"]

        async def fake_exchange(spec, code, verifier, *, client=None):
            return {"access_token": "at", "refresh_token": "rt"}

        monkeypatch.setattr(webui_app, "exchange_code", fake_exchange)
        monkeypatch.setattr(webui_app, "extract_code_from_redirect", lambda x: "code123")
        monkeypatch.setattr(webui_app, "extract_codex_account_id", lambda x: None)

        resp = client.post(
            "/accounts/codex/default/oauth/complete",
            json={"session_key": session_key, "code_or_redirect": "code123"},
        )
        assert resp.status_code == 200
        assert upserted.get("auth_mode") == "subscription"
        assert upserted.get("enabled") is True

    def test_codex_oauth_extracts_account_id_from_id_token(self, monkeypatch, tmp_path):
        """Codex OAuth complete saves account_id extracted from id_token."""
        from modeldeck.webui import app as webui_app

        saved_fields: dict = {}

        def capture_write(provider, account_id, fields, **kw):
            saved_fields.update(fields)
            return True

        client = _make_webui_client(monkeypatch, tmp_path, provider="codex")
        monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", capture_write)

        start = client.post("/accounts/codex/default/oauth/start").json()
        session_key = start["session_key"]

        id_token = _make_id_token({"chatgpt_account_id": "user-test-999"})

        async def fake_exchange(spec, code, verifier, *, client=None):
            return {"access_token": "at", "refresh_token": "rt", "id_token": id_token}

        monkeypatch.setattr(webui_app, "exchange_code", fake_exchange)
        monkeypatch.setattr(webui_app, "extract_code_from_redirect", lambda x: "code123")

        resp = client.post(
            "/accounts/codex/default/oauth/complete",
            json={"session_key": session_key, "code_or_redirect": "code123"},
        )
        assert resp.status_code == 200
        assert saved_fields.get("account_id") == "user-test-999"

    def test_claude_oauth_complete_sets_oauth_mode(self, monkeypatch, tmp_path):
        """Claude OAuth complete upserts account with auth_mode=oauth."""
        from modeldeck.webui import app as webui_app

        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["auth_mode"] = auth_mode
            upserted["enabled"] = enabled

        client = _make_webui_client(monkeypatch, tmp_path, provider="claude")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)

        start = client.post("/accounts/claude/default/oauth/start").json()
        session_key = start["session_key"]

        async def fake_exchange(spec, code, verifier, *, client=None):
            return {"access_token": "at", "refresh_token": "rt"}

        monkeypatch.setattr(webui_app, "exchange_code", fake_exchange)
        monkeypatch.setattr(webui_app, "extract_code_from_redirect", lambda x: "code123")

        resp = client.post(
            "/accounts/claude/default/oauth/complete",
            json={"session_key": session_key, "code_or_redirect": "code123"},
        )
        assert resp.status_code == 200
        assert upserted.get("auth_mode") == "oauth"
        assert upserted.get("enabled") is True


# ---------------------------------------------------------------------------
# F. /switch-oauth endpoint
# ---------------------------------------------------------------------------

class TestSwitchOAuth:
    def test_switch_oauth_claude_returns_authorize_url(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path, provider="claude")
        resp = client.post("/accounts/claude/default/switch-oauth")
        assert resp.status_code == 200
        data = resp.json()
        assert "authorize_url" in data
        assert "claude.ai" in data["authorize_url"]
        assert "session_key" in data

    def test_switch_oauth_codex_returns_authorize_url(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path, provider="codex")
        resp = client.post("/accounts/codex/default/switch-oauth")
        assert resp.status_code == 200
        data = resp.json()
        assert "authorize_url" in data
        assert "auth.openai.com" in data["authorize_url"]

    def test_switch_oauth_cursor_returns_400(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path, provider="cursor")
        resp = client.post("/accounts/cursor/default/switch-oauth")
        assert resp.status_code == 400
        assert "Cursor" in resp.json()["detail"] or "OAuth" in resp.json()["detail"]

    def test_switch_oauth_updates_auth_mode_before_start(self, monkeypatch, tmp_path):
        """switch-oauth must call upsert with correct oauth_mode before returning URL."""
        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["auth_mode"] = auth_mode
            upserted["enabled"] = enabled

        client = _make_webui_client(monkeypatch, tmp_path, provider="claude")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)
        resp = client.post("/accounts/claude/default/switch-oauth")
        assert resp.status_code == 200
        assert upserted.get("auth_mode") == "oauth"
        # Account is disabled until OAuth completes successfully.
        assert upserted.get("enabled") is False

    def test_switch_oauth_codex_uses_subscription_mode(self, monkeypatch, tmp_path):
        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["auth_mode"] = auth_mode

        client = _make_webui_client(monkeypatch, tmp_path, provider="codex")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)
        resp = client.post("/accounts/codex/default/switch-oauth")
        assert resp.status_code == 200
        assert upserted.get("auth_mode") == "subscription"


# ---------------------------------------------------------------------------
# G. /providers — new fields present
# ---------------------------------------------------------------------------

class TestProvidersNewFields:
    def test_providers_have_default_mode(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        for prov in data["providers"]:
            assert "default_mode" in prov, f"{prov['name']} missing default_mode"

    def test_codex_default_mode_is_subscription(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        codex = next(p for p in data["providers"] if p["name"] == "OpenAI Codex")
        assert codex["default_mode"] == "subscription"

    def test_claude_default_mode_is_oauth(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        claude = next(p for p in data["providers"] if p["name"] == "Claude")
        assert claude["default_mode"] == "oauth"

    def test_cursor_has_no_oauth_note(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        cursor = next(p for p in data["providers"] if p["name"] == "Cursor")
        assert "no_oauth_note" in cursor
        assert cursor["no_oauth_note"]

    def test_codex_has_paste_back_note(self, monkeypatch, tmp_path):
        client = _make_webui_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        codex = next(p for p in data["providers"] if p["name"] == "OpenAI Codex")
        assert "oauth_paste_back_note" in codex
        assert "localhost:1455" in codex["oauth_paste_back_note"]
