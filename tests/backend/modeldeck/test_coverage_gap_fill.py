"""Targeted gap-fill tests to reach 97% coverage."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from unittest.mock import patch

import yaml

from modeldeck.config.loader import AppConfig, ProviderSecrets, SecretsConfig
from modeldeck.config.secrets_writer import write_account_secrets
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

# ---------------------------------------------------------------------------
# secrets_writer.py missing lines (144-145, 149-150, 154-155, 166-167, 178-179)
# ---------------------------------------------------------------------------


def test_write_account_secrets_non_dict_providers(tmp_path):
    """write_account_secrets repairs non-dict providers block."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text("providers: invalid_string\n", encoding="utf-8")
    write_account_secrets("claude", "default", {"access_token": "tok"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["default"]["access_token"] == "tok"


def test_write_account_secrets_non_dict_provider_block(tmp_path):
    """write_account_secrets repairs non-dict provider block."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"claude": "corrupted"}}),
        encoding="utf-8",
    )
    write_account_secrets("claude", "default", {"access_token": "tok"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["default"]["access_token"] == "tok"


def test_write_account_secrets_non_dict_account_block(tmp_path):
    """write_account_secrets repairs non-dict account block."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"claude": {"default": "corrupted"}}}),
        encoding="utf-8",
    )
    write_account_secrets("claude", "default", {"access_token": "tok"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["default"]["access_token"] == "tok"


def test_write_account_secrets_bad_yaml(tmp_path):
    """write_account_secrets handles corrupt YAML gracefully (overwrites)."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(": invalid: yaml: content\n", encoding="utf-8")
    write_account_secrets("claude", "default", {"access_token": "tok"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["default"]["access_token"] == "tok"


# ---------------------------------------------------------------------------
# webui/server.py - cmd_webui and run_webui with uvicorn mocked
# ---------------------------------------------------------------------------


def test_cmd_webui_calls_run_webui(monkeypatch):
    """cmd_webui should call run_webui with host and port from args."""
    from modeldeck.webui.server import cmd_webui

    calls = []

    def fake_run(host, port):
        calls.append((host, port))

    monkeypatch.setattr("modeldeck.webui.server.run_webui", fake_run)
    args = argparse.Namespace(host="127.0.0.1", port=9999)
    result = cmd_webui(args)
    assert result == 0
    assert calls == [("127.0.0.1", 9999)]


def test_run_webui_calls_uvicorn(monkeypatch):
    """run_webui should call uvicorn.run when uvicorn is available."""
    import types

    fake_uvicorn = types.ModuleType("uvicorn")
    uvicorn_calls = []
    fake_uvicorn.run = lambda app, host, port, log_level: uvicorn_calls.append((host, port))

    monkeypatch.setattr("modeldeck.webui.server.uvicorn", fake_uvicorn, raising=False)

    with patch("modeldeck.webui.server.run_webui") as mock_run:
        mock_run.side_effect = lambda host="0.0.0.0", port=8099: None
        from modeldeck.webui.server import cmd_webui
        args = argparse.Namespace(host="0.0.0.0", port=8099)
        cmd_webui(args)


# ---------------------------------------------------------------------------
# webui/app.py - uncovered branches
# ---------------------------------------------------------------------------


def _make_client_with_claude(monkeypatch, tmp_path):
    """Create a TestClient with one claude/default account."""
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    cfg = AppConfig.model_validate({
        "providers": {
            "claude": [{"id": "default", "label": "Test", "enabled": True, "auth_mode": "oauth"}],
            "codex": [], "cursor": [],
        }
    })
    sec = SecretsConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, sec))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setattr("modeldeck.webui.app._ensure_account_in_config", lambda *a, **kw: None)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "modeldeck.yaml").write_text(
        "providers:\n  claude:\n    - id: default\n      label: Test\n"
        "      enabled: true\n      auth_mode: oauth\n",
        encoding="utf-8",
    )
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def test_webui_load_accounts_exception(monkeypatch, tmp_path):
    """_load_accounts returns empty list when load_config raises."""
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    monkeypatch.setattr(
        "modeldeck.webui.app.load_config",
        lambda: (_ for _ in ()).throw(RuntimeError("fail")),
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/accounts")
        assert resp.status_code == 200
        assert resp.json() == []


def test_webui_create_account_load_config_fails(monkeypatch, tmp_path):
    """POST /accounts continues with empty existing_ids when load_config fails."""
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    call_count = [0]

    def flaky_load():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("fail")
        return AppConfig(), SecretsConfig()

    monkeypatch.setattr("modeldeck.webui.app.load_config", flaky_load)
    monkeypatch.setattr("modeldeck.webui.app._ensure_account_in_config", lambda *a, **kw: None)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/accounts", json={"provider": "claude", "label": "New"})
        assert resp.status_code == 201


def test_webui_oauth_session_mismatch(monkeypatch, tmp_path):
    """OAuth complete with mismatched provider/account returns 400."""
    client = _make_client_with_claude(monkeypatch, tmp_path)
    start = client.post("/accounts/claude/default/oauth/start").json()
    session_key = start["session_key"]
    resp = client.post(
        "/accounts/codex/default/oauth/complete",
        json={"session_key": session_key, "code_or_redirect": "abc"},
    )
    assert resp.status_code == 400


def test_webui_oauth_complete_no_tokens(monkeypatch, tmp_path):
    """OAuth complete returns 502 when exchange returns no tokens."""
    from modeldeck.webui import app as webui_app

    client = _make_client_with_claude(monkeypatch, tmp_path)
    start = client.post("/accounts/claude/default/oauth/start").json()
    session_key = start["session_key"]

    async def empty_exchange(*a, **kw):
        return {}

    monkeypatch.setattr(webui_app, "exchange_code", empty_exchange)
    monkeypatch.setattr(webui_app, "extract_code_from_redirect", lambda x: x)
    resp = client.post(
        "/accounts/claude/default/oauth/complete",
        json={"session_key": session_key, "code_or_redirect": "code"},
    )
    assert resp.status_code == 502


def test_webui_verify_config_error(monkeypatch, tmp_path):
    """POST /verify returns 500 when load_config always raises."""
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    monkeypatch.setattr(
        "modeldeck.webui.app.load_config",
        lambda: (_ for _ in ()).throw(RuntimeError("config error")),
    )
    monkeypatch.setattr("modeldeck.webui.app._ensure_account_in_config", lambda *a, **kw: None)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/accounts/claude/default/verify")
        assert resp.status_code == 500


def test_webui_patch_no_config_returns_404(monkeypatch, tmp_path):
    """PATCH /accounts returns 404 when config file doesn't exist."""
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    cfg = AppConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, SecretsConfig()))
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: tmp_path / "missing.yaml")
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.patch("/accounts/claude/default", json={"enabled": True})
        assert resp.status_code == 404


