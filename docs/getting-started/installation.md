# Installation

## Requirements

- Docker with Compose v2
- A reachable MQTT broker (Home Assistant Mosquitto add-on or standalone)
- `linux/amd64` or `linux/arm64` host (GHCR images are multi-arch)

## Quick start (stable image)

From the repository root:

```bash
cp .env.example .env
./ops/bootstrap-config.sh          # quickstart: mock provider for smoke test
# or: ./ops/bootstrap-config.sh production
docker compose -f templates/docker-compose.yml up -d
```

On Windows, use `.\ops\bootstrap-config.ps1` instead of the shell script.

This pulls `ghcr.io/automationnexus/modeldeck:latest` by default. Edit `config/modeldeck.yaml` and `config/secrets.yaml` before or after first boot.

## Smoke test then real providers

1. **Quickstart** (`bootstrap-config.sh`) — mock data only; confirm HA entities appear.
2. **Production** — re-run `bootstrap-config.sh production` or copy `templates/modeldeck.example.yaml` to `config/modeldeck.yaml`, fill `config/secrets.yaml`, restart the container.
3. Verify `sensor.modeldeck_{provider}_status` is `ok` for each enabled provider.
4. Paste dashboard YAML from `examples/home-assistant/` (Overview + ModelDeck tab) — [dashboard.md](../guides/dashboard.md).

See [configuration.md](../admin/configuration.md) for Codex, Claude, and Cursor credentials.

For step-by-step token extraction (browser, CLI, HAOS), see [credentials.md](../guides/credentials.md).

## Home Assistant OS add-on

On HAOS, install from the dedicated add-on repository instead of Docker Compose:

1. Add repository `https://github.com/automationnexus/ModelDeck` (**Settings → Add-ons → Repositories**)
2. Install **ModelDeck**, configure MQTT + credentials in the **Configuration** tab
3. Start the add-on and verify MQTT sensors

Full walkthrough: [haos-addon.md](haos-addon.md).

## Local build (contributors)

```bash
./ops/bootstrap-config.sh
docker compose -f templates/docker-compose.build.yml up --build -d
```

## Nightly image (dev testers)

Set `IMAGE_TYPE=nightly` in `.env`, then run compose as above.

## Home Assistant

Ensure the Mosquitto broker is running. ModelDeck publishes MQTT Discovery sensors on startup.

See [home-assistant.md](../guides/home-assistant.md).
