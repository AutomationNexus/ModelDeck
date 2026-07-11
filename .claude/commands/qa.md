---
description: Run local QA (Python/MQTT side) and report pass/fail blockers.
argument-hint: [optional scope]
---

Dispatch the `qa-gatekeeper` subagent to run this repository's local QA gate (the
commands in CLAUDE.md's "QA gates" section). Return pass/fail and actionable blockers
only. No file edits. Scope/arguments: $ARGUMENTS

<!-- repo-specific -->

Python/MQTT-side QA gate (the add-on-side counterpart is `/addon-qa`): dispatch
`qa-gatekeeper` to run `git status --short --branch`, `ruff check src tests`,
`python -m pytest -q`, `pre-commit run --all-files` (if installed), `git diff --check`.
