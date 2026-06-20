"""Tests for OAuth token persistence to secrets.yaml."""

import yaml

from modeldeck.config.loader import ProviderSecrets
from modeldeck.config.secrets_writer import persist_provider_oauth_tokens


def test_persist_provider_oauth_tokens_merges(tmp_path, monkeypatch):
    """Refreshed tokens should merge into existing secrets without dropping other fields."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
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
    assert persist_provider_oauth_tokens("codex", updated, secrets_file=secrets_file)

    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    codex = raw["providers"]["codex"]
    assert codex["access_token"] == "new-access"
    assert codex["refresh_token"] == "new-refresh"
    assert codex["account_id"] == "acct-1"
    assert codex["api_key"] == "keep-me"
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
