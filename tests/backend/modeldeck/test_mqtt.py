"""MQTT discovery and publisher tests."""

import json
from datetime import UTC, datetime

import pytest

from modeldeck.config.loader import MqttConfig
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.mqtt.discovery import (
    build_discovery_payload,
    discovery_topic,
    homeassistant_entity_id,
    short_slug_discovery_topic,
    state_topic,
)
from modeldeck.mqtt.publisher import format_metric_value
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot


def _snapshot() -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        status=CollectorStatus.OK,
        usage_percent=55.0,
        usage_used=1100.0,
        usage_limit=2000.0,
        plan_name="Pro",
    )


def test_discovery_topic_and_payload():
    """Discovery topics and payloads should follow HA conventions."""
    mqtt = MqttConfig()
    snap = _snapshot()
    topic = discovery_topic(mqtt, "mock", "default", MetricKind.USAGE_PERCENT)
    assert topic == "homeassistant/sensor/modeldeck_mock_default_usage_percent/config"
    payload = build_discovery_payload(mqtt, snap, MetricKind.USAGE_PERCENT)
    assert payload["unique_id"] == "modeldeck_mock_default_usage_percent"
    assert payload["object_id"] == "modeldeck_mock_default_usage_percent"
    assert payload["default_entity_id"] == "sensor.modeldeck_mock_default_usage_percent"
    assert payload["state_topic"] == state_topic(mqtt, "mock", "default", MetricKind.USAGE_PERCENT)
    assert payload["unit_of_measurement"] == "%"
    assert json.loads(json.dumps(payload))["device"]["identifiers"] == ["modeldeck_mock_default"]


def test_format_auto_api_percent():
    """Auto and API percent metrics should round to one decimal."""
    snap = _snapshot()
    snap.usage_auto_percent = 52.14
    snap.usage_api_percent = 18.36
    assert format_metric_value(snap, MetricKind.USAGE_AUTO_PERCENT) == "52.1"
    assert format_metric_value(snap, MetricKind.USAGE_API_PERCENT) == "18.4"


def test_discovery_friendly_name_no_duplicate():
    """Discovery name should use suffix only (no duplicated provider name)."""
    mqtt = MqttConfig()
    snap = _snapshot()
    snap.display_name = "Claude"
    payload = build_discovery_payload(mqtt, snap, MetricKind.USAGE_PERCENT)
    assert payload["name"] == "Usage"


def test_short_slug_discovery_topic_retired():
    """v0.1.0–v0.1.2 short-slug topics differ from stable modeldeck_* entity IDs."""
    mqtt = MqttConfig()
    assert discovery_topic(mqtt, "codex", "default", MetricKind.USAGE_PERCENT) == (
        "homeassistant/sensor/modeldeck_codex_default_usage_percent/config"
    )
    assert short_slug_discovery_topic(mqtt, "codex", MetricKind.USAGE_PERCENT) == (
        "homeassistant/sensor/codex_usage/config"
    )
    assert discovery_topic(mqtt, "codex", "default", MetricKind.STATUS) == (
        "homeassistant/sensor/modeldeck_codex_default_status/config"
    )
    assert homeassistant_entity_id("codex", "default", MetricKind.STATUS) == (
        "sensor.modeldeck_codex_default_status"
    )


@pytest.mark.asyncio
async def test_discovery_retires_short_slug_topics(monkeypatch):
    """First discovery refresh should clear v0.1.0–v0.1.2 short-slug configs."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, payload))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap = _snapshot()
    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.USAGE_PERCENT])],
        publish_discovery=True,
    )
    expected = {short_slug_discovery_topic(MqttConfig(), "mock", metric) for metric in MetricKind}
    short_retired = {t for t, p in published if p == "" and t in expected}
    assert short_retired == expected


@pytest.mark.asyncio
async def test_discovery_retires_unsupported_metrics(monkeypatch):
    """Discovery refresh should clear stale homeassistant configs."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, payload))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap = _snapshot()
    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.USAGE_PERCENT, MetricKind.STATUS])],
        publish_discovery=True,
    )
    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])],
        publish_discovery=True,
    )
    retired = [t for t, p in published if p == "" and "homeassistant" in t]
    assert retired


def test_format_metric_values():
    """Publisher should format each metric type."""
    snap = _snapshot()
    snap.usage_percent_weekly = 22.0
    snap.reset_at_weekly = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    assert format_metric_value(snap, MetricKind.USAGE_PERCENT) == "55.0"
    assert format_metric_value(snap, MetricKind.USAGE_WEEKLY_PERCENT) == "22.0"
    assert format_metric_value(snap, MetricKind.RESET_WEEKLY_AT) == "2026-06-24T12:00:00+00:00"
    assert format_metric_value(snap, MetricKind.PLAN) == "Pro"
    assert format_metric_value(snap, MetricKind.STATUS) == "ok"
    degraded = _snapshot()
    degraded.status = CollectorStatus.AUTH_ERROR
    assert format_metric_value(degraded, MetricKind.LAST_SUCCESS, last_success=snap.collected_at)
