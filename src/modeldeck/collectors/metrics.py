"""Per-provider MQTT metric sets."""

from __future__ import annotations

from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot

_ALWAYS: tuple[MetricKind, ...] = (MetricKind.STATUS, MetricKind.LAST_SUCCESS)

_BASE: dict[tuple[str, str], tuple[MetricKind, ...]] = {
    ("codex", "subscription"): (
        MetricKind.USAGE_PERCENT,
        MetricKind.RESET_AT,
        MetricKind.USAGE_WEEKLY_PERCENT,
        MetricKind.RESET_WEEKLY_AT,
        MetricKind.CREDITS,
        MetricKind.PLAN,
        *_ALWAYS,
    ),
    ("codex", "api"): (
        MetricKind.USAGE_USED,
        MetricKind.PLAN,
        *_ALWAYS,
    ),
    ("claude", "cookie"): (
        MetricKind.USAGE_PERCENT,
        MetricKind.RESET_AT,
        MetricKind.USAGE_WEEKLY_PERCENT,
        MetricKind.RESET_WEEKLY_AT,
        MetricKind.USAGE_USED,
        MetricKind.USAGE_LIMIT,
        MetricKind.CREDITS,
        MetricKind.PLAN,
        *_ALWAYS,
    ),
    ("claude", "oauth"): (
        MetricKind.USAGE_PERCENT,
        MetricKind.RESET_AT,
        MetricKind.USAGE_WEEKLY_PERCENT,
        MetricKind.RESET_WEEKLY_AT,
        MetricKind.USAGE_USED,
        MetricKind.USAGE_LIMIT,
        MetricKind.CREDITS,
        MetricKind.PLAN,
        *_ALWAYS,
    ),
    ("cursor", "personal"): (
        MetricKind.USAGE_PERCENT,
        MetricKind.USAGE_AUTO_PERCENT,
        MetricKind.USAGE_API_PERCENT,
        MetricKind.USAGE_USED,
        MetricKind.USAGE_LIMIT,
        MetricKind.RESET_AT,
        MetricKind.PLAN,
        *_ALWAYS,
    ),
    ("cursor", "enterprise"): (
        MetricKind.USAGE_PERCENT,
        MetricKind.USAGE_USED,
        MetricKind.USAGE_LIMIT,
        MetricKind.RESET_AT,
        MetricKind.PLAN,
        MetricKind.USAGE_AUTO_PERCENT,
        MetricKind.USAGE_API_PERCENT,
        *_ALWAYS,
    ),
    ("mock", "mock"): tuple(MetricKind),
}


def base_metrics(provider_id: str, auth_mode: str) -> list[MetricKind]:
    """Return the metric candidates for a provider auth mode."""
    key = (provider_id, auth_mode)
    if key in _BASE:
        return list(_BASE[key])
    if provider_id == "mock":
        return list(_BASE[("mock", "mock")])
    return list(_ALWAYS)


def _metric_populated(snapshot: ProviderSnapshot, metric: MetricKind) -> bool:
    if metric == MetricKind.USAGE_PERCENT:
        return snapshot.usage_percent is not None
    if metric == MetricKind.USAGE_USED:
        return snapshot.usage_used is not None
    if metric == MetricKind.USAGE_LIMIT:
        return snapshot.usage_limit is not None
    if metric == MetricKind.RESET_AT:
        return snapshot.reset_at is not None
    if metric == MetricKind.USAGE_WEEKLY_PERCENT:
        return snapshot.usage_percent_weekly is not None
    if metric == MetricKind.RESET_WEEKLY_AT:
        return snapshot.reset_at_weekly is not None
    if metric == MetricKind.USAGE_AUTO_PERCENT:
        return snapshot.usage_auto_percent is not None
    if metric == MetricKind.USAGE_API_PERCENT:
        return snapshot.usage_api_percent is not None
    if metric == MetricKind.CREDITS:
        return snapshot.credits_remaining is not None
    if metric == MetricKind.PLAN:
        return snapshot.plan_name is not None
    if metric in {MetricKind.STATUS, MetricKind.LAST_SUCCESS}:
        return True
    return False


def effective_metrics(snapshot: ProviderSnapshot, candidates: list[MetricKind]) -> list[MetricKind]:
    """Filter candidate metrics to those populated on the snapshot."""
    return [metric for metric in candidates if _metric_populated(snapshot, metric)]
