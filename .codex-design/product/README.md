# Project Chummer

Project Chummer is a multi-repo modernization of the legacy Chummer 5 application into a deterministic engine, workbench experience, play/mobile session shell, hosted orchestration plane, shared design system, artifact registry, and dedicated media execution service.

## Product entry

Read in this order:

1. `VISION.md`
2. `HORIZONS.md`
3. `HORIZON_REGISTRY.yaml`
4. `ARCHITECTURE.md`
5. `EXTERNAL_TOOLS_PLANE.md`
6. `LTD_CAPABILITY_MAP.md`
7. `PUBLIC_GUIDE_POLICY.md`
8. `HORIZON_SIGNAL_POLICY.md`
9. `PUBLIC_MEDIA_AND_GUIDE_ASSET_POLICY.md`
10. `OWNERSHIP_MATRIX.md`
11. `PROGRAM_MILESTONES.yaml`
12. `CONTRACT_SETS.yaml`
13. `GROUP_BLOCKERS.md`
14. `projects/*.md` for repo-specific scope

`HORIZON_REGISTRY.yaml` is the machine-readable source for horizon existence, order, public-guide eligibility, and eventual build path.
The current horizon set covers knowledge fabric, spatial/runsite artifacts, creator press, replay/forensics, and bounded table coaching in addition to the earlier continuity and simulation lanes.

## Active Chummer repos

### `chummer6-design`

Lead-designer repo. Owns cross-repo canonical design truth.

### `chummer6-core`

Deterministic rules/runtime engine. Owns engine truth, explain canon, reducer truth, runtime bundles, and engine contracts.

### `chummer6-ui`

Workbench/browser/desktop product head. Owns builders, inspectors, compare tools, moderation/admin UX, and large-screen operator flows.

### `chummer6-mobile`

Player and GM play-mode shell. Owns mobile/PWA/session UX, offline ledger, sync client, and play-safe live-session surfaces.

### `chummer6-hub`

Hosted orchestration plane. Owns identity, play API aggregation, relay, approvals, memory, Coach/Spider/Director orchestration, and service policy.

### `chummer6-ui-kit`

Shared design system package. Owns tokens, themes, shell primitives, accessibility primitives, and Chummer-specific reusable UI components.

### `chummer6-hub-registry`

Artifact catalog and publication system. Owns immutable artifacts, publication workflows, moderation state, installs, reviews, compatibility, and runtime-bundle head metadata.

### `chummer6-media-factory`

Dedicated media execution plant. Owns render jobs, previews, manifests, asset lifecycle, and provider isolation for documents, portraits, and bounded video.

## Reference-only repo

### `chummer5a`

Legacy/oracle repo. Used for migration, regression fixtures, and compatibility reference. It is not the vNext product lane.

## Adjacent repos

These inform the program but are not part of the main release train:

* `fleet` — worker orchestration/control plane, mirrored from this repo for execution policy and review context
* `executive-assistant` — skill/runtime reference pattern for governed assistant orchestration
* `Chummer6` — downstream public guide and Horizons explainer repo; useful for public storytelling, but not canonical design truth

## Current program priorities

1. Finish product completion across workbench, play, hub, assistant, and media heads.
2. Close the remaining orchestration-side and media-side external adapter depth (`C1b`, `C1c`) without re-blurring ownership.
3. Keep `chummer6-design` fresh enough that mirrors, Fleet status, and downstream public guides cannot drift from canon.
4. Purify `chummer6-core` and `chummer6-hub` further by deleting remaining legacy cargo rather than arguing about it.
5. Complete release hardening: accessibility, localization, performance, observability, DR, migration certification, and final release proof.
6. Keep Fleet’s cheap-first execution plane canonical while adding explicit premium-burst policy only through mirrored design truth, not ad hoc repo-local drift.

The current open-program follow-through is materialized in `WORKLIST.md` as `WL-D019` through `WL-D038` so the remaining closure wave is tracked as executable backlog instead of latent milestone prose.

## Non-goal

The immediate goal is not to add endless new features while the architecture is still blurry.

The immediate goal is:

* clean ownership
* package-based contracts
* real split completion
* durable design truth
* repeatable release governance
