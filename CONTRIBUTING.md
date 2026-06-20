# Contributing to ModelDeck

Thanks for helping improve ModelDeck.

## Start Here

1. Read [SECURITY.md](SECURITY.md).
2. Read [docs/development/local-development.md](docs/development/local-development.md).
3. For MQTT or collector changes, read [docs/security/threat-model.md](docs/security/threat-model.md).

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,service]"
```

## Quality Gates

Run the full CI mirror before opening a pull request:

```powershell
.\scripts\check.ps1
```

Auto-fix lint and formatting, then re-check:

```powershell
.\scripts\check.ps1 -Fix
```

Lint only (fast):

```powershell
.\scripts\check.ps1 -Quick
```

On Linux or Git Bash:

```bash
./scripts/check.sh
```

### Pre-commit (optional, recommended)

Install hooks once after `pip install -e ".[dev,service]"`:

```powershell
pre-commit install
```

Hooks run `ruff check --fix`, `ruff format`, and basic file hygiene on every commit.

### Tests only

```powershell
.\ops\run-tests.ps1
```

Local coverage target is **97%** (same as CI).

## Security Rules

- Do not commit secrets, `.env` files, API keys, or `secrets.yaml`.
- Do not paste real tokens into issues or pull requests.
- Any change touching auth, logging, or collector HTTP clients must describe its security impact in the PR.

## Pull Requests

- Target the **`dev`** branch for feature work.
- Open **`dev` → `main`** only when cutting a stable release (see [docs/releases/release-checklist.md](docs/releases/release-checklist.md)).
- PRs to `main` must come from `dev` only (enforced in CI).
- Keep one logical change per PR when possible.
- Use [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).
- Branch names: `feat/...`, `fix/...`, `docs/...`, or `chore/...`.

## Code of Conduct

We follow the [Code of Conduct](CODE_OF_CONDUCT.md).
