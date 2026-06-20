# ModelDeck

[![CI](https://github.com/automationnexus/ModelDeck/actions/workflows/ci.yml/badge.svg)](https://github.com/automationnexus/ModelDeck/actions/workflows/ci.yml)
[![Nightly](https://github.com/automationnexus/ModelDeck/actions/workflows/nightly.yml/badge.svg)](https://github.com/automationnexus/ModelDeck/actions/workflows/nightly.yml)
[![Release](https://github.com/automationnexus/ModelDeck/actions/workflows/release.yml/badge.svg)](https://github.com/automationnexus/ModelDeck/actions/workflows/release.yml)
[![Semgrep](https://github.com/automationnexus/ModelDeck/actions/workflows/semgrep.yml/badge.svg)](https://github.com/automationnexus/ModelDeck/actions/workflows/semgrep.yml)
[![Docs](https://github.com/automationnexus/ModelDeck/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/automationnexus/ModelDeck/actions/workflows/docs.yml)
[![Security](https://img.shields.io/badge/security-policy-blue)](SECURITY.md)
[![GHCR](https://img.shields.io/badge/ghcr-modeldeck:latest-blue)](https://github.com/automationnexus/ModelDeck/pkgs/container/modeldeck)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**ModelDeck** is a Dockerized AI usage and quota bridge for Home Assistant. It collects account-level usage, limits, reset times, credits, and plan data from **OpenAI Codex**, **Claude**, and **Cursor**, then publishes MQTT Discovery sensors for dashboards and automations.

**Status:** **`v0.0.1`** on `main` (`:latest`); integration builds on `dev` (`:nightly`).

### Current features

- **Metric-aware MQTT** — only discovers sensors your auth mode can populate (no **Unknown** quota fields)
- **Stable entity IDs** — `sensor.modeldeck_{provider}_{metric}` (see [sensors.md](docs/guides/sensors.md))
- **Cursor dual pools** — `sensor.modeldeck_cursor_usage_auto_percent` and `sensor.modeldeck_cursor_usage_api_percent`
- **Claude extra-usage** — `sensor.modeldeck_claude_usage_used` / `usage_limit` from on-demand budget
- **Dashboard examples** — 4-column ModelDeck tab + dual-gauge overview; optional card-mod `auth_error` styling

See [sensors.md](docs/guides/sensors.md) for the full sensor matrix.

## How it works

1. You paste provider tokens or cookies (from a browser or CLI on any PC).
2. ModelDeck polls each enabled provider on a schedule (default 5 minutes).
3. Sensors appear in Home Assistant via MQTT Discovery — for example `sensor.modeldeck_codex_usage_percent`, `sensor.modeldeck_claude_usage_weekly_percent`, `sensor.modeldeck_codex_status`.

ModelDeck does **not** log you in. Copy credentials once; the service reuses them on each poll. OAuth-based modes can auto-refresh tokens when configured.

## Quick start (Docker)

```bash
cp .env.example .env
./ops/bootstrap-config.sh
docker compose -f templates/docker-compose.yml up -d
```

Edit `config/modeldeck.yaml` (providers, auth modes) and `config/secrets.yaml` (tokens and keys). Use `bootstrap-config.sh production` for real providers. See [installation.md](docs/getting-started/installation.md).

## Home Assistant OS add-on

Install ModelDeck on HAOS via the dedicated add-on repository:

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories** → add `https://github.com/automationnexus/ModelDeck-HAOS`
2. Install **ModelDeck**, open **Configuration**, fill MQTT + provider sections, **Save**, **Start**
3. **Settings → Devices & services → MQTT** — confirm ModelDeck devices and `sensor.modeldeck_*_status` = `ok`

Full walkthrough: [ModelDeck-HAOS](https://github.com/automationnexus/ModelDeck-HAOS/blob/main/docs/getting-started/haos-addon.md)

## Getting credentials (all three providers)

Pick the auth mode that matches **how you pay**, then copy the listed values into `config/secrets.yaml` (Docker) or the add-on **Configuration** tab (HAOS).

### OpenAI Codex

| Auth mode | Account type | What to copy | Where to get it |
|-----------|--------------|--------------|-----------------|
| `subscription` | ChatGPT Plus/Pro / Codex plan | `access_token`, `refresh_token`, `account_id` | [Codex CLI](https://github.com/openai/codex) → `~/.codex/auth.json` after login |
| `api` | OpenAI Platform org billing | `api_key` (`sk-admin-…`) | [Organization Admin Keys](https://platform.openai.com/settings/organization/admin-keys) |

**CLI helper (on a PC with auth files):**

```bash
modeldeck credentials print --provider codex --full
```

### Claude

| Auth mode | Account type | What to copy | Where to get it |
|-----------|--------------|--------------|-----------------|
| `cookie` | claude.ai Pro/Max | `session_token` (sessionKey), `org_id` (lastActiveOrg) | Browser DevTools → Cookies → `https://claude.ai` while signed in |
| `oauth` | Claude Code | `access_token`, `refresh_token`; optional `subscription_tier` (HA add-on) | `~/.claude/.credentials.json` → `claudeAiOauth` after Claude Code login |

For cookie mode HTTP 403, also copy `cf_clearance` from the same cookie jar.

#### Claude OAuth: missing Plan or 5h Reset At?

ModelDeck only discovers a sensor when the provider returns data for that field. **OAuth** mode often shows Usage % and Weekly usage but not every field Codex publishes — this is usually **not a bug**.

| Sensor | Entity | OAuth behavior |
|--------|--------|----------------|
| Usage % (5h) | `sensor.modeldeck_claude_usage_percent` | Usually present |
| Weekly usage % | `sensor.modeldeck_claude_usage_weekly_percent` | Usually present |
| Weekly reset | `sensor.modeldeck_claude_reset_weekly_at` | Usually present |
| **Reset At (5h)** | `sensor.modeldeck_claude_reset_at` | **Often missing** when Anthropic returns `five_hour.resets_at: null` (common at 0% 5h utilization) |
| **Plan** | `sensor.modeldeck_claude_plan` | From API/credentials when available; set **Subscription tier** in the HA add-on (e.g. `Pro`, `Max`) or use **cookie** mode |

For full parity with Codex-style sensors (Plan + 5h reset more reliably), use **cookie** mode on claude.ai Pro/Max. Details: [sensors.md](docs/guides/sensors.md).

```bash
modeldeck credentials print --provider claude --full
```

### Cursor

| Auth mode | Account type | What to copy | Where to get it |
|-----------|--------------|--------------|-----------------|
| `personal` | Pro/Ultra individual | `session_token` **or** `access_token` | Cookie: DevTools → `WorkosCursorSessionToken` at [cursor.com/dashboard/usage](https://cursor.com/dashboard/usage). JWT: `cursorAuth/accessToken` in Cursor `state.vscdb` |
| `enterprise` | Team / Enterprise | `admin_api_key` | [cursor.com/dashboard](https://cursor.com/dashboard) → Settings → Advanced → Admin API Keys |

```bash
modeldeck credentials print --provider cursor --full
```

Merge everything at once:

```bash
modeldeck credentials print --all --write-secrets   # writes to config/secrets.yaml
```

### Example `secrets.yaml` (subscription + cookie + personal)

```yaml
providers:
  codex:
    access_token: "eyJ..."
    refresh_token: "rt_..."
    account_id: "user-..."
  claude:
    session_token: "sk-ant-sid01-..."
    org_id: "org_..."
  cursor:
    session_token: "..."
```

Match `auth_mode` in `modeldeck.yaml` (or the add-on UI) to each block. Details: [credentials.md](docs/guides/credentials.md).

---

## Verify

| Check | Expected |
|-------|----------|
| `sensor.modeldeck_codex_status` | `ok` |
| `sensor.modeldeck_claude_status` | `ok` (if enabled) |
| `sensor.modeldeck_cursor_status` | `ok` (if enabled) |
| `sensor.modeldeck_codex_usage_percent` | % used (subscription) or spend (api) |
| Poll interval | Updates within configured interval (default 5 min) |

If status is `auth_error`, re-copy credentials and confirm auth mode matches your account type.

---

## Documentation

| Need | Document |
|------|----------|
| Install (Docker) | [docs/getting-started/installation.md](docs/getting-started/installation.md) |
| Install (HAOS add-on) | [ModelDeck-HAOS](https://github.com/automationnexus/ModelDeck-HAOS) |
| Provider credentials | [docs/guides/credentials.md](docs/guides/credentials.md) |
| Configure providers | [docs/admin/configuration.md](docs/admin/configuration.md) |
| MQTT topics | [docs/guides/mqtt-topics.md](docs/guides/mqtt-topics.md) |
| Sensors (per auth mode) | [docs/guides/sensors.md](docs/guides/sensors.md) |
| Dashboard examples | [docs/guides/dashboard.md](docs/guides/dashboard.md) |
| Home Assistant | [docs/guides/home-assistant.md](docs/guides/home-assistant.md) |
| Full docs site | [https://automationnexus.github.io/ModelDeck/](https://automationnexus.github.io/ModelDeck/) |

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,service]"
.\ops\run-tests.ps1
```

## Branch and release model

| Branch | Purpose |
|--------|---------|
| `dev` | Day-to-day integration; PRs from feature branches; `:nightly` image on merge |
| `main` | Stable line; PR from `dev` only; semver tag + `:latest` on merge |

## Non-goals

- Built-in web dashboard (use Home Assistant Lovelace)
- Official provider partnerships or guaranteed API stability

## License

MIT — see [LICENSE](LICENSE).

<!-- nightly-e2e-verify -->

<!-- final-nightly-verify -->
