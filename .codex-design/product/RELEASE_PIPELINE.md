# Release pipeline canon

## Purpose

This file defines where Chummer release authority lives after the split.

The goal is to keep build recipes near the owning code, keep release control in one place, and keep public install/update truth in one registry-owned plane.

## Canonical split

### `chummer6-core`

Owns:

* runtime-bundle production
* runtime-bundle fingerprints
* ruleset/profile/build-axis truth that changes the runtime bundle matrix
* engine-side compatibility facts needed to explain or validate a runtime bundle

Must not own:

* installer packaging
* release-channel promotion
* public download UX
* updater feed publication policy

### `chummer6-ui`

Owns:

* desktop packaging recipes
* installer production recipes
* updater integration inside the desktop heads
* workbench-side release polish
* release-bundle emission for desktop artifacts

Must not own:

* release orchestration across repos
* canonical channel truth
* runtime-bundle authority
* public download/install ledger truth

### `fleet`

Owns:

* release matrix expansion
* release orchestration across owning repos
* verify gates, promotion gates, and readiness evidence
* publish history and compile-manifest evidence for the release lane
* signing/notarization job orchestration when those jobs are part of the release wave
* downstream public-guide and status projections that compile from design and registry truth

Must not own:

* installer recipe truth
* runtime-bundle canon
* canonical release-channel state
* canonical installer/update-feed metadata

### `chummer6-hub-registry`

Owns:

* release channels and promoted channel heads
* install/update metadata
* installer/download artifact records once promoted
* updater feed metadata
* compatibility truth for shipped heads and embedded runtime bundles
* runtime-bundle head metadata

Must not own:

* installer builds
* signing/notarization execution
* Hub landing-page copy authority
* media rendering

### `chummer6-hub`

Owns:

* public downloads UX
* account-aware install and entitlement UX
* signed-in "what should I install?" projections
* public rendering of registry-owned release/install/update truth

Must not own:

* release manifest generation authority
* installer/update-feed truth
* long-term release-channel truth

### `chummer6-media-factory`

Owns only render-side release adjuncts:

* screenshots
* preview images
* share cards
* bounded release-note visuals

It must not own installers, release feeds, channel policy, or publication/update truth.

## Canonical flow

1. `chummer6-core` produces runtime-bundle outputs and fingerprints.
2. `chummer6-ui` produces desktop bundles plus installer/update-ready package outputs.
3. `fleet` expands the release matrix, runs verify/promotion/signoff orchestration, and prepares a registry publication payload.
4. `chummer6-hub-registry` becomes the source of truth for promoted channels, installer/download records, update-feed metadata, compatibility, and runtime-bundle heads.
5. `chummer6-hub` reads registry truth and serves `/downloads`, account-aware install UX, and related public surfaces.
6. `Chummer6` and other downstream guide surfaces read registry-backed release projections; they do not become build authorities.

## Initial ship rule

Do not explode the first release wave into every theoretical combination.

Initial normal shape:

* one installer per `head × platform × arch × channel`
* selected runtime bundle embedded in that installer
* registry records which runtime-bundle head was embedded

Only split app-binary updates from runtime-bundle updates after the atomic installer path is stable enough to avoid app/runtime skew.

## Karma Forge rule

Karma Forge and similar future variants are build axes, not pipeline homes.

Model them as:

* runtime-bundle head choice
* ruleset/profile compatibility
* registry-visible build dimensions

Do not move release ownership into Hub or Media Factory just because the matrix gets larger.

## Updater rule

Updater integration lives in `chummer6-ui`.

Release and channel truth for that updater lives in `chummer6-hub-registry`.

Fleet may orchestrate the packaging/promotion wave, but the desktop head owns the updater client behavior and the registry owns the published feed/channel records.
