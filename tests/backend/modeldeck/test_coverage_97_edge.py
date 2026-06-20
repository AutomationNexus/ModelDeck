"""Edge-case tests for 97% coverage (scheduler, MQTT, service, CLI)."""

from __future__ import annotations

import asyncio
import runpy
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from modeldeck.cli.main import main
from modeldeck.collectors.base import build_collectors
from modeldeck.collectors.claude import ClaudeCollector
from modeldeck.collectors.mock import MockCollector
from modeldeck.config.loader import AppConfig, ProviderSecrets, SecretsConfig
from modeldeck.core.exceptions import MqttError
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.mqtt.publisher import format_metric_value
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from modeldeck.service.runner import run_service
from modeldeck.service.scheduler import CollectionRunner
from modeldeck.service.state_cache import StateCache
from tests.conftest import no_file_toggle


def test_build_collectors_skips_unknown_registry_entry(monkeypatch):
    """Enabled provider ids missing from the registry should be ignored."""
    config = AppConfig()
    providers = MagicMock()
    providers.model_dump.return_value = {
        "mock": {"enabled": True},
        "unknown": {"enabled": True},
    }
    monkeypatch.setattr(config, "providers", providers)
    collectors = build_collectors(config, SecretsConfig())
    assert len(collectors) == 1


@pytest.mark.asyncio
async def test_claude_auth_error_status():
    """Claude 401 should map to auth_error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    toggle = no_file_toggle(auth_mode="cookie")
    secrets = ProviderSecrets(session_token="t", org_id="org-1")
    snap = await ClaudeCollector(AppConfig(), secrets, toggle, client=client).collect()
    assert snap.status == CollectorStatus.AUTH_ERROR


def test_format_metric_last_success_when_ok():
    """LAST_SUCCESS should use collected_at when status is ok."""
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 17, tzinfo=UTC),
        status=CollectorStatus.OK,
    )
    assert format_metric_value(snap, MetricKind.LAST_SUCCESS) is not None


@pytest.mark.asyncio
async def test_scheduler_isolates_collector_runtime_error(tmp_path):
    """A collector raising RuntimeError should not stop the runner."""

    class BoomCollector:
        provider_id = "boom"
        display_name = "Boom"

        def supported_metrics(self):
            return list(MetricKind)

        async def collect(self):
            raise RuntimeError("boom")

    mqtt = AsyncMock()
    runner = CollectionRunner(
        [BoomCollector(), MockCollector(AppConfig(), ProviderSecrets())],
        mqtt,
        StateCache(tmp_path / "s.json"),
    )
    snaps = await runner.collect_and_publish()
    assert len(snaps) == 1
    assert snaps[0].provider_id == "mock"


@pytest.mark.asyncio
async def test_mqtt_discovery_only_mqtt_error(monkeypatch):
    """publish_discovery_only should raise MqttError on failure."""
    import aiomqtt

    class BoomClient:
        async def __aenter__(self):
            raise aiomqtt.MqttError("fail")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: BoomClient())
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    with pytest.raises(MqttError):
        await MqttBridge(AppConfig().mqtt).publish_discovery_only(
            [SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])]
        )


@pytest.mark.asyncio
async def test_mqtt_publish_discovery_only(monkeypatch):
    """Discovery-only publish should emit homeassistant topics."""
    published: list[str] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append(topic)

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        usage_percent=1.0,
    )
    await MqttBridge(AppConfig().mqtt).publish_discovery_only(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.USAGE_PERCENT, MetricKind.STATUS])]
    )
    assert published


@pytest.mark.asyncio
async def test_mqtt_status_fallback_when_value_none(monkeypatch):
    """STATUS metric should fall back to snapshot status when value is None."""

    def fake_format(snapshot, metric, last_success=None):
        if metric == MetricKind.STATUS:
            return None
        return format_metric_value(snapshot, metric, last_success=last_success)

    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, payload))

    monkeypatch.setattr("modeldeck.mqtt.client.format_metric_value", fake_format)
    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(AppConfig().mqtt)
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])],
        publish_discovery=False,
    )
    status_payloads = [p for t, p in published if t.endswith("/status/state")]
    assert status_payloads == ["ok"]


def test_runner_last_snapshots_property(tmp_path):
    """last_snapshots should return a copy of the latest cycle."""
    mqtt = AsyncMock()

    async def run():
        runner = CollectionRunner(
            [MockCollector(AppConfig(), ProviderSecrets())],
            mqtt,
            StateCache(tmp_path / "s.json"),
        )
        await runner.collect_and_publish()
        snaps = runner.last_snapshots
        assert len(snaps) == 1
        snaps.clear()
        assert len(runner.last_snapshots) == 1

    asyncio.run(run())


@pytest.mark.asyncio
async def test_mqtt_publish_states_skips_none_metrics(monkeypatch):
    """State publish should skip null optional metrics."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, payload))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(AppConfig().mqtt)
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.AUTH_ERROR,
    )
    await bridge.publish_snapshots(
        [
            SnapshotPublish(
                snapshot=snap,
                metrics=[MetricKind.USAGE_PERCENT, MetricKind.STATUS],
            )
        ],
        publish_discovery=False,
    )
    status_topics = [t for t, _ in published if t.endswith("/status/state")]
    assert status_topics
    usage_topics = [t for t, _ in published if t.endswith("/usage_percent/state")]
    assert not usage_topics


