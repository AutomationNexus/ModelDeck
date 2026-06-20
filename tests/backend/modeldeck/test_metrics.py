"""Tests for metric-aware MQTT exposure."""

import json
from datetime import UTC, datetime
from pathlib import Path

from modeldeck.collectors.cursor_personal_parser import (
    parse_cursor_period_usage,
    parse_cursor_usage_summary,
)
from modeldeck.collectors.metrics import base_metrics, effective_metrics
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from tests.conftest import publish_item

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_base_metrics_codex_subscription():
    """Codex subscription mode should not include used/limit."""
    metrics = base_metrics("codex", "subscription")
    assert MetricKind.USAGE_USED not in metrics
    assert MetricKind.USAGE_PERCENT in metrics


def test_base_metrics_cursor_personal_includes_dual_pools():
    """Cursor personal mode should include auto and api usage."""
    metrics = base_metrics("cursor", "personal")
    assert MetricKind.USAGE_AUTO_PERCENT in metrics
    assert MetricKind.USAGE_API_PERCENT in metrics
    assert MetricKind.USAGE_WEEKLY_PERCENT not in metrics


def test_effective_metrics_filters_unpopulated():
    """Only populated snapshot fields should be published."""
    snap = ProviderSnapshot(
        provider_id="codex",
        display_name="Codex",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        usage_percent=10.0,
    )
    metrics = effective_metrics(snap, base_metrics("codex", "subscription"))
    assert MetricKind.USAGE_PERCENT in metrics
    assert MetricKind.USAGE_USED not in metrics
    assert MetricKind.PLAN not in metrics


def test_cursor_dual_pool_fixture():
    """Cursor fixtures should parse auto and api percentages."""
    summary = json.loads((FIXTURES / "cursor_usage_summary.json").read_text(encoding="utf-8"))
    snap = parse_cursor_usage_summary(summary)
    assert snap.usage_auto_percent == 52.1
    assert snap.usage_api_percent == 18.3
    period = json.loads((FIXTURES / "cursor_period_usage.json").read_text(encoding="utf-8"))
    snap2 = parse_cursor_period_usage(period)
    assert snap2.usage_auto_percent == 22.0
    assert snap2.plan_name == "Pro"


def test_publish_item_wraps_metrics():
    """Test helper should attach effective metrics."""
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        usage_percent=1.0,
    )
    item = publish_item(snap)
    assert item.snapshot is snap
    assert MetricKind.STATUS in item.metrics
