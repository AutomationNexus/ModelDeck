"""Parse Claude.ai console usage responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def _window(window: dict[str, Any] | None) -> tuple[float | None, datetime | None]:
    if not window:
        return None, None
    utilization = window.get("utilization")
    percent = float(utilization) if utilization is not None else None
    reset_raw = window.get("resets_at")
    reset_at = None
    if isinstance(reset_raw, str):
        reset_at = datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
    return percent, reset_at


def _extra_usage_fields(extra: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    """Map extra_usage spend to used, limit, and credits remaining (USD)."""
    monthly_limit = extra.get("monthly_limit")
    used_credits = extra.get("used_credits")
    is_enabled = extra.get("is_enabled")
    if not monthly_limit and not used_credits:
        return None, None, None
    used = float(used_credits or 0)
    limit = float(monthly_limit or 0)
    usage_used: float | None = None
    usage_limit: float | None = None
    credits: float | None = None
    if limit > 0:
        usage_limit = limit / 100.0
        credits = max(limit - used, 0.0) / 100.0
    if is_enabled or used > 0:
        usage_used = used / 100.0
    return usage_used, usage_limit, credits


def parse_claude_console_usage(
    payload: dict[str, Any],
    provider_id: str = "claude",
) -> ProviderSnapshot:
    """Parse a Claude.ai organization usage payload."""
    now = datetime.now(UTC)
    five_hour = payload.get("five_hour") if isinstance(payload.get("five_hour"), dict) else None
    seven_day = payload.get("seven_day") if isinstance(payload.get("seven_day"), dict) else None
    primary_percent, primary_reset = _window(five_hour)
    weekly_percent, weekly_reset = _window(seven_day)
    if primary_percent is None:
        used = payload.get("usage_used")
        limit = payload.get("usage_limit")
        if used is not None and limit:
            primary_percent = round((float(used) / float(limit)) * 100.0, 1)
        percent = payload.get("usage_percent")
        if primary_percent is None and percent is not None:
            primary_percent = float(percent)
    extra = payload.get("extra_usage") if isinstance(payload.get("extra_usage"), dict) else {}
    usage_used, usage_limit, credits = _extra_usage_fields(extra)
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="Claude",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=primary_percent,
        usage_used=usage_used,
        usage_limit=usage_limit,
        reset_at=primary_reset,
        usage_percent_weekly=weekly_percent,
        reset_at_weekly=weekly_reset,
        credits_remaining=credits,
        plan_name=payload.get("plan_name"),
        raw_safe={"source": "claude_console"},
    )
