"""Parse Cursor Admin API spend responses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def parse_cursor_enterprise_spend(
    payload: dict[str, Any],
    provider_id: str = "cursor",
) -> ProviderSnapshot:
    """Parse POST /teams/spend into a team usage snapshot."""
    now = datetime.now(UTC)
    members = payload.get("teamMemberSpend")
    if not isinstance(members, list):
        members = []

    total_spend_cents = 0.0
    total_limit_dollars = 0.0
    has_limit = False
    for member in members:
        if not isinstance(member, dict):
            continue
        overall = member.get("overallSpendCents")
        if overall is not None:
            total_spend_cents += float(overall)
        limit = member.get("monthlyLimitDollars")
        if limit is not None:
            has_limit = True
            total_limit_dollars += float(limit)

    used_usd = round(total_spend_cents / 100.0, 2)
    limit_usd = round(total_limit_dollars, 2) if has_limit else None
    percent = None
    if limit_usd and limit_usd > 0:
        percent = round((used_usd / limit_usd) * 100.0, 1)

    reset_at = None
    cycle_start = payload.get("subscriptionCycleStart")
    if isinstance(cycle_start, (int, float)):
        start = datetime.fromtimestamp(cycle_start / 1000.0, tz=UTC)
        reset_at = start + timedelta(days=30)

    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="Cursor",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=percent,
        usage_used=used_usd,
        usage_limit=limit_usd,
        reset_at=reset_at,
        plan_name="Enterprise",
        raw_safe={"source": "cursor_admin_spend", "total_members": payload.get("totalMembers")},
    )
