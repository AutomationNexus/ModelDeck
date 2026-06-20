"""Dashboard example entity IDs must match MQTT discovery."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modeldeck.mqtt.discovery import homeassistant_entity_id
from modeldeck.schemas.snapshot import MetricKind

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples" / "home-assistant"
ENTITY_RE = re.compile(r"entity:\s*(sensor\.\S+)")

PROVIDER_METRICS: dict[str, set[MetricKind]] = {
    "codex": {
        MetricKind.USAGE_PERCENT,
        MetricKind.USAGE_WEEKLY_PERCENT,
        MetricKind.RESET_AT,
        MetricKind.RESET_WEEKLY_AT,
        MetricKind.PLAN,
        MetricKind.STATUS,
        MetricKind.LAST_SUCCESS,
    },
    "claude": {
        MetricKind.USAGE_PERCENT,
        MetricKind.USAGE_WEEKLY_PERCENT,
        MetricKind.RESET_AT,
        MetricKind.RESET_WEEKLY_AT,
        MetricKind.USAGE_USED,
        MetricKind.USAGE_LIMIT,
        MetricKind.CREDITS,
        MetricKind.PLAN,
        MetricKind.STATUS,
        MetricKind.LAST_SUCCESS,
    },
    "cursor": {
        MetricKind.USAGE_PERCENT,
        MetricKind.USAGE_AUTO_PERCENT,
        MetricKind.USAGE_API_PERCENT,
        MetricKind.USAGE_USED,
        MetricKind.USAGE_LIMIT,
        MetricKind.RESET_AT,
        MetricKind.PLAN,
        MetricKind.STATUS,
        MetricKind.LAST_SUCCESS,
    },
    "mock": {
        MetricKind.USAGE_PERCENT,
        MetricKind.RESET_AT,
        MetricKind.PLAN,
        MetricKind.STATUS,
    },
}


def _expected_entity_ids() -> set[str]:
    ids: set[str] = set()
    for provider, metrics in PROVIDER_METRICS.items():
        for metric in metrics:
            ids.add(homeassistant_entity_id(provider, metric))
    return ids


@pytest.mark.parametrize(
    "yaml_name",
    [
        "overview-compact.yaml",
        "modeldeck-tab.yaml",
        "usage-stack.yaml",
    ],
)
def test_dashboard_examples_use_canonical_entity_ids(yaml_name: str):
    """Example dashboards should reference MQTT discovery entity IDs."""
    text = (EXAMPLES_DIR / yaml_name).read_text(encoding="utf-8")
    referenced = set(ENTITY_RE.findall(text))
    expected = _expected_entity_ids()
    unknown = referenced - expected
    assert not unknown, f"{yaml_name} references unknown entities: {sorted(unknown)}"
    short_slug = {
        e
        for e in referenced
        if e.startswith(("sensor.codex_", "sensor.claude_", "sensor.cursor_", "sensor.mock_"))
    }
    assert not short_slug, f"{yaml_name} uses deprecated short-slug IDs: {sorted(short_slug)}"


def test_homeassistant_entity_ids_use_modeldeck_prefix():
    """Entity IDs must match homeassistant/sensor/modeldeck_{provider}_{metric}/config."""
    assert homeassistant_entity_id("codex", MetricKind.USAGE_PERCENT) == (
        "sensor.modeldeck_codex_usage_percent"
    )
    assert homeassistant_entity_id("codex", MetricKind.STATUS) == "sensor.modeldeck_codex_status"
    assert homeassistant_entity_id("cursor", MetricKind.USAGE_AUTO_PERCENT) == (
        "sensor.modeldeck_cursor_usage_auto_percent"
    )
