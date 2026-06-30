# Changelog

All notable changes are documented here.

## [Unreleased] - modern web UI + functional fixes

### Breaking

- **HAOS add-on provider sections removed**: codex/claude/cursor blocks removed from the
  add-on Configuration tab. All account setup moves to the **Ingress web UI** (Open Web UI).
  Existing add-on option values for provider credentials become inert; re-enter tokens via
  the web UI wizard.
- **`POST /accounts/{provider}/{id}/token` body changed**: `{"token": ..., "field": ...}`
  → `{"field": ..., "value": ...}`. Any tooling calling this endpoint directly must update.

### Added

- **Modern Ingress web UI**: Vite + React 19 + TypeScript SPA replacing the minimal inline
  fallback. HA-themed dark CSS (Zigbee2MQTT-style), card layout, provider icons, live status
  badges, loading skeletons, error toasts, and 30-second auto-refresh.
- **Add Account wizard**: single multi-step modal (provider → auth mode → credentials) that
  creates and enables the account only on credential success. No disabled stubs.
- **Provider-specific auth modes**: wizard restricts modes and required fields by provider
  (codex: subscription/api; claude: oauth/cookie; cursor: personal/enterprise).
- **`GET /providers`** extended with per-mode required credential field metadata so the UI
  can render the right inputs without hardcoding.
- `frontend/` directory with `package.json`, `vite.config.ts`, Vitest unit tests.
- `tests/e2e_frontend/` Playwright broader E2E suite (wizard flow, Ingress base path,
  account enable/persist, delete).
- `requirements-dev-frontend.txt` (Playwright pins).
- Multi-stage `Dockerfile`: `node:24-bookworm-slim AS frontend` → npm build → Python image.
- CI `has-frontend: true`, `has-e2e: true`, `node-version: "24"`, `spa-artifact-path`.

### Fixed

- **"Add Account does nothing" under HA Ingress**: all frontend API calls now use Ingress-
  relative base path computed from `window.location.pathname`; absolute `/accounts` calls
  that hit the HA root are gone.
- **Errors silently swallowed**: central `api()` client checks `res.ok`, parses backend
  `detail`, and surfaces errors via toasts and inline form messages.
- **New accounts left disabled after auth**: `POST /accounts/.../oauth/complete` and
  `POST /accounts/.../token` now call `upsert_account_in_config()` which updates `enabled`
  and `auth_mode` on existing accounts (not append-only).
- **Web-UI accounts wiped on add-on restart**: `render_addon_config()` now merges with
  existing `modeldeck.yaml`, preserving non-default accounts created via the web UI.

## [Unreleased] - multi-account + OAuth wizard

### Breaking

- **Entity IDs now include account slug:** `sensor.modeldeck_{provider}_{account}_{metric}`.
  The `default` account (from static add-on options or a single secrets block) produces
  `sensor.modeldeck_claude_default_usage_percent` etc. Old single-account topics are retired
  automatically on first startup. **Update all dashboards and automations.**
- `secrets.yaml` shape changes from `providers.{provider}.{field}` to
  `providers.{provider}.{account_id}.{field}`. Legacy flat secrets are auto-migrated to
  the `default` account on first read. No manual action required.

### Added

- **Multi-account support** (`modeldeck.config.loader.ProviderAccount`): multiple accounts
  per provider, each with its own HA device and sensors.
- **OAuth PKCE login wizard** (`modeldeck.auth`): Claude and Codex accounts can be
  authenticated with an authorize-URL paste-back flow — no CLI credential files needed.
  Provider protocol metadata (URLs, client_id, scopes) lives in `auth.provider_specs`;
  overridable via env vars.
- **HAOS Ingress web UI** (`modeldeck.webui`): FastAPI + minimal HTML/JS served on port 8099
  via HA add-on Ingress panel. Supports add/verify/delete/enable/disable accounts, OAuth
  wizard, and token paste for Cursor — no file editor or SSH needed.
- `modeldeck login --provider claude|codex [--label NAME]` — CLI OAuth login wizard.
- `modeldeck accounts list|add|remove|disable|enable` — account management CLI.
- `modeldeck webui [--host HOST] [--port PORT]` — start the web UI server.
- Account-aware `secrets_writer.persist_provider_oauth_tokens` and `write_account_secrets`.
- Integration tests excluded by default from `pytest -q`; run with `-m integration`.
- `fastapi>=0.111`, `uvicorn>=0.29` added to `service` and new `webui` extra.

### Changed

- MQTT `unique_id`, `object_id`, entity IDs, state/discovery topics, and device identifiers
  are all account-aware (include `{account}` segment).
- `mqtt.client._published_metrics` and `_last_success` keyed by `(provider, account)`.
- State cache keys are now `"{provider}/{account_id}"`.
- `build_collectors` iterates `list[ProviderAccount]` per provider (backward-compatible with
  `ProviderToggle` via internal shim).

## [0.0.7] - 2026-06-28

### Added

- Add `modeldeck credentials verify` for safe provider credential diagnostics.

### Fixed

- Send browser-like headers for Claude cookie usage requests and add safe 403 hints.

### Changed

- Document all required Claude cookie fields and the Docker `cf_clearance` caveat.

## [0.0.6] - 2026-06-27

### Changed

- Routine release to validate the full PR-gated promote workflow end-to-end.

## [0.0.5] - 2026-06-27

### Fixed

- Recognize merged `dev` to `main` promotion PR commits in the main push guard.

## [0.0.4] - 2026-06-27

### Changed

- Route dev-to-main promotion through a PR-gated workflow instead of direct pushes.
- Keep the main push guard aligned with merged dev-to-main promotion PRs.

## [0.0.3] - 2026-06-27

### Changed

- Sync Home Assistant OS add-on automation with dual stable/nightly channels.
- Pin Trivy workflow action versions for repeatable CI.
- Add branch-policy and OpenCode setup parity for Windows local development.

## [0.0.1] - 2026-06-19

### Changed

- Fresh repository history; Docker-only install path in this repo
- HAOS Supervisor add-on moved to [ModelDeck-HAOS](https://github.com/automationnexus/ModelDeck-HAOS)

### Added

- Docker image and Python service for Codex, Claude, and Cursor MQTT usage sensors
- CI on org self-hosted runners (`self-hosted`, `Linux`, `X64`)
