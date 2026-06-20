"""Tests for resilient poll loop and persistent MQTT."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import aiomqtt
import pytest

from modeldeck.collectors.mock import MockCollector
from modeldeck.config.loader import AppConfig, MqttConfig, ProviderSecrets
from modeldeck.core.exceptions import MqttError
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from modeldeck.service.runner import run_service
from modeldeck.service.scheduler import CollectionRunner
from modeldeck.service.state_cache import StateCache


@pytest.mark.asyncio
async def test_run_loop_continues_after_mqtt_error(tmp_path):
    """A failed MQTT publish must not stop subsequent poll cycles."""
    mqtt = MqttBridge(MqttConfig())
    calls = 0

    async def flaky_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise MqttError("broker unavailable")

    mqtt.publish_snapshots = AsyncMock(side_effect=flaky_publish)
    runner = CollectionRunner(
        collectors=[MockCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=StateCache(tmp_path / "state.json"),
    )
    stop = asyncio.Event()

    async def stop_soon():
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(runner.run_loop(0.01, stop), stop_soon())
    assert calls >= 2


@pytest.mark.asyncio
async def test_mqtt_bridge_connect_disconnect(monkeypatch):
    """Persistent connect/disconnect should manage client lifecycle."""
    closed = False

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            nonlocal closed
            closed = True
            return False

        async def publish(self, *args, **kwargs):
            return None

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    await bridge.connect()
    assert bridge.connected is True
    await bridge.disconnect()
    assert bridge.connected is False
    assert closed is True


@pytest.mark.asyncio
async def test_mqtt_bridge_drop_connection_on_publish_error(monkeypatch):
    """Publish failures should reset the persistent session."""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, *args, **kwargs):
            raise aiomqtt.MqttError("boom")

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    item = SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])
    with pytest.raises(MqttError):
        await bridge.publish_snapshots([item])
    assert bridge._client is None


@pytest.mark.asyncio
async def test_mqtt_bridge_reuses_persistent_session(monkeypatch):
    """Service mode should reuse one MQTT client across publishes."""
    entered = 0
    published: list[str] = []

    class FakeClient:
        async def __aenter__(self):
            nonlocal entered
            entered += 1
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append(topic)

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        usage_percent=1.0,
    )
    item = SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])
    await bridge.publish_snapshots([item])
    await bridge.publish_snapshots([item])
    await bridge.disconnect()
    assert entered == 1
    assert published


@pytest.mark.asyncio
async def test_run_service_supervisor_stops_on_poll_crash(tmp_config_dir, monkeypatch):
    """Unexpected poll-loop exit should stop the service."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")

    monkeypatch.setattr("modeldeck.service.runner.MqttBridge.connect", AsyncMock())
    monkeypatch.setattr("modeldeck.service.runner.MqttBridge.disconnect", AsyncMock())
    monkeypatch.setattr("modeldeck.service.runner.MqttBridge.set_offline", AsyncMock())
    monkeypatch.setattr(
        "modeldeck.service.runner.CollectionRunner.run_loop",
        AsyncMock(side_effect=RuntimeError("poll loop died")),
    )

    await run_service()


@pytest.mark.asyncio
async def test_run_service_logs_initial_mqtt_failure(tmp_config_dir, monkeypatch):
    """Service should start even when the first MQTT connect fails."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")

    monkeypatch.setattr(
        "modeldeck.service.runner.MqttBridge.connect",
        AsyncMock(side_effect=MqttError("down")),
    )
    monkeypatch.setattr(
        "modeldeck.service.runner.MqttBridge.disconnect",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "modeldeck.service.runner.MqttBridge.set_offline",
        AsyncMock(),
    )

    async def stop_immediately(self, interval, stop_event):
        stop_event.set()

    monkeypatch.setattr(
        "modeldeck.service.runner.CollectionRunner.run_loop",
        stop_immediately,
    )

    await run_service()


@pytest.mark.asyncio
async def test_mqtt_connect_failure_raises(monkeypatch):
    """connect() should surface broker errors."""

    class BoomClient:
        async def __aenter__(self):
            raise aiomqtt.MqttError("nope")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: BoomClient())
    bridge = MqttBridge(MqttConfig())
    with pytest.raises(MqttError):
        await bridge.connect()


@pytest.mark.asyncio
async def test_run_loop_logs_generic_cycle_failure(tmp_path):
    """Unexpected collector failures should not stop the poll loop."""
    mqtt = MqttBridge(MqttConfig())
    mqtt.publish_snapshots = AsyncMock()

    class BoomCollector(MockCollector):
        async def collect(self):
            raise RuntimeError("boom")

    runner = CollectionRunner(
        collectors=[BoomCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=StateCache(tmp_path / "state.json"),
    )
    stop = asyncio.Event()

    async def stop_soon():
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(runner.run_loop(0.01, stop), stop_soon())
    mqtt.publish_snapshots.assert_not_called()


@pytest.mark.asyncio
async def test_run_service_warns_when_no_collectors(tmp_config_dir, monkeypatch):
    """Service should idle when no providers are enabled."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: false\n")

    monkeypatch.setattr("modeldeck.service.runner.MqttBridge.connect", AsyncMock())
    monkeypatch.setattr("modeldeck.service.runner.MqttBridge.disconnect", AsyncMock())
    monkeypatch.setattr("modeldeck.service.runner.MqttBridge.set_offline", AsyncMock())

    async def stop_immediately(self, interval, stop_event):
        stop_event.set()

    monkeypatch.setattr("modeldeck.service.runner.CollectionRunner.run_loop", stop_immediately)
    await run_service()


