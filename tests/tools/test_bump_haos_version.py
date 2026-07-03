"""Tests for tools/bump_haos_version.py's nightly version-string generation.

tools/ is a standalone-script directory, not part of the installed package, so it's
added to sys.path directly here rather than via the normal src/ pythonpath.
"""

from __future__ import annotations

import sys
from datetime import datetime as real_datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import bump_haos_version as bump_mod  # noqa: E402
from bump_haos_version import NIGHTLY_DIR, nightly_roll  # noqa: E402


class _FrozenDatetime:
    """Stand-in for the `datetime` class exposing only the `.now(tz)` used by the module."""

    def __init__(self, yyyymmdd: str) -> None:
        self._dt = real_datetime.strptime(yyyymmdd, "%Y%m%d")

    def now(self, tz=None):  # noqa: ANN001, ARG002
        return self._dt


@pytest.fixture
def addon_root(tmp_path: Path) -> Path:
    """A repo-root-shaped tmp dir with a minimal modeldeck-nightly/config.yaml."""
    addon = tmp_path / NIGHTLY_DIR
    addon.mkdir()
    (addon / "config.yaml").write_text('name: "x"\nversion: "0.0.0"\n', encoding="utf-8")
    return tmp_path


def _set_version(root: Path, version: str) -> None:
    (root / NIGHTLY_DIR / "config.yaml").write_text(
        f'name: "x"\nversion: "{version}"\n', encoding="utf-8"
    )


def test_first_build_of_day_gets_dot_zero(addon_root: Path) -> None:
    """No prior same-day/same-parent nightly pointer -> counter starts at .0."""
    result = nightly_roll(addon_root, "0.0.8")
    assert result.startswith("0.0.8-nightly.")
    assert result.endswith(".0")


def test_new_day_resets_counter_to_zero(addon_root: Path) -> None:
    """A prior nightly from a different (past) day is not a same-day re-roll -> resets to .0."""
    _set_version(addon_root, "0.0.8-nightly.20200101.3")
    result = nightly_roll(addon_root, "0.0.8")
    assert result.endswith(".0")
    assert "20200101" not in result


def test_legacy_bare_same_day_increments_to_one(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy bare (no-counter) same-day pointer rolls forward to .1, not staying bare."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.8-nightly.{today}")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}.1"


def test_existing_counter_increments(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing same-day .N counter increments by exactly one."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.8-nightly.{today}.1")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}.2"


def test_new_parent_version_resets_to_zero(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-day pointer for a different parent version resets to .0, not continuing its counter."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.7-nightly.{today}.1")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}.0"
