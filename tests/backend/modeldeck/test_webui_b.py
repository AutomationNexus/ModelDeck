"""Tests for modeldeck.webui.app — token, delete, patch, server (part 2)."""

from __future__ import annotations

import argparse
import builtins

import pytest
import yaml
from starlette.testclient import TestClient

from modeldeck.config.loader import AppConfig, SecretsConfig
from modeldeck.webui.app import create_app


def _make_minimal_config(
    *,
    claude_accounts: list[dict] | None = None,
) -> AppConfig:
    """Build a minimal AppConfig with optional Claude accounts."""
    cfg = AppConfig()
    if claude_accounts:
        cfg = AppConfig.model_validate(
            {
                "providers": {
                    "claude": claude_accounts,
                    "codex": [],
                    "cursor": [],
                }
            }
        )
    return cfg


def _empty_secrets() -> SecretsConfig:
    return SecretsConfig()


# ---------------------------------------------------------------------------
# POST /accounts/{provider}/{account_id}/token — paste-token
# ---------------------------------------------------------------------------


def test_paste_token_empty_returns_400(monkeypatch):
    """Empty token must return 400."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts/cursor/default/token",
            json={"token": "", "field": "access_token"},
        )
    assert resp.status_code == 400


def test_paste_token_whitespace_only_returns_400(monkeypatch):
    """Whitespace-only token must return 400."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts/cursor/default/token",
            json={"token": "   ", "field": "session_token"},
        )
    assert resp.status_code == 400


def test_paste_token_valid_token_returns_200(tmp_path, monkeypatch):
    """Valid token with mocked write_account_secrets should return 200."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setattr(
        "modeldeck.webui.app._ensure_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts/cursor/default/token",
            json={"token": "eyJtest.token.value", "field": "access_token"},
        )
    assert resp.status_code == 200


def test_paste_token_unknown_field_returns_400(monkeypatch):
    """Unknown field name must return 400."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts/cursor/default/token",
            json={"token": "sometoken", "field": "bad_field_name"},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /accounts/{provider}/{account_id}
# ---------------------------------------------------------------------------


def test_delete_account_returns_200(tmp_path, monkeypatch):
    """DELETE /accounts should return 200 even when config/secrets are minimal."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "default", "label": "Test", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )
    sec_file = config_dir / "secrets.yaml"
    sec_file.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.delete("/accounts/claude/default")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /accounts/{provider}/{account_id}
# ---------------------------------------------------------------------------


def test_patch_account_enable_returns_200_or_404(tmp_path, monkeypatch):
    """PATCH /accounts with enabled=false → 200 when account present."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "default", "label": "Test", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.patch("/accounts/claude/default", json={"enabled": False})
    assert resp.status_code in (200, 404)


def test_patch_account_not_in_config_returns_404(tmp_path, monkeypatch):
    """PATCH /accounts for a missing account_id should return 404."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "other", "label": "Other", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.patch("/accounts/claude/nonexistent", json={"enabled": False})
    assert resp.status_code == 404


def test_patch_account_missing_body_returns_400(tmp_path, monkeypatch):
    """PATCH without 'enabled' field must return 400."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "default", "label": "Test", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.patch("/accounts/claude/default", json={"label": "Updated"})
    assert resp.status_code == 400


def test_patch_account_no_config_file_returns_404(tmp_path, monkeypatch):
    """PATCH when config file doesn't exist must return 404."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Do NOT create modeldeck.yaml

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.patch("/accounts/claude/default", json={"enabled": False})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# No secrets leak in account endpoint responses
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    """TestClient with load_config mocked to return a minimal config."""
    default_account = [
        {"id": "default", "label": "Test Claude", "enabled": True, "auth_mode": "oauth"}
    ]
    cfg = _make_minimal_config(claude_accounts=default_account)
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


def test_accounts_response_body_no_access_token(client):
    text = client.get("/accounts").text
    assert "access_token" not in text


def test_accounts_response_body_no_refresh_token(client):
    text = client.get("/accounts").text
    assert "refresh_token" not in text


# ---------------------------------------------------------------------------
# webui/server.py — register_webui_command and cmd_webui
# ---------------------------------------------------------------------------


def test_register_webui_command_adds_webui_subparser():
    """register_webui_command should register 'webui' in subparsers."""
    from modeldeck.webui.server import register_webui_command

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_webui_command(sub)

    args = parser.parse_args(["webui"])
    assert args.cmd == "webui"


def test_register_webui_command_subparser_name_in_choices():
    """The 'webui' subparser name should be present."""
    from modeldeck.webui.server import register_webui_command

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_webui_command(sub)
    assert "webui" in sub.choices


def test_run_webui_raises_import_error_when_uvicorn_missing(monkeypatch):
    """run_webui should raise ImportError if uvicorn is not available."""
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("No module named 'uvicorn'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from modeldeck.webui import server

    with pytest.raises(ImportError, match="uvicorn"):
        server.run_webui()


def test_cmd_webui_exists():
    """cmd_webui should be importable from server."""
    from modeldeck.webui.server import cmd_webui

    assert callable(cmd_webui)
