"""Collection scheduler and orchestration."""

from __future__ import annotations

import asyncio

from modeldeck.collectors.base import Collector
from modeldeck.collectors.metrics import effective_metrics
from modeldeck.core.exceptions import MqttError
from modeldeck.core.logging import get_logger
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.schemas.snapshot import ProviderSnapshot
from modeldeck.service.state_cache import StateCache

logger = get_logger(__name__)


class CollectionRunner:
    """Run collectors and publish results."""

    def __init__(
        self,
        collectors: list[Collector],
        mqtt: MqttBridge,
        cache: StateCache,
        retain_state: bool = True,
    ) -> None:
        self._collectors = collectors
        self._mqtt = mqtt
        self._cache = cache
        self._retain_state = retain_state
        self._last_snapshots: list[ProviderSnapshot] = []
        self._discovery_published = False

    @property
    def last_snapshots(self) -> list[ProviderSnapshot]:
        """Return snapshots from the most recent collection cycle."""
        return list(self._last_snapshots)

    async def collect_and_publish(self, *, force_discovery: bool = False) -> list[ProviderSnapshot]:
        """Collect from all providers and publish to MQTT."""
        items: list[SnapshotPublish] = []
        snapshots: list[ProviderSnapshot] = []
        for collector in self._collectors:
            try:
                snapshot = await collector.collect()
                metrics = effective_metrics(snapshot, collector.supported_metrics())
                items.append(SnapshotPublish(snapshot=snapshot, metrics=metrics))
                snapshots.append(snapshot)
                logger.info(
                    "Collected %s status=%s",
                    collector.provider_id,
                    snapshot.status.value,
                )
            except Exception as exc:
                logger.exception("Collector %s crashed: %s", collector.provider_id, exc)
        if not snapshots:
            logger.warning("No collector snapshots produced this cycle")
            return []
        publish_discovery = force_discovery or not self._discovery_published
        await self._mqtt.publish_snapshots(
            items,
            publish_discovery=publish_discovery,
        )
        if publish_discovery:
            self._discovery_published = True
        if self._retain_state:
            try:
                self._cache.save(snapshots)
            except OSError as exc:
                logger.warning("Could not persist state cache: %s", exc)
        self._last_snapshots = snapshots
        return snapshots

    async def run_loop(self, interval_seconds: int, stop_event: asyncio.Event) -> None:
        """Poll providers on a fixed interval until stop_event is set."""
        logger.info("Starting poll loop (interval=%ss)", interval_seconds)
        while not stop_event.is_set():
            try:
                await self.collect_and_publish(force_discovery=not self._discovery_published)
            except MqttError as exc:
                logger.error("MQTT publish failed; will retry next cycle: %s", exc)
            except Exception:
                logger.exception("Collection cycle failed; will retry next cycle")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue
        logger.info("Poll loop stopped")
