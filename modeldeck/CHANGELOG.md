# Changelog

## [0.0.7.2] - 2026-07-01

HAOS packaging update.

## [0.0.7.1] - 2026-07-01

HAOS packaging update.

All notable changes to the ModelDeck Home Assistant add-on are documented here.

## [Unreleased] - multi-account + Ingress UI

### Breaking

- MQTT entity IDs now include the account slug: `sensor.modeldeck_{provider}_{account}_{metric}`
  (e.g. `sensor.modeldeck_claude_default_usage_percent`). Existing dashboards and automations
  referencing `sensor.modeldeck_{provider}_{metric}` must be updated. Old topics are retired
  automatically on first startup so Home Assistant will remove the old entities.

### Added

- **Multi-account support** — add multiple accounts per provider (Codex, Claude, Cursor), each
  with its own Home Assistant sensors and device entry.
- **Ingress web UI** — open ModelDeck directly from the Home Assistant add-on panel
  (`Settings → Add-ons → ModelDeck → Open Web UI`, port 8099). Manages accounts without
  touching config files.
- **OAuth login wizard** (Claude + Codex) — click/open an authorize URL, paste back the code,
  ModelDeck exchanges it for tokens and saves them automatically.
- **Guided paste** for Cursor — paste JWT or session token through the web UI.
- **On-the-fly add/remove/disable** — accounts can be added or removed while the service is
  running; MQTT sensors appear or are retired accordingly.
- Provider spec registry: OAuth endpoint/client metadata centralized in
  `modeldeck.auth.provider_specs`; overridable via env vars.
- `modeldeck login` CLI command for Claude/Codex.
- `modeldeck accounts list|add|remove|disable` CLI commands.
- `fastapi` + `uvicorn` bundled in the parent image (`webui` extra).

### Changed

- Default account when using static add-on options is `default`; entity IDs become
  `sensor.modeldeck_{provider}_default_{metric}`.
- `secrets.yaml` now uses a nested `providers.{provider}.{account_id}.{field}` shape. Legacy
  flat secrets are migrated to the `default` account automatically on first read.

## [0.0.7.0] - 2026-06-29

### Changed

- Restore stable add-on pin to ModelDeck v0.0.7 (reverts erroneous v0.0.0.0 regression caused by unauthenticated gh api fallback in release workflow)

## [0.0.2.0] - 2026-06-27

### Changed

- Dual-channel add-on packaging: stable version uses parent release pin `v0.0.2`
- Add-on changelog now shown in Home Assistant update UI

## [0.0.1] - 2026-06-19

### Added

- Home Assistant OS Supervisor add-on for ModelDeck
- Add-on repository with Configuration UI for MQTT and provider credentials
- CI validation for add-on metadata and pinned `BUILD_FROM` image tag
