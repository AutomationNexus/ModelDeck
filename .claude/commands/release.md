---
description: Follow the CI-gated dev-to-main release workflow.
argument-hint: [optional notes]
---

Run the release workflow: $ARGUMENTS

This is a Track D action (`CLAUDE.md`'s "Risk tracks") — it is never entered implicitly
from `/execute`.

Confirm local QA passed or run `/qa`. Ensure the latest `dev` on GitHub has green CI.
Dispatch `security-auditor` for a release-sensitive security sweep over everything
`dev` has that `main` doesn't (full checklist, not just the files in the last PR) —
this is mandatory for every promotion of a full repo, not conditional on a trigger
list. Do not proceed past an unresolved finding.
Promote `dev` to `main` only via the **Promote dev to main** GitHub Actions workflow
(choose `bump-type` per the change: `patch`/`minor`/`major` — versioned repos only) —
never push `dev`/`main` directly, and only after explicit human confirmation of the
dispatch (`human-confirmation-required` per the org root's `CLAUDE.md` "Unified
authority and confirmation"). Tag only when the user explicitly requests it.

<!-- repo-specific -->

Follow `docs/releases/release-checklist.md` for the exact dispatch steps. Ensure the
latest `dev` has green CI (`gh run list --branch dev --limit 5`,
`gh run view <id> --log-failed`; add `--repo automationnexus/ModelDeck` outside the
clone). Promote `dev` to `main` only via the **Promote dev to main** GitHub Actions
workflow unless the user explicitly approves the documented manual fallback. Never
hand-edit `pyproject.toml`'s version — `bump-type` computes it automatically (see
CLAUDE.md's "App version bump" section). Never push directly to `dev`/`main`.
