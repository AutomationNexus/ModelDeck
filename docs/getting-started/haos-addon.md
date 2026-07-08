# Home Assistant OS add-on

Install ModelDeck as a **Supervisor add-on** with a Configuration tab for MQTT and provider credentials. No SSH or Samba required for basic setup.

## Prerequisites

1. [Home Assistant OS](https://www.home-assistant.io/installation/) with Supervisor
2. Official **[Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto)** add-on installed and started
3. **MQTT** integration enabled in Home Assistant (**Settings → Devices & services**)

## Add the repository

1. Open **Settings → Add-ons → Add-on store**
2. Click **⋮** (top right) → **Repositories**
3. Add:

   ```
   https://github.com/automationnexus/ModelDeck
   ```

4. Click **Add**, then **Check for updates** (or reload the store)

ModelDeck appears under the new repository section with **two add-ons**:

| Add-on | Use when |
|--------|----------|
| **ModelDeck** | Production — pins a **released** parent image (`:vX.Y.Z`) |
| **ModelDeck (Nightly)** | Testing — tracks the parent **nightly** image (`:nightly`) |

Install one or both from the same repository URL. Each add-on has its own version and **CHANGELOG** shown in the Supervisor UI when updates are available.

### Stable (recommended)

Install **ModelDeck**. It pins a released ModelDeck image (for example `ghcr.io/automationnexus/modeldeck:v0.0.2`).

### Nightly (testing only)

Install **ModelDeck (Nightly)** from the same repository — no separate URL or branch required.

The nightly add-on tracks `ghcr.io/automationnexus/modeldeck:nightly`. Expect unstable behavior — use only on a test Home Assistant instance.

## Install and start

1. Open **ModelDeck** → **Install**
2. Enable **Start on boot** (recommended)
3. Open the **Configuration** tab (see below)
4. Click **Save** (restarts the add-on)
5. Click **Start**

## Configure MQTT

Open the **MQTT** section (collapsible group, same style as Zigbee2MQTT):

| Field | Typical value |
|-------|----------------|
| Server | `mqtt://core-mosquitto:1883` |
| Username | Leave empty unless your broker requires it |
| Password | Mosquitto password if configured |
| Topic prefix | `modeldeck` (default) |
| Discovery prefix | `homeassistant` (default) |

MQTT client ID is assigned automatically (`modeldeck`) and is not shown in the UI.

If you use a broker on another machine, set **Server** to that host (for example `mqtt://192.168.1.10:1883`).

## Add provider accounts (recommended: Open Web UI)

Open **Settings → Add-ons → ModelDeck → Open Web UI** and follow the multi-step wizard:

1. Choose provider (Codex, Claude, Cursor).
2. Choose auth mode — only the modes valid for your account type are shown.
3. For OAuth-capable modes (Claude OAuth, Codex subscription): click the authorization URL,
   log in, paste the code or redirect URL back.
4. For paste modes (Claude cookie, Cursor): fill in the credential fields shown.

The wizard creates and enables the account in one step. Accounts added via the web UI
survive add-on restarts and Configuration saves.

**Logging out of Claude CLI or Codex CLI on your PC does not affect web-UI accounts** —
the wizard creates its own independent OAuth session per account.

For the full credential reference (how to extract each token/cookie, troubleshooting),
see [credentials guide](../guides/credentials.md).

## Add provider accounts (recommended: Ingress web UI)

After the add-on starts, open the ModelDeck web UI from the Home Assistant sidebar:

```
Settings → Add-ons → ModelDeck → Open Web UI
```

Or navigate directly to the **ModelDeck** panel in the HA sidebar.

### Add a Claude or Codex account (OAuth wizard)

1. Click **Add Account**
2. Provider: **Claude** (or Codex), Label: e.g. "Personal Claude", Auth mode: `oauth`
3. Click **Add Account** to save the account entry
4. Click **Re-login (OAuth)** on the new account row
5. The wizard shows an authorize URL — open it in your browser and log in
6. Paste the authorization code (or full redirect URL) back into the wizard
7. Click **Complete Login**
8. Click **Verify** — status should show `ok`

ModelDeck saves the OAuth tokens to `/config/secrets.yaml` and auto-refreshes them.
**Logging out of Claude CLI or Codex CLI on your PC does not affect this account.**

### Add a Cursor account (paste token)

1. Click **Add Account**, choose **Cursor**, label it
2. Click **Paste Token** on the account row
3. Paste your `WorkosCursorSessionToken` cookie or Cursor app JWT (`eyJ...`)
4. Click **Verify**

### Alternative: static add-on options

Still works as before via **Configuration** tab — produces a single `default` account per
provider. Tokens saved here persist via `persist_refreshed_tokens` (default: on).

## Entity ID format (multi-account)

Sensors now include the account slug:

```
sensor.modeldeck_{provider}_{account}_{metric}
```

Example: `sensor.modeldeck_claude_default_usage_percent`

The `default` account comes from the static options. Additional accounts added via the web
UI or CLI are auto-numbered (`1`, `2`, ...) with a matching auto-generated display label
(e.g. `"Claude - 1"`) — account names aren't user-customizable, though you can add an
optional cosmetic alias (e.g. `"Claude - 1 (Work)"`) from the web UI.

**If you are upgrading from a previous version:** old `sensor.modeldeck_{provider}_{metric}`
entities will be retired automatically on first start. Update your dashboards.

## Verify

1. **Settings → Devices & services → MQTT** — look for ModelDeck devices
2. Check `sensor.modeldeck_codex_default_status` (and claude/cursor) = `ok`
3. Check `sensor.modeldeck_codex_default_usage_percent` updates within one poll interval (default 5 minutes)

## Dashboard

Add Lovelace cards for usage gauges and status — see [dashboard guide](../guides/dashboard.md). Copy-paste YAML from:

- [`examples/home-assistant/overview-compact.yaml`](../../examples/home-assistant/overview-compact.yaml) — compact block on Overview (dual gauges per provider)
- [`examples/home-assistant/modeldeck-tab.yaml`](../../examples/home-assistant/modeldeck-tab.yaml) — full ModelDeck tab (**4 columns**: Codex / Claude / Cursor live + graphs)

Requires **layout-card** (HACS). Optional **card-mod** for red `auth_error` styling.

## Verify sensors

| Check | Expected |
|-------|----------|
| `sensor.modeldeck_{provider}_status` | `ok` |
| Usage sensors | Only those for your auth mode (no **Unknown**) — see [sensors.md](../guides/sensors.md) |
| Cursor personal | `sensor.modeldeck_cursor_usage_percent`, `usage_auto_percent`, `usage_api_percent` (not weekly) |
| Claude with extra-usage | `sensor.modeldeck_claude_usage_used`, `usage_limit` when API returns `extra_usage` |
| Claude OAuth Plan | `sensor.modeldeck_claude_plan` when API, credentials, or **Subscription tier** config provides a tier |
| Claude OAuth 5h reset | `sensor.modeldeck_claude_reset_at` when Anthropic returns `five_hour.resets_at` (often absent at 0% usage) |

## Token refresh and Configuration Save

Two Service toggles control **different** mechanisms:

| Toggle | Default | When | Effect |
|--------|---------|------|--------|
| **Save refreshed OAuth tokens** | ON | Background polling | Write refreshed Codex/Claude OAuth tokens to `secrets.yaml` after API refresh |
| **Overwrite secrets file from UI** | OFF | Each **Configuration → Save** | ON = replace secrets with form only; OFF = merge (empty password fields do not wipe on-disk OAuth tokens) |

Leave **Overwrite** off for everyday saves. See [credentials guide](../guides/credentials.md) for details.

Advanced: edit `secrets.yaml` under the add-on config path via **File Editor** (path shown in Supervisor logs on first start, typically under `/addon_configs/`).

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Add-on not in store | Confirm repo URL on `main`; ModelDeck's `main` must include `modeldeck/` and `modeldeck-nightly/` |
| Build fails | Ensure `ghcr.io/automationnexus/modeldeck:latest` is pullable (release published) |
| No MQTT entities | Mosquitto running; host `core-mosquitto`; MQTT integration enabled |
| `auth_error` | Re-paste credentials; match auth mode to account type |
| `PermissionError: /data/state.json` | Upgrade to v0.1.3+ (state moves to `/config/data/`); or set **Retain state** off as a temporary workaround |

## Manual smoke checklist (HAOS)

After configuring the add-on on real Home Assistant OS hardware:

- [ ] Add repository URL → ModelDeck appears in add-on store
- [ ] Configure MQTT with `core-mosquitto` → collector status sensors appear
- [ ] Enable Codex only with subscription tokens → `sensor.modeldeck_codex_status` = `ok`
- [ ] Claude enabled without creds → `auth_error`; Codex remains `ok`
- [ ] Restart add-on after OAuth refresh → tokens persist (not reverted to stale UI values)
- [ ] Works on `aarch64` (Raspberry Pi) and `amd64` (x86 HAOS)

Automated CI covers options rendering and metadata validation; hardware checks require the list above.

## Docker Compose alternative

If you prefer YAML files on disk, use [installation.md](installation.md) (Docker Compose) instead of the add-on.
