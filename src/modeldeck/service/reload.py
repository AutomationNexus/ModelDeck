"""Config-file watcher for live reload without a service restart."""

from __future__ import annotations

from pathlib import Path

from modeldeck.collectors.base import Collector, build_collectors
from modeldeck.config.loader import AppConfig, SecretsConfig, load_config
from modeldeck.core.logging import get_logger
from modeldeck.core.paths import config_path, secrets_path

logger = get_logger(__name__)


def _active_keys(config: AppConfig) -> set[tuple[str, str]]:
    """Return the set of (provider_id, account_id) pairs for enabled accounts."""
    keys: set[tuple[str, str]] = set()
    for provider_id in ("codex", "claude", "cursor"):
        accounts = getattr(config.providers, provider_id, [])
        for account in accounts:
            if account.enabled:
                keys.add((provider_id, account.id))
    return keys


class ConfigWatcher:
    """Track modification times of config/secrets files and reload on change."""

    def __init__(
        self,
        cfg_path: Path | None = None,
        sec_path: Path | None = None,
    ) -> None:
        self._cfg_path = cfg_path or config_path()
        self._sec_path = sec_path or secrets_path()
        self._cfg_mtime: float = self._mtime(self._cfg_path)
        self._sec_mtime: float = self._mtime(self._sec_path)

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def changed(self) -> bool:
        """Return True if either file has been modified since last check."""
        new_cfg = self._mtime(self._cfg_path)
        new_sec = self._mtime(self._sec_path)
        if new_cfg != self._cfg_mtime or new_sec != self._sec_mtime:
            self._cfg_mtime = new_cfg
            self._sec_mtime = new_sec
            return True
        return False

    def load(self) -> tuple[AppConfig, SecretsConfig, list[Collector], set[tuple[str, str]]]:
        """Load updated config and return collectors + active account keys."""
        config, secrets = load_config(self._cfg_path, self._sec_path)
        collectors = build_collectors(config, secrets)
        keys = _active_keys(config)
        logger.info(
            "Config reloaded: %d collector(s), %d active account(s)",
            len(collectors), len(keys),
        )
        return config, secrets, collectors, keys
