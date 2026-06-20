"""Mock collector for development and integration tests."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import AppConfig, ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot


class MockCollector:
    """Synthetic quota data that oscillates over time."""

    provider_id = "mock"
    display_name = "Mock Provider"

    def __init__(
        self,
        config: AppConfig,
        secrets: ProviderSecrets,
        toggle: ProviderToggle | None = None,
        account_label: str | None = None,
    ) -> None:
        self._config = config
        self._account_label = account_label or (toggle.account_label if toggle else None)

    def supported_metrics(self) -> list[MetricKind]:
        """Return metrics for the mock provider."""
        return base_metrics(self.provider_id, "mock")

    async def collect(self) -> ProviderSnapshot:
        """Return oscillating usage values."""
        now = datetime.now(UTC)
        phase = math.sin(now.timestamp() / 600.0)
        usage_percent = round(50.0 + phase * 40.0, 1)
        weekly_percent = round(30.0 + phase * 20.0, 1)
        usage_limit = 2000.0
        usage_used = round(usage_limit * usage_percent / 100.0, 1)
        return ProviderSnapshot(
            provider_id=self.provider_id,
            display_name=self._display_name(),
            collected_at=now,
            status=CollectorStatus.OK,
            usage_percent=usage_percent,
            usage_used=usage_used,
            usage_limit=usage_limit,
            reset_at=now + timedelta(hours=5),
            usage_percent_weekly=weekly_percent,
            reset_at_weekly=now + timedelta(days=7),
            credits_remaining=12.5,
            plan_name="Mock Pro",
            raw_safe={"source": "mock"},
        )

    def _display_name(self) -> str:
        if self._account_label:
            return f"Mock ({self._account_label})"
        return self.display_name
