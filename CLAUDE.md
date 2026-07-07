# CLAUDE.md — ModelDeck

This repo is both a Python service (`src/modeldeck/`) and a Home Assistant add-on repository
(`modeldeck/` stable channel, `modeldeck-nightly/` nightly channel). Scope your work to
whichever domain(s) a task touches.

## Conventions

- Package: `src/modeldeck/`. Tests: `tests/`. Integration: `pytest -m integration`.
- Example config: `templates/modeldeck.example.yaml`.
- Preserve stable MQTT entity IDs (`sensor.modeldeck_{provider}_{metric}`) unless a breaking
  change is explicitly requested.
- Keep changes minimal; run the full QA gate before PR.

## Add-on conventions

- `modeldeck/` = stable channel (installed by most HA users). `modeldeck-nightly/` = nightly
  channel (tracks `dev`/`:nightly` builds). Both are independent, self-contained HA add-ons
  living in this one repo.
- Each folder's `config.yaml` defines `options`/`schema`/`version`/`slug` (slug must match the
  folder name); mirror every `options` key in `schema` with the correct HA type.
- `Dockerfile`'s `ARG BUILD_FROM` must match the channel: `modeldeck/Dockerfile` pins a
  released tag, `modeldeck-nightly/Dockerfile` stays on the floating `:nightly` tag.
- **Never hand-edit `version:` or `CHANGELOG.md` in either add-on folder.** Those are written
  exclusively by automated jobs (nightly-roll, stable-sync) — see Versioning Cascade below.

## Versioning cascade (do not "simplify" this — read before touching CI)

Two independent version pointers, computed entirely by automation, never by git-merging text:

| Channel | Format | Meaning |
|---|---|---|
| `modeldeck/config.yaml` | `X.Y.Z` (bare) | Always exactly the parent release version. No packaging-revision suffix by design. |
| `modeldeck-nightly/config.yaml` | `X.Y.Z-nightly.YYYYMMDD.N` | X.Y.Z = parent dev version at build time. N = same-day re-roll counter. |

Event-driven cascade (automatic, no manual steps in the normal flow):

1. **PR merges to `dev`** → app `:nightly` image builds → nightly pointer bumped and published
   **straight to `main`** (never written back to `dev`).
2. **Release (`dev`→`main` promote)** → `:vX.Y.Z` image builds → a bot PR syncs the stable pin
   **onto `dev`** → merging that PR auto-fires the promote workflow → `main` gets the new pin.
3. **Add-on-only nightly tweak** merging to `dev` → same as event 1.
4. **Add-on-only stable tweak** merging to `dev` → auto-fires promote (path-filtered on
   `modeldeck/**`) → content lands on `main` immediately, version string does not change.

`promote-dev-to-main.yml` passes `exclude-paths` for `modeldeck-nightly/config.yaml` and
`modeldeck-nightly/CHANGELOG.md` — `main` is the sole owner of those two files. **Do not
remove `exclude-paths` without re-solving this.**

**GitHub Actions gotcha:** this repo's default branch is `main` (required for HA add-on
discovery), and `schedule:` triggers on *any* workflow always evaluate using the workflow
file version on the **default branch**, never `dev`'s copy. Any future change to a
`schedule:` block needs an explicit promote to `main` before it's actually live.

## Branch policy

See `docs/runbooks/branch-policy.md`. Summary: `dev` is workbench, `main` is stable and is
also what the HA add-on store reads from. No direct pushes (GitHub rulesets + CI guards +
`.githooks/pre-push`). Feature branch → PR → CI green → merge → delete branch. Promote
`dev`→`main` only via **Promote dev to main** (or its automatic add-on triggers above).
Enable hooks once per clone: `tools\install-githooks.cmd`.

## Shell (Windows local dev)

- Chain commands with `;`, not `&&`/`||`. Use Windows paths. Do not mix cmd/bash/PowerShell.
- Outside clone: `gh --repo automationnexus/ModelDeck <subcommand>`.
- CI logs: `gh run view <id> --log-failed`; `Select-Object -Last N` instead of `tail`.
- CI workflows keep bash on `ubuntu-latest`; do not change workflow shells.

## QA gates (run before PR)

```
git status --short --branch
ruff check src tests
python -m pytest -q
pre-commit run --all-files   # when installed
git diff --check
```
If `modeldeck/` or `modeldeck-nightly/` changed, also run:
```
python tools/validate_ha_addon.py
python tools/check_build_from.py
```

## Execute pipeline (risk-based)

Pick the track based on the size/risk of the approved plan; both still land through a
feature branch → PR → CI → merge, never a direct push to `dev`/`main`.

**Small/low-risk** (single file, docs-only, no MQTT/add-on behavior change): the main
session may implement directly, then run the relevant QA gate itself and a self-review
pass before opening the PR. No need to dispatch every subagent for a one-file fix.

**Multi-file or behavior-risk** (touches `src/modeldeck/`, `modeldeck/`, or
`modeldeck-nightly/`): full pipeline — `mqtt-engineer`/`addon-engineer` → matching
`qa-gatekeeper`/`addon-qa-gatekeeper` → `reviewer` → PR.

## Subagents

| Agent | Domain | Model |
|-------|--------|-------|
| `mqtt-engineer` | `src/modeldeck/`, MQTT/provider polling | sonnet |
| `addon-engineer` | `modeldeck/`, `modeldeck-nightly/` | sonnet |
| `qa-gatekeeper` | Python-side QA gate | haiku |
| `addon-qa-gatekeeper` | Add-on-side QA gate | haiku |
| `reviewer` | Independent review before PR | sonnet |
| `security-auditor` | Secrets, workflow/versioning-cascade safety, dependency risk | sonnet, high effort |

For hard cross-module conflicts, switch the main session to opus (`/model opus` or
`opusplan`) rather than a dedicated solver agent.

## Slash commands

Python side: `/execute`, `/qa`, `/prepush`, `/release`.
Add-on side: `/addon-execute`, `/addon-qa`, `/addon-prepush`, `/sync-schema`.

## Shared CI — do not inline

- **Never inline or fork `automationnexus/.github` reusable-workflow logic** into this
  repo's own workflow files, even temporarily. Always call it via
  `uses: automationnexus/.github/.github/workflows/<name>.yml@v1`.
- If this repo needs new CI behavior, add a generic input to the shared workflow (contribute
  it to `automationnexus/.github`), never a local copy/paste workaround.
- Never use `GITHUB_TOKEN` or a personal token for cross-branch/cascade automation
  (nightly-roll, stable-sync, promote) — only the CI-Bot GitHub App.

## Secrets / never read or print

- Never read, print, copy, edit, or commit credentials (`.env`, `secrets.yaml`, tokens,
  API keys, cookies) — including add-on credential values from a live Home Assistant instance.
- `.claude/settings.json` already denies these paths — do not weaken it.

## Do not

- Do not add model/provider/router config anywhere in this repo. Claude Code talks directly
  to Anthropic with the operator's own account.
