"""Parse ChatGPT/Codex subscription wham/usage responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def _window_percent(window: dict[str, Any] | None) -> float | None:
    if not window:
        return None
    used = window.get("used_percent")
    return float(used) if used is not None else None


def _window_reset(window: dict[str, Any] | None) -> datetime | None:
    if not window:
        return None
    reset_raw = window.get("reset_at")
    if reset_raw is None:
        return None
    if isinstance(reset_raw, (int, float)):
        return datetime.fromtimestamp(float(reset_raw), tz=UTC)
    if isinstance(reset_raw, str):
        try:
            return datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def parse_codex_wham_usage(payload: dict[str, Any], provider_id: str = "codex") -> ProviderSnapshot:
    """Parse a ChatGPT wham/usage payload into a snapshot."""
    now = datetime.now(UTC)
    rate_limit = payload.get("rate_limit") or {}
    primary = rate_limit.get("primary_window")
    secondary = rate_limit.get("secondary_window")
    credits = payload.get("credits") or {}
    credits_balance = credits.get("balance")
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name="OpenAI",
        collected_at=now,
        status=CollectorStatus.OK,
        usage_percent=_window_percent(primary if isinstance(primary, dict) else None),
        reset_at=_window_reset(primary if isinstance(primary, dict) else None),
        usage_percent_weekly=_window_percent(secondary if isinstance(secondary, dict) else None),
        reset_at_weekly=_window_reset(secondary if isinstance(secondary, dict) else None),
        credits_remaining=float(credits_balance) if credits_balance is not None else None,
        plan_name=str(payload.get("plan_type")) if payload.get("plan_type") else None,
        raw_safe={"source": "chatgpt_wham"},
    )
