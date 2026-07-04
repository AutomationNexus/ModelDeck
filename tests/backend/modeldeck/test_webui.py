"""Tests for modeldeck.webui.app — root, providers, accounts, oauth (part 1)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from modeldeck.config.loader import AppConfig, SecretsConfig
from modeldeck.webui.app import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_config(
    *,
    claude_accounts: list[dict] | None = None,
) -> AppConfig:
    """Build a minimal AppConfig with optional Claude accounts."""
    cfg = AppConfig()
    if claude_accounts:
        cfg = AppConfig.model_validate(
            {
                "providers": {
                    "claude": claude_accounts,
                    "codex": [],
                    "cursor": [],
                }
            }
        )
    return cfg


def _empty_secrets() -> SecretsConfig:
    return SecretsConfig()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    """TestClient with load_config mocked to return a minimal config."""
    default_account = [
        {"id": "default", "label": "Test Claude", "enabled": True, "auth_mode": "oauth"}
    ]
    cfg = _make_minimal_config(claude_accounts=default_account)
    secrets = _empty_secrets()

    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture()
def empty_client(monkeypatch):
    """TestClient with load_config returning empty providers."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


def test_root_returns_200(client):
    """GET / should return 200 with HTML."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_root_fallback_html_contains_modeldeck(client):
    """Fallback HTML should mention ModelDeck."""
    resp = client.get("/")
    assert "ModelDeck" in resp.text


# ---------------------------------------------------------------------------
# GET /providers
# ---------------------------------------------------------------------------


def test_providers_returns_200(client):
    resp = client.get("/providers")
    assert resp.status_code == 200


def test_providers_contains_claude(client):
    data = client.get("/providers").json()
    names = [p["name"] for p in data["providers"]]
    assert "Claude" in names


def test_providers_contains_codex(client):
    data = client.get("/providers").json()
    names = [p["name"] for p in data["providers"]]
    assert "OpenAI" in names


def test_providers_contains_cursor(client):
    data = client.get("/providers").json()
    names = [p["name"] for p in data["providers"]]
    assert "Cursor" in names


# ---------------------------------------------------------------------------
# GET /accounts
# ---------------------------------------------------------------------------


def test_accounts_empty_config_returns_200(empty_client):
    resp = empty_client.get("/accounts")
    assert resp.status_code == 200


def test_accounts_empty_config_returns_list(empty_client):
    data = empty_client.get("/accounts").json()
    assert isinstance(data, list)


def test_accounts_with_config_returns_account(client):
    data = client.get("/accounts").json()
    assert any(a["provider"] == "claude" for a in data)


def test_accounts_no_secret_values_in_response(client):
    """Account list must not leak any token/secret values."""
    text = client.get("/accounts").text
    assert "access_token" not in text
    assert "refresh_token" not in text


# ---------------------------------------------------------------------------
# POST /accounts — create account
# ---------------------------------------------------------------------------


def test_create_account_known_provider_returns_201(monkeypatch):
    """POST /accounts with a known provider should return 201."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr(
        "modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            json={"provider": "claude", "auth_mode": "oauth"},
        )
    assert resp.status_code == 201


def test_create_account_returns_account_id_and_provider(monkeypatch):
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr(
        "modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            json={"provider": "claude", "auth_mode": "oauth"},
        )
    data = resp.json()
    assert "id" in data
    assert data["provider"] == "claude"


def test_create_account_label_is_always_auto_generated(monkeypatch):
    """Account labels are always server-generated ("{Provider} {n}") and
    never customizable — even if a client sends a "label" field in the
    request body, it has no effect (there is no such field on the model).

    Regression for entity ids like sensor.modeldeck_claude_claude_1_...:
    the account id is always a plain auto-incrementing integer, which
    structurally can never re-embed the provider name.
    """
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr(
        "modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            # A client-supplied "label" is silently ignored — no such field
            # exists on CreateAccountRequest.
            json={"provider": "claude", "label": "claude 1", "auth_mode": "oauth"},
        )
    data = resp.json()
    assert data["id"] == "1"
    assert data["label"] == "Claude 1"
    assert not data["id"].startswith("claude")


def test_create_account_auto_numbers_per_provider(monkeypatch):
    """First account for a provider is always id "1" with a Provider-Display-Name
    label, regardless of what (if anything) is sent in the request body."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr(
        "modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            json={"provider": "codex", "auth_mode": "api"},
        )
    data = resp.json()
    assert data["label"] == "OpenAI 1"
    assert data["id"] == "1"


def test_create_account_auto_numbers_increment_with_existing_accounts(monkeypatch):
    """A second account for the same provider increments the id/label, and
    both entity ids stay distinct."""
    cfg = _make_minimal_config(
        claude_accounts=[
            {"id": "1", "label": "Claude 1", "enabled": True, "auth_mode": "oauth"}
        ]
    )
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr(
        "modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            json={"provider": "claude", "auth_mode": "oauth"},
        )
    data = resp.json()
    assert data["label"] == "Claude 2"
    assert data["id"] == "2"


def test_create_account_unknown_provider_returns_400(monkeypatch):
    """POST /accounts with unknown provider should return 400."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            json={"provider": "openai", "label": "Test", "auth_mode": "api"},
        )
    assert resp.status_code == 400


def test_create_account_response_no_secrets(monkeypatch):
    """POST /accounts response must not contain token/secret values."""
    cfg = _make_minimal_config()
    secrets = _empty_secrets()
    monkeypatch.setattr("modeldeck.webui.app.load_config", lambda: (cfg, secrets))
    monkeypatch.setattr(
        "modeldeck.webui.app.upsert_account_in_config", lambda *a, **kw: None
    )

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/accounts",
            json={"provider": "codex", "label": "My Codex", "auth_mode": "api"},
        )
    text = resp.text
    assert "access_token" not in text
    assert "refresh_token" not in text


# ---------------------------------------------------------------------------
# POST /accounts/{provider}/{account_id}/oauth/start
# ---------------------------------------------------------------------------


def test_oauth_start_claude_returns_200(client):
    resp = client.post("/accounts/claude/default/oauth/start")
    assert resp.status_code == 200


def test_oauth_start_claude_returns_authorize_url(client):
    data = client.post("/accounts/claude/default/oauth/start").json()
    assert "authorize_url" in data
    assert data["authorize_url"].startswith("https://")


def test_oauth_start_claude_returns_session_key(client):
    data = client.post("/accounts/claude/default/oauth/start").json()
    assert "session_key" in data
    assert len(data["session_key"]) > 0


def test_oauth_start_cursor_returns_400(client):
    """Cursor does not support OAuth — must return 400."""
    resp = client.post("/accounts/cursor/default/oauth/start")
    assert resp.status_code == 400


def test_oauth_start_unknown_provider_returns_400(client):
    resp = client.post("/accounts/unknown_provider/default/oauth/start")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /accounts/{provider}/{account_id}/oauth/complete
# ---------------------------------------------------------------------------


def test_oauth_complete_expired_session_returns_400(client):
    """Posting an unknown/expired session_key must return 400."""
    resp = client.post(
        "/accounts/claude/default/oauth/complete",
        json={"session_key": "nonexistent-key-xyz", "code_or_redirect": "some-code"},
    )
    assert resp.status_code == 400


def test_oauth_complete_missing_session_key_returns_400(client):
    resp = client.post(
        "/accounts/claude/default/oauth/complete",
        json={"session_key": "", "code_or_redirect": "some-code"},
    )
    assert resp.status_code == 400
