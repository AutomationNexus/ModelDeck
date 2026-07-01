"""Targeted gap-fill tests (part 2): cli, cursor_auth, metrics, parsers."""

from __future__ import annotations

import argparse
import json
import sqlite3

import pytest
import yaml

from modeldeck.config.loader import AppConfig, SecretsConfig
from modeldeck.schemas.snapshot import CollectorStatus

# ---------------------------------------------------------------------------
# cli/login_cmd.py gaps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_oauth_login_prints_url_before_input(monkeypatch, capsys):
    """_run_oauth_login prints URL before asking for input."""
    from modeldeck.cli.login_cmd import _run_oauth_login

    monkeypatch.setattr("builtins.input", lambda _: "")
    result = await _run_oauth_login("claude", "Test", "test")
    captured = capsys.readouterr()
    assert "claude.ai" in captured.out
    assert result == 1  # empty input → 1


def test_ensure_account_in_config_adds_new(tmp_path, monkeypatch):
    """_ensure_account_in_config adds new account to modeldeck.yaml."""
    from modeldeck.cli.login_cmd import _ensure_account_in_config

    cfg_file = tmp_path / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "default", "label": "Old", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    _ensure_account_in_config("claude", "work", "Work Claude", auth_mode="oauth")
    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    ids = [a["id"] for a in raw["providers"]["claude"]]
    assert "work" in ids


def test_cmd_accounts_add_cursor_session_token(monkeypatch):
    """cmd_accounts_add for Cursor with non-JWT token uses session_token."""
    from modeldeck.cli.login_cmd import cmd_accounts_add

    write_calls: list[tuple] = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.write_account_secrets",
        lambda p, a, f, **kw: write_calls.append((p, a, list(f.keys()))),
    )
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.load_config",
        lambda: (AppConfig(), SecretsConfig()),
    )
    args = argparse.Namespace(
        provider="cursor", label="Cursor", token="WorkosToken123", auth_mode="personal"
    )
    result = cmd_accounts_add(args)
    assert result == 0
    assert write_calls and "session_token" in write_calls[0][2]


def test_cmd_accounts_add_api_key(monkeypatch):
    """cmd_accounts_add for Codex with sk-admin key uses api_key field."""
    from modeldeck.cli.login_cmd import cmd_accounts_add

    write_calls: list[tuple] = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.write_account_secrets",
        lambda p, a, f, **kw: write_calls.append((p, a, list(f.keys()))),
    )
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.load_config",
        lambda: (AppConfig(), SecretsConfig()),
    )
    args = argparse.Namespace(
        provider="codex", label="API", token="sk-admin-xyz", auth_mode="api"
    )
    result = cmd_accounts_add(args)
    assert result == 0
    assert write_calls and "api_key" in write_calls[0][2]


def test_cmd_accounts_add_no_token(monkeypatch):
    """cmd_accounts_add with empty token still ensures config entry."""
    from modeldeck.cli.login_cmd import cmd_accounts_add

    ensure_calls: list[tuple] = []
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd._ensure_account_in_config",
        lambda *a, **kw: ensure_calls.append(a),
    )
    monkeypatch.setattr(
        "modeldeck.cli.login_cmd.load_config",
        lambda: (AppConfig(), SecretsConfig()),
    )
    args = argparse.Namespace(provider="claude", label="New", token="", auth_mode="oauth")
    result = cmd_accounts_add(args)
    assert result == 0
    assert ensure_calls


def test_cmd_accounts_remove_with_existing_data(tmp_path, monkeypatch):
    """cmd_accounts_remove removes account from both config and secrets."""
    from modeldeck.cli.login_cmd import cmd_accounts_remove

    cfg_file = tmp_path / "modeldeck.yaml"
    sec_file = tmp_path / "secrets.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "default", "label": "T", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )
    sec_file.write_text(
        yaml.safe_dump({"providers": {"claude": {"default": {"access_token": "tok"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: cfg_file)
    monkeypatch.setattr("modeldeck.core.paths.secrets_path", lambda: sec_file)
    args = argparse.Namespace(provider="claude", account="default")
    result = cmd_accounts_remove(args)
    assert result == 0
    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"] == []


def test_cmd_accounts_disable_success(tmp_path, monkeypatch):
    """cmd_accounts_disable marks account disabled."""
    from modeldeck.cli.login_cmd import cmd_accounts_disable

    cfg_file = tmp_path / "modeldeck.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "providers": {
                "claude": [
                    {"id": "default", "label": "T", "enabled": True, "auth_mode": "oauth"}
                ]
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("modeldeck.core.paths.config_path", lambda: cfg_file)
    args = argparse.Namespace(provider="claude", account="default", enable=False)
    result = cmd_accounts_disable(args)
    assert result == 0
    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"][0]["enabled"] is False


# ---------------------------------------------------------------------------
# cursor_auth.py gaps
# ---------------------------------------------------------------------------


def test_default_cursor_state_db_path_macos(monkeypatch):
    """macOS path for Cursor state.vscdb is under Library/Application Support."""
    import sys
    from importlib import reload

    monkeypatch.setattr(sys, "platform", "darwin")
    import modeldeck.collectors.credentials.cursor_auth as m

    reload(m)
    p = m.default_cursor_state_db_path()
    assert "Application Support" in str(p) or "Library" in str(p)
    monkeypatch.setattr(sys, "platform", "win32")
    reload(m)


def test_load_cursor_access_token_bytes_value(tmp_path):
    """load_cursor_access_token handles bytes value in db."""
    from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token

    db_path = tmp_path / "state.vscdb"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ItemTable (key TEXT, value BLOB)")
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)", ("cursorAuth/accessToken", b'"eyJtest"')
    )
    conn.commit()
    conn.close()
    token = load_cursor_access_token(db_path)
    assert "eyJtest" in token


def test_load_cursor_access_token_sqlite_error(tmp_path):
    """load_cursor_access_token returns empty on sqlite error."""
    from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token

    db_path = tmp_path / "not_a_db.vscdb"
    db_path.write_text("not a database", encoding="utf-8")
    result = load_cursor_access_token(db_path)
    assert result == ""


# ---------------------------------------------------------------------------
# claude_auth.py / codex_auth.py error paths
# ---------------------------------------------------------------------------


def test_load_claude_oauth_invalid_json(tmp_path):
    """load_claude_oauth returns empty on invalid JSON."""
    from modeldeck.collectors.credentials.claude_auth import load_claude_oauth

    p = tmp_path / ".credentials.json"
    p.write_text("not json", encoding="utf-8")
    assert load_claude_oauth(p) == {}


def test_load_claude_oauth_non_dict_oauth(tmp_path):
    """load_claude_oauth returns empty when claudeAiOauth is not a dict."""
    from modeldeck.collectors.credentials.claude_auth import load_claude_oauth

    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps({"claudeAiOauth": "not_a_dict"}), encoding="utf-8")
    assert load_claude_oauth(p) == {}


def test_load_codex_oauth_non_dict_tokens(tmp_path):
    """load_codex_oauth returns empty when tokens is not a dict."""
    from modeldeck.collectors.credentials.codex_auth import load_codex_oauth

    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"tokens": "not_a_dict"}), encoding="utf-8")
    assert load_codex_oauth(p) == {}


