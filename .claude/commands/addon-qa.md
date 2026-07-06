---
description: Run local QA for the HA add-on side and report pass/fail blockers.
argument-hint: [optional scope]
---

Dispatch `addon-qa-gatekeeper`: `git status`, `python tools/validate_ha_addon.py`,
`python tools/check_build_from.py`, `git diff --check`. Return pass/fail and blockers only.
No file edits. Arguments: $ARGUMENTS
