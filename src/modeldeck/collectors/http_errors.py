"""Shared collector HTTP error handling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def error_snapshot(
    provider_id: str,
    display_name: str,
    status: CollectorStatus,
    raw_safe: dict[str, Any] | None = None,
) -> ProviderSnapshot:
    """Build an error snapshot for the current UTC time."""
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name=display_name,
        collected_at=datetime.now(UTC),
        status=status,
        raw_safe=raw_safe,
    )


def status_from_http_error(exc: httpx.HTTPStatusError) -> CollectorStatus:
    """Map an HTTP status code to a collector status."""
    code = exc.response.status_code
    if code in {401, 403}:
        return CollectorStatus.AUTH_ERROR
    if code == 429:
        return CollectorStatus.RATE_LIMITED
    return CollectorStatus.UNAVAILABLE