@pytest.mark.asyncio
async def test_run_loop_continues_after_unexpected_publish_error(tmp_path):
    """Non-MQTT publish failures should be logged and retried."""
    mqtt = MqttBridge(MqttConfig())
    calls = 0

    async def flaky_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("unexpected")

    mqtt.publish_snapshots = AsyncMock(side_effect=flaky_publish)
    runner = CollectionRunner(
        collectors=[MockCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=StateCache(tmp_path / "state.json"),
    )
    stop = asyncio.Event()

    async def stop_soon():
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(runner.run_loop(0.01, stop), stop_soon())
    assert calls >= 2


@pytest.mark.asyncio
async def test_collect_and_publish_warns_when_no_snapshots(tmp_path):
    """An all-crash cycle should return without publishing."""
    mqtt = MqttBridge(MqttConfig())
    mqtt.publish_snapshots = AsyncMock()

    class BoomCollector(MockCollector):
        async def collect(self):
            raise RuntimeError("boom")

    runner = CollectionRunner(
        collectors=[BoomCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=StateCache(tmp_path / "state.json"),
    )
    assert await runner.collect_and_publish() == []
    mqtt.publish_snapshots.assert_not_called()


@pytest.mark.asyncio
async def test_mqtt_publish_reconnects_after_failure(monkeypatch):
    """After a publish failure the next cycle should open a new session."""
    sessions = 0
    failures = 0

    class FakeClient:
        async def __aenter__(self):
            nonlocal sessions
            sessions += 1
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, *args, **kwargs):
            nonlocal failures
            failures += 1
            if failures == 4:
                raise aiomqtt.MqttError("lost connection")

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    item = SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])
    await bridge.publish_snapshots([item])
    with pytest.raises(MqttError):
        await bridge.publish_snapshots([item])
    await bridge.publish_snapshots([item])
    assert sessions == 2


@pytest.mark.asyncio
async def test_run_loop_logs_stop(tmp_path):
    """Stopping the loop should exit cleanly."""
    mqtt = MqttBridge(MqttConfig())
    mqtt.publish_snapshots = AsyncMock()
    runner = CollectionRunner(
        collectors=[MockCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=StateCache(tmp_path / "state.json"),
    )
    stop = asyncio.Event()
    stop.set()
    await runner.run_loop(60, stop)


@pytest.mark.asyncio
async def test_mqtt_connect_is_idempotent(monkeypatch):
    """connect() should not open multiple sessions."""
    entered = 0

    class FakeClient:
        async def __aenter__(self):
            nonlocal entered
            entered += 1
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, *args, **kwargs):
            return None

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    await bridge.connect()
    await bridge.connect()
    assert entered == 1


@pytest.mark.asyncio
async def test_mqtt_disconnect_swallows_broker_error(monkeypatch):
    """disconnect() should clear state even when the broker close fails."""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise aiomqtt.MqttError("close failed")

        async def publish(self, *args, **kwargs):
            return None

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    await bridge.connect()
    await bridge.disconnect()
    assert bridge._client is None
    assert bridge.connected is False


@pytest.mark.asyncio
async def test_mqtt_set_offline_uses_persistent_client(monkeypatch):
    """set_offline should publish through the open persistent session."""
    published: list[str] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append(payload)

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(MqttConfig())
    await bridge.connect()
    await bridge.set_offline()
    assert published[-1] == "offline"
