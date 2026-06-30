"""Tests for modeldeck.auth.provider_specs."""

from __future__ import annotations

import pytest

from modeldeck.auth.provider_specs import (
    CLAUDE_SPEC,
    CODEX_SPEC,
    PROVIDER_SPECS,
    ProviderOAuthSpec,
    get_spec,
    supported_oauth_providers,
)

# ---------------------------------------------------------------------------
# Registry presence
# ---------------------------------------------------------------------------


def test_claude_spec_in_provider_specs():
    """CLAUDE_SPEC must be registered under 'claude'."""
    assert "claude" in PROVIDER_SPECS
    assert PROVIDER_SPECS["claude"] is CLAUDE_SPEC


def test_codex_spec_in_provider_specs():
    """CODEX_SPEC must be registered under 'codex'."""
    assert "codex" in PROVIDER_SPECS
    assert PROVIDER_SPECS["codex"] is CODEX_SPEC


# ---------------------------------------------------------------------------
# get_spec
# ---------------------------------------------------------------------------


def test_get_spec_claude_returns_provider_oauth_spec():
    """get_spec('claude') must return a ProviderOAuthSpec instance."""
    spec = get_spec("claude")
    assert isinstance(spec, ProviderOAuthSpec)
    assert spec.provider == "claude"


def test_get_spec_cursor_returns_none():
    """Cursor is not OAuth-capable; get_spec must return None."""
    assert get_spec("cursor") is None


def test_get_spec_unknown_returns_none():
    """Unknown provider should return None."""
    assert get_spec("nonexistent_provider") is None


# ---------------------------------------------------------------------------
# supported_oauth_providers
# ---------------------------------------------------------------------------


def test_supported_oauth_providers_contains_claude():
    assert "claude" in supported_oauth_providers()


def test_supported_oauth_providers_contains_codex():
    assert "codex" in supported_oauth_providers()


def test_supported_oauth_providers_not_cursor():
    """Cursor should NOT appear in the OAuth-capable list."""
    assert "cursor" not in supported_oauth_providers()


def test_supported_oauth_providers_sorted():
    """Return value should be sorted."""
    result = supported_oauth_providers()
    assert result == sorted(result)


# ---------------------------------------------------------------------------
# ProviderOAuthSpec fields are non-empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_non_empty_authorize_url(spec: ProviderOAuthSpec):
    assert spec.authorize_url


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_non_empty_token_url(spec: ProviderOAuthSpec):
    assert spec.token_url


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_non_empty_client_id(spec: ProviderOAuthSpec):
    assert spec.client_id


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_non_empty_scopes(spec: ProviderOAuthSpec):
    assert len(spec.scopes) > 0


# ---------------------------------------------------------------------------
# effective_* defaults (no env override)
# ---------------------------------------------------------------------------


def test_effective_authorize_url_default(monkeypatch):
    """effective_authorize_url returns the built-in URL when no env var is set."""
    monkeypatch.delenv("MODELDECK_CLAUDE_OAUTH_AUTHORIZE_URL", raising=False)
    assert CLAUDE_SPEC.effective_authorize_url == CLAUDE_SPEC.authorize_url


def test_effective_token_url_default(monkeypatch):
    monkeypatch.delenv("MODELDECK_CLAUDE_OAUTH_TOKEN_URL", raising=False)
    assert CLAUDE_SPEC.effective_token_url == CLAUDE_SPEC.token_url


def test_effective_client_id_default(monkeypatch):
    monkeypatch.delenv("MODELDECK_CLAUDE_OAUTH_CLIENT_ID", raising=False)
    assert CLAUDE_SPEC.effective_client_id == CLAUDE_SPEC.client_id


def test_effective_scopes_default(monkeypatch):
    monkeypatch.delenv("MODELDECK_CLAUDE_OAUTH_SCOPES", raising=False)
    assert CLAUDE_SPEC.effective_scopes == CLAUDE_SPEC.scopes


# ---------------------------------------------------------------------------
# effective_* with env overrides
# ---------------------------------------------------------------------------


def test_effective_authorize_url_env_override(monkeypatch):
    """MODELDECK_CLAUDE_OAUTH_AUTHORIZE_URL must override effective_authorize_url."""
    monkeypatch.setenv("MODELDECK_CLAUDE_OAUTH_AUTHORIZE_URL", "https://example.com/auth")
    assert CLAUDE_SPEC.effective_authorize_url == "https://example.com/auth"


def test_effective_client_id_env_override(monkeypatch):
    """MODELDECK_CLAUDE_OAUTH_CLIENT_ID must override effective_client_id."""
    monkeypatch.setenv("MODELDECK_CLAUDE_OAUTH_CLIENT_ID", "override-client-id")
    assert CLAUDE_SPEC.effective_client_id == "override-client-id"


def test_effective_scopes_env_override_space_separated(monkeypatch):
    """MODELDECK_CLAUDE_OAUTH_SCOPES (space-separated) must override effective_scopes."""
    monkeypatch.setenv("MODELDECK_CLAUDE_OAUTH_SCOPES", "openid offline_access profile")
    result = CLAUDE_SPEC.effective_scopes
    assert result == ("openid", "offline_access", "profile")


def test_effective_token_url_env_override(monkeypatch):
    monkeypatch.setenv("MODELDECK_CLAUDE_OAUTH_TOKEN_URL", "https://example.com/token")
    assert CLAUDE_SPEC.effective_token_url == "https://example.com/token"


def test_effective_redirect_uri_default(monkeypatch):
    monkeypatch.delenv("MODELDECK_CLAUDE_OAUTH_REDIRECT_URI", raising=False)
    assert CLAUDE_SPEC.effective_redirect_uri == CLAUDE_SPEC.redirect_uri


def test_effective_redirect_uri_env_override(monkeypatch):
    monkeypatch.setenv("MODELDECK_CLAUDE_OAUTH_REDIRECT_URI", "https://custom.example/cb")
    assert CLAUDE_SPEC.effective_redirect_uri == "https://custom.example/cb"


# ---------------------------------------------------------------------------
# No hardcoded secrets / user-specific data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_no_account_id(spec: ProviderOAuthSpec):
    """No user account IDs should appear in any string field."""
    for val in (spec.authorize_url, spec.token_url, spec.client_id, spec.redirect_uri):
        # Account IDs would typically look like UUIDs or numeric IDs combined with
        # user-specific context; just ensure no "account_id" literal leaks.
        assert "account_id" not in val.lower()


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_no_access_token(spec: ProviderOAuthSpec):
    """No access tokens should be hardcoded in spec fields."""
    for val in (spec.authorize_url, spec.token_url, spec.client_id, spec.redirect_uri):
        assert "access_token" not in val.lower()


@pytest.mark.parametrize("spec", [CLAUDE_SPEC, CODEX_SPEC])
def test_spec_has_no_refresh_token(spec: ProviderOAuthSpec):
    """No refresh tokens should be hardcoded in spec fields."""
    for val in (spec.authorize_url, spec.token_url, spec.client_id, spec.redirect_uri):
        assert "refresh_token" not in val.lower()
