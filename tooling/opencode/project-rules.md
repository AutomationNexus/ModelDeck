# ModelDeck OpenCode Rules

This repo is the ModelDeck Python service: a Dockerized AI usage and quota bridge for Home Assistant via MQTT Discovery.

## Branch Rules

- `dev` is the workbench branch; `main` is stable. Never push directly to `dev` or `main`.
- Create a feature branch from `dev` for all changes; never commit on `dev` or `main` directly.
- Land changes via feature branch → PR to `dev` → CI green → merge → delete feature branch.
- Promote `dev` to `main` only through the **Promote dev to main** workflow after dev CI is green.
- Enable local hook once per clone: `tools\install-githooks.cmd` (blocks direct pushes to `dev`/`main`).
- See `docs/runbooks/branch-policy.md` for the exact workflow.

## Safety Rules

- Start every task with `git status --short --branch` before edits.
- Never read, print, summarize, copy, edit, or commit credential values.
- Treat `.env`, `.env.*`, `config/secrets.yaml`, provider tokens, API keys, and session cookies as private.
- Never create or track `AGENT-HANDOFF.md`, `AGENTS.md`, or `CLAUDE.md`.
- Do not commit `opencode.json` or `.opencode/`.

## QA Gates

Before opening a PR, run local QA in the same task:

- `git status --short --branch`
- `ruff check src tests`
- `python -m pytest -q`
- `pre-commit run --all-files` (when pre-commit is installed)
- `git diff --check`

Invoke `@md-qa-gatekeeper` or run `/md-qa` before push. Run `/md-prepush` before opening or updating a PR.

## Agent Workflow

- New sessions start in built-in `plan` mode (read-only). Switch to `build` with Tab or run `/md-execute` after plan approval.
- For MQTT discovery, provider polling, or sensor schema work, invoke `@md-mqtt-engineer` before finalizing the plan.
- When the user approves a plan and says go, build, or execute, run `/md-execute` (built-in `build` orchestrator).
- `build` delegates to `@md-mqtt-engineer` for implementation, `@md-qa-gatekeeper` for local QA, and `@md-reviewer` for independent review.
- Land git changes with a feature branch and PR to `dev`; never push directly to `dev` or `main`.
- Use `@md-opus-solver` only for hard cross-module bugs, architecture conflicts, or cases where cheaper agents disagree.

## Local OpenCode Setup

- `opencode.json` and `.opencode/` are local-only and must not be committed.
- Copy from `opencode.json.example` when setting up a new machine, then run `tools\bootstrap-opencode.cmd`.
- Committed seeds live in `tooling/opencode/`; bootstrap mirrors them into local `.opencode/`.

## Token-Efficient Handoff

Before switching agents or models, write a compact handoff:

- Goal: one sentence.
- Files read/touched: paths only.
- Current branch/status: short.
- Decisions made: max 5 bullets.
- Remaining work: max 5 bullets.
- Validation run: commands and pass/fail only.
- Risks/blockers: actionable items only.

Do not paste large file contents, raw diffs, secrets, or full logs. Prefer paths, MQTT topic names, sensor keys, command names, and short status lines.

## ModelDeck Conventions

- Python package lives under `src/modeldeck/`.
- Tests live under `tests/`; integration tests use Mosquitto (`pytest -m integration`).
- Example config: `templates/modeldeck.example.yaml`.
- Preserve stable MQTT entity IDs (`sensor.modeldeck_{provider}_{metric}`) unless the user requests a breaking change.
- Keep changes minimal and run the full QA gate before PR.
