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
    # User-editable nickname shown alongside the (non-editable, auto-generated)
    # label, e.g. "Claude - 1 (Work)". Purely cosmetic — never used to derive
    # entity ids, unique ids, or MQTT topics. Settable only via the web UI's
    # edit-alias action (PATCH /accounts/{provider}/{account_id}).
    alias: str = ""
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


# Human-readable provider display names, used to build the auto-generated
# account label ("{Provider Display Name} - {n}"). Single source of truth
# shared by the web UI (POST /accounts) and the CLI (login/accounts add).
PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "codex": "OpenAI",
    "claude": "Claude",
    "cursor": "Cursor",
}


def migrate_legacy_account_labels(cfg_path: Path) -> bool:
    """Rewrite legacy auto-generated account labels to the current format.

    Migrates the old "{Provider} {n}" format to the current
    "{Provider} - {n}" format, in place on disk. Only rewrites labels that
    exactly match the old server-generated pattern for a plain-integer
    account id — custom labels (e.g. a legacy "default" account, or an HA
    add-on's ``account_label`` option value) are never touched, so this can
    never clobber user data that doesn't fit the auto-generated pattern.

    Idempotent and safe to call on every process startup: a no-op once an
    account is already migrated (or was never in the old format). Returns
    True if the file was rewritten, False otherwise (including on any read
    error, where nothing is touched).
    """
    if not cfg_path.exists():
        return False
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return False
    if not isinstance(raw, dict):
        return False
    providers = raw.get("providers")
    if not isinstance(providers, dict):
        return False

    changed = False
    for provider_id, display_name in PROVIDER_DISPLAY_NAMES.items():
        accounts = providers.get(provider_id)
        if not isinstance(accounts, list):
            continue
        for acct in accounts:
            if not isinstance(acct, dict):
                continue
            account_id = str(acct.get("id", ""))
            if not account_id.isdigit():
                continue
            old_label = f"{display_name} {account_id}"
            if acct.get("label") == old_label:
                acct["label"] = f"{display_name} - {account_id}"
                changed = True

    if changed:
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return changed


def next_account_id(existing: set[str] | None = None) -> str:
    """Return the next available auto-incrementing integer account id.

    Ids are always plain positive integers ("1", "2", "3", ...), so the
    account id never contains the provider name and can never double up
    with the ``modeldeck_{provider_id}_{account_id}`` entity id template.
    Non-numeric existing ids (e.g. the legacy "default" id, or custom
    slugs created before account labels became auto-generated) are simply
    ignored. Gaps are filled: if ids "1" and "3" already exist, the next
    id is "2", not "4".
    """
    existing = existing or set()
    used = {int(x) for x in existing if x.isdigit()}
    n = 1
    while n in used:
        n += 1
    return str(n)


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
