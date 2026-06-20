"""Runtime path helpers."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CONFIG_DIR = Path("/config")
DEFAULT_DATA_DIR = Path("/data")


def config_dir() -> Path:
    """Return the configuration directory."""
    return Path(os.environ.get("MODELDECK_CONFIG_DIR", DEFAULT_CONFIG_DIR))


def data_dir() -> Path:
    """Return the data directory."""
    return Path(os.environ.get("MODELDECK_DATA_DIR", DEFAULT_DATA_DIR))


def config_path() -> Path:
    """Return the main config file path."""
    return config_dir() / "modeldeck.yaml"


def secrets_path() -> Path:
    """Return the secrets file path."""
    return config_dir() / "secrets.yaml"


def state_path() -> Path:
    """Return the persisted state cache path."""
    return data_dir() / "state.json"
