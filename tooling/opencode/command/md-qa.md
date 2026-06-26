---
description: Run local QA checks and report pass/fail blockers.
agent: md-qa-gatekeeper
---

Run local QA for this repo.

Steps:
- Run `git status --short --branch`.
- Run `ruff check src tests`.
- Run `python -m pytest -q`.
- Run `pre-commit run --all-files` when pre-commit is installed.
- Run `git diff --check`.

Return pass/fail and actionable blockers only. Do not edit files. Arguments: `$ARGUMENTS`.
