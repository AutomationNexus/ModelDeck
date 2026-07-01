"""State cache and scheduler tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from modeldeck.collectors.mock import MockCollector
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.mqtt.client import MqttBridge
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot
from modeldeck.service.scheduler import CollectionRunner
from modeldeck.service.state_cache import StateCache, snapshot_from_dict, snapshot_to_dict


def test_state_cache_roundtrip(tmp_path):
    """Snapshots should survive JSON roundtrip."""
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 17, tzinfo=UTC),
        status=CollectorStatus.OK,
        usage_percent=10.0,
    )
    data = snapshot_to_dict(snap)
    restored = snapshot_from_dict(data)
    assert restored.provider_id == "mock"
    cache = StateCache(tmp_path / "state.json")
    cache.save([snap])
    loaded = cache.load()
    assert "mock/default" in loaded
    assert loaded["mock/default"].usage_percent == 10.0


@pytest.mark.asyncio
async def test_collection_runner_publishes(tmp_path):
    """Runner should collect and publish without raising."""
    mqtt = MqttBridge(AppConfig().mqtt)
    mqtt.publish_snapshots = AsyncMock()
    runner = CollectionRunner(
        collectors=[MockCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=StateCache(tmp_path / "state.json"),
    )
    snaps = await runner.collect_and_publish(force_discovery=True)
    assert len(snaps) == 1
    mqtt.publish_snapshots.assert_awaited_once()


@pytest.mark.asyncio
async def test_collection_runner_continues_when_state_save_fails(tmp_path, monkeypatch):
    """State cache write failures must not fail a successful MQTT cycle."""
    mqtt = MqttBridge(AppConfig().mqtt)
    mqtt.publish_snapshots = AsyncMock()
    cache = StateCache(tmp_path / "state.json")

    def _boom(_snapshots):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(cache, "save", _boom)
    runner = CollectionRunner(
        collectors=[MockCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=cache,
    )
    snaps = await runner.collect_and_publish(force_discovery=True)
    assert len(snaps) == 1
    mqtt.publish_snapshots.assert_awaited_once()
