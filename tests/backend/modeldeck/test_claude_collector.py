"""Claude collector and parser tests."""

import json
from pathlib import Path

import httpx
import pytest

from modeldeck.collectors.claude import ClaudeCollector
from modeldeck.collectors.claude_console_parser import parse_claude_console_usage
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.schemas.snapshot import CollectorStatus
from tests.conftest import no_file_toggle

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_parse_claude_console_fixture():
    """Parser should read Claude console fixture."""
    payload = json.loads((FIXTURES / "claude_console_usage.json").read_text(encoding="utf-8"))
    snap = parse_claude_console_usage(payload)
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 42.5
    assert snap.usage_percent_weekly == 18.0
    assert snap.usage_used == 5.0
    assert snap.usage_limit == 100.0
    assert snap.credits_remaining == 95.0
    assert snap.plan_name == "Pro"


@pytest.mark.asyncio
async def test_claude_collector_missing_cookie_credentials():
    """Missing session token should yield auth_error."""
    toggle = no_file_toggle(enabled=True, auth_mode="cookie")
    collector = ClaudeCollector(AppConfig(), ProviderSecrets(), toggle)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_claude_cookie_collector_with_mock_transport():
    """Cookie collector should parse mocked Claude console response."""
    payload = json.loads((FIXTURES / "claude_console_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "/organizations/org-123/usage" in str(request.url)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    toggle = no_file_toggle(enabled=True, auth_mode="cookie")
    secrets = ProviderSecrets(session_token="session-abc", org_id="org-123")
    collector = ClaudeCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 42.5


@pytest.mark.asyncio
async def test_claude_oauth_collector_with_mock_transport():
    """OAuth collector should parse mocked Claude OAuth response."""
    payload = json.loads((FIXTURES / "claude_oauth_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    toggle = no_file_toggle(enabled=True, auth_mode="oauth")
    secrets = ProviderSecrets(access_token="oauth-token")
    collector = ClaudeCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 35.0
