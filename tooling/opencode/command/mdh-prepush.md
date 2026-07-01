---
description: Verify PR readiness with local QA and branch policy.
agent: mdh-qa-gatekeeper
---

Check PR readiness for `dev`. `git status` + confirm feature branch (not dev/main, unless `$ARGUMENTS` documents exception). Run `/mdh-qa` full sequence. Report allow/block with blockers. No file edits, push, or PRs.
