# Dashboard Examples

Use Lovelace cards with ModelDeck MQTT sensors on a wall tablet or desk display. Ready-to-paste YAML lives in `examples/home-assistant/`.

## Prerequisites

- ModelDeck running and MQTT sensors visible under **Settings → Devices & services → MQTT**
- **layout-card** (HACS) — required for the full ModelDeck tab (horizontal 4-column layout)
- **card-mod** (HACS) — optional but recommended for red `auth_error` styling on status rows

## Quick install

### Compact summary on Overview

1. Open **Overview** → pencil (**Edit dashboard**)
2. **Add card** → **Manual**
3. Paste the contents of [`overview-compact.yaml`](../../examples/home-assistant/overview-compact.yaml)
4. Drag the card where you want it → **Save**

Shows **dual gauges per provider** (primary + weekly/5h where applicable) plus an optional **ModelDeck Status** row with `sensor.modeldeck_*_status` for each provider.

### Full ModelDeck tab

1. **Edit dashboard** → **Add view** (top tab bar)
2. Title: `ModelDeck`, icon: `mdi:robot-outline`
3. On the new view → **Edit** → **Raw configuration editor**
4. Paste the contents of [`modeldeck-tab.yaml`](../../examples/home-assistant/modeldeck-tab.yaml)
5. **Save**

**4-column layout:** columns 1–3 are live gauges + entity rows per provider (Codex, Claude, Cursor); column 4 has a 24h mean chart and 7-day history graphs per provider. Requires **layout-card** (HACS).

Ensure ModelDeck usage entities are not excluded from **Recorder** so history graphs populate.

### Verify entity IDs

If a card shows **Entity not found**:

1. **Developer tools → States** — filter `modeldeck`
2. You should see `sensor.modeldeck_codex_usage_percent`, `sensor.modeldeck_claude_status`, etc. (**current** since v0.1.5)
3. If you still see only `sensor.codex_*` / `sensor.claude_*`, upgrade to **v0.1.5+** and restart ModelDeck; re-paste YAML from the examples
4. Confirm IDs match your auth mode — see [sensors.md](sensors.md) for which entities exist per mode
5. An `account_label` in the add-on config changes friendly **names** only — entity IDs stay the same

Disable the **mock** provider in production so gauges show real quota data.

## Entity reference

Canonical IDs — full matrix: [sensors.md](sensors.md).

| Card use | Entity (when supported) |
|----------|-------------------------|
| 5h / primary usage gauge | `sensor.modeldeck_{provider}_usage_percent` |
| Weekly usage | `sensor.modeldeck_{provider}_usage_weekly_percent` (Codex subscription, Claude) |
| Cursor Auto pool | `sensor.modeldeck_cursor_usage_auto_percent` |
| Cursor API pool | `sensor.modeldeck_cursor_usage_api_percent` |
| Extra usage used/limit | `sensor.modeldeck_claude_usage_used`, `sensor.modeldeck_claude_usage_limit` |
| Reset time (5h / billing) | `sensor.modeldeck_{provider}_reset_at` |
| Weekly reset | `sensor.modeldeck_{provider}_reset_weekly_at` |
| Plan | `sensor.modeldeck_{provider}_plan` |
| Health | `sensor.modeldeck_{provider}_status` (`ok` = working) |
| Last poll | `sensor.modeldeck_{provider}_last_success` |

Replace `{provider}` with `codex`, `claude`, or `cursor`.

## Example files

| File | Purpose |
|------|---------|
| [`overview-compact.yaml`](../../examples/home-assistant/overview-compact.yaml) | Overview tab — dual gauges + status (card-mod optional) |
| [`modeldeck-tab.yaml`](../../examples/home-assistant/modeldeck-tab.yaml) | Full ModelDeck view — 4-column live + history (layout-card, card-mod optional) |
| [`usage-stack.yaml`](../../examples/home-assistant/usage-stack.yaml) | Single-provider stack (Codex example; swap prefix for Claude/Cursor) |

## Single usage gauge

```yaml
type: gauge
entity: sensor.modeldeck_codex_usage_percent
name: Codex Usage
min: 0
max: 100
needle: true
severity:
  green: 0
  yellow: 70
  red: 90
```

## Reset timestamp

```yaml
type: entity
entity: sensor.modeldeck_claude_reset_at
name: Claude Reset
```

## Multi-provider grid (minimal)

```yaml
type: grid
columns: 3
cards:
  - type: gauge
    entity: sensor.modeldeck_codex_usage_percent
  - type: gauge
    entity: sensor.modeldeck_claude_usage_percent
  - type: gauge
    entity: sensor.modeldeck_cursor_usage_percent
```

## ESPHome / table displays

Any device that subscribes to MQTT can render the same topics. Point an ESPHome `text_sensor` or `sensor` at `modeldeck/{provider}/usage_percent/state`.
