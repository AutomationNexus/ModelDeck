"""Configuration models and loader."""

from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from modeldeck.core.exceptions import ConfigError
from modeldeck.core.paths import config_path, secrets_path


class MqttConfig(BaseModel):
    """MQTT broker connection settings."""

    host: str = "homeassistant.local"
    port: int = 1883
    username: str = ""
    password: str = ""
    tls: bool = False
    client_id: str = "modeldeck"
    topic_prefix: str = "modeldeck"
    discovery_prefix: str = "homeassistant"


class ServiceConfig(BaseModel):
    """Service runtime settings."""

    poll_interval_seconds: int = Field(default=300, ge=60)
    retain_state: bool = True
    log_level: str = "INFO"
    persist_refreshed_tokens: bool = True


class ProviderToggle(BaseModel):
    """Enable flag and auth options for a provider (mock only; kept for testing)."""

    enabled: bool = False
    account_label: str | None = None
    auth_mode: str = "auto"
    credential_path: str | None = None


class ProviderAccount(BaseModel):
    """Multi-account entry for a real provider (codex / claude / cursor)."""

    id: str
    label: str = ""
    enabled: bool = False
    auth_mode: str = "auto"
    credential_path: str | None = None


class ProvidersConfig(BaseModel):
    """Per-provider enable flags."""

    mock: ProviderToggle = Field(default_factory=lambda: ProviderToggle(enabled=True))
    codex: list[ProviderAccount] = Field(default_factory=list)
    claude: list[ProviderAccount] = Field(default_factory=list)
    cursor: list[ProviderAccount] = Field(default_factory=list)

    @field_validator("codex", "claude", "cursor", mode="before")
    @classmethod
    def _coerce_account_list(cls, v: Any) -> list:
        """Migrate legacy single-dict format to list[ProviderAccount]."""
        if isinstance(v, dict):
            data = dict(v)
            if "id" not in data:
                data["id"] = "default"
            return [data]
        if isinstance(v, list):
            return v
        return []


class ProviderSecrets(BaseModel):
    """Provider credential fields."""

    api_key: str = ""
    session_token: str = ""
    access_token: str = ""
    refresh_token: str = ""
    account_id: str = ""
    org_id: str = ""
    device_id: str = ""
    cf_clearance: str = ""
    admin_api_key: str = ""
    subscription_tier: str = ""


# Fields recognised as belonging to a flat ProviderSecrets block.
_SECRETS_FIELDS: frozenset[str] = frozenset(
    {
        "api_key",
        "session_token",
        "access_token",
        "refresh_token",
        "account_id",
        "org_id",
        "device_id",
        "cf_clearance",
        "admin_api_key",
        "subscription_tier",
    }
)


class SecretsConfig(BaseModel):
    """Secrets loaded from secrets.yaml."""

    mqtt: dict[str, str] = Field(default_factory=dict)
    providers: dict[str, dict[str, ProviderSecrets]] = Field(default_factory=dict)

    @field_validator("providers", mode="before")
    @classmethod
    def _migrate_providers(cls, v: Any) -> dict:
        """Migrate flat ProviderSecrets dict to nested {account_id: ProviderSecrets}."""
        if not isinstance(v, dict):
            return {}
        migrated: dict[str, Any] = {}
        for pid, block in v.items():
            if not isinstance(block, dict):
                continue
            # A flat ProviderSecrets block has secret-field keys at the top level.
            if any(k in _SECRETS_FIELDS for k in block):
                migrated[pid] = {"default": block}
            else:
                migrated[pid] = block
        return migrated


class AppConfig(BaseModel):
    """Full application configuration."""

    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

    @field_validator("mqtt")
    @classmethod
    def validate_topic_prefix(cls, value: MqttConfig) -> MqttConfig:
        """Ensure topic prefix has no leading or trailing slashes."""
        value.topic_prefix = value.topic_prefix.strip("/")
        value.discovery_prefix = value.discovery_prefix.strip("/")
        return value


def slugify(label: str, existing: set[str] | None = None) -> str:
    """Convert label to a lowercase slug; suffix with _2, _3 on collision."""
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "account"
    slug = base
    n = 2
    while existing and slug in existing:
        slug = f"{base}_{n}"
        n += 1
    return slug


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Expected mapping in {path}")
    return data


def merge_secrets(config: AppConfig, secrets: SecretsConfig) -> AppConfig:
    """Merge secrets into the public config copy."""
    merged = config.model_copy(deep=True)
    if secrets.mqtt.get("password"):
        merged.mqtt.password = secrets.mqtt["password"]
    return merged


def load_config(
    config_file: Path | None = None,
    secrets_file: Path | None = None,
) -> tuple[AppConfig, SecretsConfig]:
    """Load and validate configuration and secrets."""
    cfg_path = config_file or config_path()
    sec_path = secrets_file or secrets_path()
    config = AppConfig.model_validate(_load_yaml(cfg_path))
    secrets = SecretsConfig.model_validate(_load_yaml(sec_path))
    return merge_secrets(config, secrets), secrets


def validate_config_file(path: Path) -> AppConfig:
    """Validate a config YAML file without secrets."""
    return AppConfig.model_validate(_load_yaml(path))


def check_secrets_permissions(path: Path | None = None) -> list[str]:
    """Return warnings for overly permissive secrets file."""
    sec_path = path or secrets_path()
    warnings: list[str] = []
    if not sec_path.exists():
        return warnings
    mode = stat.S_IMODE(sec_path.stat().st_mode)
    if mode & stat.S_IROTH or mode & stat.S_IWOTH:
        warnings.append(f"secrets file {sec_path} is world-readable or world-writable")
    return warnings
