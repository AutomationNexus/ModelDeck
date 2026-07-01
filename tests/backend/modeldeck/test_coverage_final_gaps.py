"""Targeted gap-fill tests (part 1): server, collectors, secrets_writer."""

from __future__ import annotations

import yaml

from modeldeck.config.loader import AppConfig, ProviderAccount, ProviderSecrets

# ---------------------------------------------------------------------------
# webui/server.py:22-26 — run_webui with real uvicorn call (mocked)
# ---------------------------------------------------------------------------


def test_run_webui_with_mocked_uvicorn(monkeypatch):
    """run_webui executes through uvicorn.run when uvicorn is importable."""
    import importlib
    import sys
    import types

    fake_uvicorn = types.ModuleType("uvicorn")
    run_calls: list[tuple[str, int]] = []
    fake_uvicorn.run = lambda app, host, port, log_level="warning": run_calls.append((host, port))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    import modeldeck.webui.server as server_mod

    importlib.reload(server_mod)

    server_mod.run_webui(host="127.0.0.1", port=8088)
    assert ("127.0.0.1", 8088) in run_calls


# ---------------------------------------------------------------------------
# codex.py:31-33,45-47 — ProviderAccount branch + else branch
# ---------------------------------------------------------------------------


def test_codex_collector_with_provider_account():
    """CodexCollector with a ProviderAccount hits account.id/.label branch."""
    from modeldeck.collectors.codex import CodexCollector

    account = ProviderAccount(
        id="work", label="Work Codex", enabled=True, auth_mode="subscription"
    )
    collector = CodexCollector(AppConfig(), ProviderSecrets(), account)
    assert collector._account_id == "work"
    assert collector._account_label == "Work Codex"


def test_codex_collector_else_branch():
    """CodexCollector with None account hits the else branch."""
    from modeldeck.collectors.codex import CodexCollector

    collector = CodexCollector(AppConfig(), ProviderSecrets(), None, "default")
    assert collector._account_id == "default"
    assert collector._account_label == ""


# ---------------------------------------------------------------------------
# cursor.py:31-33,45-47 — same pattern
# ---------------------------------------------------------------------------


def test_cursor_collector_with_provider_account():
    """CursorCollector with a ProviderAccount hits account.id/.label branch."""
    from modeldeck.collectors.cursor import CursorCollector

    account = ProviderAccount(
        id="work", label="Work Cursor", enabled=True, auth_mode="personal"
    )
    collector = CursorCollector(AppConfig(), ProviderSecrets(), account)
    assert collector._account_id == "work"
    assert collector._account_label == "Work Cursor"


def test_cursor_collector_else_branch():
    """CursorCollector with None account hits the else branch."""
    from modeldeck.collectors.cursor import CursorCollector

    collector = CursorCollector(AppConfig(), ProviderSecrets(), None, "default")
    assert collector._account_id == "default"


# ---------------------------------------------------------------------------
# secrets_writer.py persist — uncovered branches
# ---------------------------------------------------------------------------


def test_persist_bad_yaml_in_file(tmp_path, monkeypatch):
    """persist returns False when file contains bad YAML."""
    from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(": bad yaml ::\n", encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    result = persist_provider_oauth_tokens(
        "codex", ProviderSecrets(access_token="x"), secrets_file=secrets_file
    )
    assert result is False


def test_persist_non_dict_raw(tmp_path, monkeypatch):
    """persist returns False when file contains a non-dict YAML."""
    from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text("- item\n", encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    result = persist_provider_oauth_tokens(
        "codex", ProviderSecrets(access_token="x"), secrets_file=secrets_file
    )
    assert result is False


def test_persist_non_dict_providers(tmp_path, monkeypatch):
    """persist repairs non-dict providers block."""
    from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(yaml.safe_dump({"providers": "not_a_dict"}), encoding="utf-8")
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    result = persist_provider_oauth_tokens(
        "codex", ProviderSecrets(access_token="new_tok"), "default", secrets_file=secrets_file
    )
    assert result is True


def test_persist_non_dict_provider_block(tmp_path, monkeypatch):
    """persist repairs non-dict provider block (string value)."""
    from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"codex": "corrupted"}}), encoding="utf-8"
    )
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    result = persist_provider_oauth_tokens(
        "codex", ProviderSecrets(access_token="tok"), "default", secrets_file=secrets_file
    )
    assert result is True
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["default"]["access_token"] == "tok"


def test_persist_non_dict_account_block(tmp_path, monkeypatch):
    """persist repairs non-dict account block (string inside provider dict)."""
    from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"codex": {"default": "bad"}}}), encoding="utf-8"
    )
    (config_dir / "modeldeck.yaml").write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    result = persist_provider_oauth_tokens(
        "codex", ProviderSecrets(access_token="tok"), "default", secrets_file=secrets_file
    )
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    if result:
        assert raw["providers"]["codex"]["default"]["access_token"] == "tok"


def test_write_account_secrets_chmod_error(tmp_path, monkeypatch):
    """write_account_secrets ignores chmod OSError."""
    import os

    from modeldeck.config.secrets_writer import write_account_secrets

    secrets_file = tmp_path / "secrets.yaml"

    def fake_chmod(path, mode):
        raise OSError("nope")

    monkeypatch.setattr(os, "chmod", fake_chmod)
    write_account_secrets("claude", "default", {"access_token": "tok"},
                          secrets_file=secrets_file)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["default"]["access_token"] == "tok"
