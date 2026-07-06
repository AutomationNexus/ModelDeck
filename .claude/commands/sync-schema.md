---
description: Review add-on options/schema parity with the ModelDeck service config.
argument-hint: [optional scope]
---

Dispatch `addon-engineer` to review options/schema drift: $ARGUMENTS

`git status`. Read `modeldeck/config.yaml` `options` and `schema`. Compare keys against the
ModelDeck service config (sibling checkout or docs site for MQTT, service, provider fields).
Ensure every `options` key has a matching `schema` entry with the correct HA type. Run
`python tools/validate_ha_addon.py`. Summarize missing/extra/mismatched keys by section
(`mqtt`, `service`, `codex`, `claude`, `cursor`). No credential values.
