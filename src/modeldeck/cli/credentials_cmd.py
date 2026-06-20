"""CLI commands for printing provider credentials."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from modeldeck.collectors.credentials.claude_auth import (
    default_claude_credentials_path,
    load_claude_oauth,
)
from modeldeck.collectors.credentials.codex_auth import default_codex_auth_path, load_codex_oauth
from modeldeck.collectors.credentials.cursor_auth import (
    default_cursor_state_db_path,
    load_cursor_access_token,
)
from modeldeck.config.loader import secrets_path

_PROVIDERS = ("codex", "claude", "cursor")


def _mask(value: str, *, full: bool) -> str:
    if full or len(value) <= 8:
        return value
    return f"{value[:4]}...{value[-4:]}"


def _codex_block(*, full: bool) -> dict[str, str]:
    tokens = load_codex_oauth()
    if not tokens:
        return {}
    if full:
        return {
            k: tokens[k] for k in ("access_token", "refresh_token", "account_id") if tokens.get(k)
        }
    return {
        "access_token": _mask(tokens.get("access_token", ""), full=False),
        "refresh_token": _mask(tokens.get("refresh_token", ""), full=False),
        "account_id": tokens.get("account_id", ""),
    }


def _claude_block(*, full: bool) -> dict[str, str]:
    tokens = load_claude_oauth()
    if not tokens:
        return {}
    if full:
        return {k: tokens[k] for k in ("access_token", "refresh_token") if tokens.get(k)}
    return {
        "access_token": _mask(tokens.get("access_token", ""), full=False),
        "refresh_token": _mask(tokens.get("refresh_token", ""), full=False),
    }


def _cursor_block(*, full: bool) -> dict[str, str]:
    token = load_cursor_access_token()
    if not token:
        return {}
    return {"access_token": _mask(token, full=full)}


def _provider_paths() -> dict[str, str]:
    return {
        "codex": str(default_codex_auth_path()),
        "claude": str(default_claude_credentials_path()),
        "cursor": str(default_cursor_state_db_path()),
    }


def _build_yaml(
    providers: list[str],
    *,
    full: bool,
) -> dict[str, Any]:
    builders = {
        "codex": _codex_block,
        "claude": _claude_block,
        "cursor": _cursor_block,
    }
    result: dict[str, Any] = {"providers": {}}
    for name in providers:
        block = builders[name](full=full)
        if block:
            result["providers"][name] = block
    return result


def _merge_into_secrets(data: dict[str, Any]) -> bool:
    path = secrets_path()
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    providers = existing.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        existing["providers"] = providers
    for provider_id, block in data.get("providers", {}).items():
        if not isinstance(block, dict):
            continue
        current = providers.setdefault(provider_id, {})
        if not isinstance(current, dict):
            current = {}
            providers[provider_id] = current
        for key, value in block.items():
            if value:
                current[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
    return True


def cmd_credentials_print(args: argparse.Namespace) -> int:
    """Print credential YAML blocks from local provider files."""
    if args.all:
        providers = list(_PROVIDERS)
    elif args.provider:
        providers = [args.provider]
    else:
        print("Specify --provider or --all")
        return 1

    data = _build_yaml(providers, full=args.full)
    if not data.get("providers"):
        paths = _provider_paths()
        print("# No credentials found. Expected paths:")
        for name in providers:
            print(f"#   {name}: {paths.get(name, '?')}")
        return 1

    print(yaml.safe_dump(data, sort_keys=False))

    if args.write_secrets:
        write_data = _build_yaml(providers, full=True)
        _merge_into_secrets(write_data)
        print(f"Merged into {secrets_path()}", flush=True)

    return 0


def register_credentials_commands(sub: argparse._SubParsersAction) -> None:
    """Register credentials subcommands on the CLI parser."""
    creds = sub.add_parser("credentials", help="Credential extraction helpers")
    creds_sub = creds.add_subparsers(dest="credentials_cmd", required=True)
    print_cmd = creds_sub.add_parser("print", help="Print secrets.yaml snippets from local files")
    print_cmd.add_argument("--provider", choices=_PROVIDERS)
    print_cmd.add_argument("--all", action="store_true", help="Print all providers")
    print_cmd.add_argument("--full", action="store_true", help="Print full token values")
    print_cmd.add_argument(
        "--write-secrets",
        action="store_true",
        help="Merge printed values into config/secrets.yaml",
    )
    print_cmd.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Override MODELDECK_CONFIG_DIR for --write-secrets",
    )
    print_cmd.set_defaults(func=_cmd_credentials_print_wrapper)


def _cmd_credentials_print_wrapper(args: argparse.Namespace) -> int:
    if args.config_dir is not None:
        import os

        os.environ["MODELDECK_CONFIG_DIR"] = str(args.config_dir)
    return cmd_credentials_print(args)
