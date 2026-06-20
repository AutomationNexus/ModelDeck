"""Atomic updates to secrets.yaml for refreshed OAuth tokens."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import yaml

from modeldeck.config.loader import ProviderSecrets, load_config, secrets_path
from modeldeck.core.logging import get_logger

logger = get_logger(__name__)

_OAUTH_FIELDS = ("access_token", "refresh_token", "account_id")


def persist_provider_oauth_tokens(
    provider_id: str,
    secrets: ProviderSecrets,
    *,
    secrets_file: Path | None = None,
) -> bool:
    """Merge refreshed OAuth fields into secrets.yaml when persistence is enabled."""
    try:
        config, _ = load_config()
        if not config.service.persist_refreshed_tokens:
            return False
    except Exception:
        return False

    path = secrets_file or secrets_path()
    if not path.exists() or not os.access(path, os.W_OK):
        return False

    try:
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        logger.warning("Could not read secrets file for token persistence")
        return False

    if not isinstance(raw, dict):
        return False

    providers = raw.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        raw["providers"] = providers

    provider_block = providers.setdefault(provider_id, {})
    if not isinstance(provider_block, dict):
        provider_block = {}
        providers[provider_id] = provider_block

    updated = False
    for field in _OAUTH_FIELDS:
        value = getattr(secrets, field, "")
        if value and provider_block.get(field) != value:
            provider_block[field] = value
            updated = True

    if not updated:
        return False

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    logger.info("Persisted refreshed OAuth tokens for provider %s", provider_id)
    return True
