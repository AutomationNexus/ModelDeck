"""Tests for multi-account config loader (Workstream A)."""

from __future__ import annotations

import pytest
import yaml

from modeldeck.config.loader import (
    AppConfig,
    ProviderAccount,
    SecretsConfig,
    load_config,
    slugify,
)

# ---------------------------------------------------------------------------
# ProvidersConfig — new list format
# ---------------------------------------------------------------------------


def test_providers_config_list_format():
    """New list format should deserialise to ProviderAccount list."""
    config = AppConfig.model_validate(
        {
            "providers": {
                "codex": [{"id": "work", "enabled": True, "auth_mode": "subscription"}],
                "claude": [
                    {"id": "personal", "enabled": True, "auth_mode": "oauth"},
                    {"id": "work", "enabled": False, "auth_mode": "cookie"},
                ],
                "cursor": [],
            }
        }
    )
    assert len(config.providers.codex) == 1
    assert config.providers.codex[0].id == "work"
    assert config.providers.codex[0].enabled is True
    assert config.providers.codex[0].auth_mode == "subscription"
    assert len(config.providers.claude) == 2
    assert config.providers.claude[0].id == "personal"
    assert config.providers.claude[1].id == "work"
    assert config.providers.cursor == []


def test_providers_config_defaults():
    """Default ProvidersConfig should have empty account lists for real providers."""
    config = AppConfig()
    assert config.providers.codex == []
    assert config.providers.claude == []
    assert config.providers.cursor == []
    assert config.providers.mock.enabled is True  # default mock stays enabled


# ---------------------------------------------------------------------------
# Migration shim — legacy single-dict format → list[ProviderAccount]
# ---------------------------------------------------------------------------


def test_legacy_dict_config_migrates_to_list():
    """Legacy single-dict provider block should be wrapped with id='default'."""
    config = AppConfig.model_validate(
        {
            "providers": {
                "codex": {"enabled": True, "auth_mode": "subscription"},
                "claude": {"enabled": False, "auth_mode": "cookie"},
                "cursor": {"enabled": False, "auth_mode": "personal"},
            }
        }
    )
    assert len(config.providers.codex) == 1
    acct = config.providers.codex[0]
    assert isinstance(acct, ProviderAccount)
    assert acct.id == "default"
    assert acct.enabled is True
    assert acct.auth_mode == "subscription"

    assert config.providers.claude[0].id == "default"
    assert config.providers.claude[0].enabled is False


def test_legacy_dict_preserves_all_fields():
    """Legacy dict migration should carry credential_path through."""
    config = AppConfig.model_validate(
        {
            "providers": {
                "cursor": {
                    "enabled": True,
                    "auth_mode": "personal",
                    "credential_path": "/tmp/state.vscdb",
                }
            }
        }
    )
    assert config.providers.cursor[0].credential_path == "/tmp/state.vscdb"


def test_example_template_migrates_cleanly(tmp_path):
    """Example YAML should parse to ProviderAccount list."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    cfg = root / "templates" / "modeldeck.example.yaml"
    config = AppConfig.model_validate(
        __import__("yaml").safe_load(cfg.read_text(encoding="utf-8")) or {}
    )
    # The template may use list or dict format; either way should produce ProviderAccount list
    assert isinstance(config.providers.codex, list)
    if config.providers.codex:
        assert isinstance(config.providers.codex[0], ProviderAccount)


# ---------------------------------------------------------------------------
# SecretsConfig migration — flat → nested {account_id: {...}}
# ---------------------------------------------------------------------------


def test_secrets_flat_format_migrates_to_nested():
    """Flat ProviderSecrets dict should migrate to {'default': {...}}."""
    secrets = SecretsConfig.model_validate(
        {
            "providers": {
                "codex": {"access_token": "at", "refresh_token": "rt"},
                "claude": {"session_token": "sk-ant", "org_id": "org-1"},
            }
        }
    )
    assert "default" in secrets.providers["codex"]
    assert secrets.providers["codex"]["default"].access_token == "at"
    assert secrets.providers["codex"]["default"].refresh_token == "rt"
    assert secrets.providers["claude"]["default"].session_token == "sk-ant"


def test_secrets_nested_format_passes_through():
    """Already-nested secrets should not be double-wrapped."""
    secrets = SecretsConfig.model_validate(
        {
            "providers": {
                "claude": {
                    "personal": {"access_token": "personal-at"},
                    "work": {"access_token": "work-at"},
                }
            }
        }
    )
    assert "personal" in secrets.providers["claude"]
    assert "work" in secrets.providers["claude"]
    assert secrets.providers["claude"]["personal"].access_token == "personal-at"
    assert secrets.providers["claude"]["work"].access_token == "work-at"


def test_secrets_empty_providers():
    """SecretsConfig with no providers key should default to empty dict."""
    secrets = SecretsConfig.model_validate({})
    assert secrets.providers == {}


def test_secrets_load_with_flat_yaml(tmp_config_dir):
    """load_config should migrate flat secrets on first read."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("{}", encoding="utf-8")
    (config_dir / "secrets.yaml").write_text(
        yaml.dump(
            {
                "providers": {
                    "codex": {"api_key": "sk-admin", "access_token": ""},
                }
            }
        ),
        encoding="utf-8",
    )
    _, secrets = load_config(
        config_dir / "modeldeck.yaml",
        config_dir / "secrets.yaml",
    )
    assert "default" in secrets.providers["codex"]
    assert secrets.providers["codex"]["default"].api_key == "sk-admin"


# ---------------------------------------------------------------------------
# slugify helper
# ---------------------------------------------------------------------------


def test_slugify_basic():
    """Simple labels should produce clean slugs."""
    assert slugify("Work Account") == "work_account"
    assert slugify("Personal") == "personal"
    assert slugify("OpenAI-Codex") == "openai_codex"


def test_slugify_empty_falls_back_to_account():
    """Empty or symbol-only labels should fall back to 'account'."""
    assert slugify("") == "account"
    assert slugify("---") == "account"
    assert slugify("!!!") == "account"


def test_slugify_collision_suffix():
    """Collisions should produce _2, _3, … suffixes."""
    existing = {"work"}
    assert slugify("Work Account", existing) == "work_account"
    existing = {"work_account"}
    assert slugify("Work Account", existing) == "work_account_2"
    existing = {"work_account", "work_account_2"}
    assert slugify("Work Account", existing) == "work_account_3"


def test_slugify_no_collision_without_existing():
    """Without existing set, collision avoidance is skipped."""
    assert slugify("test") == "test"
    assert slugify("test", None) == "test"


# ---------------------------------------------------------------------------
# ProviderAccount model validation
# ---------------------------------------------------------------------------


def test_provider_account_requires_id():
    """ProviderAccount must have an id field."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProviderAccount.model_validate({})  # missing id


def test_provider_account_defaults():
    """ProviderAccount should have sensible defaults."""
    acct = ProviderAccount(id="default")
    assert acct.label == ""
    assert acct.enabled is False
    assert acct.auth_mode == "auto"
    assert acct.credential_path is None


def test_providers_config_invalid_value_becomes_empty_list():
    """Non-list/non-dict value for a real provider should produce an empty list."""
    config = AppConfig.model_validate({"providers": {"codex": None}})
    assert config.providers.codex == []
