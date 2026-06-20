"""Collector registry tests."""

from modeldeck.collectors.base import build_collectors
from modeldeck.config.loader import AppConfig, SecretsConfig


def test_build_collectors_respects_enabled_flags():
    """Only enabled providers should be instantiated."""
    config = AppConfig.model_validate({"providers": {"mock": {"enabled": True}}})
    secrets = SecretsConfig()
    collectors = build_collectors(config, secrets)
    assert [c.provider_id for c in collectors] == ["mock"]
