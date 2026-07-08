"""Cursor collector facade."""

from __future__ import annotations

import httpx

from modeldeck.collectors.auth_resolve import pick_cursor_mode, resolve_cursor_secrets
from modeldeck.collectors.cursor_enterprise import CursorEnterpriseCollector
from modeldeck.collectors.cursor_personal import CursorPersonalCollector
from modeldeck.collectors.metrics import base_metrics
from modeldeck.config.loader import AppConfig, ProviderAccount, ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot


class CursorCollector:
    """Collect Cursor quota via personal session or enterprise admin API."""

    provider_id = "cursor"
    display_name = "Cursor"

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
            self._account_alias = account.alias
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
            self._account_alias = ""
        else:
            self._account = ProviderAccount(id=account_id)
            self._account_id = account_id
            self._account_label = ""
            self._account_alias = ""
        self._secrets = resolve_cursor_secrets(self._account, secrets)
        self._client = client

    def supported_metrics(self) -> list[MetricKind]:
        """Return Cursor metrics for the configured auth mode."""
        mode = pick_cursor_mode(self._account, self._secrets)
        return base_metrics(self.provider_id, mode)

    async def collect(self) -> ProviderSnapshot:
        """Fetch Cursor usage using the configured auth mode."""
        mode = pick_cursor_mode(self._account, self._secrets)
        name = self._display_name()
        if mode == "enterprise":
            snapshot = await CursorEnterpriseCollector(
                self._secrets, name, self._client
            ).collect(self.provider_id)
        else:
            collector = CursorPersonalCollector(self._secrets, name, self._client)
            snapshot = await collector.collect(self.provider_id)
        snapshot.account_id = self._account_id
        snapshot.account_label = self._account_label
        snapshot.account_alias = self._account_alias
        return snapshot

    def _display_name(self) -> str:
        if self._account_label:
            return f"{self.display_name} ({self._account_label})"
        return self.display_name
