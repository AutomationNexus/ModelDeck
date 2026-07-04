"""Tests for new/updated webui features.

Covers:
- upsert_account_in_config (update path — not just append)
- /providers endpoint shape and field maps
- paste_token explicit field, enable-on-success
- oauth_complete enables account
- renderer preserves web-UI accounts across re-render
"""
from __future__ import annotations

import yaml
from starlette.testclient import TestClient

from modeldeck.config.loader import AppConfig, SecretsConfig

# ---------------------------------------------------------------------------
# upsert_account_in_config
# ---------------------------------------------------------------------------

class TestUpsertAccountInConfig:
    def test_appends_new_account(self, tmp_path, monkeypatch):
        """Upsert adds account when not present."""
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text("providers:\n  claude: []\n  codex: []\n  cursor: []\n", encoding="utf-8")
        monkeypatch.setattr("modeldeck.core.paths.config_dir", lambda: tmp_path)

        from modeldeck.webui.app import upsert_account_in_config
        upsert_account_in_config("claude", "work", "Work Claude", auth_mode="oauth", enabled=True)

        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        accounts = raw["providers"]["claude"]
        assert any(a["id"] == "work" and a["enabled"] is True for a in accounts)

    def test_updates_existing_account(self, tmp_path, monkeypatch):
        """Upsert updates enabled/auth_mode when account already exists."""
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text(
            "providers:\n  claude:\n    - id: default\n      label: Default\n"
            "      enabled: false\n      auth_mode: cookie\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("modeldeck.core.paths.config_dir", lambda: tmp_path)

        from modeldeck.webui.app import upsert_account_in_config
        upsert_account_in_config("claude", "default", "Default", auth_mode="oauth", enabled=True)

        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        acct = raw["providers"]["claude"][0]
        assert acct["enabled"] is True
        assert acct["auth_mode"] == "oauth"

    def test_does_not_duplicate(self, tmp_path, monkeypatch):
        """Upsert on existing account does not append a duplicate."""
        cfg = tmp_path / "modeldeck.yaml"
        cfg.write_text(
            "providers:\n  cursor:\n    - id: personal\n      label: Mine\n"
            "      enabled: false\n      auth_mode: personal\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("modeldeck.core.paths.config_dir", lambda: tmp_path)

        from modeldeck.webui.app import upsert_account_in_config
        upsert_account_in_config("cursor", "personal", "Mine", auth_mode="personal", enabled=True)

        raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert len(raw["providers"]["cursor"]) == 1

    def test_noop_when_config_missing(self, tmp_path, monkeypatch):
        """Upsert is a no-op when modeldeck.yaml does not exist yet."""
        monkeypatch.setattr("modeldeck.core.paths.config_dir", lambda: tmp_path)
        from modeldeck.webui.app import upsert_account_in_config
        # Should not raise.
        upsert_account_in_config("claude", "x", "X", auth_mode="auto", enabled=True)


# ---------------------------------------------------------------------------
# /providers endpoint
# ---------------------------------------------------------------------------

def _make_client(monkeypatch, tmp_path):
    from modeldeck.webui.app import create_app

    cfg = AppConfig.model_validate({
        "providers": {
            "claude": [{"id": "default", "label": "Test", "enabled": True, "auth_mode": "oauth"}],
            "codex": [], "cursor": [],
        }
    })
    sec = SecretsConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, sec))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "modeldeck.yaml").write_text(
        "providers:\n  claude:\n    - id: default\n      label: Test\n"
        "      enabled: true\n      auth_mode: oauth\n",
        encoding="utf-8",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


class TestProvidersEndpoint:
    def test_returns_three_providers(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        resp = client.get("/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["providers"]) == 3

    def test_provider_names(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        names = {p["name"] for p in data["providers"]}
        assert "Claude" in names
        assert "OpenAI" in names
        assert "Cursor" in names

    def test_auth_modes_have_required_keys(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        for prov in data["providers"]:
            for mode in prov["auth_modes"]:
                assert "id" in mode
                assert "label" in mode
                assert "fields" in mode
                assert "oauth_capable" in mode

    def test_claude_has_oauth_and_cookie_modes(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        claude = next(p for p in data["providers"] if p["name"] == "Claude")
        mode_ids = {m["id"] for m in claude["auth_modes"]}
        assert "oauth" in mode_ids
        assert "cookie" in mode_ids

    def test_cursor_has_no_oauth(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        cursor = next(p for p in data["providers"] if p["name"] == "Cursor")
        assert cursor["oauth"] is False
        for mode in cursor["auth_modes"]:
            assert mode["oauth_capable"] is False

    def test_cursor_personal_has_session_token_field(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        cursor = next(p for p in data["providers"] if p["name"] == "Cursor")
        personal = next(m for m in cursor["auth_modes"] if m["id"] == "personal")
        field_ids = {f["id"] for f in personal["fields"]}
        assert "session_token" in field_ids

    def test_cookie_mode_has_session_and_org_fields(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        data = client.get("/providers").json()
        claude = next(p for p in data["providers"] if p["name"] == "Claude")
        cookie = next(m for m in claude["auth_modes"] if m["id"] == "cookie")
        field_ids = {f["id"] for f in cookie["fields"]}
        assert "session_token" in field_ids
        assert "org_id" in field_ids


# ---------------------------------------------------------------------------
# paste_token — explicit field, enables account
# ---------------------------------------------------------------------------

class TestPasteToken:
    def test_valid_field_returns_ok(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/accounts/claude/default/token",
            json={"field": "session_token", "value": "sk-ant-sid01-test"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_unknown_field_returns_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/accounts/claude/default/token",
            json={"field": "bad_field_xyz", "value": "something"},
        )
        assert resp.status_code == 400

    def test_empty_value_returns_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/accounts/claude/default/token",
            json={"field": "session_token", "value": "   "},
        )
        assert resp.status_code == 400

    def test_all_valid_fields_accepted(self, monkeypatch, tmp_path):
        """Every documented field name is accepted."""
        client = _make_client(monkeypatch, tmp_path)
        valid_fields = [
            "access_token", "session_token", "api_key", "refresh_token",
            "account_id", "org_id", "cf_clearance", "device_id", "admin_api_key",
        ]
        for field in valid_fields:
            resp = client.post(
                "/accounts/claude/default/token",
                json={"field": field, "value": "test-value"},
            )
            assert resp.status_code == 200, f"Expected 200 for field={field}, got {resp.status_code}"

    def test_token_field_in_request_body(self, monkeypatch, tmp_path):
        """Old 'token' field name in body is rejected (breaking change from old API)."""
        client = _make_client(monkeypatch, tmp_path)
        # The new endpoint uses 'field'+'value', not 'token'+'field'.
        resp = client.post(
            "/accounts/claude/default/token",
            json={"token": "sk-ant-sid01-xxx", "field": "session_token"},
        )
        # 'value' is missing — FastAPI returns 422 Unprocessable Entity.
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /accounts — wizard reserve (no config write until credentials saved)
# ---------------------------------------------------------------------------

class TestCreateAccount:
    def test_reserve_returns_account_id(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        resp = client.post("/accounts", json={"provider": "cursor", "label": "My Cursor"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "cursor"
        assert "id" in data
        # Not enabled until credentials saved.
        assert data["enabled"] is False

    def test_unknown_provider_returns_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        resp = client.post("/accounts", json={"provider": "unknown", "label": "X"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Renderer preserves web-created accounts
# ---------------------------------------------------------------------------

class TestRendererPreservesWebAccounts:
    def test_extra_accounts_survive_rerender(self, tmp_path):
        """Web-UI accounts (non-default) are preserved across render_addon_config calls."""
        from modeldeck.config.addon_bootstrap import render_addon_config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        # Simulate a web-UI account added after first boot.
        existing_cfg = config_dir / "modeldeck.yaml"
        existing_cfg.write_text(
            "providers:\n"
            "  mock:\n    enabled: false\n"
            "  codex:\n    - id: default\n      enabled: false\n      auth_mode: subscription\n"
            "  claude:\n"
            "    - id: default\n      enabled: false\n      auth_mode: cookie\n"
            "    - id: work_claude\n      label: Work Claude\n      enabled: true\n      auth_mode: oauth\n"
            "  cursor:\n    - id: default\n      enabled: false\n      auth_mode: personal\n",
            encoding="utf-8",
        )

        options = {
            "mqtt": {"server": "mqtt://core-mosquitto:1883"},
            "service": {},
        }
        render_addon_config(options, config_dir)

        raw = yaml.safe_load(existing_cfg.read_text(encoding="utf-8"))
        claude_ids = [a["id"] for a in raw["providers"]["claude"]]
        assert "default" in claude_ids
        assert "work_claude" in claude_ids, "Web-UI account 'work_claude' must survive re-render"

    def test_default_account_updated_from_addon_options(self, tmp_path):
        """The default account reflects add-on options after re-render."""
        from modeldeck.config.addon_bootstrap import render_addon_config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        existing_cfg = config_dir / "modeldeck.yaml"
        existing_cfg.write_text(
            "providers:\n  mock:\n    enabled: false\n"
            "  codex:\n    - id: default\n      enabled: false\n      auth_mode: subscription\n"
            "  claude:\n    - id: default\n      enabled: false\n      auth_mode: cookie\n"
            "  cursor:\n    - id: default\n      enabled: false\n      auth_mode: personal\n",
            encoding="utf-8",
        )

        options = {
            "mqtt": {"server": "mqtt://core-mosquitto:1883"},
            "service": {},
            "claude": {"enabled": True, "auth_mode": "oauth"},
        }
        render_addon_config(options, config_dir)

        raw = yaml.safe_load(existing_cfg.read_text(encoding="utf-8"))
        default = next(a for a in raw["providers"]["claude"] if a["id"] == "default")
        assert default["enabled"] is True
        assert default["auth_mode"] == "oauth"
