"""Collector protocol and registry."""

from __future__ import annotations

from typing import Protocol

from modeldeck.config.loader import AppConfig, ProviderSecrets, SecretsConfig
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

    registry: dict[str, type] = {
        "codex": CodexCollector,
        "claude": ClaudeCollector,
        "cursor": CursorCollector,
    }
    collectors: list[Collector] = []

    # Mock stays single-account with ProviderToggle pattern (testing only).
    if config.providers.mock.enabled:
        mock_secrets = secrets.providers.get("mock", {}).get("default", ProviderSecrets())
        collectors.append(MockCollector(config, mock_secrets))

    # Real providers iterate their account lists.
    for provider_id in ("codex", "claude", "cursor"):
        accounts = getattr(config.providers, provider_id, [])
        for account in accounts:
            if not account.enabled:
                continue
            cls = registry.get(provider_id)
            if cls is None:
                continue
            acct_secrets = (
                secrets.providers.get(provider_id, {}).get(account.id, ProviderSecrets())
            )
            collectors.append(cls(config, acct_secrets, account, account.id))

    return collectors


def default_metrics() -> list[MetricKind]:
    """Return the default metric list."""
    return list(DEFAULT_METRICS)
