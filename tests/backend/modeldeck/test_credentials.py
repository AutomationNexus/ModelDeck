"""Credential loader tests."""

import json

from modeldeck.collectors.credentials.claude_auth import load_claude_oauth
from modeldeck.collectors.credentials.codex_auth import load_codex_oauth
from modeldeck.collectors.credentials.cursor_auth import load_cursor_access_token


def test_load_codex_oauth_from_file(tmp_path):
    """Codex auth.json should yield OAuth tokens."""
    auth = {
        "tokens": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "account_id": "acct-1",
        }
    }
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth), encoding="utf-8")
    tokens = load_codex_oauth(path)
    assert tokens["access_token"] == "access-1"
    assert tokens["account_id"] == "acct-1"


def test_load_claude_oauth_from_file(tmp_path):
    """Claude credentials file should yield OAuth tokens."""
    creds = {
        "claudeAiOauth": {
            "accessToken": "claude-access",
            "refreshToken": "claude-refresh",
            "subscriptionType": "pro",
        }
    }
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    tokens = load_claude_oauth(path)
    assert tokens["access_token"] == "claude-access"
    assert tokens["refresh_token"] == "claude-refresh"
    assert tokens["subscription_tier"] == "pro"


def test_load_cursor_access_token_missing_db(tmp_path):
    """Missing Cursor state DB should return empty token."""
    assert load_cursor_access_token(tmp_path / "missing.vscdb") == ""
