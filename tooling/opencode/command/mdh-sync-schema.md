---
description: Review add-on options/schema parity with ModelDeck service config.
agent: mdh-addon-engineer
---

Review options/schema drift. `git status`. Read `modeldeck/config.yaml` `options` and `schema`. Compare keys against ModelDeck service config (sibling checkout or docs site for MQTT, service, provider fields). Ensure every `options` key has a matching `schema` entry with correct HA type. Run `python tools/validate_ha_addon.py`. Summarize missing/extra/mismatched keys by section (`mqtt`, `service`, `codex`, `claude`, `cursor`). No credential values. Arguments: `$ARGUMENTS`.
