---
description: Execute an approved plan for the Python/MQTT side through expert subagents (implement, QA, review, optional PR).
argument-hint: [optional focus notes]
---

Run the build pipeline for an approved plan: $ARGUMENTS

0. If this is a single-file/low-risk change, stop — implement it directly in the main
   session per the CLAUDE.md risk tiering (if defined) instead of running this full
   pipeline.
1. Confirm you are on a feature branch off `dev` (never `dev`/`main` directly), using
   the repo's branch prefix from `CLAUDE.md`.
2. Dispatch the repo's domain engineer agent(s) for the implementation (see the
   CLAUDE.md subagent table).
3. Dispatch `qa-gatekeeper` for the local QA gate.
4. Dispatch `reviewer` for independent review.
5. Stop and report on the first failed gate — do not continue past a failure.
6. Push the feature branch and open a PR to `dev`.

For hard cross-module conflicts or disagreement between subagents, escalate by
switching the main session to opus (`/model opus` or `opusplan`) rather than a
dedicated solver agent.

<!-- repo-specific -->

This is the Python/MQTT-side pipeline (the add-on-side counterpart is
`/addon-execute`). Step 2 dispatches `mqtt-engineer` to implement or verify
Python/MQTT/provider changes under `src/modeldeck/`. Step 3 runs the full `/qa`
local gate via `qa-gatekeeper`. Step 4 dispatches `reviewer` for independent review
of changed files. Push the feature branch and open a PR to `dev` — never push
directly to `dev` or `main`.
