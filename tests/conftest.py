"""Pytest configuration."""

from __future__ import annotations

import os
import sys

import pytest

from modeldeck.collectors.metrics import base_metrics, effective_metrics
from modeldeck.config.loader import ProviderToggle
from modeldeck.mqtt.client import SnapshotPublish
from modeldeck.schemas.snapshot import ProviderSnapshot


def publish_item(snapshot: ProviderSnapshot, auth_mode: str = "mock") -> SnapshotPublish:
    """Build a SnapshotPublish for tests."""
    metrics = effective_metrics(snapshot, base_metrics(snapshot.provider_id, auth_mode))
    return SnapshotPublish(snapshot=snapshot, metrics=metrics)


@pytest.fixture(autouse=True)
def _clear_windows_path_env(monkeypatch):
    """Drop Windows-only env vars on Linux/macOS CI runners."""
    if sys.platform != "win32":
        for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
            if key in os.environ and "\\" in os.environ[key]:
                monkeypatch.delenv(key, raising=False)


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch):
    """Point config paths at a temporary directory."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("MODELDECK_DATA_DIR", str(data_dir))
    return config_dir, data_dir


def no_file_toggle(**kwargs: object) -> ProviderToggle:
    """Provider toggle that skips local credential file loading."""
    return ProviderToggle.model_validate({"credential_path": "", **kwargs})
