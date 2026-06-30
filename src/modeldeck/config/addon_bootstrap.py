"""Render modeldeck.yaml and secrets.yaml from Home Assistant add-on options."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from modeldeck.config.loader import AppConfig, SecretsConfig

_OAUTH_FIELDS = ("access_token", "refresh_token", "account_id")

_PROVIDER_SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "codex": ("api_key", "access_token", "refresh_token", "account_id"),
    "claude": (
        "session_token",
        "org_id",
        "cf_clearance",
        "device_id",
        "access_token",
        "refresh_token",
        "subscription_tier",
    ),
    "cursor": ("session_token", "access_token", "refresh_token", "admin_api_key"),
}

_PROVIDER_AUTH_DEFAULTS: dict[str, str] = {
    "codex": "subscription",
    "claude": "cookie",
    "cursor": "personal",
}

# All known secret fields across providers (used for flat-vs-nested detection).
_ALL_SECRET_FIELDS: frozenset[str] = frozenset(
    field for fields in _PROVIDER_SECRET_FIELDS.values() for field in fields
)


def _opt(options: dict[str, Any], key: str, default: Any = "") -> Any:
    value = options.get(key, default)
    return default if value is None else value


def parse_mqtt_server(server: str) -> tuple[str, int, bool]:
    """Parse Zigbee2MQTT-style broker URL into host, port, and TLS flag."""
    value = server.strip()
    if not value:
        return "core-mosquitto", 1883, False

    if "://" in value:
        parsed = urlparse(value)
        host = (parsed.hostname or "core-mosquitto").strip()
        tls = parsed.scheme.lower() in {"mqtts", "ssl", "tls"}
        if parsed.port is not None:
            port = parsed.port
        else:
            port = 8883 if tls else 1883
        return host, port, tls

    tls = False
    host_part = value
    if ":" in value:
        host_part, _, port_text = value.rpartition(":")
        port = int(port_text)
        host = host_part.strip() or "core-mosquitto"
        return host, port, tls

    return value, 1883, tls


def normalize_mqtt_host(host: str) -> str:
    """Strip accidental URL scheme from a legacy broker host value."""
    host_value, _, _ = parse_mqtt_server(host)
    return host_value


def addon_mqtt_client_id() -> str:
    """Stable MQTT client ID for the HA add-on (not exposed in the UI)."""
    return "modeldeck"


def _is_nested_options(options: dict[str, Any]) -> bool:
    return any(key in options for key in ("mqtt", "service", "codex", "claude", "cursor"))


def _block(options: dict[str, Any], key: str) -> dict[str, Any]:
    value = options.get(key)
    return value if isinstance(value, dict) else {}


def normalize_options(options: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested HA add-on options (or pass through legacy flat keys)."""
    if not options:
        return {}
    if not _is_nested_options(options):
        return dict(options)

    flat: dict[str, Any] = {}
    mqtt = _block(options, "mqtt")
    host, port, tls = parse_mqtt_server(str(mqtt.get("server", "mqtt://core-mosquitto:1883")))
    flat["mqtt_host"] = host
    flat["mqtt_port"] = port
    flat["mqtt_tls"] = tls
    flat["mqtt_username"] = str(mqtt.get("username", ""))
    flat["mqtt_password"] = str(mqtt.get("password", ""))
    flat["mqtt_topic_prefix"] = str(mqtt.get("topic_prefix", "modeldeck"))
    flat["mqtt_discovery_prefix"] = str(mqtt.get("discovery_prefix", "homeassistant"))

    service = _block(options, "service")
    flat["poll_interval_seconds"] = service.get("poll_interval_seconds", 300)
    flat["retain_state"] = service.get("retain_state", True)
    flat["log_level"] = service.get("log_level", "INFO")
    flat["persist_refreshed_tokens"] = service.get("persist_refreshed_tokens", True)
    flat["reset_secrets"] = service.get("reset_secrets", False)

    for provider_id in ("codex", "claude", "cursor"):
        provider = _block(options, provider_id)
        flat[f"{provider_id}_enabled"] = bool(provider.get("enabled", False))
        flat[f"{provider_id}_auth_mode"] = str(
            provider.get("auth_mode", _PROVIDER_AUTH_DEFAULTS[provider_id])
        )
        flat[f"{provider_id}_account_label"] = provider.get("account_label", "")
        for field in _PROVIDER_SECRET_FIELDS[provider_id]:
            flat[f"{provider_id}_{field}"] = provider.get(field, "")

    return flat


