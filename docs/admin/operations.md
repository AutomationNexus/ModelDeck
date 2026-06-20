# Operations

## Logs

ModelDeck logs to stdout. Sensitive values are redacted.

## Poll interval

Default: 300 seconds (minimum 60). Increase if providers rate-limit your account.

## State cache

Last-good snapshots are stored when `service.retain_state` is true:

| Deployment | Path |
|------------|------|
| Docker Compose | `/data/state.json` (bind mount) |
| HAOS add-on | `/config/data/state.json` (add-on config volume) |

## Upgrades

**Stable (recommended):**

```bash
docker pull ghcr.io/automationnexus/modeldeck:latest
docker compose -f templates/docker-compose.yml up -d
```

**Nightly (dev integration):** set `IMAGE_TYPE=nightly` in `.env`, then run the same compose command.

Pinned semver: `IMAGE_TYPE=v0.0.1` (or newer tag from [GitHub Releases](https://github.com/automationnexus/ModelDeck/releases)).

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No HA entities | MQTT broker reachable; `mqtt.host` correct; discovery prefix `homeassistant` |
| Gauges show mock data | Disable `providers.mock` in `modeldeck.yaml` |
| `auth_error` on status sensor | Renew token/API key in `secrets.yaml`; restart container |
| `parse_error` | Provider API may have changed — check GitHub issues |
| `rate_limited` | Increase `service.poll_interval_seconds` |
| Sensors show old "last updated" | Upgrade to v0.1.1+; restart add-on; check logs for `MQTT publish failed` or `Collection cycle failed` |
| Collectors failing | Check `sensor.modeldeck_{provider}_status` in Home Assistant |
