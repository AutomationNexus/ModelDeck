# Home Assistant

ModelDeck uses [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) to create sensors automatically.

## Prerequisites

- MQTT integration enabled in Home Assistant
- ModelDeck configured with the same broker host, port, and credentials

## Entities per provider

Each enabled provider creates a **ModelDeck** device with sensors such as:

- `sensor.modeldeck_codex_usage_percent`, `sensor.modeldeck_claude_usage_percent`, `sensor.modeldeck_cursor_usage_percent`
- `sensor.modeldeck_cursor_usage_auto_percent`, `sensor.modeldeck_cursor_usage_api_percent` (Cursor personal)
- `sensor.modeldeck_{provider}_status` — check this after adding credentials (`ok` = working)

Only sensors supported by your auth mode are discovered. See [sensors.md](sensors.md) for the full matrix.

Find entities under **Settings → Devices & services → MQTT → ModelDeck** (device name matches the provider display name).

Disable the **mock** provider in production config so gauges show real quota data.

## Dashboard

Copy-paste Lovelace YAML for two example views:

- [dashboard.md](dashboard.md) — install steps (layout-card required for full tab; card-mod optional)
- [`overview-compact.yaml`](../../examples/home-assistant/overview-compact.yaml) — Overview summary (dual gauges)
- [`modeldeck-tab.yaml`](../../examples/home-assistant/modeldeck-tab.yaml) — full ModelDeck view (4-column live + history graphs)

Ensure usage entities are not excluded from **Recorder** for history graphs to populate.


Alert when a collector reports `auth_error`:

```yaml
alias: ModelDeck auth alert
trigger:
  - platform: mqtt
    topic: modeldeck/claude/status/state
condition:
  - condition: template
    value_template: "{{ trigger.payload == 'auth_error' }}"
action:
  - service: notify.persistent_notification
    data:
      message: "Claude token expired — update ModelDeck secrets.yaml"
```

See [dashboard.md](dashboard.md) for Lovelace examples.
