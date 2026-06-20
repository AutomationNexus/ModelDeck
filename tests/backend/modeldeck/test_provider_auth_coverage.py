"""Coverage tests for provider auth polish (Admin APIs, CLI, token persistence)."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import httpx
import pytest
import yaml

from modeldeck.cli.credentials_cmd import (
    _build_yaml,
    _cmd_credentials_print_wrapper,
    _merge_into_secrets,
    _provider_paths,
    cmd_credentials_print,
)
from modeldeck.cli.main import main
from modeldeck.collectors.codex_api import parse_codex_billing_usage
from modeldeck.collectors.codex_api_collector import CodexApiCollector
from modeldeck.collectors.codex_subscription import CodexSubscriptionCollector
from modeldeck.collectors.credentials.cursor_auth import (
    default_cursor_state_db_path,
    load_cursor_access_token,
)
from modeldeck.collectors.cursor_enterprise import CursorEnterpriseCollector
from modeldeck.collectors.cursor_enterprise_parser import parse_cursor_enterprise_spend
from modeldeck.config.loader import ProviderSecrets
from modeldeck.config.secrets_writer import persist_provider_oauth_tokens
from modeldeck.schemas.snapshot import CollectorStatus


def test_parse_codex_billing_usage_data_array_and_reset():
    """Legacy billing parser should sum token fields and parse reset_at."""
    snap = parse_codex_billing_usage(
        {
            "data": [{"n_context_tokens_total": 3}, {"n_context_tokens_total": 7}],
            "hard_limit_usd": 20,
            "reset_at": "2026-07-01T00:00:00Z",
        }
    )
    assert snap.usage_used == 10.0
    assert snap.usage_limit == 20.0
    assert snap.reset_at is not None


def test_parse_codex_admin_costs_skips_invalid_buckets():
    """Admin cost sum should ignore malformed bucket entries."""
    from modeldeck.collectors.codex_api import _sum_cost_usd

    total = _sum_cost_usd(
        {
            "data": [
                "bad",
                {"results": ["bad", {"amount": "bad"}, {"amount": {"value": 2.5}}]},
            ]
        }
    )
    assert total == 2.5


def test_parse_cursor_enterprise_spend_empty_members():
    """Spend parser should handle missing teamMemberSpend."""
    snap = parse_cursor_enterprise_spend({})
    assert snap.status == CollectorStatus.OK
    assert snap.usage_used == 0.0


@pytest.mark.asyncio
async def test_codex_api_missing_key():
    """API collector without key should return auth_error."""
    snap = await CodexApiCollector(ProviderSecrets(), "Codex").collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_codex_api_admin_key_401():
    """401 from admin API should map to auth_error with hint."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    snap = await CodexApiCollector(ProviderSecrets(api_key="sk-admin-x"), "Codex", client).collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_cursor_enterprise_missing_admin_key():
    """Enterprise collector without admin key should return auth_error."""
    snap = await CursorEnterpriseCollector(ProviderSecrets(), "Cursor").collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_codex_subscription_refresh_retry_still_401():
    """Refresh success but retry 401 should surface auth error."""
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "new"})
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="old", refresh_token="refresh")
    snap = await CodexSubscriptionCollector(secrets, "Codex", client).collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_codex_subscription_refresh_live_client_post(monkeypatch, tmp_path):
    """Token refresh without injected client should use httpx.AsyncClient.post."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "live-new", "refresh_token": "live-r"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data=None):
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.codex_subscription.httpx.AsyncClient", lambda **k: FakeClient()
    )
    secrets = ProviderSecrets(access_token="old", refresh_token="r")
    collector = CodexSubscriptionCollector(secrets, "Codex")
    assert await collector._refresh_token()
    assert secrets.access_token == "live-new"


def test_credentials_build_yaml_all_providers(monkeypatch):
    """All provider blocks should be built when loaders return data."""
    monkeypatch.setattr(
        "modeldeck.cli.credentials_cmd.load_codex_oauth",
        lambda: {"access_token": "a", "refresh_token": "r", "account_id": "1"},
    )
    monkeypatch.setattr(
        "modeldeck.cli.credentials_cmd.load_claude_oauth",
        lambda: {"access_token": "ca", "refresh_token": "cr"},
    )
    monkeypatch.setattr(
        "modeldeck.cli.credentials_cmd.load_cursor_access_token",
        lambda: "cursor-jwt",
    )
    data = _build_yaml(["codex", "claude", "cursor"], full=True)
    assert len(data["providers"]) == 3
    assert _provider_paths()["codex"]


def test_credentials_print_not_found(capsys, monkeypatch):
    """Missing credentials should print expected paths."""
    monkeypatch.setattr("modeldeck.cli.credentials_cmd.load_codex_oauth", lambda: None)
    args = argparse.Namespace(all=False, provider="codex", full=False, write_secrets=False)
    assert cmd_credentials_print(args) == 1
    assert "No credentials found" in capsys.readouterr().out


def test_credentials_print_all_and_write(tmp_path, monkeypatch, capsys):
    """--all with --write-secrets should merge full tokens."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(
        "modeldeck.cli.credentials_cmd.load_codex_oauth",
        lambda: {"access_token": "full-a", "refresh_token": "full-r"},
    )
    monkeypatch.setattr("modeldeck.cli.credentials_cmd.load_claude_oauth", lambda: None)
    monkeypatch.setattr("modeldeck.cli.credentials_cmd.load_cursor_access_token", lambda: "")
    args = argparse.Namespace(all=True, provider=None, full=False, write_secrets=True)
    assert cmd_credentials_print(args) == 0
    assert "Merged into" in capsys.readouterr().out
    raw = yaml.safe_load((config_dir / "secrets.yaml").read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["access_token"] == "full-a"


def test_credentials_wrapper_config_dir(tmp_path, monkeypatch, capsys):
    """Wrapper should honor --config-dir for secrets path."""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    monkeypatch.setattr("modeldeck.cli.credentials_cmd.load_codex_oauth", lambda: None)
    args = argparse.Namespace(
        all=False,
        provider="codex",
        full=False,
        write_secrets=False,
        config_dir=config_dir,
    )
    assert _cmd_credentials_print_wrapper(args) == 1


def test_merge_into_secrets_invalid_blocks(tmp_path, monkeypatch):
    """Merge should coerce invalid provider mappings."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets = config_dir / "secrets.yaml"
    secrets.write_text("providers:\n  codex: not-a-map\n", encoding="utf-8")
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    _merge_into_secrets({"providers": {"codex": {"access_token": "x"}, "bad": "nope"}})
    raw = yaml.safe_load(secrets.read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["access_token"] == "x"


def test_persist_oauth_no_update_same_tokens(tmp_path, monkeypatch):
    """Identical tokens should not rewrite secrets file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        "providers:\n  codex:\n    access_token: same\n",
        encoding="utf-8",
    )
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    before = secrets_file.read_text(encoding="utf-8")
    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="same"),
        secrets_file=secrets_file,
    )
    assert secrets_file.read_text(encoding="utf-8") == before


