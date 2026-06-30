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
    account_id: str = "default",
    *,
    secrets_file: Path | None = None,
) -> bool:
    """Merge refreshed OAuth fields into secrets.yaml when persistence is enabled.

    Writes under ``providers[provider_id][account_id]`` in the nested
    multi-account secrets format.

    Parameters
    ----------
    provider_id:
        e.g. ``"claude"`` or ``"codex"``.
    secrets:
        The refreshed ProviderSecrets object.
    account_id:
        The account slug (default ``"default"``).
    secrets_file:
        Override the secrets file path (for testing).
    """
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

    # Ensure provider block is nested {account_id: {fields}} format.
    provider_block = providers.setdefault(provider_id, {})
    if not isinstance(provider_block, dict):
        provider_block = {}
        providers[provider_id] = provider_block

    # If existing block is flat (legacy), migrate to nested on write.
    from modeldeck.config.addon_bootstrap import _ALL_SECRET_FIELDS

    if any(k in _ALL_SECRET_FIELDS for k in provider_block):
        # Flat format: migrate to nested under "default".
        provider_block = {"default": dict(provider_block)}
        providers[provider_id] = provider_block

    account_block = provider_block.setdefault(account_id, {})
    if not isinstance(account_block, dict):
        account_block = {}
        provider_block[account_id] = account_block

    updated = False
    for field in _OAUTH_FIELDS:
        value = getattr(secrets, field, "")
        if value and account_block.get(field) != value:
            account_block[field] = value
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
    logger.info(
        "Persisted refreshed OAuth tokens for provider %s account %s",
        provider_id,
        account_id,
    )
    return True


def move_account_secrets(
    provider_id: str,
    old_id: str,
    new_id: str,
    *,
    secrets_file: Path | None = None,
) -> bool:
    """Rename a secrets block from old_id to new_id within a provider.

    Used when an account rename changes the account slug (entity-id update
    path).  Atomic: writes to a temp file then replaces.

    Returns True if the block was moved, False if old_id was not found.
    """
    path = secrets_file or secrets_path()
    if not path.exists():
        return False

    try:
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        logger.warning("Could not read secrets file for account move")
        return False

    if not isinstance(raw, dict):
        return False

    providers = raw.get("providers", {})
    if not isinstance(providers, dict):
        return False

    provider_block = providers.get(provider_id, {})
    if not isinstance(provider_block, dict):
        return False

    # Migrate flat legacy format if needed.
    from modeldeck.config.addon_bootstrap import _ALL_SECRET_FIELDS

    if any(k in _ALL_SECRET_FIELDS for k in provider_block):
        provider_block = {"default": dict(provider_block)}
        providers[provider_id] = provider_block

    if old_id not in provider_block:
        return False

    provider_block[new_id] = provider_block.pop(old_id)
    raw["providers"][provider_id] = provider_block

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    try:
        import os as _os
        _os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    logger.info(
        "Moved secrets for provider %s: %s -> %s",
        provider_id, old_id, new_id,
    )
    return True


def write_account_secrets(
    provider_id: str,
    account_id: str,
    fields: dict[str, str],
    *,
    secrets_file: Path | None = None,
) -> bool:
    """Write arbitrary secret fields for a provider account into secrets.yaml.

    Used by the login wizard and web UI to save newly obtained tokens.
    Only non-empty field values are written.

    Parameters
    ----------
    provider_id:
        e.g. ``"claude"`` or ``"codex"``.
    account_id:
        The account slug.
    fields:
        Dict of secret field names → values.
    secrets_file:
        Override the secrets file path (for testing).
    """
    path = secrets_file or secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, yaml.YAMLError):
            logger.warning("Could not read secrets file; will overwrite")

    providers = raw.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        raw["providers"] = providers

    provider_block = providers.setdefault(provider_id, {})
    if not isinstance(provider_block, dict):
        provider_block = {}
        providers[provider_id] = provider_block

    # Migrate flat format if needed.
    from modeldeck.config.addon_bootstrap import _ALL_SECRET_FIELDS

    if any(k in _ALL_SECRET_FIELDS for k in provider_block):
        provider_block = {"default": dict(provider_block)}
        providers[provider_id] = provider_block

    account_block = provider_block.setdefault(account_id, {})
    if not isinstance(account_block, dict):
        account_block = {}
        provider_block[account_id] = account_block

    for key, value in fields.items():
        if value:
            account_block[key] = value

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    logger.info(
        "Wrote secrets for provider %s account %s",
        provider_id,
        account_id,
    )
    return True
