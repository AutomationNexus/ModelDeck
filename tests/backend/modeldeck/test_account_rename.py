"""Tests for account rename and move_account_secrets."""

from __future__ import annotations

from pathlib import Path

import yaml
from starlette.testclient import TestClient

from modeldeck.config.secrets_writer import move_account_secrets
from modeldeck.webui.app import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(path: Path, providers: dict) -> None:
    data = {
        "mqtt": {"host": "localhost", "port": 1883, "username": "", "tls": False,
                 "client_id": "md", "topic_prefix": "modeldeck",
                 "discovery_prefix": "homeassistant"},
        "service": {"poll_interval_seconds": 300, "retain_state": True,
                    "log_level": "INFO", "persist_refreshed_tokens": True},
        "providers": {"mock": {"enabled": False}, **providers},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_secrets(path: Path, providers: dict) -> None:
    path.write_text(
        yaml.safe_dump({"mqtt": {}, "providers": providers}, sort_keys=False),
        encoding="utf-8",
    )


def _make_client(monkeypatch, tmp_path: Path) -> TestClient:
    cfg = tmp_path / "modeldeck.yaml"
    sec = tmp_path / "secrets.yaml"
    _write_config(cfg, {
        "codex": [{"id": "work", "label": "Work", "enabled": True, "auth_mode": "subscription"}],
        "claude": [{"id": "personal", "label": "Personal", "enabled": True, "auth_mode": "oauth"}],
        "cursor": [],
    })
    _write_secrets(sec, {
        "codex": {"work": {"access_token": "tok-work"}},
        "claude": {"personal": {"access_token": "tok-personal"}},
    })
    monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: cfg)
    monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
    monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)
    monkeypatch.setattr("modeldeck.config.secrets_writer.secrets_path", lambda: sec)
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# move_account_secrets
# ---------------------------------------------------------------------------

class TestMoveAccountSecrets:
    def test_moves_block(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        _write_secrets(sec, {"codex": {"old_id": {"access_token": "tok"}}})
        result = move_account_secrets("codex", "old_id", "new_id", secrets_file=sec)
        assert result is True
        raw = yaml.safe_load(sec.read_text())
        assert "new_id" in raw["providers"]["codex"]
        assert "old_id" not in raw["providers"]["codex"]
        assert raw["providers"]["codex"]["new_id"]["access_token"] == "tok"

    def test_returns_false_when_missing(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        _write_secrets(sec, {"codex": {}})
        assert move_account_secrets("codex", "nonexistent", "new_id", secrets_file=sec) is False

    def test_returns_false_when_file_missing(self, tmp_path):
        assert move_account_secrets("codex", "a", "b", secrets_file=tmp_path / "nope.yaml") is False

    def test_migrates_flat_format(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        # Flat (legacy) format — no nested account_id key.
        sec.write_text(
            yaml.safe_dump({"mqtt": {}, "providers": {"codex": {"access_token": "flat_tok"}}}),
            encoding="utf-8",
        )
        result = move_account_secrets("codex", "default", "new_id", secrets_file=sec)
        assert result is True
        raw = yaml.safe_load(sec.read_text())
        assert raw["providers"]["codex"]["new_id"]["access_token"] == "flat_tok"

    def test_returns_false_on_yaml_read_error(self, tmp_path):
        """Corrupted YAML content hits the except (OSError, yaml.YAMLError) branch."""
        sec = tmp_path / "secrets.yaml"
        # Invalid YAML (unbalanced flow mapping) raises yaml.YAMLError on parse.
        sec.write_text("providers: {codex: [unterminated", encoding="utf-8")
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False

    def test_chmod_oserror_is_swallowed(self, tmp_path, monkeypatch):
        """chmod failure after a successful move does not raise (except OSError: pass)."""
        sec = tmp_path / "secrets.yaml"
        _write_secrets(sec, {"codex": {"old_id": {"access_token": "tok"}}})

        def boom_chmod(*a, **kw):
            raise OSError("cannot chmod")

        # move_account_secrets imports os as _os locally and calls _os.chmod —
        # patch the os module's chmod function (auto-restored by monkeypatch
        # at test teardown).
        monkeypatch.setattr("os.chmod", boom_chmod)
        result = move_account_secrets("codex", "old_id", "new_id", secrets_file=sec)
        assert result is True
        raw = yaml.safe_load(sec.read_text())
        assert "new_id" in raw["providers"]["codex"]


class TestMoveAccountSecretsEdgeCases:
    def test_returns_false_for_non_dict_raw(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        sec.write_text("- not a dict", encoding="utf-8")
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False

    def test_returns_false_for_non_dict_providers(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": "broken"}), encoding="utf-8")
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False

    def test_returns_false_for_non_dict_provider_block(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        sec.write_text(
            yaml.safe_dump({"mqtt": {}, "providers": {"codex": "broken_string"}}),
            encoding="utf-8",
        )
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False


# ---------------------------------------------------------------------------
# Rename endpoint
# ---------------------------------------------------------------------------

class TestRenameEndpoint:
    def test_label_only_rename(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/work/rename", json={"label": "My Work", "update_entity_id": False})
        assert r.status_code == 200
        data = r.json()
        assert data["account_id"] == "work"  # slug unchanged
        assert data["label"] == "My Work"
        assert data["entity_id_changed"] is False

    def test_entity_id_rename_changes_slug(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/work/rename", json={"label": "Home Office", "update_entity_id": True})
        assert r.status_code == 200
        data = r.json()
        assert data["account_id"] == "home_office"  # new slug
        assert data["entity_id_changed"] is True

    def test_entity_id_rename_slug_same_no_change(self, monkeypatch, tmp_path):
        """When new slug equals old slug, entity_id_changed is False."""
        client = _make_client(monkeypatch, tmp_path)
        # "Work" → "work" → same slug
        r = client.post("/accounts/codex/work/rename", json={"label": "Work", "update_entity_id": True})
        assert r.status_code == 200
        assert r.json()["entity_id_changed"] is False
        assert r.json()["account_id"] == "work"

    def test_empty_label_rejected(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/work/rename", json={"label": "  ", "update_entity_id": False})
        assert r.status_code == 400

    def test_unknown_account_404(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/nonexistent/rename", json={"label": "X", "update_entity_id": False})
        assert r.status_code == 404

    def test_entity_id_rename_migrates_secrets(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        client.post("/accounts/codex/work/rename", json={"label": "Home", "update_entity_id": True})
        sec = tmp_path / "secrets.yaml"
        raw = yaml.safe_load(sec.read_text())
        assert "home" in raw["providers"]["codex"]
        assert "work" not in raw["providers"]["codex"]

    def test_unknown_provider_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/unknown/work/rename", json={"label": "X", "update_entity_id": False})
        assert r.status_code == 400

    def test_config_not_found_404(self, monkeypatch, tmp_path):
        """rename returns 404 when modeldeck.yaml does not exist on disk."""
        missing_cfg = tmp_path / "missing.yaml"
        monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: missing_cfg)
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: missing_cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: tmp_path / "secrets.yaml")
        client = TestClient(create_app())
        r = client.post("/accounts/codex/work/rename", json={"label": "X", "update_entity_id": False})
        assert r.status_code == 404
