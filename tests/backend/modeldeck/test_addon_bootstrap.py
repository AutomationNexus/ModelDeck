"""Tests for Home Assistant add-on options rendering."""

import json

import yaml

from modeldeck.config.addon_bootstrap import (
    _merge_secrets,
    addon_mqtt_client_id,
    build_config_dict,
    build_secrets_dict,
    load_options_file,
    normalize_mqtt_host,
    normalize_options,
    parse_mqtt_server,
    render_addon_config,
)
from modeldeck.config.loader import AppConfig, SecretsConfig

NESTED_DEFAULT_OPTIONS = {
    "mqtt": {"server": "mqtt://core-mosquitto:1883"},
    "service": {},
    "codex": {"enabled": False},
    "claude": {"enabled": False},
    "cursor": {"enabled": False},
}


def test_parse_mqtt_server_empty_and_host_port():
    """Empty server and host:port forms should use sensible defaults."""
    assert parse_mqtt_server("") == ("core-mosquitto", 1883, False)
    assert parse_mqtt_server("broker.local:8888") == ("broker.local", 8888, False)
    assert parse_mqtt_server("mqtt://core-mosquitto") == ("core-mosquitto", 1883, False)


def test_normalize_options_empty_dict():
    """Empty options should flatten to an empty dict."""
    assert normalize_options({}) == {}


def test_merge_secrets_repairs_invalid_provider_blocks():
    """Merge should skip invalid provider payloads and repair bad on-disk blocks."""
    merged = _merge_secrets(
        {"providers": {"codex": "stale"}},
        {
            "providers": {
                "codex": "ignored",
                "claude": {"session_token": "new-session"},
            }
        },
        reset=False,
    )
    assert merged["providers"]["claude"]["default"]["session_token"] == "new-session"
    assert "codex" not in merged["providers"]


def test_render_addon_config_chmod_error_is_ignored(tmp_path, monkeypatch):
    """chmod failures after writing secrets should not abort render."""
    config_dir = tmp_path / "config"

    def _boom(_mode: int) -> None:
        raise OSError("nope")

    monkeypatch.setattr(
        "modeldeck.config.addon_bootstrap.Path.chmod",
        lambda self, mode: _boom(mode),
        raising=False,
    )
    cfg_path, sec_path = render_addon_config(NESTED_DEFAULT_OPTIONS, config_dir)
    assert cfg_path.exists()
    assert sec_path.exists()


def test_merge_secrets_repairs_non_dict_current_block():
    """Merge should replace a corrupted on-disk provider block before applying UI fields."""
    merged = _merge_secrets(
        {"providers": {"codex": {"access_token": "keep"}}},
        {"providers": {"codex": {"api_key": "sk-admin-1"}}},
        reset=False,
    )
    # Force a non-dict current block through the repair branch.
    merged["providers"]["codex"] = "broken"
    merged = _merge_secrets(
        merged,
        {"providers": {"codex": {"api_key": "sk-admin-2"}}},
        reset=False,
    )
    assert merged["providers"]["codex"]["default"]["api_key"] == "sk-admin-2"


def test_build_config_dict_defaults():
    """Default nested options should produce valid HA-oriented MQTT settings."""
    config = build_config_dict(NESTED_DEFAULT_OPTIONS)
    assert config["mqtt"]["host"] == "core-mosquitto"
    assert config["mqtt"]["port"] == 1883
    assert config["providers"]["mock"]["enabled"] is False
    AppConfig.model_validate(config)


def test_parse_mqtt_server_zigbee2mqtt_style():
    """Broker URL should parse like Zigbee2MQTT server field."""
    assert parse_mqtt_server("mqtt://core-mosquitto:1883") == (
        "core-mosquitto",
        1883,
        False,
    )
    assert parse_mqtt_server("mqtts://broker.example.com:8883") == (
        "broker.example.com",
        8883,
        True,
    )


def test_normalize_mqtt_host_strips_scheme():
    """Legacy broker host values should normalize to hostname."""
    assert normalize_mqtt_host("mqtt://core-mosquitto") == "core-mosquitto"
    assert normalize_mqtt_host("core-mosquitto") == "core-mosquitto"


def test_normalize_options_nested_providers():
    """Nested provider blocks should flatten to internal keys."""
    flat = normalize_options(
        {
            "mqtt": {"server": "mqtt://broker.local:1883", "password": "pw"},
            "service": {"poll_interval_seconds": 120},
            "codex": {
                "enabled": True,
                "auth_mode": "api",
                "api_key": "sk-admin-test",
            },
            "claude": {"enabled": False},
            "cursor": {"enabled": False},
        }
    )
    assert flat["mqtt_host"] == "broker.local"
    assert flat["mqtt_password"] == "pw"
    assert flat["poll_interval_seconds"] == 120
    assert flat["codex_enabled"] is True
    assert flat["codex_api_key"] == "sk-admin-test"


def test_normalize_options_legacy_flat_keys():
    """Legacy flat add-on options should still work."""
    flat = normalize_options({"mqtt_host": "legacy.local", "codex_enabled": True})
    assert flat["mqtt_host"] == "legacy.local"
    assert flat["codex_enabled"] is True


def test_addon_mqtt_client_id_is_auto_assigned():
    """Client ID is set internally for the add-on, not from user options."""
    assert addon_mqtt_client_id() == "modeldeck"
    config = build_config_dict(NESTED_DEFAULT_OPTIONS)
    assert config["mqtt"]["client_id"] == "modeldeck"