# ---------------------------------------------------------------------------
# metrics.py + collectors/base.py
# ---------------------------------------------------------------------------


def test_base_metrics_unknown_provider():
    """base_metrics returns only STATUS/LAST_SUCCESS for unknown provider."""
    from modeldeck.collectors.metrics import base_metrics
    from modeldeck.schemas.snapshot import MetricKind

    metrics = base_metrics("unknown", "auto")
    assert MetricKind.STATUS in metrics
    assert MetricKind.LAST_SUCCESS in metrics
    assert MetricKind.USAGE_PERCENT not in metrics


def test_base_metrics_mock_provider():
    """base_metrics for mock provider returns all metrics."""
    from modeldeck.collectors.metrics import base_metrics
    from modeldeck.schemas.snapshot import MetricKind

    metrics = base_metrics("mock", "any")
    assert MetricKind.USAGE_PERCENT in metrics


def test_build_collectors_with_mock_enabled():
    """build_collectors includes mock when enabled."""
    from modeldeck.collectors.base import build_collectors
    from modeldeck.config.loader import ProviderToggle

    config = AppConfig()
    config.providers.mock = ProviderToggle(enabled=True)
    collectors = build_collectors(config, SecretsConfig())
    ids = [c.provider_id for c in collectors]
    assert "mock" in ids


# ---------------------------------------------------------------------------
# codex_wham_parser.py
# ---------------------------------------------------------------------------


def test_codex_wham_parser_primary_window():
    """parse_codex_wham_usage returns usage_percent from primary_window."""
    from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage

    payload = {
        "rate_limit": {
            "primary_window": {"used_percent": 55.0, "reset_at": 1751328000},
            "secondary_window": {"used_percent": 10.0},
        }
    }
    snap = parse_codex_wham_usage(payload)
    assert snap.usage_percent == 55.0
    assert snap.usage_percent_weekly == 10.0


def test_codex_wham_parser_no_rate_limit():
    """parse_codex_wham_usage with no rate_limit returns None percents."""
    from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage

    snap = parse_codex_wham_usage({})
    assert snap.usage_percent is None
    assert snap.usage_percent_weekly is None


def test_codex_wham_parser_credits():
    """parse_codex_wham_usage parses credits balance."""
    from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage

    payload = {"credits": {"balance": 42.5}, "plan_type": "pro"}
    snap = parse_codex_wham_usage(payload)
    assert snap.credits_remaining == 42.5
    assert snap.plan_name == "pro"


# ---------------------------------------------------------------------------
# cursor_personal_parser.py
# ---------------------------------------------------------------------------


def test_cursor_usage_summary_minimal():
    """parse_cursor_usage_summary handles empty payload."""
    from modeldeck.collectors.cursor_personal_parser import parse_cursor_usage_summary

    snap = parse_cursor_usage_summary({})
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent is None


def test_cursor_usage_summary_with_plan_usage():
    """parse_cursor_usage_summary parses planUsage block."""
    from modeldeck.collectors.cursor_personal_parser import parse_cursor_usage_summary

    payload = {
        "planUsage": {
            "totalPercentUsed": 60.0,
            "autoPercentUsed": 40.0,
            "apiPercentUsed": 20.0,
            "limit": 10000,
            "includedSpend": 5000,
            "billingCycleEnd": "2026-07-31T00:00:00Z",
        },
        "planName": "Pro",
    }
    snap = parse_cursor_usage_summary(payload)
    assert snap.usage_percent == 60.0
    assert snap.usage_auto_percent == 40.0
    assert snap.plan_name == "Pro"
