"""Additional unit tests for coverage."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from modeldeck.cli.main import main
from modeldeck.collectors.codex import CodexCollector
from modeldeck.config.loader import check_secrets_permissions
from modeldeck.core.logging import RedactingFilter, setup_logging
from modeldeck.core.paths import config_dir, config_path, data_dir, secrets_path, state_path
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.mqtt.discovery import bridge_status_topic, discovery_payload_json
from modeldeck.mqtt.publisher import format_metric_value
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from modeldeck.service.scheduler import CollectionRunner


def test_paths_defaults(monkeypatch):
    """Path helpers should respect environment overrides."""
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", "/tmp/cfg")
    monkeypatch.setenv("MODELDECK_DATA_DIR", "/tmp/data")
    assert config_dir() == Path("/tmp/cfg")
    assert data_dir() == Path("/tmp/data")
    assert config_path() == Path("/tmp/cfg/modeldeck.yaml")
    assert secrets_path() == Path("/tmp/cfg/secrets.yaml")
    assert state_path() == Path("/tmp/data/state.json")


def test_check_secrets_permissions_warns_world_readable(tmp_path):
    """World-readable secrets should produce a warning."""
    sec = tmp_path / "secrets.yaml"
    sec.write_text("mqtt: {}\n", encoding="utf-8")
    sec.chmod(0o644)
    warnings = check_secrets_permissions(sec)
    assert warnings


def test_setup_logging_configures_root():
    """setup_logging should attach a handler."""
    setup_logging("DEBUG")
    import logging

    assert logging.getLogger().handlers


def test_redacting_filter_on_log_record():
    """Filter should redact record message in place."""
    filt = RedactingFilter()
    record = logging_record("Cookie: abc123")
    assert filt.filter(record) is True
    assert "abc123" not in record.msg


def logging_record(msg: str):
    import logging

    return logging.LogRecord("x", logging.INFO, "", 0, msg, (), None)


def test_format_all_metrics():
    """Publisher should handle timestamp and last_success branches."""
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime(2026, 6, 17, tzinfo=UTC),
        status=CollectorStatus.AUTH_ERROR,
        reset_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    assert format_metric_value(snap, MetricKind.RESET_AT) is not None
    assert format_metric_value(snap, MetricKind.LAST_SUCCESS, last_success=None) is None


def test_bridge_status_topic():
    """Bridge topic should use configured prefix."""
    from modeldeck.config.loader import MqttConfig

    assert bridge_status_topic(MqttConfig()) == "modeldeck/bridge/status"


def test_discovery_payload_json_roundtrip():
    """JSON helper should return valid JSON."""
    from modeldeck.config.loader import MqttConfig

    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    raw = discovery_payload_json(MqttConfig(), snap, MetricKind.PLAN)
    assert "modeldeck_mock_default_plan" in raw


@pytest.mark.asyncio
async def test_mqtt_bridge_publish_snapshots(monkeypatch):
    """MqttBridge should publish via aiomqtt client."""
    published: list[tuple[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, payload))

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(__import__("modeldeck.config.loader", fromlist=["MqttConfig"]).MqttConfig())
    snap = ProviderSnapshot(
        provider_id="mock",
        display_name="Mock",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
        usage_percent=1.0,
        plan_name="x",
    )
    await bridge.publish_snapshots(
        [SnapshotPublish(snapshot=snap, metrics=list(MetricKind))],
        publish_discovery=True,
    )
    assert bridge.connected is True
    assert published


@pytest.mark.asyncio
async def test_mqtt_bridge_set_offline(monkeypatch):
    """set_offline should be best-effort."""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def publish(self, *args, **kwargs):
            return None

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: FakeClient())
    bridge = MqttBridge(__import__("modeldeck.config.loader", fromlist=["MqttConfig"]).MqttConfig())
    await bridge.set_offline()


def test_cli_config_validate(tmp_path):
    """CLI validate should exit zero on good config."""
    cfg = tmp_path / "modeldeck.yaml"
    cfg.write_text(yaml.dump({"mqtt": {"host": "localhost"}}), encoding="utf-8")
    code = main(["config", "validate", "--config", str(cfg)])
    assert code == 0


@pytest.mark.asyncio
async def test_codex_rate_limited():
    """Codex 429 should map to rate_limited."""
    import httpx

    from modeldeck.config.loader import AppConfig, ProviderSecrets
    from tests.conftest import no_file_toggle

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    toggle = no_file_toggle(auth_mode="api")
    collector = CodexCollector(AppConfig(), ProviderSecrets(api_key="k"), toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.RATE_LIMITED


@pytest.mark.asyncio
async def test_scheduler_run_loop_stops_on_event(tmp_path):
    """Scheduler loop should exit when stop_event is set."""
    from modeldeck.collectors.mock import MockCollector
    from modeldeck.config.loader import AppConfig, ProviderSecrets

    mqtt = MagicMock()
    mqtt.publish_snapshots = AsyncMock()
    runner = CollectionRunner(
        collectors=[MockCollector(AppConfig(), ProviderSecrets())],
        mqtt=mqtt,
        cache=__import__("modeldeck.service.state_cache", fromlist=["StateCache"]).StateCache(
            tmp_path / "s.json"
        ),
    )
    stop = asyncio.Event()
    stop.set()
    await runner.run_loop(60, stop)
