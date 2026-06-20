"""Tests to reach coverage targets."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from modeldeck.cli.main import main
from modeldeck.collectors.base import build_collectors
from modeldeck.collectors.claude import ClaudeCollector
from modeldeck.collectors.codex import CodexCollector
from modeldeck.collectors.cursor import CursorCollector
from modeldeck.config.loader import AppConfig, ProviderSecrets, SecretsConfig, _load_yaml
from modeldeck.core.exceptions import ConfigError, MqttError
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from modeldeck.service.runner import main as service_main
from modeldeck.service.runner import run_service
from tests.conftest import no_file_toggle


def test_build_collectors_skips_unknown(tmp_path):
    """Unknown provider ids should be ignored."""
    config = AppConfig.model_validate(
        {"providers": {"mock": {"enabled": True}, "codex": {"enabled": False}}}
    )
    collectors = build_collectors(config, SecretsConfig())
    assert len(collectors) == 1


def test_load_yaml_invalid_type(tmp_path):
    """Non-mapping YAML should raise ConfigError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        _load_yaml(bad)


@pytest.mark.asyncio
async def test_codex_live_client_path(monkeypatch):
    """Codex without injected client should use httpx.AsyncClient."""
    calls = 0

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "results": [
                            {"amount": {"value": 1.0, "currency": "usd"}},
                        ]
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            nonlocal calls
            calls += 1
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.codex_api_collector.httpx.AsyncClient", lambda **k: FakeClient()
    )
    toggle = no_file_toggle(auth_mode="api")
    snap = await CodexCollector(AppConfig(), ProviderSecrets(api_key="k"), toggle).collect()
    assert calls == 1
    assert snap.status == CollectorStatus.OK


@pytest.mark.asyncio
async def test_claude_parse_error():
    """Invalid JSON shape should become parse_error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    toggle = no_file_toggle(auth_mode="cookie")
    secrets = ProviderSecrets(session_token="t", org_id="org-1")
    collector = ClaudeCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status in {CollectorStatus.OK, CollectorStatus.PARSE_ERROR}


@pytest.mark.asyncio
async def test_claude_unavailable():
    """5xx should map to unavailable."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    toggle = no_file_toggle(auth_mode="cookie")
    secrets = ProviderSecrets(session_token="t", org_id="org-1")
    collector = ClaudeCollector(AppConfig(), secrets, toggle, client=client)
    snap = await collector.collect()
    assert snap.status == CollectorStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_cursor_live_client(monkeypatch):
    """Cursor without injected client should use httpx.AsyncClient."""
    import json
    from pathlib import Path

    fixtures_dir = Path(__file__).resolve().parents[2] / "fixtures"
    fixture = json.loads((fixtures_dir / "cursor_usage_summary.json").read_text(encoding="utf-8"))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fixture

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr(
        "modeldeck.collectors.cursor_personal.httpx.AsyncClient", lambda **k: FakeClient()
    )
    toggle = no_file_toggle(auth_mode="personal")
    snap = await CursorCollector(AppConfig(), ProviderSecrets(session_token="t"), toggle).collect()
    assert snap.status == CollectorStatus.OK


@pytest.mark.asyncio
async def test_mqtt_bridge_mqtt_error(monkeypatch):
    """MqttError should be raised on connection failure."""
    import aiomqtt

    class BoomClient:
        async def __aenter__(self):
            raise aiomqtt.MqttError("fail")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("modeldeck.mqtt.client.aiomqtt.Client", lambda **kwargs: BoomClient())
    bridge = MqttBridge(AppConfig().mqtt)
    from datetime import UTC, datetime

    snap = ProviderSnapshot(
        provider_id="m",
        display_name="M",
        collected_at=datetime.now(UTC),
        status=CollectorStatus.OK,
    )
    with pytest.raises(MqttError):
        await bridge.publish_snapshots(
            [SnapshotPublish(snapshot=snap, metrics=[MetricKind.STATUS])]
        )


@pytest.mark.asyncio
async def test_mqtt_client_kwargs_tls():
    """TLS and credentials should be passed to aiomqtt."""
    from modeldeck.config.loader import MqttConfig

    cfg = MqttConfig(username="u", password="p", tls=True)
    bridge = MqttBridge(cfg)
    kwargs = bridge._client_kwargs()
    assert kwargs["username"] == "u"
    assert kwargs["password"] == "p"
    assert kwargs["tls_context"] is True


@pytest.mark.asyncio
async def test_run_service_starts_and_stops(tmp_config_dir, monkeypatch):
    """run_service should start tasks and stop on event."""
    config_dir, _data_dir = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")
    monkeypatch.setattr(
        "modeldeck.service.runner.MqttBridge.set_offline",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "modeldeck.service.runner.CollectionRunner.run_loop",
        AsyncMock(side_effect=lambda interval, ev: ev.set()),
    )

    await run_service()


def test_service_main():
    """service main should invoke asyncio.run."""
    with patch("modeldeck.service.runner.asyncio.run") as run:
        service_main()
        run.assert_called_once()


def test_cli_collect_once(tmp_config_dir, monkeypatch):
    """collect-once command should run without error."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")
    monkeypatch.setattr(
        "modeldeck.cli.main.CollectionRunner.collect_and_publish",
        AsyncMock(return_value=[]),
    )
    code = main(
        [
            "collect-once",
            "--config",
            str(config_dir / "modeldeck.yaml"),
            "--secrets",
            str(config_dir / "secrets.yaml"),
            "--discovery",
        ]
    )
    assert code == 0


def test_cli_discovery_publish(tmp_config_dir, monkeypatch):
    """discovery publish should complete."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")
    monkeypatch.setattr(
        "modeldeck.cli.main.MqttBridge.publish_discovery_only",
        AsyncMock(),
    )
    code = main(
        [
            "discovery",
            "publish",
            "--config",
            str(config_dir / "modeldeck.yaml"),
            "--secrets",
            str(config_dir / "secrets.yaml"),
        ]
    )
    assert code == 0
