# ModelDeck Plan Mode

- Stay read-only in plan mode. Do not edit files.
- Never commit on `dev` or `main`. Plan work for a feature branch from `dev` (see `docs/runbooks/branch-policy.md`).
- This repo covers two domains — the Python service (`src/`) and the Home Assistant add-ons
  (`modeldeck/`, `modeldeck-nightly/`). Scope the plan to whichever domain(s) the request touches.
- For sensor/auth design, MQTT discovery, provider polling, or sensor schema work, invoke
  `@md-mqtt-engineer` before finalizing the plan.
- For add-on config, `Dockerfile`, `run.sh`, or add-on schema work, invoke `@mdh-addon-engineer`
  before finalizing the plan.
- Never plan to hand-edit `modeldeck/config.yaml` or `modeldeck-nightly/config.yaml`'s `version`
  field or `CHANGELOG.md` — those are written only by automated jobs (nightly-roll, stable-sync).
  Stable is always bare `X.Y.Z` matching the parent release; there is no packaging-revision
  suffix.
- When the user approves the plan and says go, build, or execute, hand off to `/md-execute`
  (built-in `build`). Do not implement inline.
