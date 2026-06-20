"""Parse Cursor personal usage responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def _parse_reset(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        millis = float(value)
        if millis > 1_000_000_000_000:
            millis /= 1000.0
        return datetime.fromtimestamp(millis, tz=UTC)
    if isinstance(value, str):
        if value.isdigit():
            millis = float(value)
            if millis > 1_000_000_000_000:
                millis /= 1000.0
            return datetime.fromtimestamp(millis, tz=UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def parse_cursor_usage_summary(
    payload: dict[str, Any],
    provider_id: str = "cursor",
) -> ProviderSnapshot:
    """Parse cursor.com/api/usage-summary payload."""
    now = datetime.now(UTC)
    plan_usage = payload.get("planUsage") if isinstance(payload.get("planUsage"), dict) else payload
    percent = plan_usage.get("totalPercentUsed")
    if percent is None:
        percent = plan_usage.get("usage_percent")
    auto_percent = plan_usage.get("autoPercentUsed")
    api_percent = plan_usage.get("apiPercentUsed")
    limit_cents = plan_usage.get("limit")
    used_cents = plan_usage.get("includedSpend") or plan_usage.get("totalSpend")
    used = float(used_cents) / 100.0 if used_cents is not None else None
    limit = float(limit_cents) / 100.0 if limit_cents is not None else None
    reset_at = _parse_reset(payload.get("billingCycleEnd") or plan_usage.get("billingCycleEnd"))
    plan_name = payload.get("planName") or plan_usage.get("planName")
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="Cursor",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=float(percent) if percent is not None else None,
        usage_auto_percent=float(auto_percent) if auto_percent is not None else None,
        usage_api_percent=float(api_percent) if api_percent is not None else None,
        usage_used=used,
        usage_limit=limit,
        reset_at=reset_at,
        plan_name=str(plan_name) if plan_name else None,
        raw_safe={"source": "cursor_usage_summary"},
    )


def parse_cursor_period_usage(
    payload: dict[str, Any],
    provider_id: str = "cursor",
) -> ProviderSnapshot:
    """Parse api2.cursor.sh GetCurrentPeriodUsage payload."""
    now = datetime.now(UTC)
    plan_usage = payload.get("planUsage") if isinstance(payload.get("planUsage"), dict) else {}
    percent = plan_usage.get("totalPercentUsed")
    auto_percent = plan_usage.get("autoPercentUsed")
    api_percent = plan_usage.get("apiPercentUsed")
    if percent is None and plan_usage.get("limit"):
        remaining = float(plan_usage.get("remaining", 0))
        limit = float(plan_usage["limit"])
        percent = round(((limit - remaining) / limit) * 100.0, 1)
    used_cents = plan_usage.get("includedSpend") or plan_usage.get("totalSpend")
    limit_cents = plan_usage.get("limit")
    reset_at = _parse_reset(payload.get("billingCycleEnd"))
    plan_name = payload.get("planName") or plan_usage.get("planName")
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="Cursor",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=float(percent) if percent is not None else None,
        usage_auto_percent=float(auto_percent) if auto_percent is not None else None,
        usage_api_percent=float(api_percent) if api_percent is not None else None,
        usage_used=float(used_cents) / 100.0 if used_cents is not None else None,
        usage_limit=float(limit_cents) / 100.0 if limit_cents is not None else None,
        reset_at=reset_at,
        plan_name=str(plan_name) if plan_name else None,
        raw_safe={"source": "cursor_period_usage"},
    )
