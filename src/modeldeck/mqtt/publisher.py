"""Format snapshot values for MQTT state topics."""

from __future__ import annotations

from datetime import datetime

from modeldeck.schemas.snapshot import CollectorStatus, MetricKind, ProviderSnapshot


def format_metric_value(
    snapshot: ProviderSnapshot,
    metric: MetricKind,
    last_success: datetime | None = None,
) -> str | None:
    """Return the MQTT payload string for a metric, or None to skip."""
    if metric == MetricKind.USAGE_PERCENT:
        return _fmt_percent(snapshot.usage_percent)
    if metric == MetricKind.USAGE_USED:
        return _fmt_float(snapshot.usage_used)
    if metric == MetricKind.USAGE_LIMIT:
        return _fmt_float(snapshot.usage_limit)
    if metric == MetricKind.RESET_AT:
        return _fmt_datetime(snapshot.reset_at)
    if metric == MetricKind.USAGE_WEEKLY_PERCENT:
        return _fmt_percent(snapshot.usage_percent_weekly)
    if metric == MetricKind.USAGE_AUTO_PERCENT:
        return _fmt_percent(snapshot.usage_auto_percent)
    if metric == MetricKind.USAGE_API_PERCENT:
        return _fmt_percent(snapshot.usage_api_percent)
    if metric == MetricKind.RESET_WEEKLY_AT:
        return _fmt_datetime(snapshot.reset_at_weekly)
    if metric == MetricKind.CREDITS:
        return _fmt_float(snapshot.credits_remaining)
    if metric == MetricKind.PLAN:
        return snapshot.plan_name
    if metric == MetricKind.STATUS:
        return snapshot.status.value
    if metric == MetricKind.LAST_SUCCESS:
        if snapshot.status == CollectorStatus.OK:
            return _fmt_datetime(snapshot.collected_at)
        return _fmt_datetime(last_success)
    return None


def _fmt_percent(value: float | None) -> str | None:
    if value is None:
        return None
    return str(round(float(value), 1))


def _fmt_float(value: float | None) -> str | None:
    if value is None:
        return None
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _fmt_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
