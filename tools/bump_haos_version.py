#!/usr/bin/env python3
"""Roll the nightly HAOS add-on version.

Stable add-on versioning has no separate bump logic — it is always exactly the
parent release version (see tools/sync_haos_addon.py); an add-on-only
packaging change is never released standalone, it ships bundled at the next
real release.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
NIGHTLY_DIR = "modeldeck-nightly"
NIGHTLY_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)-nightly\.(\d{8})(?:\.(\d+))?$")


def _config_path(root: Path, folder: str) -> Path:
    return root / folder / "config.yaml"


def _changelog_path(root: Path, folder: str) -> Path:
    return root / folder / "CHANGELOG.md"


def _save_version(config_path: Path, addon: dict, version: str) -> None:
    addon["version"] = version
    text = yaml.safe_dump(addon, sort_keys=False)
    text = re.sub(
        r"^version: .*$",
        f'version: "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    config_path.write_text(text, encoding="utf-8")


def _prepend_changelog(path: Path, version: str, body: str) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    entry = f"## [{version}] - {today}\n\n{body.strip()}\n\n"
    existing = path.read_text(encoding="utf-8") if path.is_file() else "# Changelog\n\n"
    if not existing.startswith("#"):
        existing = "# Changelog\n\n" + existing
    parts = existing.split("\n\n", 1)
    if len(parts) == 2 and parts[0].startswith("#"):
        path.write_text(f"{parts[0]}\n\n{entry}{parts[1]}", encoding="utf-8")
    else:
        path.write_text(existing + "\n" + entry, encoding="utf-8")


def nightly_roll(
    root: Path,
    parent_version: str,
    sha: str = "",
    note: str = "",
) -> str:
    """Roll nightly add-on version and changelog. Returns new version."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", parent_version.strip()):
        raise ValueError(f"parent_version must be X.Y.Z, got {parent_version!r}")

    config_path = _config_path(root, NIGHTLY_DIR)
    addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    current = str(addon.get("version", ""))
    today = datetime.now(UTC).strftime("%Y%m%d")

    build_num = 0
    match = NIGHTLY_VERSION_RE.match(current)
    if match and match.group(1) == parent_version and match.group(2) == today:
        build_num = int(match.group(3) or 0) + 1

    if build_num:
        new_version = f"{parent_version}-nightly.{today}.{build_num}"
    else:
        new_version = f"{parent_version}-nightly.{today}"

    _save_version(config_path, addon, new_version)
    body = note.strip() or "Nightly build roll."
    if sha:
        body = f"{body}\n\n- Parent SHA: `{sha[:12]}`"
    _prepend_changelog(_changelog_path(root, NIGHTLY_DIR), new_version, body)
    return new_version


def main() -> int:
    """CLI entry: roll the nightly add-on version."""
    parser = argparse.ArgumentParser(description="Roll the nightly HAOS add-on version")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    nightly = sub.add_parser("nightly-roll", help="Roll nightly add-on version")
    nightly.add_argument("--parent-version", required=True)
    nightly.add_argument("--sha", default="")
    nightly.add_argument("--reason", default="")

    args = parser.parse_args()
    root = args.root.resolve()

    try:
        if args.command == "nightly-roll":
            print(
                nightly_roll(
                    root,
                    args.parent_version,
                    args.sha,
                    args.reason or "Nightly build roll.",
                )
            )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
