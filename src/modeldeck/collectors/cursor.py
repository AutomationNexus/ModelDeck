"""Cursor collector facade."""

from __future__ import annotations

import httpx

from modeldeck.collectors.auth_resolve import pick_cursor_mode, resolve_cursor_secrets
from modeldeck.collectors.cursor_enterprise import CursorEnterpriseCollector
from modeldeck.collectors.cursor_personal import CursorPersonalCollector
from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import AppConfig, ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot


class CursorCollector:
    """Collect Cursor quota via personal session or enterprise admin API."""

    provider_id = "cursor"
    display_name = "Cursor"

    def __init__(
        self,
        config: AppConfig,
        secrets: ProviderSecrets,
        toggle: ProviderToggle | None = None,
        account_label: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._toggle = toggle or ProviderToggle()
        self._secrets = resolve_cursor_secrets(self._toggle, secrets)
        self._account_label = account_label or self._toggle.account_label
        self._client = client

    def supported_metrics(self) -> list[MetricKind]:
        """Return Cursor metrics for the configured auth mode."""
        mode = pick_cursor_mode(self._toggle, self._secrets)
        return base_metrics(self.provider_id, mode)

    async def collect(self) -> ProviderSnapshot:
        """Fetch Cursor usage using the configured auth mode."""
        mode = pick_cursor_mode(self._toggle, self._secrets)
        name = self._display_name()
        if mode == "enterprise":
            return await CursorEnterpriseCollector(self._secrets, name, self._client).collect(
                self.provider_id
            )
        collector = CursorPersonalCollector(self._secrets, name, self._client)
        return await collector.collect(self.provider_id)

    def _display_name(self) -> str:
        if self._account_label:
            return f"{self.display_name} ({self._account_label})"
        return self.display_name
