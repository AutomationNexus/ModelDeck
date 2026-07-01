# Branch Policy

GitHub rulesets (`protect-dev`, `protect-main`) enforce these rules, backed up by CI guards and local git hooks.

## Protected branches

| Branch | How changes land |
|--------|------------------|
| `dev` | Feature branch → PR → CI green → merge → delete feature branch |
| `main` | `Promote dev to main` workflow after dev CI is green |

Direct `git push` to `dev` or `main` is blocked locally (`.githooks/pre-push`) and fails CI if bypassed.

## Feature branch workflow

```cmd
git checkout dev
git pull origin dev
git checkout -b fix/short-description
REM ... edit, commit ...
ruff check src tests
python -m pytest -q
pre-commit run --all-files
REM If you touched modeldeck/ or modeldeck-nightly/ (HA add-on folders):
python tools/validate_ha_addon.py
python tools/check_build_from.py
git diff --check
git push -u origin HEAD
gh pr create --base dev --title "Short title" --body "Summary and test plan"
```

After CI is green on the PR, merge on GitHub (squash or merge commit). Delete the feature branch when prompted.

## Local hook setup (once per clone)

```cmd
tools\install-githooks.cmd
```

Or manually: `git config core.hooksPath .githooks`

Requires Git Bash (Git for Windows). The hook blocks `git push` to `dev` and `main`.

## Promotion to main

Never push `dev` to `main` manually. Normal path:

1. Ensure latest `dev` CI is green.
2. Run the **Promote dev to main** workflow in GitHub Actions.
3. Wait for `main` CI to pass.
4. Tag stable baselines when appropriate.

## Agent rules

- Never `git push origin dev` or `git push origin main`.
- Never ask the user to bypass CI guards.
- Release operator: create/use a feature branch, open PR, wait for CI, merge via `gh pr merge` only after user approval.
