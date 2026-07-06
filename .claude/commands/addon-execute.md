---
description: Execute an approved plan for the HA add-on side (modeldeck/, modeldeck-nightly/) through expert subagents.
argument-hint: [optional focus notes]
---

Execute pipeline for an approved add-on plan: $ARGUMENTS

1. `git status` — confirm/checkout a feature branch from `dev`.
2. Dispatch `addon-engineer` for add-on config, Dockerfile, run.sh, docs.
3. Dispatch `addon-qa-gatekeeper` for the `/addon-qa` gate.
4. Stop on first failure.
5. Push → PR to `dev`.
