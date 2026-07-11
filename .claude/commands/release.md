---
description: Follow the CI-gated dev-to-main release workflow.
argument-hint: [optional notes]
---

Run the release workflow: $ARGUMENTS

Confirm local QA passed or run `/qa`. Ensure the latest `dev` on GitHub has green CI.
Promote `dev` to `main` only via the **Promote dev to main** GitHub Actions workflow
(choose `bump-type` per the change: `patch`/`minor`/`major` — versioned repos only) —
never push `dev`/`main` directly. Tag only when the user explicitly requests it.

<!-- repo-specific -->

Follow `docs/releases/release-checklist.md` for the exact dispatch steps. Ensure the
latest `dev` has green CI (`gh run list --branch dev --limit 5`,
`gh run view <id> --log-failed`; add `--repo automationnexus/ModelDeck` outside the
clone). Promote `dev` to `main` only via the **Promote dev to main** GitHub Actions
workflow unless the user explicitly approves the documented manual fallback. Never
hand-edit `pyproject.toml`'s version — `bump-type` computes it automatically (see
CLAUDE.md's "App version bump" section). Never push directly to `dev`/`main`.
