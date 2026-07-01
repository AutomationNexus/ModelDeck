#!/usr/bin/env python3
"""Bump HAOS add-on versions for stable packaging rev and nightly rolls."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STABLE_DIR = "modeldeck"
NIGHTLY_DIR = "modeldeck-nightly"
BUILD_FROM_RE = re.compile(r"^ARG\s+BUILD_FROM=(.+)$", re.MULTILINE)
STABLE_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)\.(\d+)$")
NIGHTLY_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)-nightly\.(\d{8})(?:\.(\d+))?$")
PARENT_SEMVER_RE = re.compile(r":v(\d+\.\d+\.\d+)")


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


def _read_build_from(root: Path, folder: str) -> str:
    docker = (root / folder / "Dockerfile").read_text(encoding="utf-8")
    match = BUILD_FROM_RE.search(docker)
    if not match:
        raise ValueError(f"BUILD_FROM not found in {folder}/Dockerfile")
    return match.group(1).strip()


def stable_packaging_rev(root: Path, *, note: str = "HAOS packaging update.") -> str:
    """Increment stable packaging revision (.R). Returns new version."""
    config_path = _config_path(root, STABLE_DIR)
    addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    version = str(addon["version"])
    match = STABLE_VERSION_RE.match(version)
    if not match:
        raise ValueError(f"invalid stable version {version!r}")
    base = match.group(1)
    rev = int(match.group(2))
    new_version = f"{base}.{rev + 1}"
    _save_version(config_path, addon, new_version)
    _prepend_changelog(_changelog_path(root, STABLE_DIR), new_version, note)
    return new_version


def stable_packaging_rev_after_promote(root: Path, old_main_sha: str) -> str | None:
    """Bump stable .R when modeldeck/ changed but parent image pin did not."""
    diff = subprocess.run(
        ["git", "diff", "--name-only", old_main_sha, "HEAD", "--", "modeldeck/"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    if not diff.stdout.strip():
        return None

    old_docker = subprocess.run(
        ["git", "show", f"{old_main_sha}:modeldeck/Dockerfile"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    new_docker = _read_build_from(root, STABLE_DIR)
    old_parent = PARENT_SEMVER_RE.search(old_docker.stdout)
    new_parent = PARENT_SEMVER_RE.search(new_docker)
    if not old_parent or not new_parent:
        return stable_packaging_rev(root)
    if old_parent.group(1) != new_parent.group(1):
        return None
    return stable_packaging_rev(root)


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
    """CLI entry: dispatch to the requested version-bump subcommand."""
    parser = argparse.ArgumentParser(description="Bump HAOS add-on versions")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stable-packaging-rev", help="Increment stable .R")

    promote = sub.add_parser(
        "promote-stable-bump-if-needed",
        help="After promote merge, bump stable .R when appropriate",
    )
    promote.add_argument("--old-main", required=True)
    promote.add_argument("--reason", default="HAOS stable packaging update.")

    nightly = sub.add_parser("nightly-roll", help="Roll nightly add-on version")
    nightly.add_argument("--parent-version", required=True)
    nightly.add_argument("--sha", default="")
    nightly.add_argument("--reason", default="")

    args = parser.parse_args()
    root = args.root.resolve()

    try:
        if args.command == "stable-packaging-rev":
            print(stable_packaging_rev(root))
        elif args.command == "promote-stable-bump-if-needed":
            new = stable_packaging_rev_after_promote(root, args.old_main)
            if new:
                print(new)
            else:
                print("skip")
        elif args.command == "nightly-roll":
            print(
                nightly_roll(
                    root,
                    args.parent_version,
                    args.sha,
                    args.reason or "Nightly build roll.",
                )
            )
    except (ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
