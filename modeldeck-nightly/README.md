# ModelDeck (Nightly) — Home Assistant add-on

Nightly channel for ModelDeck on Home Assistant OS. Uses the parent **`ghcr.io/automationnexus/modeldeck:nightly`** image with HAOS-specific packaging (Configuration UI, `run.sh`, schema).

Install **ModelDeck** for stable releases, or **ModelDeck (Nightly)** for bleeding-edge parent builds.

## Install

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add: `https://github.com/automationnexus/ModelDeck`
3. Install **ModelDeck (Nightly)** (not the stable **ModelDeck** tile unless you want both)
4. Configure, **Save**, **Start**

Expect unstable behavior — use on a test instance only.

Nightly updates are published automatically after the parent ModelDeck `dev`
build passes CI and the HAOS nightly roll PR is merged.

Configuration fields match the stable add-on; see [modeldeck/README.md](../modeldeck/README.md).