def _provider_account(options: dict[str, Any], provider_id: str) -> dict[str, Any]:
    """Build the default ProviderAccount dict for a provider from flat options."""
    prefix = provider_id
    return {
        "id": "default",
        "label": _opt(options, f"{prefix}_account_label") or "",
        "enabled": bool(_opt(options, f"{prefix}_enabled", False)),
        "auth_mode": str(
            _opt(options, f"{prefix}_auth_mode", _PROVIDER_AUTH_DEFAULTS[provider_id])
        ),
    }


def _provider_secrets(options: dict[str, Any], provider_id: str) -> dict[str, str]:
    block: dict[str, str] = {}
    for field in _PROVIDER_SECRET_FIELDS[provider_id]:
        value = str(_opt(options, f"{provider_id}_{field}", "")).strip()
        if value:
            block[field] = value
    return block


def build_config_dict(
    options: dict[str, Any],
    existing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the public modeldeck.yaml mapping from add-on options.

    If *existing_config* is provided (the current on-disk modeldeck.yaml), any
    provider accounts beyond the add-on ``default`` account are preserved so
    that accounts created via the web UI survive an add-on restart.
    """
    opts = normalize_options(options)
    config: dict[str, Any] = {
        "mqtt": {
            "host": normalize_mqtt_host(str(_opt(opts, "mqtt_host", "core-mosquitto"))),
            "port": int(_opt(opts, "mqtt_port", 1883)),
            "username": str(_opt(opts, "mqtt_username", "")),
            "tls": bool(_opt(opts, "mqtt_tls", False)),
            "client_id": addon_mqtt_client_id(),
            "topic_prefix": str(_opt(opts, "mqtt_topic_prefix", "modeldeck")),
            "discovery_prefix": str(_opt(opts, "mqtt_discovery_prefix", "homeassistant")),
        },
        "service": {
            "poll_interval_seconds": int(_opt(opts, "poll_interval_seconds", 300)),
            "retain_state": bool(_opt(opts, "retain_state", True)),
            "log_level": str(_opt(opts, "log_level", "INFO")),
            "persist_refreshed_tokens": bool(_opt(opts, "persist_refreshed_tokens", True)),
        },
        "providers": {
            "mock": {"enabled": False},
            "codex": [_provider_account(opts, "codex")],
            "claude": [_provider_account(opts, "claude")],
            "cursor": [_provider_account(opts, "cursor")],
        },
    }

    # Merge web-UI accounts: preserve extra accounts (non-default) from existing config.
    if existing_config and isinstance(existing_config.get("providers"), dict):
        for provider_id in ("codex", "claude", "cursor"):
            existing_accounts = existing_config["providers"].get(provider_id, [])
            if not isinstance(existing_accounts, list):
                continue
            addon_default = config["providers"][provider_id][0]  # the default account
            # Keep non-default accounts that were created via the web UI.
            extra = [
                a for a in existing_accounts
                if isinstance(a, dict) and a.get("id") != "default"
            ]
            if extra:
                config["providers"][provider_id] = [addon_default, *extra]

    return config


def build_secrets_dict(options: dict[str, Any]) -> dict[str, Any]:
    """Build secrets.yaml content from add-on options."""
    opts = normalize_options(options)
    mqtt_password = str(_opt(opts, "mqtt_password", "")).strip()
    providers: dict[str, dict[str, Any]] = {}
    for provider_id in ("codex", "claude", "cursor"):
        block = _provider_secrets(opts, provider_id)
        if block:
            providers[provider_id] = {"default": block}
    secrets: dict[str, Any] = {"mqtt": {}, "providers": providers}
    if mqtt_password:
        secrets["mqtt"]["password"] = mqtt_password
    return secrets


def _normalize_providers_raw(providers: dict[str, Any]) -> dict[str, Any]:
    """Ensure provider secrets are in nested {account_id: {fields}} format."""
    result: dict[str, Any] = {}
    for pid, block in providers.items():
        if not isinstance(block, dict):
            continue  # Skip invalid/corrupted entries
        # Flat format: has secret field keys at the top level
        if any(k in _ALL_SECRET_FIELDS for k in block):
            result[pid] = {"default": block}
        else:
            result[pid] = block
    return result


def _merge_secrets(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    *,
    reset: bool,
) -> dict[str, Any]:
    """Merge UI secrets into on-disk secrets; refreshed OAuth tokens win over stale UI."""
    if reset or not existing:
        return incoming

    # Normalise both to nested {account_id: {fields}} format.
    existing_providers = _normalize_providers_raw(existing.get("providers") or {})
    incoming_providers = _normalize_providers_raw(incoming.get("providers") or {})

    # Start with existing MQTT, then overlay incoming password.
    merged_mqtt = dict(existing.get("mqtt") or {})
    incoming_mqtt = incoming.get("mqtt") or {}
    if isinstance(incoming_mqtt, dict) and incoming_mqtt.get("password"):
        merged_mqtt["password"] = incoming_mqtt["password"]

    # Merge provider account secrets.
    merged_providers: dict[str, Any] = {}

    for pid, accounts in existing_providers.items():
        merged_providers[pid] = dict(accounts) if isinstance(accounts, dict) else {}

    for pid, incoming_accounts in incoming_providers.items():
        if not isinstance(incoming_accounts, dict):
            continue
        if pid not in merged_providers:
            merged_providers[pid] = {}

        for account_id, incoming_fields in incoming_accounts.items():
            if not isinstance(incoming_fields, dict):
                continue
            current = merged_providers[pid].get(account_id, {})
            if not isinstance(current, dict):
                current = {}

            for field, value in incoming_fields.items():
                if not value:
                    continue
                if field in _OAUTH_FIELDS and str(current.get(field, "")).strip():
                    continue
                current[field] = value

            merged_providers[pid][account_id] = current

    return {
        "mqtt": merged_mqtt,
        "providers": merged_providers,
    }


def render_addon_config(
    options: dict[str, Any],
    config_dir: Path,
    *,
    secrets_path: Path | None = None,
) -> tuple[Path, Path]:
    """Write modeldeck.yaml and secrets.yaml from add-on options."""
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_dir / "modeldeck.yaml"
    sec_path = secrets_path or config_dir / "secrets.yaml"

    opts = normalize_options(options)

    # Load existing modeldeck.yaml so web-UI accounts survive re-render.
    existing_config: dict[str, Any] = {}
    if cfg_path.exists():
        loaded_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded_cfg, dict):
            existing_config = loaded_cfg

    config_dict = build_config_dict(opts, existing_config=existing_config)
    secrets_dict = build_secrets_dict(opts)

    AppConfig.model_validate(config_dict)
    SecretsConfig.model_validate(secrets_dict)

    existing: dict[str, Any] = {}
    if sec_path.exists() and not bool(_opt(opts, "reset_secrets", False)):
        loaded = yaml.safe_load(sec_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded

    secrets_dict = _merge_secrets(
        existing,
        secrets_dict,
        reset=bool(_opt(opts, "reset_secrets", False)),
    )

    cfg_path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
    sec_path.write_text(yaml.safe_dump(secrets_dict, sort_keys=False), encoding="utf-8")
    try:
        sec_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return cfg_path, sec_path


def load_options_file(path: Path) -> dict[str, Any]:
    """Load add-on options from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("options must be a JSON object")
    return data
