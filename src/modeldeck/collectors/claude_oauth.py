"""Claude OAuth collector (Claude Code / openusage pattern)."""

from __future__ import annotations

from typing import Any

import httpx

from modeldeck.collectors.claude_oauth_parser import parse_claude_oauth_usage
from modeldeck.collectors.http_errors import error_snapshot, status_from_http_error
from modeldeck.config.loader import ProviderSecrets
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)

CLAUDE_OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


class ClaudeOAuthCollector:
    """Collect Claude subscription usage via OAuth bearer token."""

    def __init__(
        self,
        secrets: ProviderSecrets,
        display_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._secrets = secrets
        self._display_name = display_name
        self._client = client

    def _enrich_snapshot(self, snapshot: ProviderSnapshot) -> ProviderSnapshot:
        if not snapshot.plan_name and self._secrets.subscription_tier.strip():
            snapshot.plan_name = self._secrets.subscription_tier.strip()
        return snapshot

    async def collect(self, provider_id: str = "claude") -> ProviderSnapshot:
        """Fetch Claude OAuth usage or return an error snapshot."""
        if not self._secrets.access_token and not self._secrets.refresh_token:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_oauth_token"},
            )
        # D3: if only a refresh_token is stored (no access_token), pre-emptively
        # refresh before the first usage call to avoid a guaranteed 401.
        if not self._secrets.access_token and self._secrets.refresh_token:
            logger.debug("Claude OAuth: no access_token present; refreshing before first call")
            if not await self._refresh_token():
                return error_snapshot(
                    provider_id,
                    self._display_name,
                    CollectorStatus.AUTH_ERROR,
                    {"reason": "refresh_token_exchange_failed"},
                )
        try:
            payload = await self._fetch_usage()
            snapshot = parse_claude_oauth_usage(payload, provider_id=provider_id)
            snapshot.display_name = self._display_name
            return self._enrich_snapshot(snapshot)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403} and self._secrets.refresh_token:
                if await self._refresh_token():
                    try:
                        payload = await self._fetch_usage()
                        snapshot = parse_claude_oauth_usage(payload, provider_id=provider_id)
                        snapshot.display_name = self._display_name
                        return self._enrich_snapshot(snapshot)
                    except httpx.HTTPStatusError as retry_exc:
                        exc = retry_exc
            return error_snapshot(
                provider_id,
                self._display_name,
                status_from_http_error(exc),
                {"http_status": exc.response.status_code},
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Claude OAuth collection failed: %s", type(exc).__name__)
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.PARSE_ERROR,
                {"error": type(exc).__name__},
            )

    async def _fetch_usage(self) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._secrets.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
        }
        return await self._request("GET", CLAUDE_OAUTH_USAGE_URL, headers=headers)

    async def _refresh_token(self) -> bool:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": self._secrets.refresh_token,
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
            "scope": (
                "user:profile user:inference user:sessions:claude_code "
                "user:mcp_servers user:file_upload"
            ),
        }
        try:
            payload = await self._request("POST", CLAUDE_TOKEN_URL, json_body=body)
            access = payload.get("access_token")
            if isinstance(access, str) and access:
                self._secrets.access_token = access
                refresh = payload.get("refresh_token")
                if isinstance(refresh, str) and refresh:
                    self._secrets.refresh_token = refresh
                from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

                persist_provider_oauth_tokens("claude", self._secrets)
                return True
        except httpx.HTTPError:
            logger.warning("Claude token refresh failed")
        return False

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
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
