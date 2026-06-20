"""Codex collector and parser tests."""

import json
from pathlib import Path

import httpx
import pytest

from modeldeck.collectors.codex import CodexCollector
from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.schemas.snapshot import CollectorStatus
from tests.conftest import no_file_toggle

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_parse_codex_wham_fixture():
    """Parser should read ChatGPT wham/usage fixture."""
    payload = json.loads((FIXTURES / "codex_wham_usage.json").read_text(encoding="utf-8"))
    snap = parse_codex_wham_usage(payload)
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 6.0
    assert snap.usage_percent_weekly == 24.0
    assert snap.plan_name == "plus"


@pytest.mark.asyncio
async def test_codex_collector_missing_subscription_token():
    """Missing subscription token should yield auth_error."""
    toggle = no_file_toggle(enabled=True, auth_mode="subscription")
    collector = CodexCollector(AppConfig(), ProviderSecrets(), toggle)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_codex_subscription_with_mock_transport():
    """Subscription collector should parse wham/usage response."""
    payload = json.loads((FIXTURES / "codex_wham_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    toggle = no_file_toggle(enabled=True, auth_mode="subscription")
    secrets = ProviderSecrets(access_token="oauth-token")
    collector = CodexCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 6.0


@pytest.mark.asyncio
async def test_codex_api_with_mock_transport():
    """API collector should parse organization admin costs response."""
    payload = json.loads((FIXTURES / "codex_admin_costs.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "/organization/costs" in str(request.url)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    toggle = no_file_toggle(enabled=True, auth_mode="api")
    secrets = ProviderSecrets(api_key="sk-admin-test")
    collector = CodexCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_used == 8.5
