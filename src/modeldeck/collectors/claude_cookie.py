"""Claude cookie-based collector (ClaudeDash pattern)."""

from __future__ import annotations

from typing import Any

import httpx

from modeldeck.collectors.claude_console_parser import parse_claude_console_usage
from modeldeck.collectors.http_errors import error_snapshot, status_from_http_error
from modeldeck.config.loader import ProviderSecrets
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)


class ClaudeCookieCollector:
    """Collect Claude subscription usage via claude.ai session cookies."""

    def __init__(
        self,
        secrets: ProviderSecrets,
        display_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._secrets = secrets
        self._display_name = display_name
        self._client = client

    async def collect(self, provider_id: str = "claude") -> ProviderSnapshot:
        """Fetch Claude console usage or return an error snapshot."""
        if not self._secrets.session_token:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_session_token"},
            )
        if not self._secrets.org_id:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_org_id"},
            )
        try:
            payload = await self._fetch_usage()
            snapshot = parse_claude_console_usage(payload, provider_id=provider_id)
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
            logger.warning("Claude cookie collection failed: %s", type(exc).__name__)
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.PARSE_ERROR,
                {"error": type(exc).__name__},
            )

    def _cookie_header(self) -> str:
        parts = [f"sessionKey={self._secrets.session_token}"]
        if self._secrets.cf_clearance:
            parts.append(f"cf_clearance={self._secrets.cf_clearance}")
        if self._secrets.device_id:
            parts.append(f"anthropic-device-id={self._secrets.device_id}")
        return "; ".join(parts)

    async def _fetch_usage(self) -> dict[str, Any]:
        url = f"https://claude.ai/api/organizations/{self._secrets.org_id}/usage"
        headers = {"Cookie": self._cookie_header()}
        if self._client is not None:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
