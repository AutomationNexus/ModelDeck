"""Configuration models and loader."""

from __future__ import annotations

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
    """Enable flag and auth options for a provider."""

    enabled: bool = False
    account_label: str | None = None
    auth_mode: str = "auto"
    credential_path: str | None = None


class ProvidersConfig(BaseModel):
    """Per-provider enable flags."""

    mock: ProviderToggle = Field(default_factory=lambda: ProviderToggle(enabled=True))
    codex: ProviderToggle = Field(default_factory=ProviderToggle)
    claude: ProviderToggle = Field(default_factory=ProviderToggle)
    cursor: ProviderToggle = Field(default_factory=ProviderToggle)


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


class SecretsConfig(BaseModel):
    """Secrets loaded from secrets.yaml."""

    mqtt: dict[str, str] = Field(default_factory=dict)
    providers: dict[str, ProviderSecrets] = Field(default_factory=dict)


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
