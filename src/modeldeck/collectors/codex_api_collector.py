"""Codex API collector via OpenAI Organization Admin API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from modeldeck.collectors.codex_api import parse_codex_admin_costs
from modeldeck.collectors.http_errors import error_snapshot, status_from_http_error
from modeldeck.config.loader import ProviderSecrets
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)

CODEX_ADMIN_COSTS_URL = "https://api.openai.com/v1/organization/costs"


def _month_start_unix() -> int:
    now = datetime.now(UTC)
    return int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


class CodexApiCollector:
    """Collect OpenAI Platform spend via Organization Admin API."""

    def __init__(
        self,
        secrets: ProviderSecrets,
        display_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._secrets = secrets
        self._display_name = display_name
        self._client = client

    async def collect(self, provider_id: str = "codex") -> ProviderSnapshot:
        """Fetch API organization costs or return an error snapshot."""
        api_key = self._secrets.api_key
        if not api_key:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_api_key"},
            )
        if not api_key.startswith("sk-admin-"):
            logger.warning(
                "Codex api mode expects an Organization Admin key (sk-admin-...); "
                "standard project keys cannot read usage/cost APIs"
            )
        try:
            payload = await self._fetch_admin_costs(api_key)
            snapshot = parse_codex_admin_costs(payload, provider_id=provider_id)
            snapshot.display_name = self._display_name
            return snapshot
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                return error_snapshot(
                    provider_id,
                    self._display_name,
                    CollectorStatus.AUTH_ERROR,
                    {"http_status": exc.response.status_code, "hint": "use_sk_admin_key"},
                )
            return error_snapshot(
                provider_id,
                self._display_name,
                status_from_http_error(exc),
                {"http_status": exc.response.status_code},
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Codex API collection failed: %s", type(exc).__name__)
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.PARSE_ERROR,
                {"error": type(exc).__name__},
            )

    async def _fetch_admin_costs(self, api_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"start_time": _month_start_unix(), "limit": 31}
        return await self._request("GET", CODEX_ADMIN_COSTS_URL, headers=headers, params=params)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.request(method, url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
