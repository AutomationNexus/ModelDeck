"""Gap-covering tests for secrets_writer and webui/app endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from modeldeck.config.loader import AppConfig, ProviderSecrets, SecretsConfig
from modeldeck.config.secrets_writer import persist_provider_oauth_tokens, write_account_secrets

# ---------------------------------------------------------------------------
# secrets_writer.py - uncovered branches
# ---------------------------------------------------------------------------


def test_persist_skips_when_file_not_writable(tmp_path, monkeypatch):
    """persist should return False when file is not writable."""
    secrets_file = tmp_path / "secrets.yaml"
    # File does not exist at all — os.access returns False.
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    # secrets_file does not exist; persist returns False.
    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="x"),
        secrets_file=secrets_file,
    )


def test_persist_skips_when_raw_not_dict(tmp_path, monkeypatch):
    """persist returns False when secrets file is not a YAML dict."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text("- item1\n- item2\n", encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="x"),
        secrets_file=secrets_file,
    )


def test_persist_no_update_when_same_tokens(tmp_path, monkeypatch):
    """persist returns False when tokens haven't changed."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"codex": {"default": {"access_token": "same"}}}}),
        encoding="utf-8",
    )
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    # Same value — no update needed.
    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="same"),
        "default",
        secrets_file=secrets_file,
    )


def test_write_account_secrets_creates_file(tmp_path):
    """write_account_secrets creates secrets.yaml if it doesn't exist."""
    secrets_file = tmp_path / "secrets.yaml"
    assert not secrets_file.exists()
    write_account_secrets("claude", "personal", {"access_token": "tok"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["personal"]["access_token"] == "tok"


def test_write_account_secrets_migrates_flat(tmp_path):
    """write_account_secrets migrates existing flat provider secrets."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"cursor": {"session_token": "old"}}}),
        encoding="utf-8",
    )
    write_account_secrets("cursor", "default", {"access_token": "new"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["cursor"]["default"]["access_token"] == "new"
    # old flat field should be under default after migration
    assert "session_token" in raw["providers"]["cursor"]["default"]


def test_write_account_secrets_skips_empty_values(tmp_path):
    """write_account_secrets does not write empty string values."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text("providers: {}\n", encoding="utf-8")
    write_account_secrets("claude", "default", {"access_token": "", "refresh_token": "rt"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert "access_token" not in raw["providers"]["claude"]["default"]
    assert raw["providers"]["claude"]["default"]["refresh_token"] == "rt"


# ---------------------------------------------------------------------------
# webui/app.py - uncovered endpoints via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def _minimal_config_with_claude():
    """Return (AppConfig, SecretsConfig) with one claude default account."""
    cfg = AppConfig.model_validate({
        "providers": {
            "claude": [{"id": "default", "label": "Test", "enabled": True, "auth_mode": "oauth"}],
            "codex": [],
            "cursor": [],
        }
    })
    return cfg, SecretsConfig()


@pytest.fixture()
def webui_client(monkeypatch, _minimal_config_with_claude, tmp_path):
    """TestClient with full monkeypatching for webui tests."""
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    cfg, sec = _minimal_config_with_claude

    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, sec))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "modeldeck.yaml").write_text(
        "providers:\n  claude:\n    - id: default\n      label: Test\n"
        "      enabled: true\n      auth_mode: oauth\n",
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def test_webui_get_root(webui_client):
    """GET / should return 200 HTML."""
    resp = webui_client.get("/")
    assert resp.status_code == 200
    assert "ModelDeck" in resp.text


def test_webui_get_providers(webui_client):
    """GET /providers returns provider list with name and auth_modes."""
    resp = webui_client.get("/providers")
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data["providers"]]
    assert "Claude" in names
    assert "Cursor" in names


def test_webui_list_accounts(webui_client):
    """GET /accounts returns account list."""
    resp = webui_client.get("/accounts")
    assert resp.status_code == 200
    accounts = resp.json()
    assert any(a["provider"] == "claude" and a["id"] == "default" for a in accounts)


def test_webui_create_account_unknown_provider(webui_client):
    """POST /accounts with bad provider returns 400."""
    resp = webui_client.post("/accounts", json={"provider": "unknown", "label": "X"})
    assert resp.status_code == 400


def test_webui_oauth_start_cursor_returns_400(webui_client):
    """OAuth start for Cursor should return 400."""
    resp = webui_client.post("/accounts/cursor/default/oauth/start")
    assert resp.status_code == 400


def test_webui_oauth_start_claude_returns_url(webui_client):
    """OAuth start for Claude returns authorize URL and session key."""
    resp = webui_client.post("/accounts/claude/default/oauth/start")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorize_url" in data
    assert "session_key" in data
    assert "claude.ai" in data["authorize_url"]


def test_webui_oauth_complete_missing_session(webui_client):
    """OAuth complete with missing session key returns 400."""
    resp = webui_client.post(
        "/accounts/claude/default/oauth/complete",
        json={"session_key": "bad-key", "code_or_redirect": "abc"},
    )
    assert resp.status_code == 400


def test_webui_oauth_complete_success(webui_client, monkeypatch):
    """OAuth complete exchanges code and saves tokens."""
    from modeldeck.webui import app as webui_app

    # Start a real session first.
    start = webui_client.post("/accounts/claude/default/oauth/start").json()
    session_key = start["session_key"]

    # Mock exchange_code to return tokens.
    async def fake_exchange(spec, code, verifier, *, client=None):
        return {"access_token": "at", "refresh_token": "rt"}

    monkeypatch.setattr(webui_app, "exchange_code", fake_exchange)
    monkeypatch.setattr(webui_app, "extract_code_from_redirect", lambda x: "code123")

    resp = webui_client.post(
        "/accounts/claude/default/oauth/complete",
        json={"session_key": session_key, "code_or_redirect": "code123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_webui_oauth_complete_exchange_error(webui_client, monkeypatch):
    """OAuth complete returns 400 when exchange fails."""
    from modeldeck.auth.oauth_flow import OAuthFlowError
    from modeldeck.webui import app as webui_app

    start = webui_client.post("/accounts/claude/default/oauth/start").json()
    session_key = start["session_key"]

    async def fake_exchange(spec, code, verifier, *, client=None):
        raise OAuthFlowError("bad code")

    monkeypatch.setattr(webui_app, "exchange_code", fake_exchange)
    monkeypatch.setattr(webui_app, "extract_code_from_redirect", lambda x: "code123")

    resp = webui_client.post(
        "/accounts/claude/default/oauth/complete",
        json={"session_key": session_key, "code_or_redirect": "code123"},
    )
    assert resp.status_code == 400


def test_webui_paste_token_empty(webui_client):
    """POST /token with empty value returns 400."""
    resp = webui_client.post(
        "/accounts/cursor/default/token",
        json={"field": "access_token", "value": ""},
    )
    assert resp.status_code == 400


def test_webui_paste_token_bad_field(webui_client):
    """POST /token with invalid field returns 400."""
    resp = webui_client.post(
        "/accounts/cursor/default/token",
        json={"field": "bad_field", "value": "abc"},
    )
    assert resp.status_code == 400


def test_webui_paste_token_success(webui_client):
    """POST /token with valid field+value returns 200."""
    resp = webui_client.post(
        "/accounts/cursor/default/token",
        json={"field": "access_token", "value": "eyJtest"},
    )
    assert resp.status_code == 200


def test_webui_verify_unknown_provider(webui_client):
    """POST /verify with bad provider returns 400."""
    resp = webui_client.post("/accounts/unknown/default/verify")
    assert resp.status_code == 400


def test_webui_verify_account_not_found(webui_client):
    """POST /verify for missing account returns 404."""
    resp = webui_client.post("/accounts/claude/nonexistent/verify")
    assert resp.status_code == 404


def test_webui_verify_success(webui_client, monkeypatch):
    """POST /verify returns status ok when collector succeeds."""
    from datetime import UTC, datetime

    from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

    snap = ProviderSnapshot(
        provider_id="claude",
        display_name="Claude",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        account_id="default",
    )

    mock_collector = MagicMock()
    mock_collector.collect = AsyncMock(return_value=snap)

    monkeypatch.setattr(
        "modeldeck.collectors.claude.ClaudeCollector",
        lambda *a, **kw: mock_collector,
    )
    monkeypatch.setattr(
        "modeldeck.webui.app.ClaudeCollector",
        lambda *a, **kw: mock_collector,
        raising=False,
    )

    resp = webui_client.post("/accounts/claude/default/verify")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webui_delete_account(webui_client, tmp_path, monkeypatch):
    """DELETE /accounts removes account from config."""
    (tmp_path / "modeldeck.yaml").write_text(
        "providers:\n  claude:\n    - id: default\n      label: Test\n"
        "      enabled: true\n      auth_mode: oauth\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: tmp_path / "modeldeck.yaml")
    monkeypatch.setattr("modeldeck.core.paths.secrets_path", lambda: tmp_path / "secrets.yaml")
    resp = webui_client.delete("/accounts/claude/default")
    assert resp.status_code == 200


def test_webui_patch_account_enable(webui_client, tmp_path, monkeypatch):
    """PATCH /accounts enables account."""
    (tmp_path / "modeldeck.yaml").write_text(
        "providers:\n  claude:\n    - id: default\n      label: Test\n"
        "      enabled: false\n      auth_mode: oauth\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: tmp_path / "modeldeck.yaml")
    resp = webui_client.patch("/accounts/claude/default", json={"enabled": True})
    assert resp.status_code == 200
    raw = yaml.safe_load((tmp_path / "modeldeck.yaml").read_text(encoding="utf-8"))
    assert raw["providers"]["claude"][0]["enabled"] is True


def test_webui_patch_missing_enabled_key(webui_client):
    """PATCH without 'enabled' key returns 400."""
    resp = webui_client.patch("/accounts/claude/default", json={"other": "x"})
    assert resp.status_code == 400


def test_webui_response_no_secrets_leaked(webui_client):
    """Account list response must not contain secret values."""
    resp = webui_client.get("/accounts")
    body = resp.text
    for _secret_key in ("access_token", "refresh_token", "session_token", "api_key"):
        assert "sk-ant-" not in body
        assert "eyJ" not in body
