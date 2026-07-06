---
description: Run local QA (Python/MQTT side) and report pass/fail blockers.
argument-hint: [optional scope]
---

Dispatch `qa-gatekeeper`: `git status --short --branch`, `ruff check src tests`,
`python -m pytest -q`, `pre-commit run --all-files` (if installed), `git diff --check`.
Return pass/fail and actionable blockers only. No file edits. Arguments: $ARGUMENTS
