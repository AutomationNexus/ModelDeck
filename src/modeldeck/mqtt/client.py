"""Async MQTT client wrapper."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiomqtt

from modeldeck.config.loader import MqttConfig
from modeldeck.core.exceptions import MqttError
from modeldeck.core.logging import get_logger
from modeldeck.mqtt.discovery import (
    bridge_status_topic,
    build_discovery_payload,
    discovery_topic,
    homeassistant_entity_id,
    legacy_single_account_discovery_topic,
    short_slug_discovery_topic,
    state_topic,
)
from modeldeck.mqtt.publisher import format_metric_value
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotPublish:
    """Snapshot plus the metrics to expose in Home Assistant."""

    snapshot: ProviderSnapshot
    metrics: list[MetricKind]


class MqttBridge:
    """Publish discovery and state updates to MQTT."""

    def __init__(self, mqtt: MqttConfig) -> None:
        self._mqtt = mqtt
        self._connected = False
        self._last_success: dict[tuple[str, str], Any] = {}
        self._published_metrics: dict[tuple[str, str], set[MetricKind]] = {}
        self._short_slug_retired: set[str] = set()
        self._legacy_retired: set[str] = set()
        self._client: aiomqtt.Client | None = None

    @property
    def connected(self) -> bool:
        """Return whether the bridge last connected successfully."""
        return self._connected

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "hostname": self._mqtt.host,
            "port": self._mqtt.port,
            "identifier": self._mqtt.client_id,
            "keepalive": 60,
        }
        if self._mqtt.username:
            kwargs["username"] = self._mqtt.username
        if self._mqtt.password:
            kwargs["password"] = self._mqtt.password
        if self._mqtt.tls:
            kwargs["tls_context"] = True
        return kwargs

    async def connect(self) -> None:
        """Open a persistent MQTT session for the service poll loop."""
        if self._client is not None:
            return
        try:
            client = aiomqtt.Client(**self._client_kwargs())
            await client.__aenter__()
            self._client = client
            self._connected = True
            await self._publish_bridge_status(client, "online")
        except aiomqtt.MqttError as exc:
            self._client = None
            self._connected = False
            raise MqttError(str(exc)) from exc

    async def disconnect(self) -> None:
        """Close the persistent MQTT session."""
        client = self._client
        self._client = None
        self._connected = False
        if client is None:
            return
        try:
            await client.__aexit__(None, None, None)
        except aiomqtt.MqttError as exc:
            logger.debug("MQTT disconnect error: %s", exc)

    async def _drop_connection(self) -> None:
        """Reset the persistent session after a publish failure."""
        await self.disconnect()

    async def _session(self) -> aiomqtt.Client:
        """Return a connected client, reconnecting when needed."""
        if self._client is None:
            await self.connect()
        assert self._client is not None
        return self._client

    async def publish_snapshots(
        self,
        items: list[SnapshotPublish],
        *,
        publish_discovery: bool = False,
    ) -> None:
        """Publish state for all snapshots; optionally publish discovery."""
        try:
            client = await self._session()
            await self._publish_bridge_status(client, "online")
            for item in items:
                if publish_discovery:
                    await self._publish_discovery(client, item)
                await self._publish_states(client, item)
        except aiomqtt.MqttError as exc:
            self._connected = False
            await self._drop_connection()
            raise MqttError(str(exc)) from exc

    async def publish_discovery_only(self, items: list[SnapshotPublish]) -> None:
        """Publish Home Assistant discovery configs without state."""
        try:
            async with aiomqtt.Client(**self._client_kwargs()) as client:
                self._connected = True
                for item in items:
                    await self._publish_discovery(client, item)
        except aiomqtt.MqttError as exc:
            self._connected = False
            raise MqttError(str(exc)) from exc

    async def _publish_bridge_status(self, client: aiomqtt.Client, status: str) -> None:
        await client.publish(
            bridge_status_topic(self._mqtt),
            payload=status,
            qos=1,
            retain=True,
        )

    async def _retire_short_slug_discovery(
        self,
        client: aiomqtt.Client,
        provider_id: str,
    ) -> None:
        """Clear v0.1.0–v0.1.2 short-slug discovery topics."""
        if provider_id in self._short_slug_retired:
            return
        for metric in MetricKind:
            topic = short_slug_discovery_topic(self._mqtt, provider_id, metric)
            await client.publish(topic, payload="", qos=0, retain=True)
        self._short_slug_retired.add(provider_id)

    async def _retire_legacy_single_account_discovery(
        self,
        client: aiomqtt.Client,
        provider_id: str,
    ) -> None:
        """Clear pre-multi-account (no account_id) discovery topics once per provider."""
        if provider_id in self._legacy_retired:
            return
        for metric in MetricKind:
            topic = legacy_single_account_discovery_topic(self._mqtt, provider_id, metric)
            await client.publish(topic, payload="", qos=0, retain=True)
        self._legacy_retired.add(provider_id)

    async def _publish_discovery(
        self,
        client: aiomqtt.Client,
        item: SnapshotPublish,
    ) -> None:
        snapshot = item.snapshot
        current = set(item.metrics)
        provider_id = snapshot.provider_id
        account_id = snapshot.account_id
        key = (provider_id, account_id)

        await self._retire_short_slug_discovery(client, provider_id)
        await self._retire_legacy_single_account_discovery(client, provider_id)

        previous = self._published_metrics.get(key, set())
        retire = (set(MetricKind) - current) if not previous else previous - current
        for metric in retire:
            topic = discovery_topic(self._mqtt, provider_id, account_id, metric)
            await client.publish(topic, payload="", qos=0, retain=True)
        for metric in item.metrics:
            topic = discovery_topic(self._mqtt, provider_id, account_id, metric)
            payload = build_discovery_payload(self._mqtt, snapshot, metric)
            entity_id = homeassistant_entity_id(provider_id, account_id, metric)
            logger.info("MQTT discovery %s (%s)", entity_id, topic)
            await client.publish(
                topic,
                payload=json.dumps(payload),
                qos=0,
                retain=True,
            )
        self._published_metrics[key] = current

    async def _publish_states(
        self,
        client: aiomqtt.Client,
        item: SnapshotPublish,
    ) -> None:
        snapshot = item.snapshot
        key = (snapshot.provider_id, snapshot.account_id)
        if snapshot.status == CollectorStatus.OK:
            self._last_success[key] = snapshot.collected_at
        last_ok = self._last_success.get(key)
        for metric in item.metrics:
            value = format_metric_value(snapshot, metric, last_success=last_ok)
            if value is None and metric != MetricKind.STATUS:
                continue
            if value is None:
                value = snapshot.status.value
            topic = state_topic(self._mqtt, snapshot.provider_id, snapshot.account_id, metric)
            await client.publish(
                topic,
                payload=value,
                qos=1,
                retain=True,
            )

    async def retire_account(self, provider_id: str, account_id: str) -> None:
        """Publish empty retained payloads to remove all sensors for an account."""
        try:
            client = await self._session()
            for metric in MetricKind:
                topic = discovery_topic(self._mqtt, provider_id, account_id, metric)
                await client.publish(topic, payload="", qos=0, retain=True)
                s_topic = state_topic(self._mqtt, provider_id, account_id, metric)
                await client.publish(s_topic, payload="", qos=0, retain=True)
            key = (provider_id, account_id)
            self._published_metrics.pop(key, None)
            self._last_success.pop(key, None)
        except aiomqtt.MqttError as exc:
            raise MqttError(str(exc)) from exc

    async def set_offline(self) -> None:
        """Publish bridge offline status (best-effort)."""
        try:
            async with asyncio.timeout(5):
                if self._client is not None:
                    await self._publish_bridge_status(self._client, "offline")
                    return
                async with aiomqtt.Client(**self._client_kwargs()) as client:
                    await self._publish_bridge_status(client, "offline")
        except (aiomqtt.MqttError, TimeoutError):
            logger.debug("Could not publish offline status")
