"""Provider snapshot and status types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class CollectorStatus(StrEnum):
    """Outcome of a single collector run."""

    OK = "ok"
    AUTH_ERROR = "auth_error"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    PARSE_ERROR = "parse_error"


class MetricKind(StrEnum):
    """Metrics exposed as Home Assistant sensors."""

    USAGE_PERCENT = "usage_percent"
    USAGE_USED = "usage_used"
    USAGE_LIMIT = "usage_limit"
    RESET_AT = "reset_at"
    USAGE_WEEKLY_PERCENT = "usage_weekly_percent"
    RESET_WEEKLY_AT = "reset_weekly_at"
    USAGE_AUTO_PERCENT = "usage_auto_percent"
    USAGE_API_PERCENT = "usage_api_percent"
    CREDITS = "credits"
    PLAN = "plan"
    STATUS = "status"
    LAST_SUCCESS = "last_success"


DEFAULT_METRICS: tuple[MetricKind, ...] = tuple(MetricKind)


@dataclass(slots=True)
class ProviderSnapshot:
    """Normalized quota reading for one provider account."""

    provider_id: str
    display_name: str
    collected_at: datetime
    status: CollectorStatus
    account_id: str = "default"
    account_label: str = ""
    account_alias: str = ""
    usage_percent: float | None = None
    usage_used: float | None = None
    usage_limit: float | None = None
    reset_at: datetime | None = None
    usage_percent_weekly: float | None = None
    reset_at_weekly: datetime | None = None
    usage_auto_percent: float | None = None
    usage_api_percent: float | None = None
    credits_remaining: float | None = None
    plan_name: str | None = None
    raw_safe: dict[str, Any] | None = field(default=None, repr=False)
