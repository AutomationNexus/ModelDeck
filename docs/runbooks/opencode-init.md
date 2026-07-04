# Opencode Init Prompt

Use this prompt when handing the ModelDeck repo to opencode or another coding agent.

## Local OpenCode setup

- `opencode.json` and `.opencode/` are local-only. Never commit them.
- Bootstrap on a new machine: run `tools\bootstrap-opencode.cmd` (or `tools\bootstrap-opencode.ps1`). This copies `opencode.json.example` to `opencode.json` when missing, and mirrors committed seeds from `tooling/opencode/` into `.opencode/`.
- Committed templates: `opencode.json.example` and `tooling/opencode/` (project rules, plan/build instructions, agents, commands).
- New sessions default to **plan** mode (`openai/gpt-5.5`, read-only). Switch to **build** with Tab or run `/md-execute` after plan approval. Build uses the same model with `.opencode/project-rules.md` and `.opencode/build-instructions.md`.
- Built-in `general`, `explore`, and `scout` agents are disabled in `opencode.json`.
- File watcher ignores `.venv`, `__pycache__`, `.ruff_cache`, and `.pytest_cache` (see `watcher.ignore` in `opencode.json.example`).

```text
You are working in C:\Users\Tahasanul\Desktop\RemoteRepo\GitHub\ModelDeck.

This is the ModelDeck Python service: a Dockerized AI usage and quota bridge for Home Assistant. It polls OpenAI, Claude, and Cursor for account usage and publishes MQTT Discovery sensors. Secrets, provider tokens, API keys, session cookies, and local operator files must stay out of git.

This repo is also a Home Assistant add-on repository: `modeldeck/` (stable channel) and
`modeldeck-nightly/` (nightly channel) are separate, independently versioned add-ons that
real Home Assistant users install directly from this repo's `main` branch.

Start by reading:
- README.md
- docs/runbooks/branch-policy.md
- docs/development/repository-structure.md
- docs/releases/release-checklist.md
- docs/guides/sensors.md
- docs/getting-started/haos-addon.md
- modeldeck/README.md
- modeldeck/config.yaml
- pyproject.toml

Branch model:
- dev is the workbench branch for features, tests, nightly builds, and HA add-on changes.
- main is the stable release branch, and is also what the HA add-on store reads from.
- Never push directly to dev or main. Use feature branches, open PRs to dev, merge after CI is green, then delete the feature branch.
- Stable release is dev to main through the "Promote dev to main" GitHub Actions workflow after dev CI is green.
- GitHub rulesets (`protect-dev`, `protect-main`) enforce these rules, backed up by CI guards and `.githooks/pre-push`.
- Read docs/runbooks/branch-policy.md for the exact agent workflow.

Local access:
- Real credentials live only in ignored local files such as .env, config/secrets.yaml, and provider auth files on the workstation.
- Do not print, commit, summarize, or copy credential values.

Add-on conventions:
- `modeldeck/config.yaml` and `modeldeck-nightly/config.yaml` define options, schema, version, and slug (must match the folder name).
- `modeldeck/Dockerfile` / `modeldeck-nightly/Dockerfile` `ARG BUILD_FROM` must match the parent image tag: pinned `vX.Y.Z` for stable, `:nightly` for nightly channel.
- Password fields in schema use `password?` type; never commit real tokens in tracked files.
- Pin ModelDeck image tags in `BUILD_FROM`; do not use floating tags on `main`.
- `modeldeck-nightly/` and `modeldeck/`'s `config.yaml`/`CHANGELOG.md` are updated by automated jobs (nightly-roll, stable-sync, stable packaging-rev bump) — do not hand-edit their version fields.

Normal workflow:
1. Run git status --short --branch and confirm the working tree before changing files.
2. Work on a feature branch from dev (never commit directly on dev or main).
3. Never track AGENT-HANDOFF.md, AGENTS.md, CLAUDE.md, .env files, secrets.yaml, opencode.json, or .opencode/.
4. For OpenCode on a new machine, run tools\bootstrap-opencode.cmd and tools\install-githooks.cmd. New sessions start in plan mode; say go to switch to build or run /md-execute after plan approval.
5. Before committing, run:
   ruff check src tests
   pytest -q
   pre-commit run --all-files
   git diff --check
   If you touched modeldeck/ or modeldeck-nightly/, also run:
   python tools/validate_ha_addon.py
   python tools/check_build_from.py
6. Push the feature branch and open a PR to dev; merge after CI is green; delete the feature branch.
7. Promote dev to main only with the GitHub Actions workflow after dev CI succeeds.
```
