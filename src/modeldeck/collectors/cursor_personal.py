"""Cursor personal subscription collector."""

from __future__ import annotations

from typing import Any

import httpx

from modeldeck.collectors.cursor_personal_parser import (
    parse_cursor_period_usage,
    parse_cursor_usage_summary,
)
from modeldeck.collectors.http_errors import error_snapshot, status_from_http_error
from modeldeck.config.loader import ProviderSecrets
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)

CURSOR_USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
CURSOR_PERIOD_USAGE_URL = (
    "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
)


class CursorPersonalCollector:
    """Collect Cursor personal plan usage via cookie or JWT."""

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
        """Fetch personal Cursor usage or return an error snapshot."""
        if not self._secrets.session_token and not self._secrets.access_token:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_cursor_token"},
            )
        try:
            if self._secrets.session_token:
                payload = await self._fetch_usage_summary()
                snapshot = parse_cursor_usage_summary(payload, provider_id=provider_id)
            else:
                payload = await self._fetch_period_usage()
                snapshot = parse_cursor_period_usage(payload, provider_id=provider_id)
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
            logger.warning("Cursor personal collection failed: %s", type(exc).__name__)
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.PARSE_ERROR,
                {"error": type(exc).__name__},
            )

    async def _fetch_usage_summary(self) -> dict[str, Any]:
        headers = {
            "Cookie": f"WorkosCursorSessionToken={self._secrets.session_token}",
            "Origin": "https://cursor.com",
        }
        return await self._request("GET", CURSOR_USAGE_SUMMARY_URL, headers=headers)

    async def _fetch_period_usage(self) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._secrets.access_token}",
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        }
        return await self._request("POST", CURSOR_PERIOD_USAGE_URL, headers=headers, json_body={})

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.request(method, url, headers=headers, json=json_body)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=headers, json=json_body)
            response.raise_for_status()
            return response.json()
