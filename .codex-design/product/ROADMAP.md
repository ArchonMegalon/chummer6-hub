# Long-range roadmap

This roadmap carries the program all the way to finished-state vision, not just to the split wave.

Current status on 2026-03-19:

* package canon, split completion, explain canon, runtime-bundle canon, hub product-consumer planes, play-shell closure, assistant-plane governance, media capability closure, replay/DR hardening, legacy migration certification, and release-governance closure are materially complete
* the foundational program is now in maintenance mode rather than split-wave closeout mode

## Phase A — Canon and package plane

### A0 — Design repo bootstrap complete

`chummer6-design` becomes trustworthy: full canon, full sync coverage, real milestones, real blockers, real ownership matrix.

### A1 — Engine contract canon

`Chummer.Engine.Contracts` becomes the only cross-repo source for engine/runtime/explain semantics.

### A2 — Play contract canon

`Chummer.Play.Contracts` becomes the stable play/mobile/service seam.

### A3 — Run orchestration contract canon

`Chummer.Run.Contracts` becomes the hosted orchestration package without duplicating engine or play semantics.

## Phase B — Surface split completion

### B0 — Play split real

`chummer6-mobile` moves beyond scaffold to real offline ledger, real sync client, and real player/GM shells.

### B1 — UI kit real

`chummer6-ui-kit` becomes the actual shared design system package used by UI and mobile.

### B2 — UI purified

`chummer6-ui` becomes workbench/browser/desktop only, with no play-shell confusion.

## Phase C — Service extraction

### C0 — Registry extraction

`chummer6-hub-registry` takes ownership of catalog, publication, moderation, installs, reviews, and compatibility metadata.

### C1 — Media extraction

`chummer6-media-factory` takes ownership of render jobs, manifests, previews, and asset lifecycle.

### C2 — Hub shrink

`chummer6-hub` becomes a clean orchestration service rather than a hidden super-repo.

## Phase D — Truth and session canon

### D0 — Explain canon complete

Structured explain/provenance becomes authoritative and consumable across product surfaces.

### D1 — Session semantic canon complete

Reducer-safe session semantics are owned once and consumed everywhere else.

### D2 — Runtime bundle canon complete

Runtime bundles, fingerprints, and replay-safe payloads stabilize across engine and clients.

## Phase E — Product completion

### E0 — Workbench complete

UI ships robust builder, compare, explain, publish, review, and admin surfaces.

### E1 — Play complete

Mobile ships installable PWA/mobile session OS for players and GMs.

### E2 — Hub complete

Registry and orchestration together deliver publication, installs, reviews, discovery, and moderation.

### E3 — Assistant plane complete

Coach / Spider / Director become governed hosted capabilities grounded on engine truth.

### E4 — Media plane complete

Documents, portraits, and bounded video become dependable service capabilities.

## Phase F — Hardening and release

### F0 — Performance, accessibility, localization

Cross-head quality bar is real.

### F1 — Replay, observability, DR

Core, hub, registry, and media all have operational confidence.

### F2 — Legacy migration and certification

`chummer5a` migration and regression confidence are formally certified.

### F3 — Release complete

The product vision is complete enough for release: split finished, boundaries clean, packages canonical, product surfaces coherent, and operational discipline in place.

## Non-blocking Horizons canon lane

This lane makes future-capability posture explicit without turning Horizons into a release gate for `vnext-foundation`.

It now spans knowledge fabric, spatial/runsite artifacts, creator press, replay/forensics, and bounded table coaching/social-dynamics futures.

### H0 — Horizon canon established

`chummer6-design` publishes a canonical Horizons layer and keeps it ahead of downstream public storytelling.

### H1 — Public guide and horizon sync policy

`Chummer6` is governed as a downstream guide that cannot outrun canonical horizon docs.

### H2 — LTD capability map complete

Owned external tools are mapped to promoted, bounded, parked, or non-product states with explicit owners and system-of-record limits.

### H3 — First bounded horizon promoted to research-ready

At least one horizon has enough owner, tool, and provenance detail to move from vague idea to bounded research lane.

