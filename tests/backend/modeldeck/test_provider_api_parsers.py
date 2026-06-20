"""Tests for official provider Admin API response parsers."""

import json
from pathlib import Path

from modeldeck.collectors.claude_console_parser import parse_claude_console_usage
from modeldeck.collectors.claude_oauth_parser import parse_claude_oauth_usage
from modeldeck.collectors.codex_api import parse_codex_admin_costs, parse_codex_billing_usage
from modeldeck.collectors.cursor_enterprise_parser import parse_cursor_enterprise_spend
from modeldeck.schemas.snapshot import CollectorStatus

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_parse_claude_console_extra_usage():
    """Claude console should map extra_usage to used/limit/credits."""
    payload = json.loads((FIXTURES / "claude_console_usage.json").read_text(encoding="utf-8"))
    snap = parse_claude_console_usage(payload)
    assert snap.usage_used == 5.0
    assert snap.usage_limit == 100.0
    assert snap.credits_remaining == 95.0


def test_parse_claude_oauth_no_extra_usage():
    """OAuth without extra_usage should omit used/limit."""
    payload = json.loads((FIXTURES / "claude_oauth_usage.json").read_text(encoding="utf-8"))
    snap = parse_claude_oauth_usage(payload)
    assert snap.usage_used is None
    assert snap.usage_limit is None
    assert snap.credits_remaining is None


def test_parse_codex_admin_costs_fixture():
    """Admin costs parser should sum USD amounts from fixture."""
    payload = json.loads((FIXTURES / "codex_admin_costs.json").read_text(encoding="utf-8"))
    snap = parse_codex_admin_costs(payload)
    assert snap.status == CollectorStatus.OK
    assert snap.usage_used == 8.5
    assert snap.plan_name == "OpenAI Platform"


def test_parse_codex_billing_usage_legacy():
    """Legacy billing parser should still compute percent from limits."""
    snap = parse_codex_billing_usage({"usage_used": 5, "usage_limit": 10})
    assert snap.usage_percent == 50.0
    assert snap.usage_used == 5.0


def test_parse_cursor_enterprise_spend_fixture():
    """Enterprise spend parser should aggregate team member totals."""
    payload = json.loads((FIXTURES / "cursor_enterprise_usage.json").read_text(encoding="utf-8"))
    snap = parse_cursor_enterprise_spend(payload)
    assert snap.status == CollectorStatus.OK
    assert snap.usage_used == 32.5
    assert snap.usage_limit == 500.0
    assert snap.usage_percent == 6.5
    assert snap.reset_at is not None
