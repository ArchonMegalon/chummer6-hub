# Campaign workspace and device roles

## Purpose

This file defines how Chummer's home and campaign surfaces stop being generic dashboards and become a real Shadowrun cockpit.

The product promise is:

> Chummer should tell the user what changed for them, what is safe to do next, which campaign needs attention, and which device they are using for that job.

## Canonical principle

Campaigns are operational workspaces, not folders with extra tabs.

The home surface and campaign surface must compile from:

* campaign spine truth
* living-dossier continuity
* roaming workspace restore posture
* release and install truth
* support and closure truth
* artifact and publication refs

Do not design these surfaces as:

* a generic dashboard full of unrelated counters
* a repo-status wall leaking operator vocabulary
* a hidden cloud blob with no conflict semantics
* a local-only guess about release, entitlement, or support posture

## Core product objects

### Home cockpit

The signed-in home surface is the first proof that Chummer understands the user's real situation.

It should be able to project:

* continue this runner
* continue this campaign
* this campaign changed rules
* this device is on `Stable` or `Preview`
* this install has role `workstation`, `play_tablet`, or another concrete posture
* this issue you reported is fixed on your channel
* this artifact or recap packet is ready
* this campaign or install needs attention before you keep going

### Campaign workspace

A campaign workspace is the operational center for one crew or campaign.

It should carry:

* campaign roster authority
* active rule-environment posture
* dossier freshness and stale-state cues
* session-start readiness check
* GM-ready runboard
* recent recap and artifact shelf
* unresolved restore or continuity conflicts

### What-changed-for-me packet

The product should be able to tell one user:

* what changed since last use
* why it changed
* whether it is safe to proceed
* what the next safe action is

This is more important than showing a raw version number or a generic notification count.

### Trust rail

Home and campaign surfaces should expose visible trust cues for:

* why a number changed
* why a build or dossier is stale
* why a rule environment no longer matches
* why this install should not update yet
* why a support case is still open
* why a fix notice is real for this user

### Publication shelf

Campaign and home surfaces may expose:

* dossier packets
* recap cards
* briefings
* evidence rooms
* primers
* other publication-safe artifacts

Those outputs remain downstream of provenance-bearing truth rather than becoming a second system of record.

## Device roles

Device roles are install-local posture, not person or entitlement truth.

### `workstation`

Primary build, compare, moderation, publication, and operator surface.

Expected posture:

* richest authoring and compare tooling
* broadest local cache
* optional preview-channel participation when explicitly chosen

### `play_tablet`

Fast resume and session-safe field device.

Expected posture:

* continuity-first home surface
* travel-safe caching and reconnect posture
* fewer high-risk authoring affordances during live play

### `observer_screen`

Read-mostly or presentation-first install.

Expected posture:

* recap, runboard, or spectator-safe projections
* minimal authoring authority
* explicit dependence on hosted or nearby truth

### `travel_cache`

Offline or low-connectivity posture for a claimed device.

Expected posture:

* pinned campaign and runner continuity
* explicit prefetch status
* louder stale-state and repair cues

### `preview_scout`

A spare install that tries preview or guided lanes earlier than the main machine.

Expected posture:

* clearer warning language
* install-local channel posture
* no bleed-through into other claimed installs

## Authority split

### `chummer6-hub`

Owns:

* home cockpit and campaign workspace projections
* what-changed-for-me packets
* roster, rule-environment, and dossier readiness summaries
* organizer and community operator posture built on the same group and entitlement substrate

### `chummer6-hub-registry`

Owns:

* install channel posture
* compatibility and update truth
* immutable artifact and publication refs

### `chummer6-ui`

Owns:

* workstation cockpit UX
* compare, repair, readiness, and runboard surfaces on desktop
* device-role selection or local posture controls where exposed

### `chummer6-mobile`

Owns:

* play-tablet and travel-cache UX
* continuity-first resume behavior
* offline prefetch and reconnect posture

### `chummer6-core`

Owns:

* deterministic explainability
* rules and pack provenance
* compatibility inputs behind rule-environment health

### `chummer6-media-factory`

Owns:

* rendered publication outputs and previews

It does not own the home cockpit, campaign workspace meaning, or readiness truth.

## Compounding loops

The point of this surface is to make the product's loops visible:

### Continuity loop

claim -> restore -> continue -> reconnect -> recap

### Confidence loop

inspect -> explain -> compare -> decide -> trust

### Closure loop

report -> cluster -> route -> release -> notify

### Output loop

dossier -> artifact -> recap -> primer -> publication

### Community loop

account -> group -> campaign -> entitlement -> operator surface

## Rules

* The first screen must answer "what changed for me?" before it answers "what version exists?"
* Campaign workspaces must expose rule-environment and dossier health before live play continues.
* Device roles are install-local posture and must not silently rewrite entitlements or campaign truth.
* Per-install channel posture must stay visible when one claimed device is on `Preview` and another stays on `Stable`.
* A fix notice is only trustworthy when support and release truth agree it reached the reporter's real channel.
* Organizer and community operator surfaces must reuse the same account, group, and entitlement substrate rather than inventing a second authority model.

## Non-goals

This file does not:

* replace `ROAMING_WORKSPACE_AND_ENTITLEMENT_SYNC.md`
* create a second campaign truth outside `Chummer.Campaign.Contracts`
* turn output artifacts into canonical continuity records
* require every install to look the same regardless of role
