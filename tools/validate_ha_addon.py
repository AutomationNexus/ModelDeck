#!/usr/bin/env python3
"""Validate Home Assistant add-on config.yaml structure."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
REPOSITORY = REPO_ROOT / "repository.yaml"
REQUIRED_ADDON_KEYS = {
    "name",
    "version",
    "slug",
    "description",
    "arch",
    "startup",
    "options",
    "schema",
}

ADDON_SPECS: dict[str, str] = {
    "modeldeck": "modeldeck",
    "modeldeck-nightly": "modeldeck-nightly",
}


def _validate_options_schema(
    options: Any,
    schema: Any,
    path: str,
    errors: list[str],
) -> None:
    """Recursively ensure each option key has a matching schema entry."""
    if not isinstance(options, dict) or not isinstance(schema, dict):
        return
    for key, value in options.items():
        item_path = f"{path}.{key}" if path else key
        if key not in schema:
            errors.append(f"option {item_path!r} has no schema entry")
            continue
        schema_value = schema[key]
        if isinstance(value, dict) and isinstance(schema_value, dict):
            _validate_options_schema(value, schema_value, item_path, errors)


def validate_addon_folder(folder: str, errors: list[str]) -> None:
    """Validate one add-on directory."""
    addon_root = REPO_ROOT / folder
    config_path = addon_root / "config.yaml"
    if not config_path.exists():
        errors.append(f"Missing {config_path}")
        return

    addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(addon, dict):
        errors.append(f"{folder}/config.yaml must be a mapping")
        return

    missing = REQUIRED_ADDON_KEYS - set(addon)
    if missing:
        errors.append(f"{folder}/config.yaml missing keys: {sorted(missing)}")

    options = addon.get("options", {})
    schema = addon.get("schema", {})
    _validate_options_schema(options, schema, "", errors)

    expected_slug = ADDON_SPECS.get(folder)
    slug = addon.get("slug")
    if expected_slug and slug != expected_slug:
        errors.append(f"{folder} slug must be {expected_slug!r}, got {slug!r}")

    if "addon_config" not in str(addon.get("map", [])):
        errors.append(f"{folder} map must include addon_config for /config persistence")

    icon = addon_root / "icon.png"
    logo = addon_root / "logo.png"
    if not icon.is_file():
        errors.append(f"Missing {icon}")
    if not logo.is_file():
        errors.append(f"Missing {logo}")

    mqtt_schema = schema.get("mqtt") if isinstance(schema, dict) else None
    if not isinstance(mqtt_schema, dict) or "server" not in mqtt_schema:
        errors.append(f"{folder} mqtt schema must include server url field")


def main() -> int:
    """Exit non-zero when add-on metadata is invalid."""
    errors: list[str] = []

    if not REPOSITORY.exists():
        errors.append(f"Missing {REPOSITORY}")
    else:
        repo = yaml.safe_load(REPOSITORY.read_text(encoding="utf-8"))
        if not isinstance(repo, dict) or not repo.get("url"):
            errors.append("repository.yaml must contain url")

    for folder in ADDON_SPECS:
        if (REPO_ROOT / folder / "config.yaml").is_file():
            validate_addon_folder(folder, errors)

    from check_build_from import check_build_from

    errors.extend(check_build_from())

    return report(errors)


def report(errors: list[str]) -> int:
    """Print validation errors and return an exit code."""
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("OK: add-on metadata valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
