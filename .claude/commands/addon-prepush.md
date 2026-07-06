---
description: Verify PR readiness for the HA add-on side with local QA and branch policy.
---

Check PR readiness for `dev`. `git status` + confirm feature branch (not `dev`/`main`,
unless the user explicitly documents an exception). Run the full `/addon-qa` sequence.
Report allow/block with blockers. No file edits, push, or PRs.
