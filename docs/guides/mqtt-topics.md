# MQTT Topics

Prefix defaults to `modeldeck`. Discovery uses `homeassistant`.

ModelDeck discovers **only supported metrics** for your provider auth mode. See [sensors.md](sensors.md) for the full matrix.

## Bridge

| Topic | Payload |
|-------|---------|
| `modeldeck/bridge/status` | `online` / `offline` |

## Per provider

| Metric | MQTT state topic | Home Assistant entity (example: `codex`) |
|--------|------------------|----------------------------------------|
| Usage % | `modeldeck/{provider}/usage_percent/state` | `sensor.modeldeck_{provider}_usage_percent` |
| Used | `modeldeck/{provider}/usage_used/state` | `sensor.modeldeck_{provider}_usage_used` |
| Limit | `modeldeck/{provider}/usage_limit/state` | `sensor.modeldeck_{provider}_usage_limit` |
| Reset at | `modeldeck/{provider}/reset_at/state` | `sensor.modeldeck_{provider}_reset_at` |
| Weekly usage % | `modeldeck/{provider}/usage_weekly_percent/state` | `sensor.modeldeck_{provider}_usage_weekly_percent` |
| Weekly reset at | `modeldeck/{provider}/reset_weekly_at/state` | `sensor.modeldeck_{provider}_reset_weekly_at` |
| Auto + Composer % | `modeldeck/{provider}/usage_auto_percent/state` | `sensor.modeldeck_{provider}_usage_auto_percent` |
| API % | `modeldeck/{provider}/usage_api_percent/state` | `sensor.modeldeck_{provider}_usage_api_percent` |
| Credits | `modeldeck/{provider}/credits/state` | `sensor.modeldeck_{provider}_credits` |
| Plan | `modeldeck/{provider}/plan/state` | `sensor.modeldeck_{provider}_plan` |
| Collector status | `modeldeck/{provider}/status/state` | `sensor.modeldeck_{provider}_status` |
| Last success | `modeldeck/{provider}/last_success/state` | `sensor.modeldeck_{provider}_last_success` |

Example payloads: `42.5`, `850`, `2000`, ISO 8601 timestamps, `Pro`, `ok` / `auth_error`, etc. Percent values are rounded to one decimal.

## Discovery

`homeassistant/sensor/modeldeck_{provider}_{metric}/config` — retained JSON discovery payload.

Examples: `homeassistant/sensor/modeldeck_codex_usage_percent/config`, `homeassistant/sensor/modeldeck_cursor_usage_auto_percent/config`, `homeassistant/sensor/modeldeck_claude_status/config`.

The JSON `unique_id` field is `modeldeck_{provider}_{metric}` and matches the entity_id suffix.

### Subset discovery and retirement

On each discovery refresh, ModelDeck publishes configs only for metrics supported by the current snapshot. Previously published sensors that are no longer supported receive an **empty retained payload** on their discovery topic so Home Assistant can remove them. After upgrading from 0.0.x, delete any remaining **Unknown** entities manually if needed.
