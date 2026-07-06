---
description: Follow the CI-gated dev-to-main release workflow.
argument-hint: [optional notes]
---

Follow `docs/releases/release-checklist.md`. $ARGUMENTS

Confirm local branch/status. Ensure local QA passed or run `/qa` now. Ensure latest `dev`
has green CI (`gh run list --branch dev --limit 5`, `gh run view <id> --log-failed`; add
`--repo automationnexus/ModelDeck` outside the clone). Promote `dev` to `main` only via the
**Promote dev to main** GitHub Actions workflow unless the user explicitly approves the
documented manual fallback. Tag only when the user requests it. Never push directly to
`dev`/`main`.
