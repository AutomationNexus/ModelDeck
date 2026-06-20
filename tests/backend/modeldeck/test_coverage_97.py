"""Tests targeting 97% total coverage without skips or coverage omissions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
import pytest

from modeldeck.collectors.base import default_metrics
from modeldeck.collectors.claude import ClaudeCollector
from modeldeck.collectors.claude_parser import parse_claude_usage
from modeldeck.collectors.codex import CodexCollector
from modeldeck.collectors.cursor import CursorCollector
from modeldeck.collectors.cursor_personal_parser import parse_cursor_usage_summary
from modeldeck.collectors.mock import MockCollector
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.core.logging import setup_logging
from modeldeck.mqtt.publisher import format_metric_value
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from tests.conftest import no_file_toggle


def test_default_metrics():
    """default_metrics should return all metric kinds."""
    assert len(default_metrics()) == len(MetricKind)


def test_setup_logging_json_format():
    """JSON logging format branch should configure handlers."""
    setup_logging("INFO", json_format=True)
    root = logging.getLogger()
    assert root.handlers
    setup_logging("INFO", json_format=False)


def test_claude_parser_computes_percent_from_used_and_limit():
    """Parser should derive usage_percent when omitted."""
    snap = parse_claude_usage({"usage_used": 25, "usage_limit": 100})
    assert snap.usage_percent == 25.0


def test_claude_supported_metrics_and_account_label():
    """Claude collector metadata helpers."""
    collector = ClaudeCollector(
        AppConfig(), ProviderSecrets(), no_file_toggle(account_label="work")
    )
    assert collector.supported_metrics()
    assert "work" in collector._display_name()


@pytest.mark.asyncio
async def test_claude_rate_limited_and_parse_error():
    """Claude HTTP 429 and transport errors."""
    toggle = no_file_toggle(auth_mode="cookie")
    secrets = ProviderSecrets(session_token="t", org_id="org-1")
    collector = ClaudeCollector(AppConfig(), secrets, toggle)

    async def rate_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = httpx.AsyncClient(transport=httpx.MockTransport(rate_handler))
    snap = await ClaudeCollector(AppConfig(), secrets, toggle, client=client).collect()
    assert snap.status == CollectorStatus.RATE_LIMITED

    async def boom_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client2 = httpx.AsyncClient(transport=httpx.MockTransport(boom_handler))
    snap2 = await ClaudeCollector(AppConfig(), secrets, toggle, client=client2).collect()
    assert snap2.status == CollectorStatus.PARSE_ERROR
    assert collector.supported_metrics()


@pytest.mark.asyncio
async def test_claude_live_client_branch(monkeypatch):
    """Claude without injected client uses httpx.AsyncClient."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "five_hour": {"utilization": 10.0, "resets_at": "2026-06-24T12:00:00+00:00"},
                "seven_day": {"utilization": 5.0, "resets_at": "2026-07-01T00:00:00+00:00"},
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.claude_cookie.httpx.AsyncClient", lambda **k: FakeClient()
    )
    toggle = no_file_toggle(auth_mode="cookie")
    secrets = ProviderSecrets(session_token="t", org_id="org-1")
    snap = await ClaudeCollector(AppConfig(), secrets, toggle).collect()
    assert snap.status == CollectorStatus.OK


def test_codex_supported_metrics_and_account_label():
    """Codex collector metadata helpers."""
    collector = CodexCollector(AppConfig(), ProviderSecrets(), no_file_toggle(account_label="api"))
    assert collector.supported_metrics()
    assert "api" in collector._display_name()


@pytest.mark.asyncio
async def test_codex_unavailable_and_parse_error():
    """Codex 503 and transport errors."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    toggle = no_file_toggle(auth_mode="api")
    snap = await CodexCollector(
        AppConfig(), ProviderSecrets(api_key="k"), toggle, client=client
    ).collect()
    assert snap.status == CollectorStatus.UNAVAILABLE

    async def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client2 = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    snap2 = await CodexCollector(
        AppConfig(), ProviderSecrets(api_key="k"), toggle, client=client2
    ).collect()
    assert snap2.status == CollectorStatus.PARSE_ERROR


def test_cursor_supported_metrics_and_account_label():
    """Cursor collector metadata helpers."""
    collector = CursorCollector(
        AppConfig(), ProviderSecrets(), no_file_toggle(account_label="desk")
    )
    assert collector.supported_metrics()
    assert "desk" in collector._display_name()


@pytest.mark.asyncio
async def test_cursor_auth_unavailable_parse_and_alt_fields():
    """Cursor error paths and alternate payload keys."""
    token = ProviderSecrets(session_token="t")
    toggle = no_file_toggle(auth_mode="personal")

    async def auth_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(transport=httpx.MockTransport(auth_handler))
    auth_snap = await CursorCollector(AppConfig(), token, toggle, client=client).collect()
    assert auth_snap.status == CollectorStatus.AUTH_ERROR

    async def unavail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client2 = httpx.AsyncClient(transport=httpx.MockTransport(unavail_handler))
    unavail_snap = await CursorCollector(AppConfig(), token, toggle, client=client2).collect()
    assert unavail_snap.status == CollectorStatus.UNAVAILABLE

    snap = parse_cursor_usage_summary({"usage_percent": 25.0, "planName": "Team"})
    assert snap.usage_percent == 25.0

    async def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client3 = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    parse_snap = await CursorCollector(AppConfig(), token, toggle, client=client3).collect()
    assert parse_snap.status == CollectorStatus.PARSE_ERROR


def test_mock_supported_metrics():
    """Mock collector should list all metrics."""
    assert MockCollector(AppConfig(), ProviderSecrets()).supported_metrics()


def test_format_metric_credits_and_last_success_fallback():
    """Credits and failed last_success branches."""
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 17, tzinfo=UTC),
        status=CollectorStatus.AUTH_ERROR,
        credits_remaining=3.5,
    )
    assert format_metric_value(snap, MetricKind.CREDITS) == "3.5"
    assert format_metric_value(snap, MetricKind.LAST_SUCCESS, last_success=None) is None
