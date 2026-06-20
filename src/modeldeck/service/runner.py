"""Long-running service entrypoint."""

from __future__ import annotations

import asyncio
import signal

from modeldeck.collectors.base import build_collectors
from modeldeck.config.loader import check_secrets_permissions, load_config
from modeldeck.core.exceptions import MqttError
from modeldeck.core.logging import get_logger, setup_logging
from modeldeck.mqtt.client import MqttBridge
from modeldeck.service.scheduler import CollectionRunner
from modeldeck.service.state_cache import StateCache

logger = get_logger(__name__)


async def _supervise_poll_task(
    poll_task: asyncio.Task[None],
    stop_event: asyncio.Event,
) -> None:
    """Log and surface unexpected poll-loop exits while the service runs."""
    try:
        await poll_task
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Poll loop task exited unexpectedly")
        stop_event.set()


async def run_service() -> None:
    """Start the ModelDeck service."""
    config, secrets = load_config()
    setup_logging(config.service.log_level)
    for warning in check_secrets_permissions():
        logger.warning(warning)
    collectors = build_collectors(config, secrets)
    if not collectors:
        logger.warning("No enabled collectors — service will idle until configuration changes")
    mqtt = MqttBridge(config.mqtt)
    try:
        await mqtt.connect()
    except MqttError as exc:
        logger.error("Initial MQTT connection failed: %s", exc)
    cache = StateCache()
    runner = CollectionRunner(
        collectors=collectors,
        mqtt=mqtt,
        cache=cache,
        retain_state=config.service.retain_state,
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    except NotImplementedError:
        # Windows does not support add_signal_handler for all signals.
        signal.signal(signal.SIGINT, lambda _n, _f: stop_event.set())
    poll_task = asyncio.create_task(
        runner.run_loop(config.service.poll_interval_seconds, stop_event),
        name="modeldeck-poll-loop",
    )
    supervisor = asyncio.create_task(_supervise_poll_task(poll_task, stop_event))
    try:
        await stop_event.wait()
    finally:
        poll_task.cancel()
        supervisor.cancel()
        await mqtt.set_offline()
        await mqtt.disconnect()
        await asyncio.gather(poll_task, supervisor, return_exceptions=True)


def main() -> None:
    """CLI entry for modeldeck-service."""
    asyncio.run(run_service())
