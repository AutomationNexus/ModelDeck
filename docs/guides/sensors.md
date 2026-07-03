# Sensors Reference

ModelDeck publishes **only the sensors your provider and auth mode can populate**. Sensors that do not apply to your account are not discovered, so Home Assistant should not show **Unknown** for missing quota fields.

Full matrix below. For MQTT topic names see [mqtt-topics.md](mqtt-topics.md).

## Quick reference

| Entity pattern | Meaning |
|----------------|---------|
| `sensor.modeldeck_{provider}_usage_percent` | Primary usage % (5h window for Claude; billing cycle for Cursor; subscription % for Codex) |
| `sensor.modeldeck_{provider}_usage_weekly_percent` | 7-day usage % (Claude, Codex subscription) |
| `sensor.modeldeck_{provider}_reset_at` | Primary window reset time (5h for Claude; billing cycle for Cursor/Codex) |
| `sensor.modeldeck_{provider}_reset_weekly_at` | Weekly window reset time |
| `sensor.modeldeck_{provider}_plan` | Plan or subscription tier name |
| `sensor.modeldeck_cursor_usage_auto_percent` | Cursor Auto + Composer pool % (personal) |
| `sensor.modeldeck_cursor_usage_api_percent` | Cursor API pool % (personal) |
| `sensor.modeldeck_{provider}_usage_used` | Absolute spend used (USD) — Claude extra-usage budget or Cursor/Codex API |
| `sensor.modeldeck_{provider}_usage_limit` | Absolute spend limit (USD) |
| `sensor.modeldeck_{provider}_credits` | Remaining extra-usage credits (Claude) |
| `sensor.modeldeck_{provider}_status` | Collector health: `ok`, `auth_error`, `rate_limited`, etc. |
| `sensor.modeldeck_{provider}_last_success` | Last successful poll timestamp |

Replace `{provider}` with `codex`, `claude`, or `cursor`.

## Provider × auth mode matrix

### OpenAI Codex

| Sensor | `subscription` | `api` |
|--------|:------------:|:-----:|
| Usage % | ✓ | — |
| Weekly usage % | ✓ | — |
| Reset at / weekly reset | ✓ | — |
| Credits | ✓* | — |
| Used / Limit | — | Used only |
| Plan | ✓ | ✓ |
| Status / Last success | ✓ | ✓ |

\*Credits when the subscription API returns credit data.

### Claude

| Sensor | `cookie` | `oauth` |
|--------|:--------:|:-------:|
| Usage % (5h) | ✓ | ✓ |
| Weekly usage % | ✓ | ✓ |
| Reset at (5h) | ✓ | ✓* |
| Weekly reset at | ✓ | ✓ |
| Used / Limit | ✓** | ✓** |
| Credits | ✓** | ✓** |
| Plan | ✓ | ✓*** |
| Status / Last success | ✓ | ✓ |

**Used / Limit / Credits** come from Claude **extra-usage** (on-demand spend budget), not the 5-hour message quota. The 5h quota is `sensor.modeldeck_claude_usage_percent`.

\*OAuth **Reset at (5h)** appears only when Anthropic returns `five_hour.resets_at` in the usage API. When the 5h window is idle (0% utilization), the API often omits the timestamp — this is normal.

\*\*Only when `extra_usage` is present in the API response (`monthly_limit > 0` or `used_credits > 0` / `is_enabled`).

\*\*\*OAuth **Plan** comes from the usage API when present, from Claude Code `subscriptionType` in credentials, or from the optional **Subscription tier** field in the HA add-on Configuration tab.

For full parity with Codex-style sensors (plan + 5h reset more often), use **cookie** mode on claude.ai Pro/Max.

**`auto` mode resolution order:** OAuth (`access_token` or `refresh_token`) → cookie (`session_token` or `org_id`) → cookie default. When both OAuth and cookie credentials are present, OAuth takes precedence. Set `auth_mode: cookie` or `auth_mode: oauth` explicitly to override. The resolved mode is logged at INFO on every poll cycle (`Claude collecting via mode=...`).

### Cursor

| Sensor | `personal` | `enterprise` |
|--------|:----------:|:------------:|
| Usage % (total) | ✓ | ✓ |
| Auto + Composer % | ✓ | ✓* |
| API % | ✓ | ✓* |
| Used / Limit | ✓ | ✓ |
| Reset at | ✓ | ✓ |
| Weekly usage | — | — |
| Plan | ✓* | ✓ |
| Status / Last success | ✓ | ✓ |

