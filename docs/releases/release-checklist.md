# Release Checklist

Use this before the first (or any) `dev` → `main` release PR.

## Pre-merge

- Dependabot opens monthly grouped minor/patch PRs to `dev` (max 3 per ecosystem). Major bumps are reviewed individually. Use manual `chore/deps-batch` PRs before a release if needed.

- [ ] All feature work merged to `dev`; CI green on `dev`
- [ ] `ops/run-tests.ps1` passes locally (97%+ coverage)
- [ ] `modeldeck config validate` on example configs
- [ ] CHANGELOG updated for the release
- [ ] **Version bump type decided**: dispatch **Promote dev to main** with the `bump-type`
      input set to `patch` (default), `minor`, or `major` — never hand-edit `pyproject.toml`'s
      version. The promote workflow computes the new `X.Y.Z` from the latest `vX.Y.Z` tag
      reachable on `main` and writes it to `pyproject.toml` on the promote branch.

`release.yml` tags **`v{project.version}`** from `pyproject.toml` on merge to `main` — it just
reads whatever version the promote step already wrote; it does not itself compute a bump.

## Post-merge

- [ ] `release.yml` completed: git tag `vX.Y.Z` matches `pyproject.toml`, GHCR `:latest`, GitHub Release
- [ ] Docs deployed from `main` (if `docs/` changed)
- [ ] Smoke test: `docker pull ghcr.io/automationnexus/modeldeck:latest`

## Retag / rebuild an existing version

Use **Actions → Release → Run workflow** with an existing tag name (e.g. `v0.0.1`) to rebuild the image and refresh the GitHub Release without merging to `main`.

## Until first release

No PR to `main` is required during initial development. Use `:nightly` from `dev` merges only.
