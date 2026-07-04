# ModelDeck — Home Assistant add-on

[![GitHub release](https://img.shields.io/github/v/release/automationnexus/ModelDeck)](https://github.com/automationnexus/ModelDeck/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/automationnexus/ModelDeck/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-ModelDeck-blue)](https://automationnexus.github.io/ModelDeck/)

ModelDeck polls your **OpenAI**, **Claude**, and **Cursor** accounts for usage and quota data, then publishes **MQTT Discovery** sensors in Home Assistant (for example `sensor.modeldeck_codex_usage_percent`, `sensor.modeldeck_claude_usage_weekly_percent`).

There is no web dashboard inside the add-on. After configuration, check **Settings → Devices & services → MQTT** for ModelDeck devices and sensors.

## Prerequisites

1. **Home Assistant OS** with Supervisor
2. Official **[Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto)** add-on installed and **started**
3. **MQTT** integration enabled (**Settings → Devices & services**)

## Install

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add: `https://github.com/automationnexus/ModelDeck`
3. Open **ModelDeck** → **Install**
4. Enable **Start on boot**
5. Open the **Configuration** tab (sections below), **Save**, then **Start**

## How to use

1. Configure **MQTT** (defaults work with the official Mosquitto add-on).
2. Enable only the providers you use and paste credentials for each.
3. **Save** — the add-on restarts and begins polling (default every 5 minutes).
4. In Home Assistant, open **Settings → Devices & services → MQTT** and find ModelDeck devices.
5. Add dashboard views from the example YAML (see [Dashboard examples](#dashboard-examples)).

**Verify it works:** `sensor.modeldeck_codex_status` (and claude/cursor if enabled) should show `ok`. Usage sensors update within one poll interval. Only sensors supported by your auth mode appear — see [sensors.md](https://automationnexus.github.io/ModelDeck/guides/sensors/).

ModelDeck does **not** log you in. You sign in once in a browser or CLI on any computer, copy tokens or cookies into the Configuration tab, and ModelDeck reuses them on each poll.

---

## MQTT section

| Field | What to enter |
|-------|----------------|
| **Server** | `mqtt://core-mosquitto:1883` when using the official Mosquitto add-on on the same HA box. Use `mqtt://host:port` for a remote broker. |
| **Username** | Leave empty unless Mosquitto requires authentication for local clients. |
| **Password** | Mosquitto broker password (not your Home Assistant login). |
| **Topic prefix** | `modeldeck` (default) — MQTT topic root for this instance. |
| **Discovery prefix** | `homeassistant` (default) — Home Assistant MQTT discovery prefix. |

Client ID is assigned automatically (`modeldeck`).

---

## Service section

Two toggles control **different** mechanisms — they are not two ways to “save” the same thing.

| Toggle | Default | When it runs | What it does |
|--------|---------|--------------|--------------|
| **Save refreshed OAuth tokens to secrets file** | **ON** | During **polling** (background) | After Codex/Claude refresh tokens via API, write new `access_token` / `refresh_token` to `secrets.yaml` |
| **Overwrite secrets file from UI** | **OFF** | On each **Configuration → Save** | **ON** = replace entire secrets file with only what is in the form (wipes merged/auto-refreshed tokens if fields are blank). **OFF** = merge: UI updates non-OAuth fields; keeps on-disk OAuth tokens when password fields are empty |

**Recommended:** leave **Overwrite** off for everyday saves. Use **Save** (merge) to update credentials. Enable **Save refreshed OAuth tokens** so automatic refresh survives restarts.

| Field | What to enter |
|-------|----------------|
| **Poll interval** | Seconds between usage checks (default `300`). |
| **Retain last sensor state** | Keep last values on the broker when the add-on restarts (recommended). |
| **Log level** | `INFO` for normal operation; `DEBUG` when troubleshooting. |

---

## OpenAI

Turn on **Enable Codex collector**, then pick **Auth mode**:

| Auth mode | You have… | Fill these fields |
|-----------|-----------|-------------------|
| `subscription` | ChatGPT Plus/Pro / Codex plan | Access token, Refresh token, Account ID |
| `api` | OpenAI Platform API billing (org admin) | Organization Admin API key |

### Subscription — get tokens (recommended: Codex CLI)

1. On a PC where you are signed into ChatGPT/Codex, install the [Codex CLI](https://github.com/openai/codex) and complete login.
2. Open the auth file:
   - Linux/macOS: `~/.codex/auth.json` or `~/.config/codex/auth.json`
   - Windows: `%USERPROFILE%\.codex\auth.json`
3. Copy into the Configuration tab:
   - **Access token** ← `access_token` (starts with `eyJ…`)
   - **Refresh token** ← `refresh_token` (starts with `rt_…`)
   - **Account ID** ← `account_id` (e.g. `user-…`)

**Alternative:** On your PC run `modeldeck credentials print --provider codex --full` and paste the YAML values into the matching fields.

### API — get Organization Admin key

1. Open [OpenAI Organization Admin Keys](https://platform.openai.com/settings/organization/admin-keys).
2. Create a **read-only** admin key (`sk-admin-…`).
3. Paste into **Organization Admin API key**.

> Standard project keys (`sk-proj-…`) do **not** work for usage/cost APIs.

---

## Claude

Turn on **Enable Claude collector**, then pick **Auth mode**:

| Auth mode | You have… | Fill these fields |
|-----------|-----------|-------------------|
| `cookie` | claude.ai Pro/Max (web) | sessionKey, Organization ID |
| `oauth` | Claude Code subscription | OAuth access token, OAuth refresh token; optional **Subscription tier** for Plan sensor |

For full sensor parity with Codex (Plan, 5h Reset At more often), use **cookie** mode on claude.ai Pro/Max. OAuth mode may omit 5h reset when Anthropic returns `five_hour.resets_at: null` (common at 0% utilization).

#### Claude OAuth: which sensors appear?

ModelDeck publishes a sensor only when the OAuth usage API (or your config) supplies that value. Dashboard cards for missing entities show **Entity not found** — remove those rows or switch auth mode.

| Sensor | MQTT entity | OAuth notes |
|--------|-------------|-------------|
| Usage % (5h) | `sensor.modeldeck_claude_usage_percent` | Usually present |
| Weekly usage % | `sensor.modeldeck_claude_usage_weekly_percent` | Usually present |
| Weekly reset | `sensor.modeldeck_claude_reset_weekly_at` | Usually present |
| Reset At (5h) | `sensor.modeldeck_claude_reset_at` | **Often absent** at 0% 5h usage — API omits `five_hour.resets_at` |
| Plan | `sensor.modeldeck_claude_plan` | Set **Subscription tier** below, or use cookie mode |
| Used / Limit / Credits | `sensor.modeldeck_claude_usage_*`, `credits` | Only when `extra_usage` is enabled on your account |

This is an Anthropic API limitation, not a ModelDeck discovery bug. ModelDeck never invents a reset time or plan name.

### Cookie mode — get sessionKey and org ID

1. Sign in at [claude.ai](https://claude.ai) in Chrome or Edge.
2. Press **F12** → **Application** (Chrome) or **Storage** (Firefox) → **Cookies** → `https://claude.ai`.
3. Copy:
   - **sessionKey cookie** → **sessionKey cookie** field (value starts with `sk-ant-sid01-…`)
   - **lastActiveOrg** → **Organization ID** field (e.g. `org_…`)
4. If you get `auth_error` with HTTP 403, also copy **cf_clearance** into **Cloudflare clearance cookie** (optional).

### OAuth mode — get Claude Code tokens

1. Sign in with [Claude Code](https://claude.ai/code) CLI on a PC.
2. Open `~/.claude/.credentials.json` (or `%USERPROFILE%\.claude\.credentials.json` on Windows).
3. Under `claudeAiOauth`, copy:
   - **OAuth access token** ← `accessToken`
   - **OAuth refresh token** ← `refreshToken`
4. Optional: set **Subscription tier** (e.g. `Pro`, `Max`) if the Plan sensor does not appear from the API.

**Alternative:** `modeldeck credentials print --provider claude --full` on a machine with the credential file.

---

## Cursor

Turn on **Enable Cursor collector**, then pick **Auth mode**:

| Auth mode | You have… | Fill these fields |
|-----------|-----------|-------------------|
| `personal` | Cursor Pro/Ultra (individual) | Session token *or* App JWT |
| `enterprise` | Cursor Team / Enterprise admin | Team Admin API key |

### Personal — option A: dashboard cookie (easiest)

1. Sign in at [cursor.com/dashboard/usage](https://cursor.com/dashboard/usage).
2. **F12** → **Application** → **Cookies** → `https://cursor.com`.
3. Copy **WorkosCursorSessionToken** into **WorkosCursorSessionToken cookie**.

### Personal — option B: app JWT

1. Close Cursor IDE (so the DB is not locked).
2. Open Cursor’s `state.vscdb`:
   - Linux: `~/.config/Cursor/User/globalStorage/state.vscdb`
   - macOS: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
   - Windows: `%APPDATA%\Cursor\User\globalStorage\state.vscdb`
3. Use SQLite or a VS Code state viewer to read `cursorAuth/accessToken`.
4. Paste the JWT into **App JWT (personal)**.

You only need **one** of session token or app JWT for personal mode.

### Enterprise — get Admin API key

1. [cursor.com/dashboard](https://cursor.com/dashboard) → **Settings** → **Advanced** → **Admin API Keys**.
2. Create a key (`crsr_…` or `key_…`).
3. Paste into **Team Admin API key**.

---

## Choose the right auth mode

| You pay for… | Provider | Auth mode |
|--------------|----------|-----------|
| ChatGPT Plus/Pro / Codex | Codex | `subscription` |
| OpenAI Platform API billing | Codex | `api` |
| claude.ai Pro/Max | Claude | `cookie` |
| Claude Code | Claude | `oauth` |
| Cursor Pro/Ultra (personal) | Cursor | `personal` |
| Cursor Team / Enterprise | Cursor | `enterprise` |

Subscription/cookie modes show the **same % bars** as the provider website. API/enterprise modes show **billing or spend**, not consumer quota bars.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No MQTT entities | Mosquitto running; Server = `mqtt://core-mosquitto:1883`; MQTT integration enabled |
| `auth_error` | Re-copy credentials; confirm auth mode matches your account type |
| Claude 403 | Add **cf_clearance** cookie |
| Claude OAuth: no **Plan** sensor | Set **Subscription tier** (e.g. `Pro`, `Max`) or switch to **cookie** mode |
| Claude OAuth: no **Reset At (5h)** | Normal at 0% 5h usage — API omits `five_hour.resets_at`; appears when the 5h window is active |
| Dashboard **Entity not found** on Claude rows | Entity not published for your auth mode — trim YAML or see table above |
| Codex API 401 | Use `sk-admin-…`, not `sk-proj-…` |
| Tokens stop working after weeks | Re-copy from browser/CLI; enable **Save refreshed OAuth tokens** |
| Only want one provider | Disable the other collectors |

---

## Dashboard examples

Paste these from the repository (`examples/home-assistant/`):

| View | File | Layout |
|------|------|--------|
| Overview compact | `overview-compact.yaml` | Dual gauges per provider + optional collector status row |
| Full ModelDeck tab | `modeldeck-tab.yaml` | 4 columns: Codex / Claude / Cursor live + graphs column (requires **layout-card**) |

Install steps: [dashboard.md](https://automationnexus.github.io/ModelDeck/guides/dashboard/). Optional **card-mod** (HACS) enables red styling when status is `auth_error`.

---

## More documentation

- Full HAOS guide: [haos-addon.md](https://automationnexus.github.io/ModelDeck/getting-started/haos-addon/)
- Credential reference: [credentials.md](https://automationnexus.github.io/ModelDeck/guides/credentials/)
- Sensor matrix (per auth mode): [sensors.md](https://automationnexus.github.io/ModelDeck/guides/sensors/)
- MQTT topics: [mqtt-topics.md](https://automationnexus.github.io/ModelDeck/guides/mqtt-topics/)
