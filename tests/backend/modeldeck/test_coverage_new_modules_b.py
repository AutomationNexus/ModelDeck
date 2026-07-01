"""Tests for webui/server.py and cli/login_cmd.py (split from test_coverage_new_modules)."""

from __future__ import annotations

import argparse
import builtins

import pytest

from modeldeck.config.loader import AppConfig, SecretsConfig

# ---------------------------------------------------------------------------
# webui/server.py - uncovered lines
# ---------------------------------------------------------------------------


def test_register_webui_command_adds_subparser():
    """register_webui_command should add 'webui' to subparsers."""
    from modeldeck.webui.server import register_webui_command

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_webui_command(sub)
    args = parser.parse_args(["webui", "--port", "9090"])
    assert args.port == 9090


def test_run_webui_raises_without_uvicorn(monkeypatch):
    """run_webui raises ImportError when uvicorn is not installed."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("no uvicorn")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from modeldeck.webui.server import run_webui

    with pytest.raises(ImportError, match="uvicorn"):
        run_webui()


# ---------------------------------------------------------------------------
# cli/login_cmd.py - uncovered async branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_oauth_login_no_input(monkeypatch):
    """_run_oauth_login returns 1 when user inputs empty string."""
    from modeldeck.cli.login_cmd import _run_oauth_login

    monkeypatch.setattr("builtins.input", lambda _: "")
    result = await _run_oauth_login("claude", "Test", "test")
    assert result == 1


@pytest.mark.asyncio
async def test_run_oauth_login_bad_code(monkeypatch):
    """_run_oauth_login returns 1 when code extraction fails."""
    from modeldeck.auth.oauth_flow import OAuthFlowError
    from modeldeck.cli.login_cmd import _run_oauth_login

    monkeypatch.setattr("builtins.input", lambda _: "https://no-code-here.local/")

    def bad_parse(x):
        raise OAuthFlowError("no code")

    monkeypatch.setattr("modeldeck.cli.login_cmd.parse_code_and_state", bad_parse)
    result = await _run_oauth_login("claude", "Test", "test")
    assert result == 1


@pytest.mark.asyncio
async def test_run_oauth_login_exchange_fails(monkeypatch):
    """_run_oauth_login returns 1 when exchange fails."""
    from modeldeck.auth.oauth_flow import OAuthFlowError
    from modeldeck.cli.login_cmd import _run_oauth_login

    monkeypatch.setattr("builtins.input", lambda _: "abc123")
    monkeypatch.setattr("modeldeck.cli.login_cmd.parse_code_and_state", lambda x: (x, None))

    async def bad_exchange(*a, **kw):
        raise OAuthFlowError("bad exchange")

    monkeypatch.setattr("modeldeck.cli.login_cmd.exchange_code", bad_exchange)
    result = await _run_oauth_login("claude", "Test", "test")
    assert result == 1


@pytest.mark.asyncio
async def test_run_oauth_login_no_tokens_in_response(monkeypatch):
    """_run_oauth_login returns 1 when exchange returns no tokens."""
    from modeldeck.cli.login_cmd import _run_oauth_login

    monkeypatch.setattr("builtins.input", lambda _: "abc123")
    monkeypatch.setattr("modeldeck.cli.login_cmd.parse_code_and_state", lambda x: (x, None))

    async def empty_exchange(*a, **kw):
        return {}  # no access_token

    monkeypatch.setattr("modeldeck.cli.login_cmd.exchange_code", empty_exchange)
    result = await _run_oauth_login("claude", "Test", "test")
    assert result == 1


@pytest.mark.asyncio
async def test_run_oauth_login_success(monkeypatch, tmp_path):
    """_run_oauth_login returns 0 on success."""
    from modeldeck.cli.login_cmd import _run_oauth_login

    monkeypatch.setattr("builtins.input", lambda _: "abc123")
    monkeypatch.setattr("modeldeck.cli.login_cmd.parse_code_and_state", lambda x: (x, None))

    async def good_exchange(*a, **kw):
        return {"access_token": "at", "refresh_token": "rt"}

    monkeypatch.setattr("modeldeck.cli.login_cmd.exchange_code", good_exchange)
    monkeypatch.setattr("modeldeck.cli.login_cmd.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config", lambda *a, **kw: None
    )
    result = await _run_oauth_login("claude", "Test Claude", "test")
    assert result == 0


def test_cmd_login_cursor_returns_1():
    """cmd_login for cursor always returns 1 (no OAuth)."""
    from modeldeck.cli.login_cmd import cmd_login

    args = argparse.Namespace(provider="cursor", label="My Cursor")
    result = cmd_login(args)
    assert result == 1


def test_cmd_accounts_list_empty(monkeypatch):
    """cmd_accounts_list returns 0 with no accounts."""
    from modeldeck.cli.login_cmd import cmd_accounts_list

    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.load_config",
        lambda: (AppConfig(), SecretsConfig()),
    )
    args = argparse.Namespace()
    assert cmd_accounts_list(args) == 0


def test_cmd_accounts_remove_no_config(tmp_path, monkeypatch):
    """cmd_accounts_remove is safe when config files are absent."""
    from modeldeck.cli.login_cmd import cmd_accounts_remove

    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: tmp_path / "modeldeck.yaml")
    monkeypatch.setattr("modeldeck.core.paths.secrets_path", lambda: tmp_path / "secrets.yaml")
    args = argparse.Namespace(provider="claude", account="default")
    assert cmd_accounts_remove(args) == 0


def test_cmd_accounts_disable_not_found(tmp_path, monkeypatch):
    """cmd_accounts_disable returns 1 when account not found."""
    from modeldeck.cli.login_cmd import cmd_accounts_disable

    cfg_file = tmp_path / "modeldeck.yaml"
    cfg_file.write_text(
        "providers:\n  claude:\n    - id: other\n      enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: cfg_file)
    args = argparse.Namespace(provider="claude", account="missing", enable=False)
    assert cmd_accounts_disable(args) == 1


def test_register_login_commands_registers_subparsers():
    """register_login_commands registers login and accounts subcommands."""
    from modeldeck.cli.login_cmd import register_login_commands

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_login_commands(sub)
    args = parser.parse_args(["accounts", "list"])
    assert args.accounts_cmd == "list"
