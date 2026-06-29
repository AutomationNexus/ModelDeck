# ModelDeck OpenCode Rules

## Shell (Windows local dev)

- Chain commands with `;`, not `&&` or `||`.
- Use Windows paths (`\` or quoted full paths). Do not mix cmd/bash/PowerShell syntax.
- Outside clone: `gh --repo automationnexus/ModelDeck <subcommand>`.
- For CI logs: `gh run view <id> --log-failed`; use `Select-Object -Last N` instead of `tail`.
- Debug: one command per tool call.
- CI workflows keep bash on `ubuntu-latest`; do not change workflow shells.

## Safety Rules

- Start every task with `git status --short --branch`.
- Never read, print, copy, edit, or commit credentials (.env, secrets.yaml, tokens, API keys, cookies).
- Never create/track `AGENT-HANDOFF.md`, `AGENTS.md`, `CLAUDE.md`.
- Do not commit `opencode.json` or `.opencode/`.

## QA Gates (run before PR)

- `git status --short --branch`
- `ruff check src tests`
- `python -m pytest -q`
- `pre-commit run --all-files` (when installed)
- `git diff --check`

Invoke `@md-qa-gatekeeper` or `/md-qa` before push. `/md-prepush` before opening PR.

## Token-Efficient Handoff (agent-to-agent)

- Goal: one sentence.
- Files read/touched: paths only.
- Current branch/status: short.
- Decisions: max 5 bullets.
- Remaining work: max 5 bullets.
- Validation: commands + pass/fail only.
- Risks/blockers: actionable only.

No large file contents, raw diffs, secrets, or full logs.

## ModelDeck Conventions

- Package: `src/modeldeck/`. Tests: `tests/`. Integration: `pytest -m integration`.
- Example config: `templates/modeldeck.example.yaml`.
- Preserve stable MQTT entity IDs (`sensor.modeldeck_{provider}_{metric}`) unless breaking change requested.
- Keep changes minimal; run full QA gate before PR.

## Branch Policy

See `docs/runbooks/branch-policy.md`. Summary:
- `dev` is workbench, `main` is stable. No direct pushes.
- Feature branch → PR → CI green → merge → delete branch.
- Promote `dev`→`main` only via **Promote dev to main** workflow.
- Enable hooks: `tools\install-githooks.cmd`.
