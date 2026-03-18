# Project Chummer

Project Chummer is a multi-repo modernization of the legacy Chummer 5 application into a deterministic engine, workbench experience, play/mobile session shell, hosted orchestration plane, shared design system, artifact registry, and dedicated media execution service.

## Product entry

Read in this order:

1. `VISION.md`
2. `HORIZONS.md`
3. `ARCHITECTURE.md`
4. `EXTERNAL_TOOLS_PLANE.md`
5. `LTD_CAPABILITY_MAP.md`
6. `PUBLIC_GUIDE_POLICY.md`
7. `HORIZON_SIGNAL_POLICY.md`
8. `PUBLIC_MEDIA_AND_GUIDE_ASSET_POLICY.md`
9. `OWNERSHIP_MATRIX.md`
10. `PROGRAM_MILESTONES.yaml`
11. `CONTRACT_SETS.yaml`
12. `GROUP_BLOCKERS.md`
13. `projects/*.md` for repo-specific scope

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

* `fleet` — worker orchestration/control plane
* `executive-assistant` — skill/runtime reference pattern for governed assistant orchestration
* `Chummer6` — downstream public guide and Horizons explainer repo; useful for public storytelling, but not canonical design truth

## Current program priorities

1. Make `chummer6-design` trustworthy as the lead-designer repo.
2. Finalize package/contract canon.
3. Complete the play split with package-only dependency discipline in `chummer6-mobile`.
4. Expand `chummer6-ui-kit` into the real shared UI boundary.
5. Complete registry and media service extractions.
6. Shrink `chummer6-hub` into orchestration-only ownership where appropriate.
7. Purify `chummer6-core` into a true deterministic engine repo.
8. Finish product surfaces and release hardening.

## Non-goal

The immediate goal is not to add endless new features while the architecture is still blurry.

The immediate goal is:

* clean ownership
* package-based contracts
* real split completion
* durable design truth
* repeatable release governance
