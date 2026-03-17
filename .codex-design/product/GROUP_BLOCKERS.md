# Group blockers

Last reviewed: 2026-03-13

Review-template mirror drift status:
- `BLK-007` remains cleared after WL-D012 drift follow-up completion and the `chummer6-ui` UI-template parity revalidation recorded on `2026-03-13T18:15:19Z`.
- Completed WL-D007 drift rows now include `57`, `58`, `59`, `60`, `61`, `62`, and `63` with publish/revalidation evidence in `products/chummer/sync/REVIEW_TEMPLATE_MIRROR_PUBLISH_EVIDENCE.md`.

## RED blockers

### BLK-001 — design repo is not yet fully canonical

The central design repo still needs complete, current, substantive canon for active repos, packages, milestones, blockers, and mirrors.

Why this matters:
Workers will improvise boundaries if central design stays shallow or stale.

Unblock by:

* replacing stub files with substantive canon
* onboarding media-factory everywhere
* removing orphan root-level product docs
* making sync coverage complete

Owners:

* chummer6-design

### BLK-002 — package canon is not fully settled

`Chummer.Engine.Contracts`, `Chummer.Play.Contracts`, `Chummer.Run.Contracts`, `Chummer.Ui.Kit`, `Chummer.Hub.Registry.Contracts`, and `Chummer.Media.Contracts` are not yet all equally real, equally canonical, and equally consumed package-only.

Why this matters:
Repo splits remain conceptual if package truth is ambiguous.

Owners:

* chummer6-design
* chummer6-core
* chummer6-hub
* chummer6-ui-kit
* chummer6-hub-registry
* chummer6-media-factory

### BLK-003 — session semantic duplication risk

Semantic session event meaning still risks being defined in more than one place when play/run transport contracts duplicate engine semantics.

Why this matters:
Replay truth, sync truth, reducer truth, and client truth can drift.

Owners:

* chummer6-core
* chummer6-hub
* chummer6-mobile

## YELLOW blockers

### BLK-004 — play repo still needs mirror and real client maturity

`chummer6-mobile` must fully consume package-only seams, receive mirrored design context, and replace placeholder/scaffold flows with real client and ledger behavior.

Owners:

* chummer6-mobile
* chummer6-design

### BLK-005 — media-factory split is not yet operational

The repo exists, but contract ownership, source tree, mirror coverage, and live execution cutover are still incomplete.

Owners:

* chummer6-media-factory
* chummer6-hub
* chummer6-design

### BLK-006 — README drift in older repos

Core and hub still narrate older multi-head runtime ownership in ways that can mislead workers.

Owners:

* chummer6-core
* chummer6-hub

## GREEN candidates once current blockers clear

* full hub-registry extraction
* hub shrink phase
* engine purification phase
* release hardening phase
