"""Cursor enterprise collector via Admin API."""

from __future__ import annotations

from typing import Any

import httpx

from modeldeck.collectors.cursor_enterprise_parser import parse_cursor_enterprise_spend
from modeldeck.collectors.http_errors import error_snapshot, status_from_http_error
from modeldeck.config.loader import ProviderSecrets
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)

CURSOR_TEAMS_SPEND_URL = "https://api.cursor.com/teams/spend"


class CursorEnterpriseCollector:
    """Collect Cursor team/enterprise usage via Admin API key."""

    def __init__(
        self,
        secrets: ProviderSecrets,
        display_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._secrets = secrets
        self._display_name = display_name
        self._client = client

    async def collect(self, provider_id: str = "cursor") -> ProviderSnapshot:
        """Fetch enterprise Cursor spend or return an error snapshot."""
        if not self._secrets.admin_api_key:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_admin_api_key"},
            )
        try:
            payload = await self._fetch_spend()
            snapshot = parse_cursor_enterprise_spend(payload, provider_id=provider_id)
            snapshot.display_name = self._display_name
            return snapshot
        except httpx.HTTPStatusError as exc:
            return error_snapshot(
                provider_id,
                self._display_name,
                status_from_http_error(exc),
                {"http_status": exc.response.status_code},
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Cursor enterprise collection failed: %s", type(exc).__name__)
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.PARSE_ERROR,
                {"error": type(exc).__name__},
            )

    async def _fetch_spend(self) -> dict[str, Any]:
        auth = httpx.BasicAuth(username=self._secrets.admin_api_key, password="")
        body = {"page": 1, "pageSize": 100}
        if self._client is not None:
            response = await self._client.request(
                "POST",
                CURSOR_TEAMS_SPEND_URL,
                auth=auth,
                json=body,
            )
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                "POST",
                CURSOR_TEAMS_SPEND_URL,
                auth=auth,
                json=body,
            )
            response.raise_for_status()
            return response.json()