def test_build_secrets_from_nested_options():
    """Provider secret fields should map from nested option groups."""
    secrets = build_secrets_dict(
        {
            "mqtt": {"password": "mqtt-secret"},
            "codex": {"enabled": True, "access_token": "codex-at"},
            "claude": {
                "enabled": True,
                "session_token": "claude-sid",
                "org_id": "org-1",
            },
            "cursor": {"enabled": False},
            "service": {},
        }
    )
    assert secrets["mqtt"]["password"] == "mqtt-secret"
    assert secrets["providers"]["codex"]["default"]["access_token"] == "codex-at"
    SecretsConfig.model_validate(secrets)


def test_render_addon_config_writes_files(tmp_path):
    """Render should write modeldeck.yaml and secrets.yaml."""
    options = {
        "mqtt": {"server": "mqtt://broker.local:1883", "password": "pw"},
        "service": {},
        "codex": {
            "enabled": True,
            "auth_mode": "subscription",
            "access_token": "token-a",
        },
        "claude": {"enabled": False},
        "cursor": {"enabled": False},
    }
    cfg_path, sec_path = render_addon_config(options, tmp_path)
    assert cfg_path.exists()
    assert sec_path.exists()
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert config["mqtt"]["host"] == "broker.local"
    assert config["providers"]["codex"][0]["enabled"] is True


def test_render_preserves_refreshed_oauth_tokens(tmp_path):
    """On-disk OAuth tokens should survive re-render with stale UI options."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "codex": {
                        "access_token": "refreshed-on-disk",
                        "refresh_token": "refresh-disk",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    options = {
        "mqtt": {"server": "mqtt://core-mosquitto:1883"},
        "service": {},
        "codex": {
            "enabled": True,
            "auth_mode": "subscription",
            "access_token": "stale-ui-token",
            "refresh_token": "stale-ui-refresh",
        },
        "claude": {"enabled": False},
        "cursor": {"enabled": False},
    }
    render_addon_config(options, config_dir)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["default"]["access_token"] == "refreshed-on-disk"
    assert raw["providers"]["codex"]["default"]["refresh_token"] == "refresh-disk"


def test_render_reset_secrets_overwrites(tmp_path):
    """reset_secrets should replace on-disk OAuth tokens from UI."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"providers": {"codex": {"access_token": "old"}}}),
        encoding="utf-8",
    )
    options = {
        "mqtt": {"server": "mqtt://core-mosquitto:1883"},
        "service": {"reset_secrets": True},
        "codex": {"enabled": True, "access_token": "new-from-ui"},
        "claude": {"enabled": False},
        "cursor": {"enabled": False},
    }
    render_addon_config(options, config_dir)
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["providers"]["codex"]["default"]["access_token"] == "new-from-ui"


def test_merge_updates_mqtt_password_from_ui(tmp_path):
    """UI MQTT password should overlay existing secrets on merge."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump({"mqtt": {"password": "old"}, "providers": {}}),
        encoding="utf-8",
    )
    render_addon_config(
        {
            "mqtt": {"server": "mqtt://core-mosquitto:1883", "password": "new-password"},
            "service": {},
            "codex": {"enabled": False},
            "claude": {"enabled": False},
            "cursor": {"enabled": False},
        },
        config_dir,
    )
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    assert raw["mqtt"]["password"] == "new-password"


def test_merge_adds_new_provider_fields(tmp_path):
    """Merge should add new fields while preserving existing OAuth tokens."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secrets_file = config_dir / "secrets.yaml"
    secrets_file.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "claude": {
                        "access_token": "keep-oauth",
                        "session_token": "old-session",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    render_addon_config(
        {
            "mqtt": {"server": "mqtt://core-mosquitto:1883"},
            "service": {},
            "codex": {"enabled": False},
            "claude": {
                "enabled": True,
                "access_token": "stale-ui",
                "session_token": "new-session",
                "org_id": "org-99",
            },
            "cursor": {"enabled": False},
        },
        config_dir,
    )
    raw = yaml.safe_load(secrets_file.read_text(encoding="utf-8"))
    claude = raw["providers"]["claude"]["default"]
    assert claude["access_token"] == "keep-oauth"
    assert claude["session_token"] == "new-session"
    assert claude["org_id"] == "org-99"


def test_load_options_file(tmp_path):
    """Options JSON loader should return a dict."""
    path = tmp_path / "options.json"
    path.write_text(
        json.dumps({"mqtt": {"server": "mqtt://core-mosquitto:1883"}}),
        encoding="utf-8",
    )
    assert load_options_file(path)["mqtt"]["server"] == "mqtt://core-mosquitto:1883"


def test_load_options_file_rejects_non_object(tmp_path):
    """Options file must contain a JSON object."""
    import pytest

    path = tmp_path / "options.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_options_file(path)


def test_cli_render_addon(tmp_path):
    """CLI render-addon should write config files from options JSON."""
    from modeldeck.cli.main import main

    config_dir = tmp_path / "config"
    options = tmp_path / "options.json"
    options.write_text(
        json.dumps(
            {
                "mqtt": {"server": "mqtt://broker:1883"},
                "service": {},
                "codex": {"enabled": False},
                "claude": {"enabled": False},
                "cursor": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "config",
            "render-addon",
            "--options",
            str(options),
            "--config-dir",
            str(config_dir),
        ]
    )
    assert code == 0
    assert (config_dir / "modeldeck.yaml").exists()
