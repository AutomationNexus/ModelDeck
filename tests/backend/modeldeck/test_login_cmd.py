"""Tests for modeldeck.cli.login_cmd."""

from __future__ import annotations

import argparse

import pytest
import yaml

from modeldeck.cli.login_cmd import (
    _ensure_account_in_config,
    cmd_accounts_add,
    cmd_accounts_disable,
    cmd_accounts_list,
    cmd_accounts_remove,
    cmd_login,
    register_login_commands,
)
from modeldeck.config.loader import AppConfig, SecretsConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs) -> argparse.Namespace:
    """Build a namespace with given kwargs as attributes."""
    return argparse.Namespace(**kwargs)


def _make_config_with_account(tmp_path, provider: str, account_id: str) -> None:
    """Write a minimal modeldeck.yaml with one account."""
    cfg_file = tmp_path / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                provider: [
                    {"id": account_id, "label": "Test", "enabled": True, "auth_mode": "auto"}
                ]
            }
        }),
        encoding="utf-8",
    )
    return cfg_file


def _empty_config() -> AppConfig:
    return AppConfig()


def _empty_secrets() -> SecretsConfig:
    return SecretsConfig()


# ---------------------------------------------------------------------------
# cmd_login
# ---------------------------------------------------------------------------


def test_cmd_login_cursor_prints_message_and_returns_1(capsys):
    """cmd_login with cursor should print paste-token guidance and return 1."""
    args = _make_args(provider="cursor", label="My Cursor")
    # Mock load_config so we don't need real config files
    result = cmd_login(args)
    out = capsys.readouterr().out
    assert result == 1
    assert "Cursor" in out or "cursor" in out.lower()


def test_cmd_login_cursor_returns_int_1():
    """Return value must be exactly 1 for cursor provider."""
    args = _make_args(provider="cursor", label="")
    result = cmd_login(args)
    assert result == 1


def test_cmd_login_cursor_no_secrets_printed(capsys):
    """No credential values should be printed when cursor login fails."""
    args = _make_args(provider="cursor", label="")
    cmd_login(args)
    out, err = capsys.readouterr()
    assert "access_token" not in out
    assert "refresh_token" not in out


# ---------------------------------------------------------------------------
# cmd_accounts_list
# ---------------------------------------------------------------------------


def test_cmd_accounts_list_empty_config_returns_0(monkeypatch):
    """cmd_accounts_list with empty providers should return 0."""
    cfg = _empty_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))

    args = _make_args()
    result = cmd_accounts_list(args)
    assert result == 0


def test_cmd_accounts_list_empty_config_no_output(monkeypatch, capsys):
    """cmd_accounts_list with no accounts should produce no meaningful output."""
    cfg = _empty_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))

    args = _make_args()
    cmd_accounts_list(args)
    out = capsys.readouterr().out
    # With empty providers list the output should be empty.
    assert out.strip() == ""


def test_cmd_accounts_list_with_accounts(monkeypatch, capsys):
    """cmd_accounts_list should print account info when accounts exist."""
    cfg = AppConfig.model_validate({
        "providers": {
            "claude": [{"id": "personal", "label": "Personal", "enabled": True, "auth_mode": "oauth"}]
        }
    })
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))

    args = _make_args()
    result = cmd_accounts_list(args)
    out = capsys.readouterr().out
    assert result == 0
    assert "claude" in out
    assert "personal" in out


def test_cmd_accounts_list_load_config_error(monkeypatch):
    """cmd_accounts_list should return 1 when load_config raises."""
    def _raise():
        raise RuntimeError("config broken")

    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", _raise)

    args = _make_args()
    result = cmd_accounts_list(args)
    assert result == 1


# ---------------------------------------------------------------------------
# cmd_accounts_add
# ---------------------------------------------------------------------------


