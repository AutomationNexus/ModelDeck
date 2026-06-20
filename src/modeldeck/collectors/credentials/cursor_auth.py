"""Load Cursor access tokens from the local state.vscdb SQLite store."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def default_cursor_state_db_path() -> Path:
    """Return the default Cursor globalStorage state.vscdb path."""
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "globalStorage"
            / "state.vscdb"
        )
    return Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def load_cursor_access_token(path: Path | None = None) -> str:
    """Read cursorAuth/accessToken from Cursor's SQLite state database."""
    db_path = path or default_cursor_state_db_path()
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM ItemTable WHERE key = ?",
                ("cursorAuth/accessToken",),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return ""
    if row is None or row[0] is None:
        return ""
    value = row[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value).strip().strip('"')
