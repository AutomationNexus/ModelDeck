---
description: Execute an approved plan for the Python/MQTT side through expert subagents (implement, QA, review, optional PR).
argument-hint: [optional focus notes]
---

Run the ModelDeck execute pipeline for an approved plan: $ARGUMENTS

0. If this is a single-file/low-risk change, stop — implement it directly in the main
   session per CLAUDE.md's risk tiering instead of running this full pipeline.
1. `git status --short --branch` — confirm a feature branch (not `dev`/`main`); create one
   from updated `dev` if needed.
2. Dispatch `mqtt-engineer` to implement or verify Python/MQTT/provider changes.
3. Dispatch `qa-gatekeeper` for the full `/qa` local gate.
4. Dispatch `reviewer` for independent review of changed files.
5. Stop on the first failed gate.
6. Push the feature branch and open a PR to `dev` (never push directly to `dev` or `main`).

For hard cross-module conflicts, escalate by switching the main session to opus
(`/model opus` or `opusplan`) rather than a dedicated solver agent.
