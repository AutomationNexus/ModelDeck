"""MQTT discovery identity tests for multi-account format (Workstream B)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from modeldeck.config.loader import MqttConfig
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.mqtt.discovery import (
    build_discovery_payload,
    discovery_topic,
    homeassistant_entity_id,
    legacy_single_account_discovery_topic,
    metric_unique_id,
    short_slug_discovery_topic,
    state_topic,
)
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot


def _snapshot(provider_id: str = "claude", account_id: str = "work") -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="Claude",
        collected_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        status=CollectorStatus.OK,
        account_id=account_id,
        account_label="Work",
        usage_percent=42.0,
    )


# ---------------------------------------------------------------------------
# Identity functions
# ---------------------------------------------------------------------------


def test_metric_unique_id():
    """unique_id includes provider and account slug."""
    assert (
        metric_unique_id("claude", "work", MetricKind.STATUS)
        == "modeldeck_claude_work_status"
    )
    assert (
        metric_unique_id("codex", "default", MetricKind.USAGE_PERCENT)
        == "modeldeck_codex_default_usage_percent"
    )


def test_homeassistant_entity_id():
    """Entity ID includes account_id between provider and metric."""
    assert (
        homeassistant_entity_id("claude", "work", MetricKind.STATUS)
        == "sensor.modeldeck_claude_work_status"
    )
    assert (
        homeassistant_entity_id("codex", "default", MetricKind.USAGE_PERCENT)
        == "sensor.modeldeck_codex_default_usage_percent"
    )
    assert (
        homeassistant_entity_id("cursor", "personal", MetricKind.USAGE_AUTO_PERCENT)
        == "sensor.modeldeck_cursor_personal_usage_auto_percent"
    )


def test_state_topic_includes_account():
    """State topic path includes account_id segment."""
    mqtt = MqttConfig()
    topic = state_topic(mqtt, "claude", "work", MetricKind.USAGE_PERCENT)
    assert topic == "modeldeck/claude/work/usage_percent/state"


def test_discovery_topic_includes_account():
    """Discovery config topic includes account_id in object_id."""
    mqtt = MqttConfig()
    topic = discovery_topic(mqtt, "claude", "work", MetricKind.STATUS)
    assert topic == "homeassistant/sensor/modeldeck_claude_work_status/config"


# ---------------------------------------------------------------------------
# build_discovery_payload
# ---------------------------------------------------------------------------


def test_build_discovery_payload_device_identifiers():
    """Device identifiers include provider_id and account_id."""
    mqtt = MqttConfig()
    snap = _snapshot("claude", "work")
    payload = build_discovery_payload(mqtt, snap, MetricKind.STATUS)
    assert payload["device"]["identifiers"] == ["modeldeck_claude_work"]


def test_build_discovery_payload_unique_id_and_object_id():
    """unique_id and object_id use account-aware format."""
    mqtt = MqttConfig()
    snap = _snapshot("claude", "work")
    payload = build_discovery_payload(mqtt, snap, MetricKind.STATUS)
    assert payload["unique_id"] == "modeldeck_claude_work_status"
    assert payload["object_id"] == "modeldeck_claude_work_status"
    assert payload["default_entity_id"] == "sensor.modeldeck_claude_work_status"


def test_build_discovery_payload_state_topic():
    """State topic in payload uses account_id."""
    mqtt = MqttConfig()
    snap = _snapshot("claude", "work")
    payload = build_discovery_payload(mqtt, snap, MetricKind.USAGE_PERCENT)
    assert payload["state_topic"] == "modeldeck/claude/work/usage_percent/state"


def test_build_discovery_payload_device_name_from_account_label():
    """Device name uses account_label when present."""
    mqtt = MqttConfig()
    snap = _snapshot("claude", "work")
    snap.account_label = "Work Account"
    payload = build_discovery_payload(mqtt, snap, MetricKind.STATUS)
    assert payload["device"]["name"] == "Work Account"


def test_build_discovery_payload_device_name_falls_back_to_display_name():
    """Device name falls back to display_name when account_label is empty."""
    mqtt = MqttConfig()
    snap = _snapshot("claude", "default")
    snap.account_label = ""
    payload = build_discovery_payload(mqtt, snap, MetricKind.STATUS)
    assert payload["device"]["name"] == snap.display_name


# ---------------------------------------------------------------------------
# Legacy retirement helpers
# ---------------------------------------------------------------------------


def test_legacy_single_account_discovery_topic_format():
    """Legacy topic uses old two-part format (no account_id)."""
    mqtt = MqttConfig()
    topic = legacy_single_account_discovery_topic(mqtt, "claude", MetricKind.STATUS)
    assert topic == "homeassistant/sensor/modeldeck_claude_status/config"
    topic2 = legacy_single_account_discovery_topic(mqtt, "codex", MetricKind.USAGE_PERCENT)
    assert topic2 == "homeassistant/sensor/modeldeck_codex_usage_percent/config"


def test_short_slug_topic_unchanged():
    """Short-slug topics should still use the old pre-v0.1.3 format."""
    mqtt = MqttConfig()
    assert short_slug_discovery_topic(mqtt, "codex", MetricKind.USAGE_PERCENT) == (
        "homeassistant/sensor/codex_usage/config"
    )


# ---------------------------------------------------------------------------
# MqttBridge — account-keyed state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_keys_discovery_by_account(monkeypatch):
    """Bridge should track published metrics per (provider_id, account_id) pair."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, str(payload)))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap_work = _snapshot("claude", "work")
    snap_personal = _snapshot("claude", "personal")
    snap_personal.account_label = "Personal"

    await bridge.publish_snapshots(
        [
            SnapshotPublish(snapshot=snap_work, metrics=[MetricKind.STATUS]),
            SnapshotPublish(snapshot=snap_personal, metrics=[MetricKind.STATUS]),
        ],
        publish_discovery=True,
    )

    # Both account discovery topics should have been published
    work_disc = "homeassistant/sensor/modeldeck_claude_work_status/config"
    personal_disc = "homeassistant/sensor/modeldeck_claude_personal_status/config"
    topics = [t for t, _ in published]
    assert work_disc in topics
    assert personal_disc in topics


@pytest.mark.asyncio
async def test_legacy_single_account_topics_retired_once(monkeypatch):
    """Bridge should retire legacy (no-account_id) discovery topics once per provider."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, str(payload)))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap = _snapshot("claude", "default")

    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])],
        publish_discovery=True,
    )

    # Legacy topics should be in the retired (empty payload) list
    legacy_topics = {
        legacy_single_account_discovery_topic(MqttConfig(), "claude", metric)
        for metric in MetricKind
    }
    retired = {t for t, p in published if p == "" and t in legacy_topics}
    assert retired == legacy_topics

    before_count = len(published)
    # Second publish should NOT re-retire the same set
    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])],
        publish_discovery=True,
    )
    new_legacy_retirements = [
        t
        for t, p in published[before_count:]
        if p == "" and t in legacy_topics
    ]
    assert not new_legacy_retirements


@pytest.mark.asyncio
async def test_retire_account_publishes_empty_payloads(monkeypatch):
    """retire_account should clear all metric topics for the account."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, str(payload)))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    # Pre-connect so _session() uses the existing client
    await bridge.connect()
    await bridge.retire_account("claude", "work")

    empty_payloads = [t for t, p in published if p == ""]
    assert any("claude/work" in t for t in empty_payloads)
    assert any("modeldeck_claude_work" in t for t in empty_payloads)
