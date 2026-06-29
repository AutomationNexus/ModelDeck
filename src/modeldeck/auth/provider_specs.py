"""Provider OAuth protocol metadata registry.

This module contains only non-secret, non-user-specific protocol constants
(authorize URLs, token URLs, public client IDs, required scopes).

All values are overridable via environment variables so a provider endpoint
change does not require a code edit.

No user credentials, account IDs, or tokens are stored here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderOAuthSpec:
    """Non-secret OAuth protocol metadata for one provider."""

    provider: str
    authorize_url: str
    token_url: str
    client_id: str
    scopes: tuple[str, ...]
    redirect_uri: str = "https://modeldeck.local/oauth/callback"

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


# ---------------------------------------------------------------------------
# Claude OAuth spec
# Verified working: api.anthropic.com/api/oauth/usage returns 200 with these.
# Token URL: platform.claude.com/v1/oauth/token
# Client ID: public Claude Code client (non-secret, same as Claude CLI uses).
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
)

# ---------------------------------------------------------------------------
# Codex / ChatGPT OAuth spec
# Uses the same OAuth infrastructure as the Codex CLI / ChatGPT web app.
# ---------------------------------------------------------------------------
CODEX_SPEC = ProviderOAuthSpec(
    provider="codex",
    authorize_url="https://chatgpt.com/api/auth/authorize",
    token_url="https://chatgpt.com/api/auth/token",
    client_id="app_codex",
    scopes=("openid", "offline_access"),
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
