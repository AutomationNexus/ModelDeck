"""Tests for modeldeck credentials print CLI."""

import argparse

import yaml

from modeldeck.cli.credentials_cmd import (
    _build_yaml,
    _mask,
    _merge_into_secrets,
    cmd_credentials_print,
)


def test_mask_short_and_long():
    """Masking should hide middle of long tokens only."""
    assert _mask("short", full=False) == "short"
    assert _mask("abcdefghijklmnop", full=False) == "abcd...mnop"
    assert _mask("abcdefghijklmnop", full=True) == "abcdefghijklmnop"


def test_build_yaml_empty_when_no_loaders(monkeypatch):
    """Without credential files, YAML builder should return empty providers."""
    monkeypatch.setattr("modeldeck.cli.credentials_cmd.load_codex_oauth", lambda: None)
    data = _build_yaml(["codex"], full=False)
    assert data == {"providers": {}}


def test_cmd_credentials_print_no_args(capsys):
    """Missing --provider/--all should exit with code 1."""
    args = argparse.Namespace(all=False, provider=None, full=False, write_secrets=False)
    assert cmd_credentials_print(args) == 1
    assert "Specify --provider or --all" in capsys.readouterr().out


def test_cmd_credentials_print_with_mock_codex(tmp_path, monkeypatch, capsys):
    """Print should emit masked YAML when codex auth file is available."""
    monkeypatch.setattr(
        "modeldeck.cli.credentials_cmd.load_codex_oauth",
        lambda: {
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
            "account_id": "acct-123",
        },
    )
    args = argparse.Namespace(all=False, provider="codex", full=False, write_secrets=False)
    assert cmd_credentials_print(args) == 0
    out = capsys.readouterr().out
    data = yaml.safe_load(out)
    assert data["providers"]["codex"]["account_id"] == "acct-123"
    assert "..." in data["providers"]["codex"]["access_token"]


def test_merge_into_secrets(tmp_path, monkeypatch):
    """--write-secrets merge should create secrets.yaml with full tokens."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    data = {
        "providers": {
            "codex": {
                "access_token": "full-access",
                "refresh_token": "full-refresh",
            }
        }
    }
    _merge_into_secrets(data)
    path = config_dir / "secrets.yaml"
    assert path.exists()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["access_token"] == "full-access"
