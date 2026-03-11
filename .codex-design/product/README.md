# Project Chummer

Project Chummer is a multi-repo modernization of the legacy Chummer 5 application into a deterministic engine, workbench experience, play/mobile session shell, hosted orchestration plane, shared design system, artifact registry, and dedicated media execution service.

## Product entry

Read in this order:

1. `VISION.md`
2. `ARCHITECTURE.md`
3. `EXTERNAL_TOOLS_PLANE.md`
4. `OWNERSHIP_MATRIX.md`
5. `PROGRAM_MILESTONES.yaml`
6. `CONTRACT_SETS.yaml`
7. `GROUP_BLOCKERS.md`
8. `projects/*.md` for repo-specific scope

## Active Chummer repos

### `chummer-design`

Lead-designer repo. Owns cross-repo canonical design truth.

### `chummer-core-engine`

Deterministic rules/runtime engine. Owns engine truth, explain canon, reducer truth, runtime bundles, and engine contracts.

### `chummer-presentation`

Workbench/browser/desktop product head. Owns builders, inspectors, compare tools, moderation/admin UX, and large-screen operator flows.

### `chummer-play`

Player and GM play-mode shell. Owns mobile/PWA/session UX, offline ledger, sync client, and play-safe live-session surfaces.

### `chummer.run-services`

Hosted orchestration plane. Owns identity, play API aggregation, relay, approvals, memory, Coach/Spider/Director orchestration, and service policy.

### `chummer-ui-kit`

Shared design system package. Owns tokens, themes, shell primitives, accessibility primitives, and Chummer-specific reusable UI components.

### `chummer-hub-registry`

Artifact catalog and publication system. Owns immutable artifacts, publication workflows, moderation state, installs, reviews, compatibility, and runtime-bundle head metadata.

### `chummer-media-factory`

Dedicated media execution plant. Owns render jobs, previews, manifests, asset lifecycle, and provider isolation for documents, portraits, and bounded video.

## Reference-only repo

### `chummer5a`

Legacy/oracle repo. Used for migration, regression fixtures, and compatibility reference. It is not the vNext product lane.

## Adjacent repos

These inform the program but are not part of the main release train:

* `fleet` — worker orchestration/control plane
* `executive-assistant` — skill/runtime reference pattern for governed assistant orchestration

## Current program priorities

1. Make `chummer-design` trustworthy as the lead-designer repo.
2. Finalize package/contract canon.
3. Complete the play split with package-only dependency discipline.
4. Expand `chummer-ui-kit` into the real shared UI boundary.
5. Complete registry and media service extractions.
6. Shrink `chummer.run-services` into orchestration-only ownership where appropriate.
7. Purify `chummer-core-engine` into a true deterministic engine repo.
8. Finish product surfaces and release hardening.

## Non-goal

The immediate goal is not to add endless new features while the architecture is still blurry.

The immediate goal is:

* clean ownership
* package-based contracts
* real split completion
* durable design truth
* repeatable release governance