def test_persist_oauth_corrupt_yaml(tmp_path, monkeypatch):
    """Unreadable secrets should return False without raising."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(":\n  bad\n", encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="new"),
        secrets_file=secrets_file,
    )


def test_persist_oauth_load_config_failure(monkeypatch, tmp_path):
    """load_config failure should skip persistence."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text("providers: {}\n", encoding="utf-8")
    with patch("modeldeck.config.secrets_writer.load_config", side_effect=RuntimeError("boom")):
        assert not persist_provider_oauth_tokens(
            "codex",
            ProviderSecrets(access_token="x"),
            secrets_file=secrets_file,
        )


def test_persist_oauth_non_dict_root(tmp_path, monkeypatch):
    """Non-dict secrets root should abort."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text("- list\n", encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="x"),
        secrets_file=secrets_file,
    )


def test_persist_oauth_chmod_error(tmp_path, monkeypatch):
    """chmod failures after write should still return True."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text("providers:\n  codex:\n    access_token: old\n", encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    with patch("modeldeck.config.secrets_writer.os.chmod", side_effect=OSError("nope")):
        assert persist_provider_oauth_tokens(
            "codex",
            ProviderSecrets(access_token="new"),
            secrets_file=secrets_file,
        )


def test_load_cursor_token_from_sqlite(tmp_path):
    """Cursor SQLite reader should return stored access token."""
    import sqlite3

    db = tmp_path / "state.vscdb"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("cursorAuth/accessToken", '"jwt-from-db"'),
    )
    conn.commit()
    conn.close()
    assert load_cursor_access_token(db) == "jwt-from-db"


def test_default_cursor_state_db_path_win32(monkeypatch):
    """Windows default path should use APPDATA when set."""
    monkeypatch.setattr("modeldeck.collectors.credentials.cursor_auth.sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
    path = default_cursor_state_db_path()
    assert "Cursor" in str(path)
    assert "state.vscdb" in str(path)


def test_cli_credentials_subcommand_registered(tmp_path, monkeypatch):
    """main() should dispatch credentials print."""
    monkeypatch.setattr("modeldeck.cli.credentials_cmd.load_codex_oauth", lambda: None)
    code = main(["credentials", "print", "--provider", "codex"])
    assert code == 1
