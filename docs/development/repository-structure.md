# Repository Structure

```
src/modeldeck/     Python package
tests/             pytest suite
docs/              MkDocs site
templates/         Compose and config examples
.github/workflows/ ci.yml, nightly.yml, release.yml, semgrep.yml, docs.yml
tools/             CI helper scripts
ops/               Local test runners
examples/          Lovelace snippets
```

## Branch flow

```text
feature branches → PR to dev → merge → nightly.yml → ghcr.io/.../modeldeck:nightly
dev → PR to main (when ready) → merge → release.yml → vX.Y.Z tag + :latest
```

## Current state

- **Active:** merges to `dev` and `:nightly` builds
- **Configured, not yet used:** `dev` → `main` PR and semver releases via `release.yml`

See [release-checklist.md](../releases/release-checklist.md) before the first merge to `main`.
