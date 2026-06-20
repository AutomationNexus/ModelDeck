"""Collector protocol and registry."""

from __future__ import annotations

from typing import Protocol

from modeldeck.config.loader import AppConfig, ProviderSecrets, ProviderToggle, SecretsConfig
from modeldeck.schemas.snapshot import DEFAULT_METRICS, MetricKind, ProviderSnapshot


class Collector(Protocol):
    """Collect quota data from one AI provider."""

    provider_id: str
    display_name: str

    async def collect(self) -> ProviderSnapshot:
        """Fetch the latest provider snapshot."""

    def supported_metrics(self) -> list[MetricKind]:
        """Return metrics published for this provider."""


def build_collectors(
    config: AppConfig,
    secrets: SecretsConfig,
) -> list[Collector]:
    """Instantiate enabled collectors from configuration."""
    from modeldeck.collectors.claude import ClaudeCollector
    from modeldeck.collectors.codex import CodexCollector
    from modeldeck.collectors.cursor import CursorCollector
    from modeldeck.collectors.mock import MockCollector

    registry: dict[str, type[Collector]] = {
        "mock": MockCollector,
        "codex": CodexCollector,
        "claude": ClaudeCollector,
        "cursor": CursorCollector,
    }
    collectors: list[Collector] = []
    provider_flags = config.providers.model_dump()
    for provider_id, toggle_data in provider_flags.items():
        if not toggle_data.get("enabled"):
            continue
        cls = registry.get(provider_id)
        if cls is None:
            continue
        toggle = ProviderToggle.model_validate(toggle_data)
        provider_secrets = secrets.providers.get(provider_id, ProviderSecrets())
        collectors.append(cls(config, provider_secrets, toggle))
    return collectors


def default_metrics() -> list[MetricKind]:
    """Return the default metric list."""
    return list(DEFAULT_METRICS)
