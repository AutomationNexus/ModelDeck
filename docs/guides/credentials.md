# Provider credentials

ModelDeck does **not** log you in. You authenticate once in a browser or CLI, copy tokens or cookies into `config/secrets.yaml`, and ModelDeck reuses them on each poll.

## Choose the right auth mode

| You pay for… | Provider | `auth_mode` | Official API? |
|--------------|----------|-------------|---------------|
| ChatGPT Plus/Pro / Codex subscription | codex | `subscription` | No — community pattern ([openusage](https://github.com/robinebers/openusage/blob/main/docs/providers/codex.md)) |
| OpenAI Platform API billing | codex | `api` | Yes — [Organization Costs API](https://platform.openai.com/docs/api-reference/usage/costs) (`sk-admin-*` key) |
| claude.ai Pro/Max (web) | claude | `cookie` | No — console API ([ClaudeDash](https://github.com/mingzapingin/ClaudeDash)) |
| Claude Code subscription | claude | `oauth` | No — Claude Code OAuth usage endpoint |
| Cursor personal Pro/Ultra | cursor | `personal` | No — session cookie or app JWT ([CursorMonitor](https://github.com/Coldaine/CursorMonitor)) |
| Cursor Team / Enterprise | cursor | `enterprise` | Yes — [Cursor Admin API](https://cursor.com/docs/account/teams/admin-api) |

Subscription modes show the **same % bars** as the provider website (5h / 7d). API modes show **billing or spend**, not consumer subscription quotas.

## Which sensors appear

ModelDeck discovers only metrics your auth mode can populate. See [sensors.md](sensors.md) for the full matrix. Examples:

| Auth mode | Typical sensors |
|-----------|-----------------|
| Codex `subscription` | `usage`, `usage_weekly`, resets, plan |
| Codex `api` | `usage_used`, plan (no % bar) |
| Claude `cookie` / `oauth` | `usage`, `usage_weekly`, optional `usage_used`/`usage_limit` from extra-usage |
| Cursor `personal` | `usage`, `usage_auto`, `usage_api`, used/limit, reset |
| Cursor `enterprise` | `usage`, used/limit, reset, plan |

## Quick setup (all providers)

1. Set `auth_mode` in `config/modeldeck.yaml`.
2. Paste credentials into `config/secrets.yaml` (`chmod 600`).
3. Restart: `docker compose -f templates/docker-compose.yml restart`
4. Confirm `sensor.modeldeck_{provider}_status` is `ok`.
5. Check `sensor.{provider}_usage` and `sensor.{provider}_usage_weekly` within one poll interval.

### CLI helper (on a machine with credential files)

```bash
modeldeck credentials print --all
modeldeck credentials print --provider codex --full
modeldeck credentials print --all --write-secrets   # merge into config/secrets.yaml
```

## Codex (OpenAI)

### Subscription (`auth_mode: subscription`)

Tracks ChatGPT/Codex plan limits (5h / 7d windows).

**Option A — Codex CLI (recommended)**

1. Install and sign in: [Codex CLI](https://github.com/openai/codex)
2. Copy tokens from `~/.codex/auth.json` (or `~/.config/codex/auth.json`):

```yaml
providers:
  codex:
    access_token: "eyJ..."
    refresh_token: "rt_..."
    account_id: "user-..."
```

**Option B — Docker bind-mount**

```yaml
volumes:
  - ./config:/config
  - ~/.codex:/root/.codex:ro
```

Leave `credential_path` unset; ModelDeck reads `/root/.codex/auth.json` inside the container.

**Option C — Browser extraction**

Extract OAuth `access_token` from an authenticated ChatGPT session (advanced; same tokens as Codex CLI stores).

Official docs: none for this endpoint.

### API (`auth_mode: api`)

Tracks **Platform organization spend** (USD), not ChatGPT subscription %.

1. Open [Organization Admin Keys](https://platform.openai.com/settings/organization/admin-keys)
2. Create a **read-only** admin key (`sk-admin-...`)
3. Paste into `secrets.yaml`:

```yaml
providers:
  codex:
    api_key: "sk-admin-..."
```

Official docs: [Usage and costs](https://platform.openai.com/docs/api-reference/usage/costs)

!!! warning
    Standard project keys (`sk-proj-...`) and user keys (`sk-...`) **do not** work for usage/cost APIs.

## Claude

### Cookie (`auth_mode: cookie`)

For claude.ai Pro/Max subscribers.

1. Sign in at [claude.ai](https://claude.ai)
2. Open DevTools → Application → Cookies → `https://claude.ai`
3. Copy **all four** cookies (not just the first two — the Cloudflare and
   device cookies are what get you past HTTP 403):
   - `sessionKey` → `session_token`
   - `lastActiveOrg` → `org_id` (a UUID is normal)
   - `cf_clearance` → `cf_clearance`
   - `anthropic-device-id` → `device_id`

```yaml
providers:
  claude:
    session_token: "sk-ant-sid01-..."
    org_id: "..."
    cf_clearance: ""   # paste cf_clearance; required for many 403s
    device_id: ""      # paste anthropic-device-id when present
```

!!! warning "Docker + cookie mode"
    `cf_clearance` is bound to the **IP and User-Agent** that solved the
    Cloudflare challenge. When ModelDeck runs in Docker, the container's
    outbound IP differs from your browser, so claude.ai can still return
    **403** even with correct cookies. If 403 persists after re-copying all
    four cookies, run ModelDeck on the same host/IP as the browser. Use
    `modeldeck credentials verify --provider claude` to confirm the live
    status and hint.

### OAuth (`auth_mode: oauth`)

For **Claude Code** subscribers only. claude.ai Pro/Max web subscriptions
use `cookie` mode above, not `oauth`.

1. Sign in with Claude Code CLI on a machine with `~/.claude/.credentials.json`
2. Copy `claudeAiOauth.accessToken` and `refreshToken`, or bind-mount the file:

```yaml
providers:
  claude:
    access_token: "..."
    refresh_token: "..."
```

Official docs: none for the OAuth usage endpoint (undocumented).

## Cursor

### Personal (`auth_mode: personal`)

**Option A — Dashboard cookie (easiest)**

1. Sign in at [cursor.com/dashboard/usage](https://cursor.com/dashboard/usage)
2. DevTools → Cookies → copy `WorkosCursorSessionToken`

```yaml
providers:
  cursor:
    session_token: "..."
```

**Option B — App JWT**

Copy `cursorAuth/accessToken` from Cursor `state.vscdb`:

| OS | Path |
|----|------|
| Linux | `~/.config/Cursor/User/globalStorage/state.vscdb` |
| macOS | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Windows | `%APPDATA%\Cursor\User\globalStorage\state.vscdb` |

```yaml
providers:
  cursor:
    access_token: "eyJ..."
```

### Enterprise (`auth_mode: enterprise`)

Team / Enterprise admins only. Personal accounts must use `personal`.

1. [cursor.com/dashboard](https://cursor.com/dashboard) → Settings → Advanced → Admin API Keys
2. Create key (`crsr_...` or `key_...` format)
3. Paste:

```yaml
providers:
  cursor:
    admin_api_key: "crsr_..."
```

Official docs: [Admin API — Get Spending Data](https://cursor.com/docs/account/teams/admin-api)

## Home Assistant OS

### Add-on Configuration tab (recommended)

Install the ModelDeck add-on ([haos-addon guide](../getting-started/haos-addon.md)) and paste credentials in **Settings → Add-ons → ModelDeck → Configuration**. MQTT host defaults to `core-mosquitto` when using the official Mosquitto add-on.

### File-based setup

1. Edit `config/secrets.yaml` via Samba, SSH, or the File Editor add-on.
2. Use `modeldeck credentials print` on your PC, then paste the YAML block.
3. For CLI credential files, bind-mount read-only into the container (see Codex example above).
4. Set `IMAGE_TYPE=nightly` in `.env` for latest `dev` features until the next release tag.

## Token refresh

Codex subscription and Claude OAuth collectors refresh tokens on HTTP 401.

| Mechanism | Config key | Default | When |
|-----------|------------|---------|------|
| Runtime token persist | `service.persist_refreshed_tokens` | `true` | During polling — writes refreshed OAuth tokens to `secrets.yaml` |
| Configuration Save merge | `reset_secrets` = `false` | off (HA add-on) | Each Save merges UI into on-disk secrets; empty password fields do not wipe OAuth tokens |
| Full replace on Save | `reset_secrets` = `true` | — | Replaces secrets with form only — use only when rotating credentials |

When `persist_refreshed_tokens` is `true` (default) and `secrets.yaml` is writable, refreshed tokens survive container or add-on restarts without re-pasting from the UI.

Docker: ensure `./config` is bind-mounted read-write (default in `templates/docker-compose.yml`).

## Troubleshooting

| `collector_status` | Action |
|--------------------|--------|
| `auth_error` | Re-copy token/cookie; check `auth_mode` matches account type |
| `rate_limited` | Wait and retry; reduce poll frequency |
| `parse_error` | Provider changed API shape; check GitHub issues |
| `unavailable` | Provider outage or network issue |

| Symptom | Fix |
|---------|-----|
| Codex `api` fails with 401 | Use `sk-admin-*` key, not `sk-proj-*` |
| Claude 403 (cookie) | Copy all 4 cookies incl. `cf_clearance`; in Docker, run on the browser's host/IP |
| Cursor enterprise 403 | Confirm Team/Enterprise plan and admin key scope |
| Weekly sensor empty | Normal for Cursor personal (billing cycle only) |

## Manual smoke checklist

After configuring credentials:

- [ ] `sensor.modeldeck_codex_status` = `ok`
- [ ] `sensor.modeldeck_claude_status` = `ok`
- [ ] `sensor.modeldeck_cursor_status` = `ok`
- [ ] `sensor.modeldeck_codex_usage_percent` shows a percentage (subscription) or spend (api)
- [ ] `sensor.modeldeck_codex_usage_weekly_percent` populated (subscription)
- [ ] `sensor.modeldeck_claude_usage_weekly_percent` populated (cookie/oauth)
- [ ] Tokens survive container restart (OAuth refresh persistence)
