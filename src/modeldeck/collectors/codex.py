"""OpenAI Codex collector facade."""

from __future__ import annotations

import httpx

from modeldeck.collectors.auth_resolve import pick_codex_mode, resolve_codex_secrets
from modeldeck.collectors.codex_api_collector import CodexApiCollector
from modeldeck.collectors.codex_subscription import CodexSubscriptionCollector
from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import AppConfig, ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot


class CodexCollector:
    """Collect OpenAI/Codex quota via subscription or API key."""

    provider_id = "codex"
    display_name = "OpenAI Codex"

    def __init__(
        self,
        config: AppConfig,
        secrets: ProviderSecrets,
        toggle: ProviderToggle | None = None,
        account_label: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._toggle = toggle or ProviderToggle()
        self._secrets = resolve_codex_secrets(self._toggle, secrets)
        self._account_label = account_label or self._toggle.account_label
        self._client = client

    def supported_metrics(self) -> list[MetricKind]:
        """Return Codex metrics for the configured auth mode."""
        mode = pick_codex_mode(self._toggle, self._secrets)
        return base_metrics(self.provider_id, mode)

    async def collect(self) -> ProviderSnapshot:
        """Fetch Codex usage using the configured auth mode."""
        mode = pick_codex_mode(self._toggle, self._secrets)
        name = self._display_name()
        if mode == "api":
            collector = CodexApiCollector(self._secrets, name, self._client)
        else:
            collector = CodexSubscriptionCollector(self._secrets, name, self._client)
        return await collector.collect(self.provider_id)

    def _display_name(self) -> str:
        if self._account_label:
            return f"{self.display_name} ({self._account_label})"
        return self.display_name
