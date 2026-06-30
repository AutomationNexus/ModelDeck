"""Tests for OAuth token persistence to secrets.yaml."""

import yaml

from modeldeck.config.loader import ProviderSecrets
from modeldeck.config.secrets_writer import persist_provider_oauth_tokens, write_account_secrets


def test_persist_provider_oauth_tokens_merges(tmp_path, monkeypatch):
    """Refreshed tokens should merge into existing secrets (account-nested format)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    # Write pre-existing flat-format secrets (legacy); persist should migrate to nested.
    secrets_file.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "codex": {"access_token": "old-access", "api_key": "keep-me"},
                    "claude": {"session_token": "cookie"},
                }
            }
        ),
        encoding="utf-8",
    )
    modeldeck_yaml = config_dir / "modeldeck.yaml"
    modeldeck_yaml.write_text(
        "service:\n  persist_refreshed_tokens: true\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

    updated = ProviderSecrets(
        access_token="new-access",
        refresh_token="new-refresh",
        account_id="acct-1",
    )
    # Persist into the default account slot.
    assert persist_provider_oauth_tokens("codex", updated, "default", secrets_file=secrets_file)

    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    # After migration flat -> nested, codex block is {"default": {...}}.
    codex_default = raw["providers"]["codex"]["default"]
    assert codex_default["access_token"] == "new-access"
    assert codex_default["refresh_token"] == "new-refresh"
    assert codex_default["account_id"] == "acct-1"
    assert codex_default["api_key"] == "keep-me"
    # Claude stays flat (not touched by this persist call) — but will also be nested on next write.
    assert raw["providers"]["claude"]["session_token"] == "cookie"


def test_persist_skips_when_disabled(tmp_path, monkeypatch):
    """Persistence should no-op when service.persist_refreshed_tokens is false."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text("providers:\n  codex:\n    access_token: old\n", encoding="utf-8")
    modeldeck_yaml = config_dir / "modeldeck.yaml"
    modeldeck_yaml.write_text(
        "service:\n  persist_refreshed_tokens: false\nproviders: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("MODELDECK_CONFIG", raising=False)

    assert not persist_provider_oauth_tokens(
        "codex",
        ProviderSecrets(access_token="new"),
        secrets_file=secrets_file,
    )
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["access_token"] == "old"


def test_write_account_secrets_creates_nested(tmp_path):
    """write_account_secrets should create nested account block."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text("providers: {}\n", encoding="utf-8")

    write_account_secrets("claude", "work", {"access_token": "tok", "refresh_token": "ref"},
                          secrets_file=secrets_file)

    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["work"]["access_token"] == "tok"
    assert raw["providers"]["claude"]["work"]["refresh_token"] == "ref"


def test_write_account_secrets_preserves_other_accounts(tmp_path):
    """write_account_secrets should not overwrite other accounts."""
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"claude": {"personal": {"access_token": "p-tok"}}}}),
        encoding="utf-8",
    )

    write_account_secrets("claude", "work", {"access_token": "w-tok"},
                          secrets_file=secrets_file)

    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["claude"]["personal"]["access_token"] == "p-tok"
    assert raw["providers"]["claude"]["work"]["access_token"] == "w-tok"
