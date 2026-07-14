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

### App version bump (`bump-type`)

The **parent release version** in the table above (row 1 — what
`modeldeck/config.yaml` mirrors) is the `pyproject.toml` version on `main`,
computed by the generic `bump-type` input on `promote-dev-to-main.yml`
(`patch` default / `minor` / `major` → next `X.Y.Z` off the latest `vX.Y.Z`
tag on `main`). This only applies to event 2 above (a real manual-dispatch
release) — never hand-edit `pyproject.toml`'s version. The `push`-triggered
add-on-only auto-promote paths (events 3 and 4) always pass `bump-type: none`
and must keep doing so; they're content-only syncs that must never touch the
app version. See `docs/releases/release-checklist.md` for the release
dispatch steps.

## Branch policy

See `docs/runbooks/branch-policy.md`. Summary: `dev` is workbench, `main` is stable and is
also what the HA add-on store reads from. No direct pushes (GitHub rulesets + CI guards +
`.githooks/pre-push`). Feature branch → PR → CI green → merge → delete branch. Promote
`dev`→`main` only via **Promote dev to main** (or its automatic add-on triggers above).
Enable hooks once per clone: `tools\install-githooks.cmd`.
Org-wide CI/PR flow, branch rules, and auto-versioning: see `../CLAUDE.md` (the
AutomationNexus GitHub workspace root) — consult it first for anything not
covered here, or if CI/promote looks broken.

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
`modeldeck-nightly/`): run `architect` first when domain boundaries are unclear or the
change spans both the Python service and an add-on channel — it plans the cross-domain
contract before any engineer touches code. Then: `mqtt-engineer`/`addon-engineer` →
matching `qa-gatekeeper`/`addon-qa-gatekeeper` → `reviewer` → PR.

## Subagents

The four core roles (`architect`, `qa-gatekeeper`, `reviewer`, `security-auditor`) are
the org-standard shared core, sourced from
`automationnexus/.github/templates/_shared/.claude/` — each carries a
`<!-- repo-specific -->` marker separating the shared skeleton body from ModelDeck's
distilled facts below it. `mqtt-engineer` and `addon-engineer` are domain layers on top
of that core, specific to this repo's two domains. See the workspace-root
`CLAUDE.md`'s "Agent organization" section for the full org-wide model.

| Agent | Domain | Model |
|-------|--------|-------|
| `architect` | Cross-domain boundaries, versioning-cascade release risk — before implementation | sonnet, high effort |
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
