# Configuration

ModelDeck uses two files in `./config` (bind-mounted to `/config` in Docker):

| File | Purpose |
|------|---------|
| `modeldeck.yaml` | MQTT, poll interval, enabled providers, `auth_mode` per provider |
| `secrets.yaml` | Passwords and provider tokens (`chmod 600`) |

Bootstrap with `ops/bootstrap-config.sh` (quickstart) or `ops/bootstrap-config.sh production`.

On **Home Assistant OS**, use the [add-on Configuration tab](../getting-started/haos-addon.md) instead of editing these files by hand (the add-on renders them on start).

For step-by-step credential extraction per provider, see [credentials guide](../guides/credentials.md).

## Auth modes

| Provider | `auth_mode` | Credential | Source |
|----------|-------------|------------|--------|
| **codex** | `subscription` | `access_token`, `refresh_token`, `account_id` | ChatGPT/Codex OAuth (`~/.codex/auth.json` or browser) |
| **codex** | `api` | `api_key` (`sk-admin-*` Admin key) | [OpenAI Admin API](https://platform.openai.com/settings/organization/admin-keys) |
| **claude** | `cookie` | `session_token` (`sessionKey`), `org_id` (`lastActiveOrg`) | [claude.ai](https://claude.ai) cookies (see [ClaudeDash](https://github.com/mingzapingin/ClaudeDash)) |
| **claude** | `oauth` | `access_token`, `refresh_token` | Claude Code (`~/.claude/.credentials.json`) |
| **cursor** | `personal` | `session_token` (`WorkosCursorSessionToken`) or `access_token` | [cursor.com/dashboard/usage](https://cursor.com/dashboard/usage) or Cursor `state.vscdb` |
| **cursor** | `enterprise` | `admin_api_key` | Cursor team Admin API |

Set `auth_mode: auto` to pick the first mode with credentials (subscription/cookie/personal before api/enterprise).

Optional `credential_path` on each provider overrides the default CLI credential file location. Set `credential_path: ""` to disable file loading (secrets only).

### Docker + CLI credentials

Bind-mount host credential dirs read-only, for example:

```yaml
volumes:
  - ./config:/config
  - ~/.codex:/root/.codex:ro
```

Or paste tokens directly into `config/secrets.yaml`.

## Enable a provider

1. Set `enabled: true` and `auth_mode` in `config/modeldeck.yaml`.
2. Add credentials to `config/secrets.yaml`.
3. Restart: `docker compose -f templates/docker-compose.yml restart`.
4. Confirm `sensor.modeldeck_{provider}_status` is `ok`.
5. Check `sensor.{provider}_usage` and `sensor.{provider}_usage_weekly` within one poll interval (default 5 minutes).

## Codex (OpenAI)

**Subscription** (ChatGPT Plus/Pro plan limits): use `auth_mode: subscription`. Copy OAuth tokens from `~/.codex/auth.json` after signing in with the Codex CLI, or extract from ChatGPT browser session.

**API billing** (Platform organization spend): use `auth_mode: api` with an **Organization Admin key** (`sk-admin-...`). This tracks API costs in USD, not your ChatGPT subscription quota. See [credentials guide](../guides/credentials.md).

## Claude

**Cookie mode** (claude.ai web subscription): DevTools → Application → Cookies → copy `sessionKey` and `lastActiveOrg`.

**OAuth mode** (Claude Code): tokens load from `~/.claude/.credentials.json` when `credential_path` is unset.

Tokens expire — renew when `sensor.modeldeck_claude_status` shows `auth_error`.

## Cursor

**Personal**: copy `WorkosCursorSessionToken` from cursor.com dashboard cookies ([CursorMonitor](https://github.com/Coldaine/CursorMonitor) pattern).

**Enterprise**: Admin API key from team settings.

## Collector status values

| Value | Meaning |
|-------|---------|
| `ok` | Last collection succeeded |
| `auth_error` | Missing or expired credential |
| `rate_limited` | Provider returned HTTP 429 |
| `parse_error` | Response shape unexpected |
| `unavailable` | Provider returned 5xx or transport failure |

## MQTT broker

Set `mqtt.host` to your Home Assistant hostname or Mosquitto add-on IP. Add `mqtt.password` in `secrets.yaml` if required.
