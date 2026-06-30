"""ModelDeck CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from modeldeck.cli.credentials_cmd import register_credentials_commands
from modeldeck.cli.login_cmd import register_login_commands
from modeldeck.collectors.base import build_collectors
from modeldeck.collectors.metrics import effective_metrics
from modeldeck.config.addon_bootstrap import load_options_file, render_addon_config
from modeldeck.config.loader import load_config, validate_config_file
from modeldeck.core.logging import setup_logging
from modeldeck.mqtt.client import MqttBridge, SnapshotPublish
from modeldeck.service.runner import run_service
from modeldeck.service.scheduler import CollectionRunner
from modeldeck.service.state_cache import StateCache
from modeldeck.webui.server import register_webui_command


def main(argv: list[str] | None = None) -> int:
    """Run the ModelDeck CLI."""
    parser = argparse.ArgumentParser(prog="modeldeck")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the long-lived service")
    serve.set_defaults(func=_cmd_serve)

    once = sub.add_parser("collect-once", help="Collect and publish once")
    once.add_argument("--config", type=Path, default=None)
    once.add_argument("--secrets", type=Path, default=None)
    once.add_argument("--discovery", action="store_true", help="Publish HA discovery")
    once.set_defaults(func=_cmd_collect_once)

    validate = sub.add_parser("config", help="Configuration commands")
    validate_sub = validate.add_subparsers(dest="config_cmd", required=True)
    val = validate_sub.add_parser("validate", help="Validate a config file")
    val.add_argument("--config", type=Path, required=True)
    val.set_defaults(func=_cmd_validate)

    render = validate_sub.add_parser(
        "render-addon",
        help="Render modeldeck.yaml and secrets.yaml from HA add-on options JSON",
    )
    render.add_argument("--options", type=Path, required=True)
    render.add_argument("--config-dir", type=Path, required=True)
    render.set_defaults(func=_cmd_render_addon)

    discovery = sub.add_parser("discovery", help="Discovery commands")
    disc_sub = discovery.add_subparsers(dest="discovery_cmd", required=True)
    disc_pub = disc_sub.add_parser("publish", help="Publish discovery configs")
    disc_pub.add_argument("--config", type=Path, default=None)
    disc_pub.add_argument("--secrets", type=Path, default=None)
    disc_pub.set_defaults(func=_cmd_discovery_publish)

    register_credentials_commands(sub)
    register_login_commands(sub)
    register_webui_command(sub)

    args = parser.parse_args(argv)
    return int(args.func(args))


def _cmd_serve(_args: argparse.Namespace) -> int:
    run_service()
    return 0


async def _collect_once_async(args: argparse.Namespace) -> int:
    config, secrets = load_config(args.config, args.secrets)
    setup_logging(config.service.log_level)
    collectors = build_collectors(config, secrets)
    runner = CollectionRunner(
        collectors=collectors,
        mqtt=MqttBridge(config.mqtt),
        cache=StateCache(),
        retain_state=config.service.retain_state,
    )
    await runner.collect_and_publish(force_discovery=args.discovery)
    return 0


def _cmd_collect_once(args: argparse.Namespace) -> int:
    return asyncio.run(_collect_once_async(args))


def _cmd_validate(args: argparse.Namespace) -> int:
    validate_config_file(args.config)
    print(f"OK: {args.config}")
    return 0


def _cmd_render_addon(args: argparse.Namespace) -> int:
    options = load_options_file(args.options)
    cfg_path, sec_path = render_addon_config(options, args.config_dir)
    print(f"Wrote {cfg_path} and {sec_path}")
    return 0


async def _discovery_publish_async(args: argparse.Namespace) -> int:
    config, secrets = load_config(args.config, args.secrets)
    collectors = build_collectors(config, secrets)
    snapshots = []
    items: list[SnapshotPublish] = []
    for collector in collectors:
        snapshot = await collector.collect()
        snapshots.append(snapshot)
        metrics = effective_metrics(snapshot, collector.supported_metrics())
        items.append(SnapshotPublish(snapshot=snapshot, metrics=metrics))
    await MqttBridge(config.mqtt).publish_discovery_only(items)
    return 0


def _cmd_discovery_publish(args: argparse.Namespace) -> int:
    return asyncio.run(_discovery_publish_async(args))


if __name__ == "__main__":
    sys.exit(main())
