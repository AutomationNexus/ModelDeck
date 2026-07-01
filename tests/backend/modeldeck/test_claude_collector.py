"""Claude collector and parser tests."""

import json
from pathlib import Path

import httpx
import pytest

from modeldeck.collectors.claude import ClaudeCollector
from modeldeck.collectors.claude_console_parser import parse_claude_console_usage
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.schemas.snapshot import CollectorStatus
from tests.conftest import no_file_account

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
    account = no_file_account(enabled=True, auth_mode="cookie")
    collector = ClaudeCollector(AppConfig(), ProviderSecrets(), account)
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
    account = no_file_account(enabled=True, auth_mode="cookie")
    secrets = ProviderSecrets(session_token="session-abc", org_id="org-123")
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
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
    account = no_file_account(enabled=True, auth_mode="oauth")
    secrets = ProviderSecrets(access_token="oauth-token")
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 35.0


@pytest.mark.asyncio
async def test_claude_cookie_sends_browser_headers():
    """Cookie collector should send browser-like headers to dodge 403s."""
    payload = json.loads(
        (FIXTURES / "claude_console_usage.json").read_text(encoding="utf-8")
    )
    seen: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    account = no_file_account(enabled=True, auth_mode="cookie")
    secrets = ProviderSecrets(session_token="session-abc", org_id="org-123")
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    assert seen.get("origin") == "https://claude.ai"
    assert seen.get("referer") == "https://claude.ai/"
    assert seen.get("accept") == "application/json"
    assert "Mozilla/5.0" in seen.get("user-agent", "")


@pytest.mark.asyncio
async def test_claude_cookie_403_sets_hint():
    """A 403 should map to auth_error and include an actionable hint."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    account = no_file_account(enabled=True, auth_mode="cookie")
    secrets = ProviderSecrets(session_token="session-abc", org_id="org-123")
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.AUTH_ERROR
    assert snap.raw_safe is not None
    assert snap.raw_safe.get("http_status") == 403
    assert snap.raw_safe.get("auth_mode") == "cookie"
    assert snap.raw_safe.get("hint") == "cf_clearance_expired_or_docker_ip"


@pytest.mark.asyncio
async def test_claude_cookie_403_presence_flags_both_absent():
    """D2: 403 raw_safe must include cf_clearance_present and device_id_present booleans."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    account = no_file_account(enabled=True, auth_mode="cookie")
    # Neither cf_clearance nor device_id supplied
    secrets = ProviderSecrets(session_token="session-abc", org_id="org-123")
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.AUTH_ERROR
    assert snap.raw_safe is not None
    assert snap.raw_safe.get("cf_clearance_present") is False
    assert snap.raw_safe.get("device_id_present") is False


@pytest.mark.asyncio
async def test_claude_cookie_403_presence_flags_both_present():
    """D2: presence flags should be True when cookies are supplied."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    account = no_file_account(enabled=True, auth_mode="cookie")
    secrets = ProviderSecrets(
        session_token="session-abc",
        org_id="org-123",
        cf_clearance="cf-value",
        device_id="device-value",
    )
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.AUTH_ERROR
    assert snap.raw_safe is not None
    assert snap.raw_safe.get("cf_clearance_present") is True
    assert snap.raw_safe.get("device_id_present") is True


@pytest.mark.asyncio
async def test_claude_collector_snapshot_carries_account_id():
    """Snapshot returned by ClaudeCollector should carry account_id."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    account = no_file_account(id="work", enabled=True, auth_mode="cookie")
    secrets = ProviderSecrets(session_token="session-abc", org_id="org-123")
    collector = ClaudeCollector(AppConfig(), secrets, account, client=client)
    snap = await collector.collect()
    assert snap.account_id == "work"
