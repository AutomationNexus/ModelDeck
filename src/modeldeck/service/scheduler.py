"""Collection scheduler and orchestration."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from modeldeck.collectors.base import Collector
from modeldeck.collectors.metrics import effective_metrics
from modeldeck.core.exceptions import MqttError
from modeldeck.core.logging import get_logger
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.schemas.snapshot import ProviderSnapshot
from modeldeck.service.state_cache import StateCache

if TYPE_CHECKING:
    from modeldeck.service.reload import ConfigWatcher

logger = get_logger(__name__)

# How often the run_loop wakes to check for config changes (seconds).
_RELOAD_CHECK_INTERVAL = 5


class CollectionRunner:
    """Run collectors and publish results."""

    def __init__(
        self,
        collectors: list[Collector],
        mqtt: MqttBridge,
        cache: StateCache,
        retain_state: bool = True,
        active_keys: set[tuple[str, str]] | None = None,
    ) -> None:
        self._collectors = collectors
        self._mqtt = mqtt
        self._cache = cache
        self._retain_state = retain_state
        self._last_snapshots: list[ProviderSnapshot] = []
        self._discovery_published = False
        # Track currently active (provider, account_id) pairs for reload diffing.
        self._active_keys: set[tuple[str, str]] = active_keys or set()

    @property
    def last_snapshots(self) -> list[ProviderSnapshot]:
        """Return snapshots from the most recent collection cycle."""
        return list(self._last_snapshots)

    async def apply_reload(
        self,
        collectors: list[Collector],
        active_keys: set[tuple[str, str]],
    ) -> None:
        """Apply a live config reload: retire removed accounts, swap collectors.

        Accounts present in the previous active set but absent in the new one
        (deleted or disabled) have their MQTT discovery/state topics retired.
        Discovery is forced on the next publish cycle so new/renamed accounts
        get fresh discovery payloads.
        """
        removed = self._active_keys - active_keys
        for provider_id, account_id in removed:
            logger.info(
                "Retiring MQTT sensors for removed account %s/%s",
                provider_id, account_id,
            )
            try:
                await self._mqtt.retire_account(provider_id, account_id)
            except MqttError as exc:
                logger.warning(
                    "Could not retire %s/%s: %s", provider_id, account_id, exc
                )

        self._collectors = collectors
        self._active_keys = active_keys
        # Force discovery republish on next cycle so new/renamed accounts appear.
        self._discovery_published = False
        logger.info(
            "Live reload applied: %d collector(s), %d active account(s)",
            len(collectors), len(active_keys),
        )

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

    async def run_loop(
        self,
        interval_seconds: int,
        stop_event: asyncio.Event,
        *,
        watcher: ConfigWatcher | None = None,
        reload_check_interval: int = _RELOAD_CHECK_INTERVAL,
    ) -> None:
        """Poll providers on a fixed interval until stop_event is set.

        The live-reload watcher can be provided either via the *watcher*
        keyword argument or pre-attached as ``self._config_watcher`` by
        the runner (the latter avoids breaking tests that monkeypatch
        ``run_loop`` with a simple positional stub).
        """
        logger.info("Starting poll loop (interval=%ss)", interval_seconds)
        next_collect_at = time.monotonic()  # collect immediately on first iteration
        # Resolve watcher: explicit kwarg takes precedence, then instance attr.
        effective_watcher: ConfigWatcher | None = watcher or getattr(
            self, "_config_watcher", None
        )

        while not stop_event.is_set():
            now = time.monotonic()

            # --- Config-change check (fast path, runs every reload_check_interval) ---
            if effective_watcher is not None and effective_watcher.changed():
                logger.info("Config change detected — reloading")
                try:
                    _, _, new_collectors, new_keys = effective_watcher.load()
                    await self.apply_reload(new_collectors, new_keys)
                    # Trigger an immediate collection so changes are visible fast.
                    next_collect_at = now
                except Exception:
                    logger.exception("Config reload failed; keeping existing collectors")

            # --- Collection (runs every interval_seconds) ---
            if now >= next_collect_at:
                try:
                    await self.collect_and_publish(
                        force_discovery=not self._discovery_published
                    )
                except MqttError as exc:
                    logger.error("MQTT publish failed; will retry next cycle: %s", exc)
                except Exception:
                    logger.exception("Collection cycle failed; will retry next cycle")
                next_collect_at = time.monotonic() + interval_seconds

            # Sleep until the next reload check (or until stopped).
            sleep_secs = min(
                reload_check_interval,
                max(0.0, next_collect_at - time.monotonic()),
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_secs)
            except TimeoutError:
                continue

        logger.info("Poll loop stopped")
