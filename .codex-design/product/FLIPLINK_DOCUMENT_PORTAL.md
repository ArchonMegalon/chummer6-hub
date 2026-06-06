# FlipLink Document Portal

FlipLink is a candidate Chummer Document Portal viewer layer.

Core rule:

- Chummer creates and owns the document.
- Chummer owns document truth, version, classification, release posture, and access policy.
- FlipLink may present, brand, embed, and measure approved documents only.

The first bounded document lane is:

- `Chummer6 Quickstart Guide`

Allowed first-wave uses:

- Chummer6 Quickstart Guide
- install/download booklet
- Black Ledger player primer
- faction dossiers
- Table Pulse GM guide
- GM Session Video Foundry guide
- Chummer5A-to-Chummer6 transition guide
- convention and launch handouts
- player-safe campaign recap packets

Forbidden roles:

- rules authority
- sourcebook host
- product release truth
- payment or entitlement truth
- private campaign archive by default
- player data warehouse
- GM private face or video library

Provider posture:

- initial publication mode is operator-managed
- provider verification is required before live embed promotion
- first publication proof is required before trusted public routing
- responsive QA, analytics receipt, and unpublish/delete proof are required before readiness claims

Public routes:

- `/docs`
- `/docs/chummer6-quickstart`
- `/docs/embed/{slug}`
- `/docs/category/{category}`

Current boundary:

- the first-party Chummer route may exist before the FlipLink viewer is trusted
- if the viewer layer is not proven, Chummer must present the document boundary honestly instead of pretending a live flipbook is already ready
