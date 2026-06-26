---
description: Execute approved plan through expert agents (implement, QA, review, optional PR).
agent: build
---

Run the ModelDeck execute pipeline for an approved plan.

Steps:
- Run `git status --short --branch` and confirm a feature branch (not `dev` or `main`). Create one from updated `dev` if needed.
- Invoke `@md-mqtt-engineer` to implement or verify Python/MQTT/provider changes from the approved plan.
- Invoke `@md-qa-gatekeeper` to run the full `/md-qa` local gate.
- Invoke `@md-reviewer` for independent review of changed files.
- Stop on the first failed gate.
- Push the feature branch and open a PR to `dev` (never push directly to `dev` or `main`).

Return a compact handoff: agents used, commands run, pass/fail. Arguments: `$ARGUMENTS`.
