"""Provider OAuth protocol metadata registry.

This module contains only non-secret, non-user-specific protocol constants
(authorize URLs, token URLs, public client IDs, required scopes).

All values are overridable via environment variables so a provider endpoint
change does not require a code edit.

No user credentials, account IDs, or tokens are stored here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderOAuthSpec:
    """Non-secret OAuth protocol metadata for one provider."""

    provider: str
    authorize_url: str
    token_url: str
    client_id: str
    scopes: tuple[str, ...]
    redirect_uri: str = "https://modeldeck.local/oauth/callback"
    # "json" (default) sends body as JSON; "form" sends application/x-www-form-urlencoded.
    # Codex token endpoint requires form-encoding; Claude accepts JSON.
    token_encoding: str = "json"
    # Extra key=value pairs appended to the authorization URL query string.
    extra_authorize_params: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def env(self, key: str, default: str) -> str:
        """Return an env-overridden value for this provider's protocol field."""
        env_key = f"MODELDECK_{self.provider.upper()}_OAUTH_{key.upper()}"
        return os.environ.get(env_key, default)

    @property
    def effective_authorize_url(self) -> str:
        """Authorize URL, overridable via MODELDECK_{PROVIDER}_OAUTH_AUTHORIZE_URL."""
        return self.env("AUTHORIZE_URL", self.authorize_url)

    @property
    def effective_token_url(self) -> str:
        """Token URL, overridable via MODELDECK_{PROVIDER}_OAUTH_TOKEN_URL."""
        return self.env("TOKEN_URL", self.token_url)

    @property
    def effective_client_id(self) -> str:
        """Client ID, overridable via MODELDECK_{PROVIDER}_OAUTH_CLIENT_ID."""
        return self.env("CLIENT_ID", self.client_id)

    @property
    def effective_scopes(self) -> tuple[str, ...]:
        """Scopes, overridable via MODELDECK_{PROVIDER}_OAUTH_SCOPES (space-separated)."""
        env_val = self.env("SCOPES", "")
        if env_val.strip():
            return tuple(env_val.strip().split())
        return self.scopes

    @property
    def effective_redirect_uri(self) -> str:
        """Redirect URI, overridable via MODELDECK_{PROVIDER}_OAUTH_REDIRECT_URI."""
        return self.env("REDIRECT_URI", self.redirect_uri)

    @property
    def effective_token_encoding(self) -> str:
        """Token encoding, overridable via MODELDECK_{PROVIDER}_OAUTH_TOKEN_ENCODING."""
        return self.env("TOKEN_ENCODING", self.token_encoding)

    @property
    def effective_extra_authorize_params(self) -> tuple[tuple[str, str], ...]:
        """Extra authorize params; individual values are env-overridable."""
        result = []
        for key, default in self.extra_authorize_params:
            env_key = f"MODELDECK_{self.provider.upper()}_OAUTH_{key.upper()}"
            result.append((key, os.environ.get(env_key, default)))
        return tuple(result)


# ---------------------------------------------------------------------------
# Claude OAuth spec
# Verified working: api.anthropic.com/api/oauth/usage returns 200 with these.
# Token URL: platform.claude.com/v1/oauth/token
# Client ID: public Claude Code client (non-secret, same as Claude CLI uses).
# Token endpoint accepts JSON body.
# ---------------------------------------------------------------------------
CLAUDE_SPEC = ProviderOAuthSpec(
    provider="claude",
    authorize_url="https://claude.ai/oauth/authorize",
    token_url="https://platform.claude.com/v1/oauth/token",
    client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    scopes=(
        "user:profile",
        "user:inference",
        "user:sessions:claude_code",
        "user:mcp_servers",
        "user:file_upload",
    ),
    redirect_uri="https://modeldeck.local/oauth/callback",
    token_encoding="json",
)

# ---------------------------------------------------------------------------
# Codex / ChatGPT OAuth spec
# Verified from openai/codex source (codex-rs/login/src/server.rs).
# Issuer: auth.openai.com (Hydra OAuth server)
# Client ID: public Codex CLI client (non-secret; same value used in
#             codex_subscription.py for token refresh).
# Redirect URI: http://localhost:1455/auth/callback (allow-listed by OpenAI).
#   Paste-back flow: the redirect page won't load (it goes to localhost on the
#   user's PC, not the HA host), but the user copies ?code=... from the
#   browser address bar and pastes it back into the web UI.
# Token endpoint requires application/x-www-form-urlencoded (not JSON).
# Extra authorize params match the Codex CLI's simplified login flow.
# ---------------------------------------------------------------------------
CODEX_SPEC = ProviderOAuthSpec(
    provider="codex",
    authorize_url="https://auth.openai.com/oauth/authorize",
    token_url="https://auth.openai.com/oauth/token",
    client_id="app_EMoamEEZ73f0CkXaXp7hrann",
    scopes=(
        "openid",
        "profile",
        "email",
        "offline_access",
        "api.connectors.read",
        "api.connectors.invoke",
    ),
    redirect_uri="http://localhost:1455/auth/callback",
    token_encoding="form",
    extra_authorize_params=(
        ("id_token_add_organizations", "true"),
        ("codex_cli_simplified_flow", "true"),
        # Overridable via MODELDECK_CODEX_OAUTH_ORIGINATOR
        ("originator", "codex_cli_rs"),
    ),
)

# ---------------------------------------------------------------------------
# Registry: provider_id -> spec (only OAuth-capable providers)
# Cursor is intentionally absent — no known public OAuth/device flow.
# ---------------------------------------------------------------------------
PROVIDER_SPECS: dict[str, ProviderOAuthSpec] = {
    "claude": CLAUDE_SPEC,
    "codex": CODEX_SPEC,
}


def get_spec(provider: str) -> ProviderOAuthSpec | None:
    """Return the OAuth spec for a provider, or None if not supported."""
    return PROVIDER_SPECS.get(provider)


def supported_oauth_providers() -> list[str]:
    """Return provider IDs that support the OAuth login wizard."""
    return sorted(PROVIDER_SPECS.keys())
