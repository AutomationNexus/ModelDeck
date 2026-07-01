#!/usr/bin/env python3
"""Validate Dockerfile BUILD_FROM matches add-on channel (stable vs nightly)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_FROM_RE = re.compile(r"^ARG\s+BUILD_FROM=(.+)$", re.MULTILINE)
STABLE_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)(?:\.(\d+))?$")
NIGHTLY_VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)-nightly\.\d{8}(?:\.\d+)?$")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Sentinel value used as fallback in the release workflow when GH_TOKEN is
# missing or gh api fails on a private repo.  This value must never land in
# a real add-on release.
_FORBIDDEN_PARENT = "0.0.0"

ADDON_SPECS: dict[str, dict[str, str]] = {
    "modeldeck": {"slug": "modeldeck", "channel": "stable"},
    "modeldeck-nightly": {"slug": "modeldeck-nightly", "channel": "nightly"},
}


class _Semver(NamedTuple):
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version: str) -> _Semver | None:
        m = SEMVER_RE.match(version.strip())
        if not m:
            return None
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def discover_addon_dirs(root: Path | None = None) -> list[Path]:
    """Return known add-on directories that exist under root."""
    root = root or REPO_ROOT
    dirs: list[Path] = []
    for name in ADDON_SPECS:
        path = root / name
        if (path / "config.yaml").is_file():
            dirs.append(path)
    return dirs


def _stable_parent_semver(addon_dir: Path) -> str | None:
    """Return the X.Y.Z parent semver from a stable add-on config, or None."""
    config_path = addon_dir / "config.yaml"
    try:
        addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        version = str(addon.get("version", "")) if isinstance(addon, dict) else ""
    except Exception:
        return None
    m = STABLE_VERSION_RE.match(version)
    return m.group(1) if m else None


def check_addon_build_from(addon_dir: Path) -> list[str]:
    """Return validation errors for one add-on folder."""
    errors: list[str] = []
    folder = addon_dir.name
    spec = ADDON_SPECS.get(folder)
    if not spec:
        errors.append(f"unknown add-on folder {folder!r}")
        return errors

    config_path = addon_dir / "config.yaml"
    docker_path = addon_dir / "Dockerfile"
    if not docker_path.is_file():
        errors.append(f"Missing {docker_path}")
        return errors

    docker_text = docker_path.read_text(encoding="utf-8")
    match = BUILD_FROM_RE.search(docker_text)
    if not match:
        errors.append(f"{folder}/Dockerfile must declare ARG BUILD_FROM=...")
        return errors
    build_from = match.group(1).strip()

    addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    version = str(addon.get("version", "")) if isinstance(addon, dict) else ""
    slug = str(addon.get("slug", "")) if isinstance(addon, dict) else ""

    if slug != spec["slug"]:
        errors.append(f"{folder} slug must be {spec['slug']!r}, got {slug!r}")

    if spec["channel"] == "nightly":
        if not build_from.endswith(":nightly"):
            errors.append(
                f"{folder} nightly channel requires BUILD_FROM ending with :nightly, "
                f"got {build_from!r}"
            )
        if not NIGHTLY_VERSION_RE.match(version):
            errors.append(
                f"{folder} nightly version must match X.Y.Z-nightly.YYYYMMDD[.n], "
                f"got {version!r}"
            )
    else:
        stable_match = STABLE_VERSION_RE.match(version)
        if not stable_match:
            errors.append(
                f"{folder} stable version must match X.Y.Z.R, got {version!r}"
            )
            return errors
        parent_semver = stable_match.group(1)

        # B2: reject the sentinel fallback value that the release workflow
        # emits when gh api fails without GH_TOKEN on a private repo.
        if parent_semver == _FORBIDDEN_PARENT:
            errors.append(
                f"{folder} stable version has forbidden parent semver {_FORBIDDEN_PARENT!r} "
                f"— this is the workflow fallback sentinel, not a real release. "
                f"Ensure GH_TOKEN is set and the release tag exists before syncing."
            )
            return errors

        expected = f"modeldeck:v{parent_semver}"
        if expected not in build_from:
            errors.append(
                f"{folder} stable channel requires BUILD_FROM containing {expected!r}, "
                f"got {build_from!r}"
            )

    return errors


def check_non_regression(root: Path | None = None) -> list[str]:
    """Return errors if stable parent semver regresses below the current on-disk version.

    B3: compares the proposed new version against the version already present
    in the stable add-on config.  This is an offline-safe check (no git/network)
    intended to catch accidental downgrades before they are committed.

    Pass ``new_parent`` via the ADDON_NEW_PARENT env var (X.Y.Z) to activate;
    if not set, the check is skipped (safe for normal local validation runs).
    """
    new_parent_str = os.environ.get("ADDON_NEW_PARENT", "").strip()
    if not new_parent_str:
        return []

    root = root or REPO_ROOT
    errors: list[str] = []
    new_sv = _Semver.parse(new_parent_str)
    if new_sv is None:
        errors.append(
            f"ADDON_NEW_PARENT={new_parent_str!r} is not a valid semver X.Y.Z"
        )
        return errors

    stable_dir = root / "modeldeck"
    current_parent = _stable_parent_semver(stable_dir)
    if current_parent is None:
        # Can't read current version — skip non-regression (not a blocking error).
        return []

    current_sv = _Semver.parse(current_parent)
    if current_sv is None:
        return []

    if new_sv < current_sv:
        errors.append(
            f"stable parent semver regression: proposed {new_parent_str!r} "
            f"< current {current_parent!r}. "
            f"Only forward-pinning is allowed. "
            f"Set ADDON_NEW_PARENT to the correct release tag."
        )
    return errors


def check_build_from(root: Path | None = None) -> list[str]:
    """Return validation errors for all add-ons."""
    root = root or REPO_ROOT
    errors: list[str] = []
    addon_dirs = discover_addon_dirs(root)
    if not addon_dirs:
        errors.append("no add-on directories found")
        return errors

    channel_filter = os.environ.get("ADDON_CHANNEL")
    for addon_dir in addon_dirs:
        folder = addon_dir.name
        if channel_filter and ADDON_SPECS[folder]["channel"] != channel_filter:
            continue
        errors.extend(check_addon_build_from(addon_dir))

    errors.extend(check_non_regression(root))
    return errors


def main() -> int:
    """CLI entry: exit non-zero when any add-on's BUILD_FROM pin is invalid."""
    errors = check_build_from()
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    channel = os.environ.get("ADDON_CHANNEL")
    if channel:
        print(f"OK: BUILD_FROM matches {channel} channel")
    else:
        print("OK: BUILD_FROM matches all add-on channels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
