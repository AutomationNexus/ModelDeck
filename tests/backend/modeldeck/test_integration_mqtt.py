"""Mosquitto integration tests."""

import os

import pytest

from modeldeck.collectors.mock import MockCollector
from modeldeck.config.loader import AppConfig, MqttConfig, ProviderSecrets
from modeldeck.mqtt.client import MqttBridge
from modeldeck.schemas.snapshot import CollectorStatus
from tests.conftest import publish_item


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_to_mosquitto():
    """Publish mock snapshot to a live Mosquitto broker."""
    host = os.environ.get("MQTT_TEST_HOST", "localhost")
    port = int(os.environ.get("MQTT_TEST_PORT", "1883"))
    mqtt = MqttConfig(host=host, port=port, client_id="modeldeck-test")
    bridge = MqttBridge(mqtt)
    collector = MockCollector(AppConfig(), ProviderSecrets())
    snap = await collector.collect()
    assert snap.status == CollectorStatus.OK
    await bridge.publish_snapshots([publish_item(snap)], publish_discovery=True)
    assert bridge.connected is True
