"""Load Codex/ChatGPT OAuth tokens from Codex CLI auth files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_codex_auth_path() -> Path:
    """Return the default Codex CLI auth.json path."""
    codex_home = os.getenv("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "auth.json"
    config_home = Path.home() / ".config" / "codex" / "auth.json"
    if config_home.exists():
        return config_home
    return Path.home() / ".codex" / "auth.json"


def load_codex_oauth(path: Path | None = None) -> dict[str, str]:
    """Load subscription OAuth tokens from a Codex auth.json file."""
    auth_path = path or default_codex_auth_path()
    if not auth_path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return {}
    result: dict[str, str] = {}
    for key in ("access_token", "refresh_token", "account_id"):
        value = tokens.get(key)
        if isinstance(value, str) and value:
            result[key] = value
    return result
