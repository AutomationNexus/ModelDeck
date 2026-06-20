"""Parse Claude usage API responses (legacy import path)."""

from modeldeck.collectors.claude_console_parser import (
    parse_claude_console_usage as parse_claude_usage,
)

__all__ = ["parse_claude_usage"]
