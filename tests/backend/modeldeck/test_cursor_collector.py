"""Cursor collector tests."""

import json
from pathlib import Path

import httpx
import pytest

from modeldeck.collectors.cursor import CursorCollector
from modeldeck.collectors.cursor_personal_parser import parse_cursor_usage_summary
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.schemas.snapshot import CollectorStatus
from tests.conftest import no_file_toggle

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_parse_cursor_usage_summary_fixture():
    """Parser should read Cursor usage-summary fixture."""
    payload = json.loads((FIXTURES / "cursor_usage_summary.json").read_text(encoding="utf-8"))
    snap = parse_cursor_usage_summary(payload)
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 46.4
    assert snap.usage_auto_percent == 52.1
    assert snap.usage_api_percent == 18.3
    assert snap.plan_name == "Ultra"


@pytest.mark.asyncio
async def test_cursor_collector_missing_token():
    """Missing session token should yield auth_error."""
    toggle = no_file_toggle(enabled=True, auth_mode="personal")
    collector = CursorCollector(AppConfig(), ProviderSecrets(), toggle)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_cursor_personal_with_mock_transport():
    """Personal collector should parse usage-summary response."""
    payload = json.loads((FIXTURES / "cursor_usage_summary.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    toggle = no_file_toggle(enabled=True, auth_mode="personal")
    secrets = ProviderSecrets(session_token="cursor-cookie-token")
    collector = CursorCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 46.4


@pytest.mark.asyncio
async def test_cursor_enterprise_with_mock_transport():
    """Enterprise collector should parse Admin API spend response."""
    payload = json.loads((FIXTURES / "cursor_enterprise_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/teams/spend" in str(request.url)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    toggle = no_file_toggle(enabled=True, auth_mode="enterprise")
    secrets = ProviderSecrets(admin_api_key="crsr_admin_key")
    collector = CursorCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_used == 32.5
    assert snap.usage_limit == 500.0
    assert snap.usage_percent == 6.5


@pytest.mark.asyncio
async def test_cursor_collector_rate_limited():
    """429 responses should map to rate_limited."""
    toggle = no_file_toggle(enabled=True, auth_mode="personal")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    secrets = ProviderSecrets(session_token="cursor-token")
    collector = CursorCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.RATE_LIMITED