\*Auto/API when the API returns `autoPercentUsed` / `apiPercentUsed`. Plan on personal when `planName` is returned.

## Entity ID format (multi-account, v0.2+)

**Current (v0.2+):** `sensor.modeldeck_{provider}_{account}_{metric}` — for example
`sensor.modeldeck_codex_default_usage_percent`, `sensor.modeldeck_claude_work_status`.

The `{account}` segment is the account slug chosen when adding an account. The static add-on
options use `default`. Extra accounts added via the web UI use the slug derived from the
account label (e.g. "Work Claude" → `work_claude`, giving
`sensor.modeldeck_claude_work_claude_status`).

If you leave the label blank when adding an account, it defaults to
`{provider}_{n}` where `n` is a 1-indexed count of existing accounts for that
provider (e.g. the first Claude account defaults to `claude_1`, the second to
`claude_2`). Because the entity id template already prepends
`modeldeck_{provider}_`, a label that repeats the provider name (whether typed
manually, e.g. `"claude 1"`, or from the auto-default `claude_1`) has that
redundant leading segment stripped from the account slug before it is used —
so the entity id is `sensor.modeldeck_claude_1_usage_percent`, not
`sensor.modeldeck_claude_claude_1_usage_percent`. Two accounts on the same
provider that would otherwise collapse to the same slug (e.g. `"Backup"` and
`"Claude Backup"`) are automatically disambiguated with a numeric suffix, the
same way plain duplicate labels are.

**Previous (v0.1.5–v0.1.x):** `sensor.modeldeck_{provider}_{metric}` (no account segment).
These are retired automatically on first startup in v0.2+.

## Entity ID migration (v0.1.5–v0.1.x only)

**Current (v0.1.5 and later, before v0.2):** `sensor.modeldeck_{provider}_{metric}` — for example `sensor.modeldeck_codex_usage_percent`, `sensor.modeldeck_claude_status`.

**Historical (v0.1.0–v0.1.4 only):** short slugs such as `sensor.codex_usage`, `sensor.codex_collector_status`. These were retired in v0.1.5.

If dashboard cards show **Entity not found**:

1. Update ModelDeck to **v0.1.5+** and restart the add-on or container.
2. In **Developer tools → States**, search `modeldeck` — you should see `sensor.modeldeck_*` entities.
3. If you still see only `sensor.codex_*` / `sensor.claude_*`, you are on an old build; upgrade and restart.
4. Remove stale MQTT entities under **Settings → Devices & services → MQTT** if duplicates remain.
5. Re-paste YAML from [overview-compact.yaml](../../examples/home-assistant/overview-compact.yaml) and [modeldeck-tab.yaml](../../examples/home-assistant/modeldeck-tab.yaml).

| Old short slug (v0.1.0–v0.1.4) | Current (v0.1.5+) |
|----------------------------------|-------------------|
| `sensor.codex_usage` | `sensor.modeldeck_codex_usage_percent` |
| `sensor.codex_usage_weekly` | `sensor.modeldeck_codex_usage_weekly_percent` |
| `sensor.codex_collector_status` | `sensor.modeldeck_codex_status` |
| `sensor.claude_usage` | `sensor.modeldeck_claude_usage_percent` |
| `sensor.cursor_usage_auto` | `sensor.modeldeck_cursor_usage_auto_percent` |

## Recorder and history graphs

Sensors with `state_class: measurement` (usage %, weekly %, auto/api %) are recorded by Home Assistant Recorder by default.

1. Ensure entities are not excluded in **Settings → System → Recorder**.
2. Add the **ModelDeck** view from [modeldeck-tab.yaml](../../examples/home-assistant/modeldeck-tab.yaml) (column 4 includes history graphs).
3. Default retention applies; adjust in Recorder settings if needed.

## Automations

Example: notify when any provider hits `auth_error`:

```yaml
trigger:
  - platform: state
    entity_id:
      - sensor.modeldeck_codex_status
      - sensor.modeldeck_claude_status
      - sensor.modeldeck_cursor_status
    to: auth_error
action:
  - service: notify.persistent_notification
    data:
      title: ModelDeck auth error
      message: "Check credentials for {{ trigger.entity_id }}"
```

See [home-assistant.md](home-assistant.md) for more patterns.