@pytest.mark.asyncio
async def test_mqtt_set_offline_on_error(monkeypatch):
    """set_offline should swallow MQTT failures."""
    import aiomqtt

    class BoomClient:
        async def __aenter__(self):
            raise aiomqtt.MqttError("fail")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: BoomClient())
    await MqttBridge(AppConfig().mqtt).set_offline()


def test_state_cache_keeps_existing_on_failed_update(tmp_path):
    """Failed snapshots should not overwrite existing good cache entries."""
    path = tmp_path / "state.json"
    cache = StateCache(path)
    good = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 17, tzinfo=UTC),
        status=CollectorStatus.OK,
        usage_percent=10.0,
    )
    cache.save([good])
    bad = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 18, tzinfo=UTC),
        status=CollectorStatus.AUTH_ERROR,
    )
    cache.save([bad])
    loaded = cache.load()["mock"]
    assert loaded.usage_percent == 10.0


def test_state_cache_stores_first_failed_snapshot(tmp_path):
    """First failed snapshot for a provider should be stored."""
    path = tmp_path / "state.json"
    cache = StateCache(path)
    bad = ProviderSnapshot(
        provider_id="codex",
        display_name="Codex",
        collected_at=datetime(2026, 6, 17, tzinfo=UTC),
        status=CollectorStatus.AUTH_ERROR,
    )
    cache.save([bad])
    assert "codex" in cache.load()


@pytest.mark.asyncio
async def test_runner_empty_collectors_returns_empty(tmp_path):
    """No snapshots should short-circuit publishing."""
    mqtt = AsyncMock()
    runner = CollectionRunner([], mqtt, StateCache(tmp_path / "s.json"))
    assert await runner.collect_and_publish() == []
    mqtt.publish_snapshots.assert_not_called()


@pytest.mark.asyncio
async def test_run_loop_timeout_continues(tmp_path):
    """run_loop should continue polling after interval timeouts."""
    mqtt = AsyncMock()
    runner = CollectionRunner(
        [MockCollector(AppConfig(), ProviderSecrets())],
        mqtt,
        StateCache(tmp_path / "s.json"),
    )
    stop = asyncio.Event()

    async def run_once():
        await runner.run_loop(0.01, stop)

    task = asyncio.create_task(run_once())
    await asyncio.sleep(0.05)
    stop.set()
    await task
    assert mqtt.publish_snapshots.await_count >= 1


@pytest.mark.asyncio
async def test_run_service_with_warnings_and_shutdown(tmp_config_dir, monkeypatch):
    """run_service should log secret warnings and shut down cleanly."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")
    sec = config_dir / "secrets.yaml"
    sec.write_text("mqtt: {}\n")
    sec.chmod(0o644)

    monkeypatch.setattr(
        "modeldeck.service.runner.MqttBridge.set_offline",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "modeldeck.service.runner.CollectionRunner.run_loop",
        AsyncMock(side_effect=lambda interval, ev: ev.set()),
    )

    await run_service()


def test_cli_serve_command(monkeypatch):
    """serve subcommand should invoke run_service."""
    monkeypatch.setattr("modeldeck.cli.main.run_service", lambda: None)
    assert main(["serve"]) == 0


def test_cli_main_module_block(tmp_path, monkeypatch):
    """python -m modeldeck should exit via SystemExit."""
    cfg = tmp_path / "modeldeck.yaml"
    cfg.write_text("providers:\n  mock:\n    enabled: true\n")
    monkeypatch.setattr(sys, "argv", ["modeldeck", "config", "validate", "--config", str(cfg)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("modeldeck", run_name="__main__", alter_sys=True)
    assert exc.value.code == 0
