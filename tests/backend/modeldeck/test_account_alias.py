"""Tests for the account alias feature.

The alias is a purely cosmetic, user-editable nickname shown alongside the
(non-editable, auto-generated) label — e.g. "Claude - 1 (Work)". It never
affects entity ids, unique ids, or MQTT topics, but it IS combined into the
Home Assistant device friendly name (mqtt/discovery.py).
"""
from __future__ import annotations

from datetime import UTC, datetime

import yaml
from starlette.testclient import TestClient

from modeldeck.config.loader import AppConfig, MqttConfig, SecretsConfig
from modeldeck.mqtt.discovery import build_discovery_payload
from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot
from modeldeck.webui.app import create_app


def _make_client(tmp_path, monkeypatch, *, alias: str = "", provider: str = "claude"):
    config_dir = tmp_path
    cfg = config_dir / "modeldeck.yaml"
    cfg.write_text(
        yaml.safe_dump({
            "providers": {
                provider: [
                    {
                        "id": "1",
                        "label": "Claude - 1" if provider == "claude" else "Account - 1",
                        "alias": alias,
                        "enabled": True,
                        "auth_mode": "oauth",
                    }
                ],
            }
        }),
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(config_dir))
    cfg_model = AppConfig.model_validate(yaml.safe_load(cfg.read_text(encoding="utf-8")))
    sec_model = SecretsConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg_model, sec_model))
    return TestClient(create_app(), raise_server_exceptions=False), cfg


class TestPatchAccountAlias:
    def test_sets_alias(self, tmp_path, monkeypatch):
        client, cfg = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"alias": "Work"})
        assert resp.status_code == 200
        assert resp.json()["alias"] == "Work"
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["claude"][0]["alias"] == "Work"

    def test_trims_whitespace(self, tmp_path, monkeypatch):
        client, cfg = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"alias": "  Work  "})
        assert resp.status_code == 200
        assert resp.json()["alias"] == "Work"

    def test_clears_alias_with_empty_string(self, tmp_path, monkeypatch):
        client, cfg = _make_client(tmp_path, monkeypatch, alias="Work")
        resp = client.patch("/accounts/claude/1", json={"alias": ""})
        assert resp.status_code == 200
        assert resp.json()["alias"] == ""
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["claude"][0]["alias"] == ""

    def test_rejects_alias_over_max_length(self, tmp_path, monkeypatch):
        client, _ = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"alias": "x" * 41})
        assert resp.status_code == 400

    def test_accepts_alias_at_exactly_max_length(self, tmp_path, monkeypatch):
        client, _ = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"alias": "x" * 40})
        assert resp.status_code == 200

    def test_rejects_non_string_alias(self, tmp_path, monkeypatch):
        client, _ = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"alias": 123})
        assert resp.status_code == 400

    def test_missing_body_still_returns_400(self, tmp_path, monkeypatch):
        """Existing behavior preserved: neither 'enabled' nor 'alias' -> 400."""
        client, _ = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"label": "Updated"})
        assert resp.status_code == 400

    def test_enabled_still_works_alongside_alias_support(self, tmp_path, monkeypatch):
        client, cfg = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "enabled": False}
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["claude"][0]["enabled"] is False

    def test_can_set_both_enabled_and_alias_together(self, tmp_path, monkeypatch):
        client, cfg = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/1", json={"enabled": False, "alias": "Home"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["alias"] == "Home"
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert raw["providers"]["claude"][0]["enabled"] is False
        assert raw["providers"]["claude"][0]["alias"] == "Home"

    def test_nonexistent_account_returns_404(self, tmp_path, monkeypatch):
        client, _ = _make_client(tmp_path, monkeypatch)
        resp = client.patch("/accounts/claude/999", json={"alias": "Work"})
        assert resp.status_code == 404


class TestLoadAccountsIncludesAlias:
    def test_get_accounts_includes_alias_field(self, tmp_path, monkeypatch):
        client, _ = _make_client(tmp_path, monkeypatch, alias="Work")
        resp = client.get("/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["alias"] == "Work"

    def test_get_accounts_alias_defaults_to_empty_string(self, tmp_path, monkeypatch):
        client, _ = _make_client(tmp_path, monkeypatch)
        resp = client.get("/accounts")
        data = resp.json()
        assert data[0]["alias"] == ""


class TestDiscoveryDeviceNameWithAlias:
    def _snapshot(self, *, label: str, alias: str) -> ProviderSnapshot:
        return ProviderSnapshot(
            provider_id="claude",
            display_name="Claude",
            collected_at=datetime.now(UTC),
            status=CollectorStatus.OK,
            account_id="1",
            account_label=label,
            account_alias=alias,
        )

    def test_device_name_combines_label_and_alias(self):
        mqtt = MqttConfig()
        snapshot = self._snapshot(label="Claude - 1", alias="Work")
        payload = build_discovery_payload(mqtt, snapshot, MetricKind.STATUS)
        assert payload["device"]["name"] == "Claude - 1 (Work)"

    def test_device_name_is_plain_label_without_alias(self):
        mqtt = MqttConfig()
        snapshot = self._snapshot(label="Claude - 1", alias="")
        payload = build_discovery_payload(mqtt, snapshot, MetricKind.STATUS)
        assert payload["device"]["name"] == "Claude - 1"

    def test_device_name_falls_back_to_display_name_without_label_or_alias(self):
        mqtt = MqttConfig()
        snapshot = self._snapshot(label="", alias="")
        payload = build_discovery_payload(mqtt, snapshot, MetricKind.STATUS)
        assert payload["device"]["name"] == "Claude"

    def test_entity_id_and_unique_id_unaffected_by_alias(self):
        """Alias must never leak into entity ids/unique ids — only the
        device friendly name changes."""
        mqtt = MqttConfig()
        snapshot = self._snapshot(label="Claude - 1", alias="Work")
        payload = build_discovery_payload(mqtt, snapshot, MetricKind.STATUS)
        assert "Work" not in payload["unique_id"]
        assert "Work" not in payload["object_id"]
        assert "Work" not in payload["default_entity_id"]
        assert payload["unique_id"] == "modeldeck_claude_1_status"
