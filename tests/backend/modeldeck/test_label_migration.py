"""Tests for migrate_legacy_account_labels() and its startup call sites.

Covers the one-time, idempotent migration of auto-generated account labels
from the old "{Provider} {n}" format (no dash) to the current
"{Provider} - {n}" format, run automatically at webui and service startup.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from modeldeck.config.loader import migrate_legacy_account_labels


def _write_config(path: Path, providers: dict) -> None:
    path.write_text(yaml.safe_dump({"providers": providers}, sort_keys=False), encoding="utf-8")


class TestMigrateLegacyAccountLabels:
    def test_no_file_returns_false(self, tmp_path):
        assert migrate_legacy_account_labels(tmp_path / "nope.yaml") is False

    def test_migrates_exact_legacy_match(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        _write_config(cfg, {
            "codex": [{"id": "1", "label": "OpenAI 1", "enabled": True, "auth_mode": "subscription"}],
        })
        assert migrate_legacy_account_labels(cfg) is True
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["codex"][0]["label"] == "OpenAI - 1"

    def test_migrates_multiple_providers_and_accounts(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        _write_config(cfg, {
            "codex": [{"id": "1", "label": "OpenAI 1", "enabled": True, "auth_mode": "api"}],
            "claude": [
                {"id": "1", "label": "Claude 1", "enabled": True, "auth_mode": "oauth"},
                {"id": "2", "label": "Claude 2", "enabled": False, "auth_mode": "cookie"},
            ],
            "cursor": [{"id": "1", "label": "Cursor 1", "enabled": True, "auth_mode": "personal"}],
        })
        assert migrate_legacy_account_labels(cfg) is True
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["codex"][0]["label"] == "OpenAI - 1"
        assert raw["providers"]["claude"][0]["label"] == "Claude - 1"
        assert raw["providers"]["claude"][1]["label"] == "Claude - 2"
        assert raw["providers"]["cursor"][0]["label"] == "Cursor - 1"

    def test_already_migrated_is_a_noop(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        _write_config(cfg, {
            "codex": [{"id": "1", "label": "OpenAI - 1", "enabled": True, "auth_mode": "api"}],
        })
        assert migrate_legacy_account_labels(cfg) is False
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["codex"][0]["label"] == "OpenAI - 1"

    def test_never_touches_non_digit_ids(self, tmp_path):
        """Legacy 'default' account ids are never touched, even if a label
        happens to look pattern-like."""
        cfg = tmp_path / "modeldeck.yaml"
        _write_config(cfg, {
            "codex": [{"id": "default", "label": "OpenAI default", "enabled": True, "auth_mode": "api"}],
        })
        assert migrate_legacy_account_labels(cfg) is False
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["codex"][0]["label"] == "OpenAI default"

    def test_never_touches_custom_labels(self, tmp_path):
        """A custom label that doesn't exactly match the old auto-generated
        pattern (e.g. HA add-on account_label option, or 'Test Claude') is
        left completely untouched."""
        cfg = tmp_path / "modeldeck.yaml"
        _write_config(cfg, {
            "claude": [{"id": "1", "label": "Test Claude", "enabled": True, "auth_mode": "oauth"}],
        })
        assert migrate_legacy_account_labels(cfg) is False
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["claude"][0]["label"] == "Test Claude"

    def test_empty_label_is_a_noop(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        _write_config(cfg, {
            "claude": [{"id": "1", "label": "", "enabled": True, "auth_mode": "oauth"}],
        })
        assert migrate_legacy_account_labels(cfg) is False

    def test_corrupted_yaml_returns_false(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text("providers: {codex: [unterminated", encoding="utf-8")
        assert migrate_legacy_account_labels(cfg) is False

    def test_non_dict_root_returns_false(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text("- not a dict", encoding="utf-8")
        assert migrate_legacy_account_labels(cfg) is False

    def test_non_dict_providers_returns_false(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text(yaml.safe_dump({"providers": "broken"}), encoding="utf-8")
        assert migrate_legacy_account_labels(cfg) is False

    def test_non_list_accounts_block_is_skipped(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text(
            yaml.safe_dump({"providers": {"codex": "broken_string"}}), encoding="utf-8"
        )
        assert migrate_legacy_account_labels(cfg) is False

    def test_non_dict_account_entry_is_skipped(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text(
            yaml.safe_dump({"providers": {"codex": ["not_a_dict"]}}), encoding="utf-8"
        )
        assert migrate_legacy_account_labels(cfg) is False


class TestMigrationRunsAtWebuiStartup:
    def test_create_app_migrates_legacy_labels_on_disk(self, tmp_path, monkeypatch):
        from modeldeck.webui.app import create_app

        config_dir = tmp_path
        cfg = config_dir / "modeldeck.yaml"
        _write_config(cfg, {
            "codex": [{"id": "1", "label": "OpenAI 1", "enabled": True, "auth_mode": "api"}],
        })
        (config_dir / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")
        monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))

        create_app()

        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["codex"][0]["label"] == "OpenAI - 1"

    def test_create_app_survives_migration_failure(self, monkeypatch):
        """A migration failure must never prevent the app from starting."""
        from modeldeck.webui import app as webui_app

        def boom(_path):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(webui_app, "migrate_legacy_account_labels", boom)
        app = webui_app.create_app()
        assert app is not None


class TestMigrationRunsAtServiceStartup:
    @pytest.mark.asyncio
    async def test_run_service_migrates_legacy_labels_on_disk(self, tmp_config_dir, monkeypatch):
        from modeldeck.service.runner import run_service

        config_dir, _ = tmp_config_dir
        cfg = config_dir / "modeldeck.yaml"
        _write_config(cfg, {
            "codex": [{"id": "1", "label": "OpenAI 1", "enabled": True, "auth_mode": "api"}],
        })
        sec = config_dir / "secrets.yaml"
        sec.write_text("mqtt: {}\n")
        sec.chmod(0o644)

        monkeypatch.setattr(
            "modeldeck.service.runner.MqttBridge.set_offline",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "modeldeck.service.runner.CollectionRunner.run_loop",
            AsyncMock(side_effect=lambda interval, ev: ev.set()),
        )

        await run_service()

        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["codex"][0]["label"] == "OpenAI - 1"

    @pytest.mark.asyncio
    async def test_run_service_survives_migration_failure(self, tmp_config_dir, monkeypatch):
        """A migration failure must never prevent the service from starting."""
        from modeldeck.service.runner import run_service

        config_dir, _ = tmp_config_dir
        (config_dir / "modeldeck.yaml").write_text("providers:\n  mock:\n    enabled: true\n")
        sec = config_dir / "secrets.yaml"
        sec.write_text("mqtt: {}\n")
        sec.chmod(0o644)

        def boom(_path):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr("modeldeck.service.runner.migrate_legacy_account_labels", boom)
        monkeypatch.setattr(
            "modeldeck.service.runner.MqttBridge.set_offline",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "modeldeck.service.runner.CollectionRunner.run_loop",
            AsyncMock(side_effect=lambda interval, ev: ev.set()),
        )

        await run_service()
