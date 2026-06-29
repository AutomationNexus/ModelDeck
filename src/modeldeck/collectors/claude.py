"""Claude collector facade."""

from __future__ import annotations

import httpx

from modeldeck.collectors.auth_resolve import pick_claude_mode, resolve_claude_secrets
from modeldeck.collectors.claude_cookie import ClaudeCookieCollector
from modeldeck.collectors.claude_oauth import ClaudeOAuthCollector
from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import AppConfig, ProviderAccount, ProviderSecrets, ProviderToggle
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot

logger = get_logger(__name__)


class ClaudeCollector:
    """Collect Claude quota via browser cookie or OAuth."""

    provider_id = "claude"
    display_name = "Claude"

    def __init__(
        self,
        config: AppConfig,
        secrets: ProviderSecrets,
        account: ProviderAccount | ProviderToggle | None = None,
        account_id: str = "default",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # Normalise to ProviderAccount internally; accept ProviderToggle for backward compat.
        if isinstance(account, ProviderAccount):
            self._account = account
            self._account_id = account.id
            self._account_label = account.label
        elif isinstance(account, ProviderToggle):
            self._account = ProviderAccount(
                id=account_id,
                label=account.account_label or "",
                enabled=account.enabled,
                auth_mode=account.auth_mode,
                credential_path=account.credential_path,
            )
            self._account_id = account_id
            self._account_label = account.account_label or ""
        else:
            self._account = ProviderAccount(id=account_id)
            self._account_id = account_id
            self._account_label = ""
        self._secrets = resolve_claude_secrets(self._account, secrets)
        self._client = client

    def supported_metrics(self) -> list[MetricKind]:
        """Return Claude metrics for the configured auth mode."""
        mode = pick_claude_mode(self._account, self._secrets)
        return base_metrics(self.provider_id, mode)

    async def collect(self) -> ProviderSnapshot:
        """Fetch Claude usage using the configured auth mode."""
        mode = pick_claude_mode(self._account, self._secrets)
        logger.info("Claude collecting via mode=%s", mode)
        name = self._display_name()
        if mode == "oauth":
            collector = ClaudeOAuthCollector(self._secrets, name, self._client, self._account_id)
        else:
            collector = ClaudeCookieCollector(self._secrets, name, self._client)
        snapshot = await collector.collect(self.provider_id)
        snapshot.account_id = self._account_id
        snapshot.account_label = self._account_label
        return snapshot

    def _display_name(self) -> str:
        if self._account_label:
            return f"{self.display_name} ({self._account_label})"
        return self.display_name
