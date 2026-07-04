"""Tests for tools/bump_haos_version.py's nightly version-string generation.

tools/ is a standalone-script directory, not part of the installed package, so it's
added to sys.path directly here rather than via the normal src/ pythonpath.
"""

from __future__ import annotations

import sys
from datetime import datetime as real_datetime
from pathlib import Path

import pytest
from awesomeversion import AwesomeVersion

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


def test_first_build_of_day_gets_merged_counter_01(addon_root: Path) -> None:
    """No prior same-day/same-parent nightly pointer -> merged counter starts at 01."""
    result = nightly_roll(addon_root, "0.0.8")
    assert result.startswith("0.0.8-nightly.")
    assert result.endswith("01")
    # No second dot after "nightly." — a lone digit run is what keeps the
    # version comparable by HA's awesomeversion-based Update button.
    suffix = result.split("-nightly.", 1)[1]
    assert "." not in suffix


def test_new_day_resets_counter_to_01(addon_root: Path) -> None:
    """A prior nightly from a different (past) day is not a same-day re-roll -> resets to 01."""
    _set_version(addon_root, "0.0.8-nightly.2020010103")
    result = nightly_roll(addon_root, "0.0.8")
    assert result.endswith("01")
    assert "20200101" not in result


def test_legacy_bare_same_day_increments_to_01(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy bare (no-counter) same-day pointer rolls forward to merged 01."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.8-nightly.{today}")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}01"


def test_legacy_dot_counter_same_day_increments(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy dot-counter (X.Y.Z-nightly.YYYYMMDD.N) same-day pointer increments and merges."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.8-nightly.{today}.1")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}02"


def test_existing_merged_counter_increments(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing same-day merged counter increments by exactly one."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.8-nightly.{today}02")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}03"


def test_new_parent_version_resets_to_01(
    addon_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-day pointer for a different parent version resets to 01, not continuing its counter."""
    today = "20260704"
    monkeypatch.setattr(bump_mod, "datetime", _FrozenDatetime(today))
    _set_version(addon_root, f"0.0.7-nightly.{today}.1")
    result = nightly_roll(addon_root, "0.0.8")
    assert result == f"0.0.8-nightly.{today}01"


# ---------------------------------------------------------------------------
# Regression tests for the HA "Update button stays disabled" bug: these use
# the real `awesomeversion` library (pinned in pyproject.toml to the exact
# version HA Supervisor/Core ship) to prove the generated version strings are
# actually orderable, not just textually different. See the NIGHTLY_VERSION_RE
# comment in bump_haos_version.py for the full root-cause explanation.
# ---------------------------------------------------------------------------


def test_merged_format_compares_newer_same_day() -> None:
    older = AwesomeVersion("0.0.8-nightly.2026070401")
    newer = AwesomeVersion("0.0.8-nightly.2026070402")
    assert newer > older


def test_merged_format_compares_newer_across_days() -> None:
    older = AwesomeVersion("0.0.8-nightly.2026070401")
    newer = AwesomeVersion("0.0.8-nightly.2026070501")
    assert newer > older


def test_merged_format_compares_newer_than_legacy_bare_installed() -> None:
    """A live HA install still on a legacy bare pointer must see the new merged
    pointer as strictly newer, or its Update button stays disabled forever."""
    installed = AwesomeVersion("0.0.7-nightly.20260701")
    new = AwesomeVersion("0.0.7-nightly.2026070201")
    assert new > installed


def test_old_dot_counter_format_is_the_bug_we_fixed() -> None:
    """Documents the bug this change fixes: two dot-separated segments after
    "nightly." are NOT reliably orderable by awesomeversion, even though the
    version strings are textually different and chronologically ordered."""
    older = AwesomeVersion("0.0.8-nightly.20260704.1")
    newer = AwesomeVersion("0.0.8-nightly.20260705.1")
    assert not (newer > older)
    assert not (newer < older)


def test_known_limitation_pre_existing_dot_counter_installs_stay_stuck_until_parent_bumps() -> None:
    """Documents a known, pre-existing limitation this change does NOT retroactively
    fix: an install already stuck on an old two-dot pointer (`modifier_type` already
    unparseable/None) cannot be un-stuck by ANY same-parent-version nightly build,
    merged-format or not — `None` never compares against anything. This only
    self-resolves once the parent X.Y.Z version changes (a routine event — see the
    Versioning Cascade), because base-version differences are compared before the
    modifier and short-circuit correctly regardless of modifier shape. The pointer
    already published on `main` today is bare (not dot-counter), so this only
    affects installs that were already stuck on an old dot-counter value before
    this fix landed."""
    stuck_installed = AwesomeVersion("0.0.7-nightly.20260630.7")
    same_parent_new = AwesomeVersion("0.0.7-nightly.2026070101")
    assert not (same_parent_new > stuck_installed)  # still stuck: same parent, modifier unparseable

    next_parent_new = AwesomeVersion("0.0.8-nightly.2026070101")
    assert next_parent_new > stuck_installed  # un-stuck: base version differs, short-circuits
