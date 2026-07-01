"""Tests for the per-account entities endpoint and static SPA serving."""

from __future__ import annotations

from pathlib import Path

import yaml
from starlette.testclient import TestClient

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
# Entities endpoint
# ---------------------------------------------------------------------------

class TestEntitiesEndpoint:
    def test_returns_entities_for_codex_account(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/codex/work/entities")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "codex"
        assert data["account_id"] == "work"
        assert "device_id" in data
        assert "availability_topic" in data
        assert len(data["entities"]) > 0
        # Check shape of one entity
        e = data["entities"][0]
        assert "entity_id" in e
        assert "state_topic" in e
        assert "discovery_topic" in e
        assert e["entity_id"].startswith("sensor.modeldeck_codex_work_")

    def test_returns_entities_for_claude_account(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/claude/personal/entities")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "claude"
        for e in data["entities"]:
            assert "modeldeck_claude_personal_" in e["entity_id"]

    def test_load_config_error_returns_500(self, monkeypatch, tmp_path):
        """entities endpoint returns 500 when load_config raises."""
        client = _make_client(monkeypatch, tmp_path)

        def boom():
            raise RuntimeError("config corrupted")

        monkeypatch.setattr("modeldeck.webui.app.load_config", boom)
        r = client.get("/accounts/codex/work/entities")
        assert r.status_code == 500

    def test_unknown_account_404(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/codex/nonexistent/entities")
        assert r.status_code == 404

    def test_unknown_provider_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/unknown/work/entities")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Entities endpoint with auto auth_mode (covers app.py lines 828-829)
# ---------------------------------------------------------------------------

class TestEntitiesAutoAuthMode:
    def test_auto_auth_mode_codex_maps_to_subscription(self, monkeypatch, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        sec = tmp_path / "secrets.yaml"
        _write_config(cfg, {
            "codex": [{"id": "auto_acc", "label": "Auto", "enabled": True, "auth_mode": "auto"}],
            "claude": [],
            "cursor": [],
        })
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": {}}), encoding="utf-8")
        monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)
        client = TestClient(create_app())
        r = client.get("/accounts/codex/auto_acc/entities")
        assert r.status_code == 200
        # subscription metrics include usage_percent and reset_at
        entity_metrics = [e["metric"] for e in r.json()["entities"]]
        assert "usage_percent" in entity_metrics

    def test_auto_auth_mode_cursor_maps_to_personal(self, monkeypatch, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        sec = tmp_path / "secrets.yaml"
        _write_config(cfg, {
            "codex": [],
            "claude": [],
            "cursor": [{"id": "cur_auto", "label": "C", "enabled": True, "auth_mode": "auto"}],
        })
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": {}}), encoding="utf-8")
        monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)
        client = TestClient(create_app())
        r = client.get("/accounts/cursor/cur_auto/entities")
        assert r.status_code == 200
        entity_metrics = [e["metric"] for e in r.json()["entities"]]
        assert "usage_percent" in entity_metrics


# ---------------------------------------------------------------------------
# Static dir serving — covers app.py lines 315-318 (asset mounts) and 329
# (index.html served when the built SPA exists on disk). These are
# environment-dependent (only exercised when a frontend build artifact is
# present), so we deterministically point MODELDECK_STATIC_DIR at a fake
# built SPA directory for this test.
# ---------------------------------------------------------------------------

class TestStaticDirServing:
    def test_serves_built_index_html_and_mounts_assets(self, monkeypatch, tmp_path):
        static_dir = tmp_path / "static"
        assets_dir = static_dir / "assets"
        assets_dir.mkdir(parents=True)
        (static_dir / "index.html").write_text(
            "<html><body>Built SPA</body></html>", encoding="utf-8"
        )
        (assets_dir / "app.js").write_text("console.log('hi');", encoding="utf-8")

        monkeypatch.setenv("MODELDECK_STATIC_DIR", str(static_dir))
        client = TestClient(create_app())
        r = client.get("/")
        assert r.status_code == 200
        assert "Built SPA" in r.text

        # Confirm the /assets mount is live.
        r2 = client.get("/assets/app.js")
        assert r2.status_code == 200
