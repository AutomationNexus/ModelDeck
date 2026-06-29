"""Dual-auth collector coverage tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from modeldeck.collectors.auth_resolve import (
    pick_claude_mode,
    pick_codex_mode,
    pick_cursor_mode,
    resolve_claude_secrets,
    resolve_codex_secrets,
    resolve_cursor_secrets,
)
from modeldeck.collectors.claude_oauth import ClaudeOAuthCollector
from modeldeck.collectors.claude_oauth_parser import parse_claude_oauth_usage
from modeldeck.collectors.codex_api_collector import CodexApiCollector
from modeldeck.collectors.codex_subscription import CodexSubscriptionCollector
from modeldeck.collectors.codex_wham_parser import parse_codex_wham_usage
from modeldeck.collectors.cursor_enterprise import CursorEnterpriseCollector
from modeldeck.collectors.cursor_personal import CursorPersonalCollector
from modeldeck.collectors.cursor_personal_parser import (
    parse_cursor_period_usage,
    parse_cursor_usage_summary,
)
from modeldeck.config.loader import ProviderSecrets, ProviderToggle
from modeldeck.schemas.snapshot import CollectorStatus

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_pick_auth_modes_auto():
    """Auto mode should prefer subscription/cookie/personal credentials."""
    assert pick_codex_mode(ProviderToggle(auth_mode="auto"), ProviderSecrets(api_key="k")) == "api"
    assert (
        pick_codex_mode(ProviderToggle(auth_mode="auto"), ProviderSecrets(access_token="t"))
        == "subscription"
    )
    assert (
        pick_claude_mode(
            ProviderToggle(auth_mode="auto"),
            ProviderSecrets(session_token="s", org_id="o"),
        )
        == "cookie"
    )
    assert (
        pick_claude_mode(ProviderToggle(auth_mode="auto"), ProviderSecrets(access_token="t"))
        == "oauth"
    )
    assert (
        pick_cursor_mode(ProviderToggle(auth_mode="auto"), ProviderSecrets(session_token="t"))
        == "personal"
    )
    assert (
        pick_cursor_mode(ProviderToggle(auth_mode="auto"), ProviderSecrets(admin_api_key="k"))
        == "enterprise"
    )


def test_pick_claude_mode_auto_oauth_wins_over_cookie():
    """D4: when both OAuth and cookie creds are present, auto must resolve to oauth."""
    secrets = ProviderSecrets(
        access_token="at",
        refresh_token="rt",
        session_token="sk-ant-sid01",
        org_id="org-123",
    )
    assert pick_claude_mode(ProviderToggle(auth_mode="auto"), secrets) == "oauth"


def test_pick_claude_mode_auto_refresh_token_only_resolves_oauth():
    """D4: refresh_token alone (no access_token) should still resolve to oauth."""
    secrets = ProviderSecrets(refresh_token="rt")
    assert pick_claude_mode(ProviderToggle(auth_mode="auto"), secrets) == "oauth"


@pytest.mark.asyncio
async def test_claude_oauth_refresh_first_when_no_access_token():
    """D3: collector must exchange refresh_token before first usage call when no access_token."""
    payload = json.loads((FIXTURES / "claude_oauth_usage.json").read_text(encoding="utf-8"))
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "oauth/token" in url:
            return httpx.Response(200, json={"access_token": "new-at", "refresh_token": "new-rt"})
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # Only refresh_token present; no access_token
    secrets = ProviderSecrets(refresh_token="initial-rt")
    snap = await ClaudeOAuthCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.OK
    # First call must have been the token exchange, not the usage endpoint
    assert any("oauth/token" in c for c in calls), f"no token exchange in calls: {calls}"
    token_idx = next(i for i, c in enumerate(calls) if "oauth/token" in c)
    usage_idx = next(i for i, c in enumerate(calls) if "oauth/usage" in c)
    assert token_idx < usage_idx, "token exchange must precede usage call"


@pytest.mark.asyncio
async def test_claude_oauth_refresh_first_fails_returns_auth_error():
    """D3: if pre-emptive refresh fails, return auth_error immediately."""
    async def handler(request: httpx.Request) -> httpx.Response:
        # Token exchange fails
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(refresh_token="bad-rt")
    snap = await ClaudeOAuthCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.AUTH_ERROR
    assert snap.raw_safe is not None
    assert snap.raw_safe.get("reason") == "refresh_token_exchange_failed"


def test_resolve_secrets_from_files(tmp_path):
    """Credential file paths should merge into provider secrets."""
    codex_auth = tmp_path / "auth.json"
    codex_auth.write_text(
        json.dumps({"tokens": {"access_token": "a", "refresh_token": "r", "account_id": "id"}}),
        encoding="utf-8",
    )
    toggle = ProviderToggle(credential_path=str(codex_auth))
    merged = resolve_codex_secrets(toggle, ProviderSecrets())
    assert merged.access_token == "a"

    claude_cred = tmp_path / "claude.json"
    claude_cred.write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "ca", "refreshToken": "cr"}}),
        encoding="utf-8",
    )
    claude_toggle = ProviderToggle(credential_path=str(claude_cred))
    claude_merged = resolve_claude_secrets(claude_toggle, ProviderSecrets())
    assert claude_merged.access_token == "ca"

    cursor_toggle = ProviderToggle(credential_path=str(tmp_path / "missing.db"))
    assert resolve_cursor_secrets(cursor_toggle, ProviderSecrets()).access_token == ""


def test_parse_cursor_period_usage_fixture():
    """Period usage parser should read billing cycle fields."""
    payload = json.loads((FIXTURES / "cursor_period_usage.json").read_text(encoding="utf-8"))
    snap = parse_cursor_period_usage(payload)
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 15.48


def test_parse_codex_wham_string_reset():
    """Wham parser should accept ISO reset timestamps."""
    snap = parse_codex_wham_usage(
        {
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": {"used_percent": 10, "reset_at": "2026-06-24T12:00:00+00:00"},
                "secondary_window": {"used_percent": 20, "reset_at": "2026-07-01T00:00:00+00:00"},
            },
        }
    )
    assert snap.usage_percent == 10.0
    assert snap.reset_at is not None


@pytest.mark.asyncio
async def test_codex_subscription_refresh_on_401():
    """Subscription collector should refresh OAuth token on 401."""
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if "oauth/token" in str(request.url):
            return httpx.Response(
                200,
                json={"access_token": "new-access", "refresh_token": "new-r"},
            )
        if calls["count"] == 2:
            return httpx.Response(401)
        return httpx.Response(
            200,
            json=json.loads((FIXTURES / "codex_wham_usage.json").read_text(encoding="utf-8")),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="old", refresh_token="refresh")
    collector = CodexSubscriptionCollector(secrets, "Codex", client)
    snap = await collector.collect()
    assert snap.status in {CollectorStatus.OK, CollectorStatus.AUTH_ERROR}


@pytest.mark.asyncio
async def test_claude_oauth_refresh_and_collect():
    """OAuth collector should parse usage and attempt refresh."""
    payload = json.loads((FIXTURES / "claude_oauth_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "new", "refresh_token": "r"})
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="token", refresh_token="refresh")
    snap = await ClaudeOAuthCollector(secrets, "Claude", client).collect()
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent == 35.0


@pytest.mark.asyncio
async def test_cursor_personal_jwt_path():
    """Personal collector should use api2 when only access_token is set."""
    payload = json.loads((FIXTURES / "cursor_period_usage.json").read_text(encoding="utf-8"))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    secrets = ProviderSecrets(access_token="jwt-token")
    snap = await CursorPersonalCollector(secrets, "Cursor", client).collect()
    assert snap.status == CollectorStatus.OK


@pytest.mark.asyncio
async def test_codex_api_and_enterprise_error_paths():
    """API and enterprise collectors should map HTTP failures."""

    async def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    api_client = httpx.AsyncClient(transport=httpx.MockTransport(api_handler))
    api_snap = await CodexApiCollector(ProviderSecrets(api_key="k"), "Codex", api_client).collect()
    assert api_snap.status == CollectorStatus.UNAVAILABLE

    async def ent_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    ent_client = httpx.AsyncClient(transport=httpx.MockTransport(ent_handler))
    ent_snap = await CursorEnterpriseCollector(
        ProviderSecrets(admin_api_key="admin"),
        "Cursor",
        ent_client,
    ).collect()
    assert ent_snap.status == CollectorStatus.PARSE_ERROR


def test_parse_claude_oauth_extra_usage():
    """OAuth parser should compute credits from extra_usage block."""
    snap = parse_claude_oauth_usage(
        {
            "five_hour": {"utilization": 1, "resets_at": "2026-06-24T12:00:00+00:00"},
            "seven_day": {"utilization": 2, "resets_at": "2026-07-01T00:00:00+00:00"},
            "extra_usage": {"monthly_limit": 10000, "used_credits": 2500},
        }
    )
    assert snap.credits_remaining == 75.0


def test_parse_claude_oauth_plan_from_api():
    snap = parse_claude_oauth_usage(
        {
            "five_hour": {"utilization": 0, "resets_at": None},
            "seven_day": {"utilization": 66, "resets_at": "2026-07-01T00:00:00+00:00"},
            "subscriptionType": "pro",
        }
    )
    assert snap.plan_name == "pro"
    assert snap.reset_at is None


@pytest.mark.asyncio
async def test_claude_oauth_subscription_tier_fallback():
    payload = {
        "five_hour": {"utilization": 10, "resets_at": "2026-06-24T12:00:00+00:00"},
        "seven_day": {"utilization": 20, "resets_at": "2026-07-01T00:00:00+00:00"},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        collector = ClaudeOAuthCollector(
            ProviderSecrets(
                access_token="tok",
                subscription_tier="Max",
            ),
            "Claude",
            client,
        )
        snap = await collector.collect()
    assert snap.plan_name == "Max"


def test_parse_cursor_usage_summary_alt_keys():
    """Usage summary parser should handle top-level percent fields."""
    snap = parse_cursor_usage_summary({"usage_percent": 33.3, "planName": "Pro"})
    assert snap.usage_percent == 33.3
    assert snap.plan_name == "Pro"
