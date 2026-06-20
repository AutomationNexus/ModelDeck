# Threat Model

## Assets

- Provider API keys and session tokens in `/config/secrets.yaml`
- MQTT broker credentials
- Quota usage data (non-sensitive but private)

## Trust boundaries

- ModelDeck container → provider HTTP APIs (internet)
- ModelDeck container → MQTT broker (LAN)
- Home Assistant ← MQTT broker

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Token theft from volume | File permissions check; non-root container |
| Token leakage in logs | RedactingFilter |
| MQTT credential sniffing | TLS option; dedicated MQTT user |
| Unofficial API ToS | Documented operator responsibility |

## Future

Optional encryption at rest with `/data/master.key` (not implemented in 0.0.x).
