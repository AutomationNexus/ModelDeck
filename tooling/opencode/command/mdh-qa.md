---
description: Run local QA checks and report pass/fail blockers.
agent: mdh-qa-gatekeeper
---

Run: `git status`, `python tools/validate_ha_addon.py`, `python tools/check_build_from.py`, `git diff --check`. Return pass/fail and blockers only. No file edits. Arguments: `$ARGUMENTS`.
