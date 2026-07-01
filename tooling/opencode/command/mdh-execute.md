---
description: Execute approved plan through expert agents (implement, QA, optional PR).
agent: build
---

Execute pipeline for an approved plan. 1. `git status`. Confirm/checkout feature branch from `dev`. 2. `@mdh-addon-engineer` for add-on config, Dockerfile, run.sh, docs. 3. `@mdh-qa-gatekeeper` for `/mdh-qa` gate. 4. Stop on first failure. 5. Push → PR to `dev`. Return compact handoff: agents used, commands run, pass/fail. Arguments: `$ARGUMENTS`.
