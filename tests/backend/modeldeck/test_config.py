"""Config loader tests."""

from pathlib import Path

import yaml

from modeldeck.config.loader import AppConfig, load_config, validate_config_file


def test_validate_example_config():
    """Example template should validate."""
    root = Path(__file__).resolve().parents[3]
    cfg = validate_config_file(root / "templates" / "modeldeck.example.yaml")
    assert cfg.providers.mock.enabled is False
    assert cfg.providers.codex.auth_mode == "subscription"
    assert cfg.mqtt.topic_prefix == "modeldeck"


def test_load_config_merges_mqtt_password(tmp_config_dir):
    """Secrets password should merge into config."""
    config_dir, _ = tmp_config_dir
    (config_dir / "modeldeck.yaml").write_text(
        yaml.dump({"mqtt": {"host": "broker.local", "port": 1883}}),
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text(
        yaml.dump({"mqtt": {"password": "secret"}}),
        encoding="utf-8",
    )
    config, secrets = load_config(config_dir / "modeldeck.yaml", config_dir / "secrets.yaml")
    assert config.mqtt.password == "secret"
    assert secrets.mqtt["password"] == "secret"


def test_strips_topic_prefix_slashes():
    """Topic prefixes should not contain slashes."""
    cfg = AppConfig.model_validate(
        {"mqtt": {"topic_prefix": "/modeldeck/", "discovery_prefix": "/ha/"}}
    )
    assert cfg.mqtt.topic_prefix == "modeldeck"
    assert cfg.mqtt.discovery_prefix == "ha"
