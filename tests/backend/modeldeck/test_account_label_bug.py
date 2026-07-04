"""Regression tests for the account-label bug.

A brand-new wizard account (not yet on disk) must get the server-generated
"{Provider Display Name} {n}" label, never the bare account_id, whether it
goes through the OAuth path or the paste-credentials path. Re-pasting
credentials on an EXISTING account must preserve its label.

Split out of test_oauth_fixes.py to keep that file under the test-standards
line-count limit.
"""
from __future__ import annotations


def _make_webui_client(monkeypatch, tmp_path, provider="codex"):
    """A webui client with one existing account (id="default", label="Test")."""
    from starlette.testclient import TestClient

    from modeldeck.config.loader import AppConfig, SecretsConfig
    from modeldeck.webui.app import create_app

    accounts = [{"id": "default", "label": "Test", "enabled": False, "auth_mode": "api"}]
    providers_cfg: dict = {"codex": [], "claude": [], "cursor": []}
    providers_cfg[provider] = accounts

    cfg = AppConfig.model_validate({"providers": providers_cfg})
    sec = SecretsConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, sec))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "modeldeck.yaml").write_text(
        f"providers:\n  {provider}:\n    - id: default\n      label: Test\n"
        "      enabled: false\n      auth_mode: api\n",
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")
    return TestClient(create_app(), raise_server_exceptions=False)


def _make_new_account_client(monkeypatch, tmp_path, provider="codex"):
    """A webui client whose provider has NO existing accounts on disk yet —
    simulates the wizard reserving a brand-new account_id."""
    from starlette.testclient import TestClient

    from modeldeck.config.loader import AppConfig, SecretsConfig
    from modeldeck.webui.app import create_app

    providers_cfg: dict = {"codex": [], "claude": [], "cursor": []}
    cfg = AppConfig.model_validate({"providers": providers_cfg})
    sec = SecretsConfig()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, sec))
    monkeypatch.setattr("modeldeck.webui.app.write_account_secrets", lambda *a, **kw: True)
    monkeypatch.setenv("MODELDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "modeldeck.yaml").write_text(
        "providers:\n  codex: []\n  claude: []\n  cursor: []\n",
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text("providers: {}\n", encoding="utf-8")
    return TestClient(create_app(), raise_server_exceptions=False)


class TestNewAccountLabelBug:
    def test_oauth_start_new_account_gets_generated_label(self, monkeypatch, tmp_path):
        """oauth_start for a brand-new (not-yet-on-disk) account must return the
        server-generated label, never the bare account_id."""
        client = _make_new_account_client(monkeypatch, tmp_path, provider="codex")
        resp = client.post("/accounts/codex/1/oauth/start")
        assert resp.status_code == 200
        assert resp.json()["label"] == "OpenAI 1"

    def test_oauth_complete_new_account_persists_generated_label(self, monkeypatch, tmp_path):
        """The label returned by oauth_start must be what actually gets persisted
        by oauth_complete — not the bare account_id."""
        from modeldeck.webui import app as webui_app

        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["label"] = label

        client = _make_new_account_client(monkeypatch, tmp_path, provider="codex")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)

        start = client.post("/accounts/codex/1/oauth/start").json()
        session_key = start["session_key"]

        async def fake_exchange(spec, code, verifier, *, state=None, client=None):
            return {"access_token": "at", "refresh_token": "rt"}

        monkeypatch.setattr(webui_app, "exchange_code", fake_exchange)
        monkeypatch.setattr(webui_app, "parse_code_and_state", lambda x: ("code123", None))
        monkeypatch.setattr(webui_app, "extract_codex_account_id", lambda x: None)

        resp = client.post(
            "/accounts/codex/1/oauth/complete",
            json={"session_key": session_key, "code_or_redirect": "code123"},
        )
        assert resp.status_code == 200
        assert upserted.get("label") == "OpenAI 1"

    def test_paste_token_new_account_gets_generated_label(self, monkeypatch, tmp_path):
        """paste_token for a brand-new (not-yet-on-disk) account must upsert with
        the server-generated label, never the bare account_id."""
        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["label"] = label

        client = _make_new_account_client(monkeypatch, tmp_path, provider="cursor")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)

        resp = client.post(
            "/accounts/cursor/1/token",
            json={"field": "session_token", "value": "sometoken"},
        )
        assert resp.status_code == 200
        assert upserted.get("label") == "Cursor 1"

    def test_paste_token_existing_account_preserves_label(self, monkeypatch, tmp_path):
        """Re-pasting credentials on an already-existing account must NOT
        overwrite its stored label with the bare account_id."""
        upserted = {}

        def capture_upsert(provider, account_id, label, *, auth_mode, enabled):
            upserted["label"] = label

        client = _make_webui_client(monkeypatch, tmp_path, provider="cursor")
        monkeypatch.setattr("modeldeck.webui.app.upsert_account_in_config", capture_upsert)

        resp = client.post(
            "/accounts/cursor/default/token",
            json={"field": "session_token", "value": "sometoken"},
        )
        assert resp.status_code == 200
        assert upserted.get("label") == "Test"
