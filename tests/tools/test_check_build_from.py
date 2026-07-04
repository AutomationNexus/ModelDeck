"""Tests for tools/check_build_from.py's nightly version-format validation.

tools/ is a standalone-script directory, not part of the installed package, so it's
added to sys.path directly here rather than via the normal src/ pythonpath.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from check_build_from import NIGHTLY_VERSION_RE  # noqa: E402


@pytest.mark.parametrize(
    "version",
    [
        "0.0.7-nightly.20260701",  # legacy bare
        "0.0.7-nightly.20260630.7",  # legacy dot-counter
        "0.0.8-nightly.2026070401",  # current: merged 2-digit counter
        "0.0.8-nightly.202607040123",  # merged counter with >2 digits (overflow-safe)
    ],
)
def test_accepts_every_published_nightly_shape(version: str) -> None:
    assert NIGHTLY_VERSION_RE.match(version)


@pytest.mark.parametrize(
    "version",
    [
        "0.0.8",  # bare stable, not a nightly version at all
        "0.0.8-nightly.2026070",  # short date
        "0.0.8-beta.1",  # wrong modifier keyword
        "",
    ],
)
def test_rejects_invalid_nightly_versions(version: str) -> None:
    assert not NIGHTLY_VERSION_RE.match(version)