def test_cmd_accounts_add_cursor_with_jwt_calls_write_account_secrets(monkeypatch):
    """Adding cursor with eyJ token should call write_account_secrets."""
    cfg = _empty_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))

    written_calls = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.write_account_secrets",
        lambda provider, account_id, fields, **kw: written_calls.append((provider, account_id, fields)),
    )
    ensure_calls = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config",
        lambda *a, **kw: ensure_calls.append(a),
    )

    args = _make_args(provider="cursor", label="Test", token="eyJtest", auth_mode="auto")
    result = cmd_accounts_add(args)
    assert result == 0
    assert len(written_calls) == 1
    assert written_calls[0][0] == "cursor"
    assert len(ensure_calls) == 1


def test_cmd_accounts_add_cursor_with_session_token(monkeypatch):
    """Adding cursor with non-eyJ token should write session_token field."""
    cfg = _empty_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))

    written_calls = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.write_account_secrets",
        lambda provider, account_id, fields, **kw: written_calls.append((provider, account_id, fields)),
    )
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config",
        lambda *a, **kw: None,
    )

    args = _make_args(provider="cursor", label="Test", token="not-a-jwt", auth_mode="personal")
    result = cmd_accounts_add(args)
    assert result == 0
    # session_token field should be used for non-JWT tokens
    assert written_calls[0][2].get("session_token") == "not-a-jwt"


def test_cmd_accounts_add_no_token_calls_ensure(monkeypatch):
    """Adding without a token should still call _ensure_account_in_config."""
    cfg = _empty_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr("modeldeck.cli.login_cmd.write_account_secrets", lambda *a, **kw: None)
    ensure_calls = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config",
        lambda *a, **kw: ensure_calls.append(a),
    )

    args = _make_args(provider="claude", label="Work", token="", auth_mode="oauth")
    result = cmd_accounts_add(args)
    assert result == 0
    assert len(ensure_calls) == 1


def test_cmd_accounts_add_api_key_provider(monkeypatch):
    """Adding codex with sk-admin token should write api_key field."""
    cfg = _empty_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.cli.login_cmd.load_config", lambda: (cfg, secrets))

    written_calls = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.write_account_secrets",
        lambda provider, account_id, fields, **kw: written_calls.append(fields),
    )
    monkeypatch.setattr("modeldeck.cli.login_cmd._ensure_account_in_config", lambda *a, **kw: None)

    args = _make_args(provider="codex", label="API", token="sk-admin-test", auth_mode="api")
    result = cmd_accounts_add(args)
    assert result == 0
    assert written_calls[0].get("api_key") == "sk-admin-test"


# ---------------------------------------------------------------------------
# cmd_accounts_remove
# ---------------------------------------------------------------------------


def test_cmd_accounts_remove_removes_from_config(tmp_path, monkeypatch):
    """cmd_accounts_remove should remove the account from modeldeck.yaml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _make_config_with_account(config_dir, "claude", "test-account")

    sec_file = config_dir / "secrets.yaml"
    sec_file.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="test-account")
    result = cmd_accounts_remove(args)
    assert result == 0

    raw = yaml.safe_load((config_dir / "modeldeck.yaml").read_text(encoding="utf-8"))
    accounts = raw.get("providers", {}).get("claude", [])
    assert not any(a.get("id") == "test-account" for a in accounts if isinstance(a, dict))


def test_cmd_accounts_remove_missing_account_still_returns_0(tmp_path, monkeypatch):
    """Removing a nonexistent account should not fail."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _make_config_with_account(config_dir, "claude", "other-account")

    sec_file = config_dir / "secrets.yaml"
    sec_file.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="nonexistent")
    result = cmd_accounts_remove(args)
    assert result == 0


def test_cmd_accounts_remove_removes_from_secrets(tmp_path, monkeypatch):
    """cmd_accounts_remove should also remove from secrets.yaml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _make_config_with_account(config_dir, "claude", "test-account")

    sec_file = config_dir / "secrets.yaml"
    sec_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": {
                    "test-account": {"access_token": "tok"}
                }
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="test-account")
    cmd_accounts_remove(args)

    raw = yaml.safe_load(sec_file.read_text(encoding="utf-8"))
    prov_secrets = raw.get("providers", {}).get("claude", {})
    assert "test-account" not in prov_secrets


# ---------------------------------------------------------------------------
# cmd_accounts_disable
# ---------------------------------------------------------------------------


def test_cmd_accounts_disable_missing_account_returns_1(tmp_path, monkeypatch):
    """Disabling a nonexistent account should return 1."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _make_config_with_account(config_dir, "claude", "other")

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="nonexistent", enable=False)
    result = cmd_accounts_disable(args)
    assert result == 1


