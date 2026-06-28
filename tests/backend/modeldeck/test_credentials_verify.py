"""Tests for `modeldeck credentials verify`."""

from __future__ import annotations

import argparse

from modeldeck.cli.credentials_cmd import (
    _set_fields,
    _verify_hint,
    cmd_credentials_verify,
)
from modeldeck.cli.main import main
from modeldeck.config.loader import ProviderSecrets


def test_set_fields_reports_presence_only():
    """_set_fields returns booleans, never raw values."""
    secrets = ProviderSecrets(session_token="secret-value", org_id="")
    flags = _set_fields(secrets, "claude")
    assert flags["session_token"] is True
    assert flags["org_id"] is False
    assert flags["cf_clearance"] is False
    # No credential value should appear anywhere in the output map.
    assert "secret-value" not in str(flags)


def test_verify_hint_prefers_raw_safe_hint():
    """A hint in raw_safe wins over status-derived defaults."""
    assert (
        _verify_hint("auth_error", {"hint": "cf_clearance_expired_or_docker_ip"})
        == "cf_clearance_expired_or_docker_ip"
    )
    assert _verify_hint("auth_error", None) == (
        "check_auth_mode_and_recopy_credentials"
    )
    assert _verify_hint("rate_limited", None) == (
        "retry_later_reduce_poll_frequency"
    )
    assert _verify_hint("ok", None) == ""


def _write_config(config_dir, *, enabled: bool) -> None:
    flag = "true" if enabled else "false"
    (config_dir / "modeldeck.yaml").write_text(
        f"providers:\n  claude:\n    enabled: {flag}\n    auth_mode: cookie\n",
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text(
        "providers:\n  claude:\n    org_id: org-xyz\n",
        encoding="utf-8",
    )


def test_verify_missing_session_reports_auth_error(tmp_path, monkeypatch, capsys):
    """Verify on cookie mode without a session token reports auth_error + hint."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_config(config_dir, enabled=True)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    args = argparse.Namespace(provider="claude", config_dir=None)
    code = cmd_credentials_verify(args)
    out = capsys.readouterr().out
    assert code == 2
    assert "auth_mode: cookie" in out
    assert "status: auth_error" in out
    # Field presence is shown, but the org_id value must not leak.
    assert "org_id: set" in out
    assert "org-xyz" not in out


def test_verify_disabled_provider_reports_and_exits(tmp_path, monkeypatch, capsys):
    """A disabled provider still prints mode + fields and returns nonzero."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_config(config_dir, enabled=False)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    args = argparse.Namespace(provider="claude", config_dir=None)
    code = cmd_credentials_verify(args)
    out = capsys.readouterr().out
    assert code == 1
    assert "disabled" in out


def test_verify_no_secrets_block_uses_empty_secrets(tmp_path, monkeypatch, capsys):
    """Missing provider secrets block still runs with empty credentials."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "modeldeck.yaml").write_text(
        (
            "providers:\n"
            "  claude:\n"
            "    enabled: true\n"
            "    auth_mode: cookie\n"
            "    credential_path: ''\n"
        ),
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    args = argparse.Namespace(provider="claude", config_dir=None)
    assert cmd_credentials_verify(args) == 2
    out = capsys.readouterr().out
    assert "status: auth_error" in out
    assert "session_token: missing" in out


def test_verify_subcommand_registered(tmp_path, monkeypatch):
    """main() should dispatch credentials verify."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_config(config_dir, enabled=True)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    code = main(["credentials", "verify", "--provider", "claude"])
    assert code == 2
