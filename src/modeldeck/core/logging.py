"""Logging setup with secret redaction."""

from __future__ import annotations

import logging
import re

_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization:\s*(?:bearer\s+)?)(\S+)", re.IGNORECASE),
    re.compile(r"(?i)(cookie:\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(?i)(session[_-]?token[\"']?\s*[:=]\s*[\"']?)(\S+)", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)(\S+)", re.IGNORECASE),
)


class RedactingFilter(logging.Filter):
    """Redact sensitive substrings from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact message text before emission."""
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            record.args = tuple(
                self.redact(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True

    @staticmethod
    def redact(text: str) -> str:
        """Return text with sensitive values masked."""
        for pattern in _REDACT_PATTERNS:
            text = pattern.sub(r"\1***", text)
        return text


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure root logging for ModelDeck."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    if json_format:
        fmt = '{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
