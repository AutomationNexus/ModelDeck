"""Claude collector facade."""

from __future__ import annotations

import httpx

from modeldeck.collectors.auth_resolve import pick_claude_mode, resolve_claude_secrets
from modeldeck.collectors.claude_cookie import ClaudeCookieCollector
from modeldeck.collectors.claude_oauth import ClaudeOAuthCollector
from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import AppConfig, ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot


class ClaudeCollector:
    """Collect Claude quota via browser cookie or OAuth."""

    provider_id = "claude"
    display_name = "Claude"

    def __init__(
        self,
        config: AppConfig,
        secrets: ProviderSecrets,
        toggle: ProviderToggle | None = None,
        account_label: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._toggle = toggle or ProviderToggle()
        self._secrets = resolve_claude_secrets(self._toggle, secrets)
        self._account_label = account_label or self._toggle.account_label
        self._client = client

    def supported_metrics(self) -> list[MetricKind]:
        """Return Claude metrics for the configured auth mode."""
        mode = pick_claude_mode(self._toggle, self._secrets)
        return base_metrics(self.provider_id, mode)

    async def collect(self) -> ProviderSnapshot:
        """Fetch Claude usage using the configured auth mode."""
        mode = pick_claude_mode(self._toggle, self._secrets)
        name = self._display_name()
        if mode == "oauth":
            collector = ClaudeOAuthCollector(self._secrets, name, self._client)
        else:
            collector = ClaudeCookieCollector(self._secrets, name, self._client)
        return await collector.collect(self.provider_id)

    def _display_name(self) -> str:
        if self._account_label:
            return f"{self.display_name} ({self._account_label})"
        return self.display_name
