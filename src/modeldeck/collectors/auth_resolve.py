"""Resolve provider credentials and auth modes."""

from __future__ import annotations

from pathlib import Path

from modeldeck.collectors.credentials.claude_auth import load_claude_oauth
from modeldeck.collectors.credentials.codex_auth import load_codex_oauth
from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token
from modeldeck.config.loader import ProviderSecrets, ProviderToggle


def _credential_file(toggle: ProviderToggle, default: Path) -> Path | None:
    if toggle.credential_path == "":
        return None
    if toggle.credential_path:
        return Path(toggle.credential_path).expanduser()
    return default


def resolve_codex_secrets(toggle: ProviderToggle, secrets: ProviderSecrets) -> ProviderSecrets:
    """Merge Codex secrets with optional Codex CLI auth file."""
    merged = secrets.model_copy()
    path = _credential_file(toggle, Path.home() / ".codex" / "auth.json")
    if path is None:
        return merged
    file_tokens = load_codex_oauth(path)
    for key, value in file_tokens.items():
        if not getattr(merged, key, ""):
            setattr(merged, key, value)
    return merged


def resolve_claude_secrets(toggle: ProviderToggle, secrets: ProviderSecrets) -> ProviderSecrets:
    """Merge Claude secrets with optional Claude Code credentials file."""
    merged = secrets.model_copy()
    path = _credential_file(toggle, Path.home() / ".claude" / ".credentials.json")
    if path is None:
        return merged
    file_tokens = load_claude_oauth(path)
    if not merged.access_token and file_tokens.get("access_token"):
        merged.access_token = file_tokens["access_token"]
    if not merged.refresh_token and file_tokens.get("refresh_token"):
        merged.refresh_token = file_tokens["refresh_token"]
    return merged


def resolve_cursor_secrets(toggle: ProviderToggle, secrets: ProviderSecrets) -> ProviderSecrets:
    """Merge Cursor secrets with optional state.vscdb access token."""
    merged = secrets.model_copy()
    if merged.access_token:
        return merged
    from modeldeck.collectors.credentials.cursor_auth import default_cursor_state_db_path

    path = _credential_file(toggle, default_cursor_state_db_path())
    if path is None:
        return merged
    token = load_cursor_access_token(path)
    if token:
        merged.access_token = token
    return merged


def pick_codex_mode(toggle: ProviderToggle, secrets: ProviderSecrets) -> str:
    """Return the effective Codex auth mode."""
    mode = toggle.auth_mode
    if mode != "auto":
        return mode
    if secrets.access_token or secrets.refresh_token:
        return "subscription"
    if secrets.api_key:
        return "api"
    return "subscription"


def pick_claude_mode(toggle: ProviderToggle, secrets: ProviderSecrets) -> str:
    """Return the effective Claude auth mode."""
    mode = toggle.auth_mode
    if mode != "auto":
        return mode
    if secrets.session_token or secrets.org_id:
        return "cookie"
    if secrets.access_token or secrets.refresh_token:
        return "oauth"
    return "cookie"


def pick_cursor_mode(toggle: ProviderToggle, secrets: ProviderSecrets) -> str:
    """Return the effective Cursor auth mode."""
    mode = toggle.auth_mode
    if mode != "auto":
        return mode
    if secrets.session_token or secrets.access_token:
        return "personal"
    if secrets.admin_api_key:
        return "enterprise"
    return "personal"
