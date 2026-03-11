# Architecture

## Canonical rules

### Rule 1 — Central design wins

Cross-repo product truth lives in `chummer-design`.
Code repos receive mirrored local context; they do not become the canonical source of cross-repo architecture.

### Rule 2 — Shared DTOs are package-owned

If a DTO crosses repo boundaries, it must have:

* a canonical package
* an owning repo
* a versioning policy
* a deprecation policy

No source-copy mirrors of cross-repo DTOs are allowed.

### Rule 3 — Engine semantics live in core

`chummer-core-engine` owns:

* rules math
* reducer truth
* runtime fingerprints
* runtime bundles
* explain provenance
* engine contract canon

No other repo may compute or redefine canonical mechanics.

### Rule 4 — Hosted orchestration lives in run-services

`chummer.run-services` owns:

* identity
* relay
* approvals
* memory
* Coach / Spider / Director orchestration
* play API aggregation
* delivery policy
* service-to-service coordination

It must not own duplicate mechanics, registry persistence after split, or media rendering after split.

### Rule 5 — Workbench and play stay separate

`chummer-presentation` owns builder/workbench/admin/browser/desktop UX.
`chummer-play` owns live-session/mobile/PWA/player/GM shell UX.

No silent re-merging of those surfaces is allowed.

### Rule 6 — UI-kit is the only shared UI boundary

Shared visual tokens, shell primitives, and reusable components belong in `chummer-ui-kit`.
Presentation and play consume the package.
They do not fork it.

### Rule 7 — Registry is a service boundary

Artifact catalog, publication workflow, moderation state, installs, reviews, and compatibility metadata belong in `chummer-hub-registry`.

### Rule 8 — Media execution is a service boundary

Render jobs, manifests, previews, asset lifecycle, and provider adapters belong in `chummer-media-factory`.

### Rule 9 — Legacy is reference-only

`chummer5a` is a migration/regression oracle. It is not part of the active multi-repo architecture.

## Repo graph

```text
chummer-design
  ├─ governs every Chummer repo
  └─ mirrors local guidance into code repos

chummer-core-engine
  ├─ publishes Chummer.Engine.Contracts
  ├─ computes mechanics truth
  └─ emits runtime/explain/reducer semantics

chummer-ui-kit
  └─ publishes Chummer.Ui.Kit

chummer-presentation
  ├─ consumes Chummer.Engine.Contracts
  ├─ consumes Chummer.Ui.Kit
  └─ consumes hosted projections from run-services / registry

chummer-play
  ├─ consumes Chummer.Engine.Contracts
  ├─ consumes Chummer.Play.Contracts
  ├─ consumes Chummer.Ui.Kit
  └─ consumes hosted play projections from run-services

chummer.run-services
  ├─ publishes Chummer.Play.Contracts
  ├─ publishes Chummer.Run.Contracts
  ├─ consumes Chummer.Engine.Contracts
  ├─ consumes Chummer.Hub.Registry.Contracts
  ├─ consumes Chummer.Media.Contracts
  └─ orchestrates hosted workflows

chummer-hub-registry
  └─ publishes Chummer.Hub.Registry.Contracts

chummer-media-factory
  └─ publishes Chummer.Media.Contracts
```

## Allowed dependency directions

### Allowed

* presentation -> engine contracts
* presentation -> ui-kit
* play -> engine contracts
* play -> play contracts
* play -> ui-kit
* run-services -> engine contracts
* run-services -> play contracts
* run-services -> run contracts
* run-services -> registry contracts
* run-services -> media contracts
* hub-registry -> its own contracts
* media-factory -> its own contracts

### Forbidden

* core -> presentation
* core -> play
* core -> run-services
* play -> presentation
* play -> run-services implementation source
* presentation -> play implementation source
* ui-kit -> domain DTO packages
* media-factory -> play contracts
* media-factory -> campaign/session DB semantics
* run-services -> duplicated engine semantic DTOs once canonical package owner exists

## New repo split gate

A new repo split is not architecturally accepted until all of the following exist in `chummer-design`:

* ownership row in `OWNERSHIP_MATRIX.md`
* active-repo entry in `products/chummer/README.md`
* implementation scope in `projects/*.md`
* mirror entry in `sync/sync-manifest.yaml`
* contract/package entry in `CONTRACT_SETS.yaml` if shared contracts are involved
* program milestone entries in `PROGRAM_MILESTONES.yaml`
* blocker update if the split introduces or resolves group risk
* review context coverage

## Drift conditions

A repo is considered architecturally drifting when any of the following is true:

* its README contradicts central design truth
* it owns a package it is not listed as owning
* its mirrored `.codex-design/*` is missing or stale
* it duplicates a contract family owned elsewhere
* it rebuilds a split boundary locally instead of consuming the package/service


## External tools plane

Project Chummer has an explicit External Tools Plane.

This plane exists to integrate owned third-party capabilities without allowing any third-party capability to become canonical Chummer truth.

### External tools plane rules

1. External tools always sit behind Chummer-owned adapters.
2. External tools may assist, project, notify, visualize, render, or archive.
3. External tools may not own:

   * rules truth
   * reducer truth
   * runtime truth
   * session truth
   * approval truth
   * registry truth
   * artifact truth
   * memory/canon truth
4. No client repo may access third-party tools directly.
5. All external-provider-assisted outputs that re-enter Chummer must carry Chummer-side provenance and receipts.
6. `chummer.run-services` owns orchestration-side integrations.
7. `chummer-media-factory` owns render/archive integrations.
8. `chummer-design` owns external-tools policy and rollout governance.

### External tools plane by repo

* `chummer.run-services`

  * reasoning providers
  * approval bridges
  * docs/help bridges
  * survey bridges
  * automation bridges
  * research/eval tooling

* `chummer-media-factory`

  * document render adapters
  * preview/thumbnail adapters
  * image/video adapters
  * route visualization adapters
  * cold-archive adapters

* `chummer-hub-registry`

  * references to promoted reusable template/style/help/preview artifacts only

### Non-goals

* no third-party tool is a required hop for live session relay
* no third-party tool holds canonical approval state
* no third-party tool owns Chummer media manifests
* no third-party tool bypasses Chummer moderation or canonization

