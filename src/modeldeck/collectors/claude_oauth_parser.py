"""Parse Claude OAuth usage API responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modeldeck.collectors.claude_console_parser import _extra_usage_fields
from modeldeck.core.logging import get_logger
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot

logger = get_logger(__name__)


def _plan_name_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("plan_name", "subscriptionType", "subscription_type", "plan"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_claude_oauth_usage(
    payload: dict[str, Any],
    provider_id: str = "claude",
) -> ProviderSnapshot:
    """Parse api.anthropic.com/api/oauth/usage payload."""
    now = datetime.now(UTC)
    five_hour = payload.get("five_hour") if isinstance(payload.get("five_hour"), dict) else None
    seven_day = payload.get("seven_day") if isinstance(payload.get("seven_day"), dict) else None

    def _window(window: dict[str, Any] | None) -> tuple[float | None, datetime | None]:
        if not window:
            return None, None
        utilization = window.get("utilization")
        percent = float(utilization) if utilization is not None else None
        reset_raw = window.get("resets_at")
        reset_at = (
            datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
            if isinstance(reset_raw, str)
            else None
        )
        return percent, reset_at

    primary_percent, primary_reset = _window(five_hour)
    weekly_percent, weekly_reset = _window(seven_day)
    if primary_percent is not None and primary_reset is None:
        logger.debug(
            "Claude OAuth five_hour utilization=%s but resets_at is null (window may be idle)",
            primary_percent,
        )
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
        plan_name=_plan_name_from_payload(payload),
        raw_safe={"source": "claude_oauth"},
    )
