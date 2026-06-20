"""Load Claude Code OAuth tokens from credentials files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_claude_credentials_path() -> Path:
    """Return the default Claude Code credentials file path."""
    return Path.home() / ".claude" / ".credentials.json"


def load_claude_oauth(path: Path | None = None) -> dict[str, str]:
    """Load OAuth tokens from Claude Code credentials JSON."""
    cred_path = path or default_claude_credentials_path()
    if not cred_path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(cred_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return {}
    result: dict[str, str] = {}
    access = oauth.get("accessToken")
    refresh = oauth.get("refreshToken")
    if isinstance(access, str) and access:
        result["access_token"] = access
    if isinstance(refresh, str) and refresh:
        result["refresh_token"] = refresh
    tier = oauth.get("subscriptionType")
    if isinstance(tier, str) and tier.strip():
        result["subscription_tier"] = tier.strip()
    return result
