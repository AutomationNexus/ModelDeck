"""Persist last-known provider snapshots."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modeldeck.core.paths import state_path
from modeldeck.schemas.snapshot import CollectorStatus, ProviderSnapshot


def _state_key(snapshot: ProviderSnapshot) -> str:
    """Return the composite cache key for a snapshot: 'provider_id/account_id'."""
    return f"{snapshot.provider_id}/{snapshot.account_id}"


def snapshot_to_dict(snapshot: ProviderSnapshot) -> dict[str, Any]:
    """Serialize a snapshot for JSON storage."""
    return {
        "provider_id": snapshot.provider_id,
        "account_id": snapshot.account_id,
        "account_label": snapshot.account_label,
        "display_name": snapshot.display_name,
        "collected_at": snapshot.collected_at.isoformat(),
        "status": snapshot.status.value,
        "usage_percent": snapshot.usage_percent,
        "usage_used": snapshot.usage_used,
        "usage_limit": snapshot.usage_limit,
        "reset_at": snapshot.reset_at.isoformat() if snapshot.reset_at else None,
        "usage_percent_weekly": snapshot.usage_percent_weekly,
        "reset_at_weekly": (
            snapshot.reset_at_weekly.isoformat() if snapshot.reset_at_weekly else None
        ),
        "usage_auto_percent": snapshot.usage_auto_percent,
        "usage_api_percent": snapshot.usage_api_percent,
        "credits_remaining": snapshot.credits_remaining,
        "plan_name": snapshot.plan_name,
    }


def snapshot_from_dict(data: dict[str, Any]) -> ProviderSnapshot:
    """Deserialize a snapshot from JSON storage."""
    reset_raw = data.get("reset_at")
    reset_weekly_raw = data.get("reset_at_weekly")
    return ProviderSnapshot(
        provider_id=data["provider_id"],
        account_id=data.get("account_id", "default"),
        account_label=data.get("account_label", ""),
        display_name=data["display_name"],
        collected_at=datetime.fromisoformat(data["collected_at"]),
        status=CollectorStatus(data["status"]),
        usage_percent=data.get("usage_percent"),
        usage_used=data.get("usage_used"),
        usage_limit=data.get("usage_limit"),
        reset_at=datetime.fromisoformat(reset_raw) if reset_raw else None,
        usage_percent_weekly=data.get("usage_percent_weekly"),
        reset_at_weekly=datetime.fromisoformat(reset_weekly_raw) if reset_weekly_raw else None,
        usage_auto_percent=data.get("usage_auto_percent"),
        usage_api_percent=data.get("usage_api_percent"),
        credits_remaining=data.get("credits_remaining"),
        plan_name=data.get("plan_name"),
    )


class StateCache:
    """Read and write last-good snapshots to disk."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or state_path()

    def load(self) -> dict[str, ProviderSnapshot]:
        """Load cached snapshots keyed by 'provider_id/account_id'."""
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {key: snapshot_from_dict(value) for key, value in raw.items()}

    def save(self, snapshots: list[ProviderSnapshot]) -> None:
        """Persist snapshots, keeping last-good values on failure."""
        existing = self.load()
        for snapshot in snapshots:
            key = _state_key(snapshot)
            if snapshot.status.value == "ok":
                existing[key] = snapshot
            elif key not in existing:
                existing[key] = snapshot
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: snapshot_to_dict(value) for key, value in existing.items()}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