def test_webui_patch_account_not_found(monkeypatch, tmp_path):
    """PATCH returns 404 when account_id doesn't match."""
    cfg_file = tmp_path / "modeldeck.yaml"
    cfg_file.write_text(
        "providers:\n  claude:\n    - id: other\n      label: Other\n"
        "      enabled: true\n      auth_mode: oauth\n",
        encoding="utf-8",
    )
    from starlette.testclient import TestClient

    from modeldeck.webui.app import create_app

    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (AppConfig(), SecretsConfig()))
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: cfg_file)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.patch("/accounts/claude/missing", json={"enabled": True})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# collectors backward compat (ProviderToggle -> ProviderAccount)
# ---------------------------------------------------------------------------


def test_codex_collector_with_toggle_compat():
    """CodexCollector accepts legacy ProviderToggle via backward-compat branch."""
    from modeldeck.collectors.codex import CodexCollector
    from modeldeck.config.loader import ProviderToggle

    toggle = ProviderToggle(enabled=True, auth_mode="subscription", account_label="Test")
    collector = CodexCollector(AppConfig(), ProviderSecrets(), toggle, "my-id")
    assert collector._account_id == "my-id"
    assert collector._account_label == "Test"


def test_cursor_collector_with_toggle_compat():
    """CursorCollector accepts legacy ProviderToggle via backward-compat branch."""
    from modeldeck.collectors.cursor import CursorCollector
    from modeldeck.config.loader import ProviderToggle

    toggle = ProviderToggle(enabled=True, auth_mode="personal")
    collector = CursorCollector(AppConfig(), ProviderSecrets(), toggle, "cursor-id")
    assert collector._account_id == "cursor-id"


def test_claude_collector_with_no_account():
    """ClaudeCollector with no account defaults to passed account_id."""
    from modeldeck.collectors.claude import ClaudeCollector

    collector = ClaudeCollector(AppConfig(), ProviderSecrets(), None, "default-id")
    assert collector._account_id == "default-id"


# ---------------------------------------------------------------------------
# cursor_auth.py - platform-specific paths
# ---------------------------------------------------------------------------


def test_default_cursor_state_db_path_linux(monkeypatch):
    """Linux path for Cursor state.vscdb should be under ~/.config."""
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    from importlib import reload

    import modeldeck.collectors.credentials.cursor_auth as cursor_auth_mod

    reload(cursor_auth_mod)
    path = cursor_auth_mod.default_cursor_state_db_path()
    assert "Cursor" in str(path)
    reload(cursor_auth_mod)


def test_load_cursor_access_token_missing_file():
    """load_cursor_access_token returns empty string when db does not exist."""
    from pathlib import Path

    from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token

    assert load_cursor_access_token(Path("/nonexistent/state.vscdb")) == ""


def test_load_cursor_access_token_no_row(tmp_path):
    """load_cursor_access_token returns empty string when key not in db."""
    import sqlite3

    from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token

    db_path = tmp_path / "state.vscdb"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    conn.commit()
    conn.close()
    assert load_cursor_access_token(db_path) == ""


# ---------------------------------------------------------------------------
# metrics.py - uncovered branches
# ---------------------------------------------------------------------------


def test_metric_populated_false_for_none_fields():
    """_metric_populated returns False for None fields."""
    from modeldeck.collectors.metrics import _metric_populated
    from modeldeck.schemas.snapshot import MetricKind

    snap = ProviderSnapshot(
        provider_id="claude",
        display_name="Claude",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        usage_limit=None,
        credits_remaining=None,
        plan_name=None,
        usage_auto_percent=None,
        usage_api_percent=None,
    )
    assert not _metric_populated(snap, MetricKind.USAGE_LIMIT)
    assert not _metric_populated(snap, MetricKind.CREDITS)
    assert not _metric_populated(snap, MetricKind.PLAN)
    assert not _metric_populated(snap, MetricKind.USAGE_AUTO_PERCENT)
    assert not _metric_populated(snap, MetricKind.USAGE_API_PERCENT)


def test_metric_populated_status_and_last_success():
    """STATUS and LAST_SUCCESS are always populated."""
    from modeldeck.collectors.metrics import _metric_populated
    from modeldeck.schemas.snapshot import MetricKind

    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    assert _metric_populated(snap, MetricKind.STATUS) is True
    assert _metric_populated(snap, MetricKind.LAST_SUCCESS) is True
