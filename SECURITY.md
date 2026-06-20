# Security Policy

## Reporting a Vulnerability

Please do not file a public issue for undisclosed security vulnerabilities.

Use GitHub's **Report a vulnerability** flow for this repository.

## Scope

In scope:

- ModelDeck application code and Docker defaults.
- MQTT publishing and provider credential handling.
- Documentation that could cause unsafe secret storage.

Out of scope:

- Home Assistant or Mosquitto themselves.
- Operator host security.
- Stolen credentials unrelated to ModelDeck behavior.

## Secure Defaults

- Provider tokens belong in `/config/secrets.yaml` on a mounted volume.
- Never log authorization headers, cookies, or session tokens.
- Use TLS for MQTT when credentials cross untrusted networks.

See [docs/security/threat-model.md](docs/security/threat-model.md) for details.
