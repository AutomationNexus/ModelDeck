# ModelDeck OpenCode Rules

This repo is both a Python service (`src/modeldeck/`) and a Home Assistant add-on
repository (`modeldeck/` stable channel, `modeldeck-nightly/` nightly channel). Scope your
work to whichever domain(s) a task touches.

## Shell (Windows local dev)

- Chain commands with `;`, not `&&` or `||`.
- Use Windows paths (`\` or quoted full paths). Do not mix cmd/bash/PowerShell syntax.
- Outside clone: `gh --repo automationnexus/ModelDeck <subcommand>`.
- For CI logs: `gh run view <id> --log-failed`; use `Select-Object -Last N` instead of `tail`.
- Debug: one command per tool call.
- CI workflows keep bash on `ubuntu-latest`; do not change workflow shells.

## Safety Rules

- Start every task with `git status --short --branch`.
- Never read, print, copy, edit, or commit credentials (.env, secrets.yaml, tokens, API keys,
  cookies) — including add-on credential values from a live Home Assistant instance.
- Never create/track `AGENT-HANDOFF.md`, `AGENTS.md`, `CLAUDE.md`.
- Do not commit `opencode.json` or `.opencode/`.

## QA Gates (run before PR)

- `git status --short --branch`
- `ruff check src tests`
- `python -m pytest -q`
- `pre-commit run --all-files` (when installed)
- `git diff --check`
- If `modeldeck/` or `modeldeck-nightly/` changed, also run:
  - `python tools/validate_ha_addon.py`
  - `python tools/check_build_from.py`

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

## Add-on Conventions

- `modeldeck/` = stable channel (installed by most HA users). `modeldeck-nightly/` = nightly
  channel (tracks `dev`/`:nightly` builds). Both are independent, self-contained HA add-ons
  living in this one repo — HA users add this repo's URL once and see both as separate
  installable add-ons from `main`.
- Each folder's `config.yaml` defines `options`/`schema`/`version`/`slug` (slug must match the
  folder name); mirror every `options` key in `schema` with the correct HA type
  (`str`, `password?`, `bool`, `url`, `list(...)`).
- `Dockerfile`'s `ARG BUILD_FROM` must match the channel: `modeldeck/Dockerfile` pins a
  released tag (`ghcr.io/automationnexus/modeldeck:v{version}`), `modeldeck-nightly/Dockerfile`
  stays on the floating `:nightly` tag. Neither Dockerfile builds anything — they are thin
  wrappers around ModelDeck's own published image.
- **Never hand-edit `version:` or `CHANGELOG.md` in either add-on folder.** Those fields are
  written exclusively by automated jobs (nightly-roll, stable-sync) — see Versioning Cascade
  below. A manual edit will be silently overwritten or will desync the pointer from what HA
  actually offers as an update.
- `@mdh-addon-engineer` for add-on config/Dockerfile/run.sh/schema work. `@mdh-qa-gatekeeper`
  for the add-on-specific local QA gate. `/mdh-sync-schema` when `options`/`schema` drift.

## Versioning Cascade (do not "simplify" this — read before touching CI)

Two independent version pointers, computed entirely by automation, never by git-merging text:

| Channel | Format | Meaning |
|---|---|---|
| `modeldeck/config.yaml` | `X.Y.Z` (bare, no suffix) | Always exactly the parent release version. There is no packaging-revision suffix by design — an add-on-only packaging change (e.g. a `run.sh` fix with no parent release) is never released standalone; it ships bundled at the next real release. |
| `modeldeck-nightly/config.yaml` | `X.Y.Z-nightly.YYYYMMDD.N` | X.Y.Z = parent dev version at build time. N = same-day re-roll counter, starting at `0` for the first build of the day. `bump_haos_version.py` always emits the counter now (a consistently-shaped version string is safer for HA's update comparator); `check_build_from.py`'s validator still accepts legacy bare `YYYYMMDD` pointers (no counter) for backward compatibility, but they are no longer generated. |

Event-driven cascade (all automatic, no manual steps in the normal flow):

1. **PR merges to `dev`** → app `:nightly` image builds → nightly pointer is bumped and
   published **straight to `main`** (never written back to `dev`) — this is what makes it
   loop-free: nightly triggers only on `dev` pushes, and the pointer commit lands on `main`.
2. **Release (`dev`→`main` promote)** → `:vX.Y.Z` image builds → a bot PR syncs the stable
   pin (bare `X.Y.Z`, no version-bump logic to run) **onto `dev`** (not main directly —
   humans also edit `modeldeck/` on dev, so the pin update must go through the same branch
   to avoid a two-writer conflict) → merging that PR touches `modeldeck/**`, which
   auto-fires the promote workflow → `main` gets the new pin.
3. **Add-on-only nightly tweak** (e.g. `modeldeck-nightly/run.sh`) merging to `dev` → same as
   event 1, folder content rides along in the next nightly-roll publish.
4. **Add-on-only stable tweak** (e.g. `modeldeck/run.sh`, no parent release) merging to `dev`
   → auto-fires the promote workflow (path-filtered push trigger on `modeldeck/**`) → content
   lands on `main` immediately (new installs get it), but the version string does **not**
   change — there is no bump job. Existing installed HA users only see it as an update at
   the next real release, when `X.Y.Z` genuinely changes. This is intentional, not a gap:
   test add-on-only changes via the nightly channel first.

The `promote-dev-to-main.yml` shared-workflow call passes `exclude-paths` for
`modeldeck-nightly/config.yaml` and `modeldeck-nightly/CHANGELOG.md` — `main` is the sole
owner of those two files (event 1 writes them), and a plain merge would otherwise regress
them back to `dev`'s stale copy on every promote. Do not remove `exclude-paths` without
re-solving this.

## Branch Policy

See `docs/runbooks/branch-policy.md`. Summary:
- `dev` is workbench, `main` is stable and is also what the HA add-on store reads from.
- No direct pushes (enforced by GitHub rulesets `protect-dev`/`protect-main`, backed by CI
  guards and `.githooks/pre-push`).
- Feature branch → PR → CI green → merge → delete branch.
- Promote `dev`→`main` only via **Promote dev to main** workflow (or its automatic add-on
  triggers described above).
- Enable hooks: `tools\install-githooks.cmd`.

## Shared CI — Do Not Inline

- **Never inline or fork `automationnexus/.github` reusable-workflow logic** into this repo's
  own workflow files, even temporarily. Always call it via
  `uses: automationnexus/.github/.github/workflows/<name>.yml@v1`.
- If this repo needs CI behavior the shared workflow doesn't support, the fix is a new
  **generic** input on the shared workflow (contributed to `automationnexus/.github`), never
  a local copy/paste workaround. Precedent: `build-args`, `main-source-allow-glob`,
  `exclude-paths` were all added this way.
- Never use `GITHUB_TOKEN` or a personal access token for cross-branch or cascade automation
  (nightly-roll, stable-sync, promote) — only the CI-Bot GitHub App. It is what makes the
  ruleset bypass and cascades actually work.
- Before touching any `.github/workflows/*.yml` file here, check
  `automationnexus/.github` first — most CI behavior lives there, not in this repo's thin
  wrapper.
