"""Codex subscription collector via ChatGPT wham/usage."""

from __future__ import annotations

from typing import Any

import httpx

from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage
from modeldeck.collectors.http_errors import error_snapshot, status_from_http_error
from modeldeck.config.loader import ProviderSecrets
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)

CODEX_WHAM_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


class CodexSubscriptionCollector:
    """Collect ChatGPT/Codex subscription quota via wham/usage."""

    def __init__(
        self,
        secrets: ProviderSecrets,
        display_name: str,
        client: httpx.AsyncClient | None = None,
        account_id: str = "default",
    ) -> None:
        self._secrets = secrets
        self._display_name = display_name
        self._client = client
        self._account_id = account_id

    async def collect(self, provider_id: str = "codex") -> ProviderSnapshot:
        """Fetch subscription usage or return an error snapshot."""
        if not self._secrets.access_token and not self._secrets.refresh_token:
            return error_snapshot(
                provider_id,
                self._display_name,
                CollectorStatus.AUTH_ERROR,
                {"reason": "missing_subscription_token"},
            )
        try:
            payload = await self._fetch_usage()
            snapshot = parse_codex_wham_usage(payload, provider_id=provider_id)
            snapshot.display_name = self._display_name
            return snapshot
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403} and self._secrets.refresh_token:
                refreshed = await self._refresh_token()
                if refreshed:
                    try:
                        payload = await self._fetch_usage()
                        snapshot = parse_codex_wham_usage(payload, provider_id=provider_id)
                        snapshot.display_name = self._display_name
                        return snapshot
                    except httpx.HTTPStatusError as retry_exc:
                        exc = retry_exc
            return error_snapshot(
                provider_id,
                self._display_name,
                status_from_http_error(exc),
                {"http_status": exc.response.status_code},
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Codex subscription collection failed: %s", type(exc).__name__)
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
        }
        if self._secrets.account_id:
            headers["ChatGPT-Account-Id"] = self._secrets.account_id
        return await self._request("GET", CODEX_WHAM_URL, headers=headers)

    async def _refresh_token(self) -> bool:
        data = {
            "grant_type": "refresh_token",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "refresh_token": self._secrets.refresh_token,
        }
        try:
            if self._client is not None:
                response = await self._client.post(CODEX_TOKEN_URL, data=data)
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(CODEX_TOKEN_URL, data=data)
            response.raise_for_status()
            payload = response.json()
            access = payload.get("access_token")
            if isinstance(access, str) and access:
                self._secrets.access_token = access
                refresh = payload.get("refresh_token")
                if isinstance(refresh, str) and refresh:
                    self._secrets.refresh_token = refresh
                from modeldeck.config.secrets_writer import persist_provider_oauth_tokens

                persist_provider_oauth_tokens("codex", self._secrets, self._account_id)
                return True
        except httpx.HTTPError:
            logger.warning("Codex token refresh failed")
        return False

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