def test_cmd_accounts_disable_disables_account(tmp_path, monkeypatch):
    """Disabling an existing account should set enabled=False and return 0."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _make_config_with_account(config_dir, "claude", "myaccount")

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="myaccount", enable=False)
    result = cmd_accounts_disable(args)
    assert result == 0

    raw = yaml.safe_load((config_dir / "modeldeck.yaml").read_text(encoding="utf-8"))
    accounts = raw.get("providers", {}).get("claude", [])
    acct = next((a for a in accounts if a.get("id") == "myaccount"), None)
    assert acct is not None
    assert acct["enabled"] is False


def test_cmd_accounts_disable_no_config_returns_1(tmp_path, monkeypatch):
    """Disabling when config file is missing should return 1."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Do NOT create modeldeck.yaml

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="anything", enable=False)
    result = cmd_accounts_disable(args)
    assert result == 1


def test_cmd_accounts_enable_sets_enabled_true(tmp_path, monkeypatch):
    """Enabling a disabled account should set enabled=True."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "myaccount", "label": "Test", "enabled": False, "auth_mode": "auto"}
                ]
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    args = _make_args(provider="claude", account="myaccount", enable=True)
    result = cmd_accounts_disable(args)  # cmd_accounts_disable handles both enable/disable
    assert result == 0

    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    accounts = raw.get("providers", {}).get("claude", [])
    acct = next((a for a in accounts if a.get("id") == "myaccount"), None)
    assert acct["enabled"] is True


# ---------------------------------------------------------------------------
# _ensure_account_in_config
# ---------------------------------------------------------------------------


def test_ensure_account_in_config_creates_entry(tmp_path, monkeypatch):
    """_ensure_account_in_config should add account to YAML."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text("providers: {}\n", encoding="utf-8")

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    _ensure_account_in_config("claude", "new-account", "New Account", auth_mode="oauth")

    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    accounts = raw.get("providers", {}).get("claude", [])
    assert any(a.get("id") == "new-account" for a in accounts)


def test_ensure_account_in_config_no_duplicate(tmp_path, monkeypatch):
    """_ensure_account_in_config should not add duplicate if account already exists."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cfg_file = config_dir / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [{"id": "existing", "label": "Existing", "enabled": True, "auth_mode": "oauth"}]
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    _ensure_account_in_config("claude", "existing", "Updated Label", auth_mode="oauth")

    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    accounts = raw.get("providers", {}).get("claude", [])
    # Should still only be one entry with id="existing"
    assert len([a for a in accounts if a.get("id") == "existing"]) == 1


def test_ensure_account_in_config_no_config_file(tmp_path, monkeypatch):
    """_ensure_account_in_config should be a no-op when config file doesn't exist."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Do NOT create modeldeck.yaml

    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    # Should not raise
    _ensure_account_in_config("claude", "test", "Test", auth_mode="oauth")


# ---------------------------------------------------------------------------
# register_login_commands
# ---------------------------------------------------------------------------


def test_register_login_commands_includes_login():
    """register_login_commands should add 'login' subparser."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_login_commands(sub)
    assert "login" in sub.choices


def test_register_login_commands_includes_accounts():
    """register_login_commands should add 'accounts' subparser."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_login_commands(sub)
    assert "accounts" in sub.choices


def test_register_login_commands_login_requires_provider():
    """login subparser should require --provider argument."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_login_commands(sub)
    with pytest.raises(SystemExit):
        parser.parse_args(["login"])  # missing --provider


def test_register_login_commands_login_parses_provider():
    """login subparser should accept --provider claude."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_login_commands(sub)
    args = parser.parse_args(["login", "--provider", "claude"])
    assert args.provider == "claude"


def test_register_login_commands_accounts_list_parseable():
    """accounts list should be parseable."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    register_login_commands(sub)
    args = parser.parse_args(["accounts", "list"])
    assert callable(args.func)
