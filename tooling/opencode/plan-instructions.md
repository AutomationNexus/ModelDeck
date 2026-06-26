# ModelDeck Plan Mode

- Stay read-only in plan mode. Do not edit files.
- Never commit on `dev` or `main`. Plan work for a feature branch from `dev` (see `docs/runbooks/branch-policy.md`).
- For sensor/auth design, MQTT discovery, provider polling, or sensor schema work, invoke `@md-mqtt-engineer` before finalizing the plan.
- When the user approves the plan and says go, build, or execute, hand off to `/md-execute` (built-in `build`). Do not implement inline.
