#!/usr/bin/env python3
"""Compute stable HAOS add-on pin updates for a ModelDeck release version."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

HAOS_CONFIG_REL = Path("modeldeck/config.yaml")
HAOS_DOCKERFILE_REL = Path("modeldeck/Dockerfile")
BUILD_FROM_LINE = re.compile(r"^(ARG BUILD_FROM=)(.+)$", re.MULTILINE)
IMAGE_PREFIX = "ghcr.io/automationnexus/modeldeck:v"


def parse_version(tag: str) -> str:
    """Strip optional v prefix and validate semver X.Y.Z."""
    tag = tag.strip()
    if tag.startswith("v"):
        tag = tag[1:]
    if not re.fullmatch(r"\d+\.\d+\.\d+", tag):
        raise ValueError(f"tag must be semver vX.Y.Z, got {tag!r}")
    return tag


def read_haos_state(haos_root: Path) -> tuple[str, str]:
    """Return (config version, BUILD_FROM image) from HAOS add-on tree."""
    config_path = haos_root / HAOS_CONFIG_REL
    docker_path = haos_root / HAOS_DOCKERFILE_REL
    addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    version = str(addon["version"])
    docker_text = docker_path.read_text(encoding="utf-8")
    match = BUILD_FROM_LINE.search(docker_text)
    if not match:
        raise ValueError(f"BUILD_FROM not found in {docker_path}")
    return version, match.group(2).strip()


def apply_stable_pin(haos_root: Path, version: str) -> bool:
    """Update HAOS stable pin files. Returns True if files changed."""
    config_path = haos_root / HAOS_CONFIG_REL
    docker_path = haos_root / HAOS_DOCKERFILE_REL
    expected_image = f"{IMAGE_PREFIX}{version}"
    haos_version = f"{version}.0"

    current_version, current_build = read_haos_state(haos_root)
    if current_version == haos_version and current_build == expected_image:
        return False

    addon = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    addon["version"] = haos_version
    text = yaml.safe_dump(addon, sort_keys=False)
    text = re.sub(
        r"^version: .*$",
        f'version: "{haos_version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    config_path.write_text(text, encoding="utf-8")

    docker_text = docker_path.read_text(encoding="utf-8")
    new_docker = BUILD_FROM_LINE.sub(
        rf"\1{expected_image}",
        docker_text,
        count=1,
    )
    docker_path.write_text(new_docker, encoding="utf-8")
    return True


def main() -> int:
    """CLI entry: sync or check stable HAOS pin against a ModelDeck release tag."""
    parser = argparse.ArgumentParser(description="Sync ModelDeck-HAOS stable add-on pin")
    parser.add_argument("haos_root", type=Path, help="Path to ModelDeck-HAOS checkout")
    parser.add_argument("tag", help="ModelDeck release tag (e.g. v0.0.2)")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Exit 0 if already synced, 2 if update needed",
    )
    args = parser.parse_args()
    version = parse_version(args.tag)
    haos_root = args.haos_root.resolve()

    if args.check_only:
        current_version, current_build = read_haos_state(haos_root)
        expected = f"{IMAGE_PREFIX}{version}"
        expected_haos_version = f"{version}.0"
        if current_version == expected_haos_version and current_build == expected:
            print("already synced")
            return 0
        print(f"needs sync: version={current_version} build_from={current_build}")
        return 2

    changed = apply_stable_pin(haos_root, version)
    if changed:
        print(f"updated HAOS pin to v{version}")
    else:
        print("no changes needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
