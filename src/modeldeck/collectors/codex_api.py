"""Parse OpenAI Platform admin usage/cost responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def _sum_cost_usd(payload: dict[str, Any]) -> float:
    """Sum USD cost amounts from an organization costs API page."""
    total = 0.0
    for bucket in payload.get("data", []):
        if not isinstance(bucket, dict):
            continue
        for result in bucket.get("results", []):
            if not isinstance(result, dict):
                continue
            amount = result.get("amount")
            if not isinstance(amount, dict):
                continue
            value = amount.get("value")
            if value is not None:
                total += float(value)
    return round(total, 4)


def parse_codex_admin_costs(
    payload: dict[str, Any],
    provider_id: str = "codex",
) -> ProviderSnapshot:
    """Parse GET /v1/organization/costs into a snapshot (USD spend)."""
    now = datetime.now(UTC)
    used = _sum_cost_usd(payload)
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="OpenAI",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=None,
        usage_used=used,
        usage_limit=None,
        reset_at=None,
        plan_name="OpenAI Platform",
        raw_safe={"source": "openai_admin_costs"},
    )


def parse_codex_billing_usage(
    payload: dict[str, Any],
    provider_id: str = "codex",
) -> ProviderSnapshot:
    """Parse legacy dashboard billing shape (deprecated fallback)."""
    now = datetime.now(UTC)
    total_usage = payload.get("total_usage")
    if total_usage is None and isinstance(payload.get("data"), list):
        total_usage = sum(item.get("n_context_tokens_total", 0) for item in payload["data"])
    used = float(payload.get("usage_used", total_usage or 0))
    limit = float(payload.get("usage_limit", payload.get("hard_limit_usd", 0) or 0))
    percent = round((used / limit) * 100.0, 1) if limit else None
    reset_raw = payload.get("reset_at")
    reset_at = None
    if isinstance(reset_raw, str):
        reset_at = datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="OpenAI",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=percent,
        usage_used=used,
        usage_limit=limit if limit else None,
        reset_at=reset_at,
        credits_remaining=payload.get("credits_remaining"),
        plan_name=payload.get("plan_name"),
        raw_safe={"source": "openai_billing_legacy"},
    )
