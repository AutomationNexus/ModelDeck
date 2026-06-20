"""Home Assistant MQTT discovery payloads."""

from __future__ import annotations

import json
from typing import Any

from modeldeck.config.loader import MqttConfig
from modeldeck.schemas.snapshot import MetricKind, ProviderSnapshot

METRIC_META: dict[MetricKind, dict[str, str]] = {
    MetricKind.USAGE_PERCENT: {
        "name_suffix": "Usage",
        "unit": "%",
        "icon": "mdi:percent-outline",
        "state_class": "measurement",
    },
    MetricKind.USAGE_USED: {
        "name_suffix": "Used",
        "icon": "mdi:counter",
        "state_class": "measurement",
    },
    MetricKind.USAGE_LIMIT: {
        "name_suffix": "Limit",
        "icon": "mdi:gauge-full",
        "state_class": "measurement",
    },
    MetricKind.RESET_AT: {
        "name_suffix": "Reset At",
        "device_class": "timestamp",
        "icon": "mdi:clock-outline",
    },
    MetricKind.USAGE_WEEKLY_PERCENT: {
        "name_suffix": "Weekly Usage",
        "unit": "%",
        "icon": "mdi:calendar-week",
        "state_class": "measurement",
    },
    MetricKind.USAGE_AUTO_PERCENT: {
        "name_suffix": "Auto + Composer Usage",
        "unit": "%",
        "icon": "mdi:robot-outline",
        "state_class": "measurement",
    },
    MetricKind.USAGE_API_PERCENT: {
        "name_suffix": "API Usage",
        "unit": "%",
        "icon": "mdi:api",
        "state_class": "measurement",
    },
    MetricKind.RESET_WEEKLY_AT: {
        "name_suffix": "Weekly Reset At",
        "device_class": "timestamp",
        "icon": "mdi:calendar-clock",
    },
    MetricKind.CREDITS: {
        "name_suffix": "Credits",
        "icon": "mdi:cash",
        "state_class": "measurement",
    },
    MetricKind.PLAN: {
        "name_suffix": "Plan",
        "icon": "mdi:card-account-details-outline",
    },
    MetricKind.STATUS: {
        "name_suffix": "Collector Status",
        "icon": "mdi:heart-pulse",
    },
    MetricKind.LAST_SUCCESS: {
        "name_suffix": "Last Success",
        "device_class": "timestamp",
        "icon": "mdi:check-circle-outline",
    },
}


METRIC_OBJECT_SLUG: dict[MetricKind, str] = {
    MetricKind.USAGE_PERCENT: "usage",
    MetricKind.USAGE_USED: "usage_used",
    MetricKind.USAGE_LIMIT: "usage_limit",
    MetricKind.RESET_AT: "reset_at",
    MetricKind.USAGE_WEEKLY_PERCENT: "usage_weekly",
    MetricKind.USAGE_AUTO_PERCENT: "usage_auto",
    MetricKind.USAGE_API_PERCENT: "usage_api",
    MetricKind.RESET_WEEKLY_AT: "reset_weekly_at",
    MetricKind.CREDITS: "credits",
    MetricKind.PLAN: "plan",
    MetricKind.STATUS: "collector_status",
    MetricKind.LAST_SUCCESS: "last_success",
}


def metric_unique_id(provider_id: str, metric: MetricKind) -> str:
    """Return a globally unique MQTT discovery identifier."""
    return f"modeldeck_{provider_id}_{metric.value}"


def discovery_object_id(provider_id: str, metric: MetricKind) -> str:
    """Return the HA discovery topic object_id (becomes entity_id)."""
    return f"modeldeck_{provider_id}_{metric.value}"


def short_slug_discovery_topic(mqtt: MqttConfig, provider_id: str, metric: MetricKind) -> str:
    """Return v0.1.0–v0.1.2 short-slug discovery topic to retire on upgrade."""
    object_id = f"{provider_id}_{METRIC_OBJECT_SLUG[metric]}"
    return f"{mqtt.discovery_prefix}/sensor/{object_id}/config"


def discovery_topic(mqtt: MqttConfig, provider_id: str, metric: MetricKind) -> str:
    """Return the HA discovery config topic."""
    object_id = discovery_object_id(provider_id, metric)
    return f"{mqtt.discovery_prefix}/sensor/{object_id}/config"


def homeassistant_entity_id(provider_id: str, metric: MetricKind) -> str:
    """Return the Home Assistant entity_id for a metric."""
    return f"sensor.{discovery_object_id(provider_id, metric)}"


def state_topic(mqtt: MqttConfig, provider_id: str, metric: MetricKind) -> str:
    """Return the MQTT state topic for a metric."""
    return f"{mqtt.topic_prefix}/{provider_id}/{metric.value}/state"


def bridge_status_topic(mqtt: MqttConfig) -> str:
    """Return the bridge online/offline topic."""
    return f"{mqtt.topic_prefix}/bridge/status"


def build_discovery_payload(
    mqtt: MqttConfig,
    snapshot: ProviderSnapshot,
    metric: MetricKind,
) -> dict[str, Any]:
    """Build a Home Assistant MQTT discovery payload."""
    meta = METRIC_META[metric]
    object_id = discovery_object_id(snapshot.provider_id, metric)
    unique_id = metric_unique_id(snapshot.provider_id, metric)
    payload: dict[str, Any] = {
        "name": meta["name_suffix"],
        "unique_id": unique_id,
        "object_id": object_id,
        "default_entity_id": homeassistant_entity_id(snapshot.provider_id, metric),
        "state_topic": state_topic(mqtt, snapshot.provider_id, metric),
        "device": {
            "identifiers": [f"modeldeck_{snapshot.provider_id}"],
            "name": snapshot.display_name,
            "manufacturer": "ModelDeck",
            "model": "AI Quota Monitor",
        },
    }
    if "unit" in meta:
        payload["unit_of_measurement"] = meta["unit"]
    if "icon" in meta:
        payload["icon"] = meta["icon"]
    if "device_class" in meta:
        payload["device_class"] = meta["device_class"]
    if "state_class" in meta:
        payload["state_class"] = meta["state_class"]
    return payload


def discovery_payload_json(
    mqtt: MqttConfig,
    snapshot: ProviderSnapshot,
    metric: MetricKind,
) -> str:
    """Serialize a discovery payload."""
    return json.dumps(build_discovery_payload(mqtt, snapshot, metric))
