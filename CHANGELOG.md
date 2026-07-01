# Changelog

All notable changes are documented here.

## [Unreleased] - HA add-on repo merge

### Changed

- The `ModelDeck-HAOS` Home Assistant add-on repository has been merged into this repo.
  `modeldeck/` (stable channel) and `modeldeck-nightly/` (nightly channel) now live here;
  HA users should point their add-on store repository URL at
  `https://github.com/automationnexus/ModelDeck` instead of `ModelDeck-HAOS`.
- Prior `ModelDeck-HAOS` repo-level history: `0.0.1` (2026-06-19) — initial Home Assistant
  OS Supervisor add-on for ModelDeck, add-on repository with Configuration UI for MQTT and
  provider credentials, CI validation for add-on metadata and pinned `BUILD_FROM` image tag.

## [Unreleased] - Claude OAuth fix, account rename, live reload, entity viewer

### Fixed

- **Claude OAuth "Token endpoint returned 400"**: Claude's token endpoint requires
  the OAuth `state` parameter in the exchange body, and returns the authorization code
  in a bare `CODE#STATE` format. `extract_code_from_redirect` sent the full `CODE#STATE`
  string as the code, causing the 400. Fixed by adding `parse_code_and_state()` which
  correctly splits the hash and threads `state` through `exchange_code` only for providers
  that declare `token_exchange_includes_state=True` (`CLAUDE_SPEC`). Codex unchanged.

### Added

- **Account rename**: `POST /accounts/{provider}/{id}/rename` with body
  `{label, update_entity_id}`. Toggle off (default/recommended): only the label
  updates; entity_id/`unique_id` stay stable and HA history + automations are
  preserved. Toggle on (Z2M-style): slug is regenerated from the new label and secrets
  are migrated — HA history referencing the old entity_id breaks (modal warns).
  `move_account_secrets()` helper added to `secrets_writer.py`.
- **Rename modal in web UI**: "Rename" button on each account card opens a modal with
  a pre-filled label field and an "Update Home Assistant entity ID" toggle (default off)
  with a clear tradeoff explanation.
- **Live config reload**: The service now detects changes to `modeldeck.yaml` /
  `secrets.yaml` every ~5s (via `ConfigWatcher` mtime). On change it rebuilds collectors,
  retires removed/disabled accounts via MQTT, and forces discovery republish — no add-on
  restart needed. Add/delete/toggle/rename all apply within one reload cycle.
- **Per-account entity ID and MQTT topic viewer**: "View entities" button on each
  account card opens a modal popup listing `entity_id`, `state_topic`, and
  `discovery_topic` for every candidate metric, plus `device_id` and
  `availability_topic`. All values are copyable with one click.
  Backend: `GET /accounts/{provider}/{id}/entities`.

## [Unreleased] - OAuth UX hardening + fresh-install fix

### Fixed

- **Claude OAuth redirect URI rejected**: `CLAUDE_SPEC.redirect_uri` was
  `https://modeldeck.local/oauth/callback` which is not registered with Anthropic's
  public Claude client. Changed to `https://console.anthropic.com/oauth/code/callback`
  (the Claude Code CLI's allow-listed URI). The callback page now renders and displays
  the authorization code instead of showing "Authorization failed."
- **Fresh install shows three disabled default accounts**: `build_config_dict` in
  `addon_bootstrap.py` unconditionally seeded a `default` account for codex/claude/cursor
  even when disabled with no credentials. The seeding is now conditional — a default
  account is only created when the provider is enabled or has credentials set. Fresh
  installs start with zero accounts; accounts are added via the web UI.
- **Paste-back extractor too strict**: `extract_code_from_redirect` only accepted `http`-
  prefixed URLs. It now handles: scheme-less address-bar URLs, `#fragment` codes, bare
  `code=VALUE` param strings, surrounding quotes/angle-brackets, and bare codes. Any
  full URL copied from the browser address bar is parsed automatically.

### Changed

- **OAuth wizard paste box**: label updated to "Paste the full URL from your browser's
  address bar" with provider-specific placeholder examples. Accepts a full URL or bare
  code — ModelDeck extracts the authorization code automatically.
- **Codex OAuth paste-back note**: clarifies that the `localhost:1455` page failing to
  load is expected; instructs to copy the entire address-bar URL and paste it in.
- **Claude OAuth paste-back note**: updated to reflect the new `console.anthropic.com`
  callback page that displays the code; instructs to copy the full URL or the displayed
  code and paste it in.

## [Unreleased] - Codex OAuth fix + OAuth-first wizard

### Fixed

- **Codex OAuth broke with NextAuth error**: `CODEX_SPEC` pointed to wrong endpoints
  (`chatgpt.com/api/auth/authorize` — a NextAuth route that rejects GET). Now uses
  the real Codex CLI OAuth server: `https://auth.openai.com/oauth/authorize` and
  `https://auth.openai.com/oauth/token`.
- **Codex token exchange failed silently**: the shared `_post_token` always sent JSON;
  Codex's token endpoint requires `application/x-www-form-urlencoded`. Per-provider
  `token_encoding` field added to `ProviderOAuthSpec`; Codex uses `"form"`, Claude `"json"`.
- **Codex account_id not saved**: the collector sends `ChatGPT-Account-Id` header using
  `secrets.account_id`. After OAuth exchange, `account_id` is now extracted from the
  `id_token` JWT claims (`https://api.openai.com/auth.chatgpt_account_id`) and persisted.
- **Codex OAuth set wrong auth_mode**: `oauth_complete` now sets `auth_mode=subscription`
  for Codex (the collector's mode for OAuth-backed tokens) and `auth_mode=oauth` for Claude.

### Added

- **`/accounts/{provider}/{account_id}/switch-oauth` endpoint**: one-click action that
  updates an existing account's `auth_mode` to the OAuth mode then returns the OAuth start
  payload (authorize URL + session key), so the UI opens the wizard in one step.
- **"Switch to OAuth" card action**: shown on Claude/Codex accounts not already in OAuth
  mode, allowing upgrade from cookie/api/paste-back to independent OAuth session.
- **OAuth-first wizard defaults**: wizard pre-selects `subscription` for Codex and `oauth`
  for Claude (both OAuth-capable and independent-session modes).
- **Paste-back instructions per provider**: OAuth step shows provider-specific note
  explaining that the redirect page won't load and how to copy the `code=` value from
  the address bar (`localhost:1455` for Codex, `modeldeck.local` for Claude).
- **Cursor no-OAuth warning**: account card and wizard show "Cursor has no public OAuth
  flow — this token shares your browser/app session."
- **`extra_authorize_params` on `ProviderOAuthSpec`**: Codex adds `originator`,
  `codex_cli_simplified_flow`, `id_token_add_organizations` to the authorize URL,
  matching the Codex CLI's simplified login flow. Env-overridable per param.
- **`decode_id_token_claims` / `extract_codex_account_id`** helpers in `oauth_flow.py`.
- 39 new Python tests; 16 new Vitest tests; coverage **97.21%**.

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
- HAOS Supervisor add-on moved to a dedicated `ModelDeck-HAOS` repo (later merged back into this repo — see `[Unreleased] - HA add-on repo merge` above)

### Added

- Docker image and Python service for Codex, Claude, and Cursor MQTT usage sensors
- CI on org self-hosted runners (`self-hosted`, `Linux`, `X64`)