### H4 — Public signal loop defined

Public proposals and advisory prioritization routes are collected through governed surfaces without turning votes into canonical truth.

### H5 — Table coaching horizon defined

`TABLE PULSE` becomes a bounded, privacy-safe post-session coaching lane with explicit owners, tool posture, and non-truth boundaries.

## Non-blocking participation and bootstrap lane

This lane makes the bounded participate/booster workflow and package bootstrap truth explicit without turning them into release-blocking gates.

### I0 — Participation workflow canon established

`chummer6-design` publishes first-class participation canon for sponsor sessions, consent, device auth, receipt semantics, recognition rules, and stop/revoke behavior.

### I1 — Participation surfaces converge on central canon

Hub, Fleet, `Chummer6`, and any EA helper compile from design-owned participation truth instead of carrying parallel README or helper-script interpretations.

### I2 — Package bootstrap becomes boring

`Chummer.Engine.Contracts` and `Chummer.Ui.Kit` restore through deterministic local/CI package feeds or explicit generated compatibility trees, not legacy ambient project references.

## Non-blocking public landing and discovery lane

This lane makes `chummer.run` a canon-backed product front door instead of leaving public discovery split across guide copy and insider routes.

### J0 — Public landing canon established

`chummer6-design` publishes first-class landing policy, route structure, feature registry, user model, and media briefs for the hosted public surface.

### J1 — Hosted landing projected from canon

`chummer6-hub` projects the public landing, proof shelf, and signed-in home shell from design-owned manifest and registry data.

### J2 — Registered overlays and teaser surfaces become boring

`chummer.run` exposes thin but real signed-in overlays, participation entry, artifact teasers, and status/download surfaces without inventing local product truth.

## Repo milestone spine

### `chummer6-design`

D0 bootstrap -> D1 contract registry -> D2 blocker publication -> D3 mirror discipline -> D4 release governance -> D5 ADR/memory -> D6 finished lead designer.

### `chummer6-core`

E0 purification -> E1 runtime DTO canon -> E2 explain canon -> E3 session reducer canon -> E4 ruleset ABI -> E5 explain backend completion -> E6 Build Lab backend -> E7 migration certification -> E8 hardening -> E9 finished engine.

### `chummer6-ui`

P0 ownership correction -> P1 package-only UI consumption -> P2 workbench shell -> P3 explain UX -> P4 Build Lab UX -> P5 registry/admin/publish UX -> P6 platform parity -> P7 accessibility/perf -> P8 finished workbench.

### `chummer6-mobile`

L0 package canon -> L1 offline ledger/sync -> L2 player shell -> L3 GM shell -> L4 relay/runtime convergence -> L5 Coach/Spider surfaces -> L6 mobile/PWA polish -> L7 observer/cross-device -> L8 hardening -> L9 finished play shell.

### `chummer6-ui-kit`

U0 governance -> U1 token canon -> U2 primitives -> U3 shell chrome -> U4 dense data controls -> U5 Chummer-specific patterns -> U6 accessibility/localization -> U7 visual regression/catalog -> U8 release discipline -> U9 finished design system.

### `chummer6-hub-registry`

H0 contract canon -> H1 artifact domain -> H2 publication drafts -> H3 install/compatibility engine -> H4 search/discovery/reviews -> H5 template/style publication -> H6 federation/org channels -> H7 hardening -> H8 finished registry.

### `chummer6-media-factory`

M0 contract canon -> M1 asset/job kernel -> M2 document rendering -> M3 portrait forge -> M4 bounded video -> M5 template/style integration -> M6 hub cutover -> M7 storage/DR/scale -> M8 finished media plant.

### `chummer6-hub`

R0 shrink-to-boundary reset -> R1 package canon -> R2 identity/campaign core -> R3 play APIs/relay -> R4 skill runtime -> R5 Spider/Director/memory -> R6 orchestration-only registry/media mode -> R7 notifications/docs/delivery -> R8 resilience/compliance -> R9 finished hosted orchestration.
