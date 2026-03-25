# Project Chummer

Project Chummer is a multi-repo modernization of the legacy Chummer 5 application into a deterministic engine, workbench experience, play/mobile session shell, hosted orchestration plane, shared design system, artifact registry, and dedicated media execution service.

## Product entry

Start with `START_HERE.md` if you are new.
Use `GLOSSARY.md` when the repo-specific language gets dense.
Use `journeys/README.md` when the question is "what does the user actually do end to end?"
Use `METRICS_AND_SLOS.yaml` when the question is "what counts as good enough to ship?"

### Reading tracks

1. Public/product story:
   `VISION.md` -> `PUBLIC_LANDING_POLICY.md` -> `PUBLIC_LANDING_MANIFEST.yaml` -> `PUBLIC_FEATURE_REGISTRY.yaml` -> `PUBLIC_USER_MODEL.md` -> `PUBLIC_AUTH_FLOW.md`
2. Repo and contract boundaries:
   `ARCHITECTURE.md` -> `OWNERSHIP_MATRIX.md` -> `CONTRACT_SETS.yaml` -> `projects/*.md`
3. Delivery and release control:
   `RELEASE_PIPELINE.md` -> `PROGRAM_MILESTONES.yaml` -> `GROUP_BLOCKERS.md` -> `RELEASE_EVIDENCE_PACK.md`
4. Future lanes and public explainer posture:
   `HORIZONS.md` -> `HORIZON_REGISTRY.yaml` -> `PUBLIC_GUIDE_POLICY.md` -> `PUBLIC_GUIDE_PAGE_REGISTRY.yaml` -> `PUBLIC_PART_REGISTRY.yaml` -> `PUBLIC_FAQ_REGISTRY.yaml`

### Full canonical set

1. `START_HERE.md`
2. `GLOSSARY.md`
3. `VISION.md`
4. `HORIZONS.md`
5. `HORIZON_REGISTRY.yaml`
6. `ARCHITECTURE.md`
7. `RELEASE_PIPELINE.md`
8. `PUBLIC_LANDING_POLICY.md`
9. `PUBLIC_LANDING_MANIFEST.yaml`
10. `PUBLIC_FEATURE_REGISTRY.yaml`
11. `PUBLIC_LANDING_ASSET_REGISTRY.yaml`
12. `PUBLIC_USER_MODEL.md`
13. `PUBLIC_AUTH_FLOW.md`
14. `IDENTITY_AND_CHANNEL_LINKING_MODEL.md`
15. `PUBLIC_MEDIA_BRIEFS.yaml`
16. `PARTICIPATION_AND_BOOSTER_WORKFLOW.md`
17. `COMMUNITY_SPONSORSHIP_BACKLOG.md`
18. `EXTERNAL_TOOLS_PLANE.md`
19. `LTD_CAPABILITY_MAP.md`
20. `PUBLIC_GUIDE_POLICY.md`
21. `PUBLIC_GUIDE_PAGE_REGISTRY.yaml`
22. `PUBLIC_PART_REGISTRY.yaml`
23. `PUBLIC_FAQ_REGISTRY.yaml`
24. `PUBLIC_HELP_COPY.md`
25. `PUBLIC_GUIDE_EXPORT_MANIFEST.yaml`
26. `HORIZON_SIGNAL_POLICY.md`
27. `PUBLIC_MEDIA_AND_GUIDE_ASSET_POLICY.md`
28. `METRICS_AND_SLOS.yaml`
29. `journeys/README.md`
30. `OWNERSHIP_MATRIX.md`
31. `PROGRAM_MILESTONES.yaml`
32. `CONTRACT_SETS.yaml`
33. `GROUP_BLOCKERS.md`
34. `projects/*.md` for repo-specific scope

`HORIZON_REGISTRY.yaml` is the machine-readable source for horizon existence, order, public-guide eligibility, and eventual build path.
The current horizon set covers knowledge fabric, spatial/runsite artifacts, creator press, replay/forensics, and bounded table coaching in addition to the earlier continuity and simulation lanes.
`RELEASE_PIPELINE.md` is the canonical source for where release orchestration, desktop packaging, runtime-bundle production, registry publication truth, updater feeds, and public download/install rendering belong.
`PUBLIC_LANDING_MANIFEST.yaml`, `PUBLIC_FEATURE_REGISTRY.yaml`, and `PUBLIC_LANDING_ASSET_REGISTRY.yaml` are the machine-readable source for the `chummer.run` landing structure, CTA routing, public proof shelf, asset slots, and signed-in overlay posture.
`PUBLIC_PROGRESS_PARTS.yaml` is the canonical product-part mapping, public copy registry, and ETA/momentum policy input for the hosted `/progress` report, while `PROGRESS_REPORT.generated.json`, `PROGRESS_REPORT.generated.html`, and `PROGRESS_REPORT_POSTER.svg` are generated downstream projections that Hub may serve directly.
`PUBLIC_AUTH_FLOW.md` defines the first-wave login/signup/logout posture, guest fallbacks, and which provider surfaces may appear publicly in the hosted shell.
`IDENTITY_AND_CHANNEL_LINKING_MODEL.md` is the canonical source for email hygiene, social bootstrap, linked identities, official companion channels, and the rule that EA stays the orchestrator brain behind those channels.
`PUBLIC_GUIDE_PAGE_REGISTRY.yaml`, `PUBLIC_PART_REGISTRY.yaml`, `PUBLIC_FAQ_REGISTRY.yaml`, and `PUBLIC_HELP_COPY.md` are the machine-readable and public-safe source of truth for downstream guide generation outside the landing surface, including the generated download/build shelf.
`METRICS_AND_SLOS.yaml` is the release-scorecard canon for measurable user-trust, continuity, publication, and install/update gates.
`journeys/*.md` defines the top end-to-end user flows and failure-mode recoveries that multiple repos must preserve.

## Active Chummer repos

### `chummer6-design`

Lead-designer repo. Owns cross-repo canonical design truth.

### `chummer6-core`

Deterministic rules/runtime engine. Owns engine truth, explain canon, reducer truth, runtime bundles, and engine contracts.

### `chummer6-ui`

Workbench/browser/desktop product head. Owns builders, inspectors, compare tools, moderation/admin UX, large-screen operator flows, and the desktop installer/updater recipe.

### `chummer6-mobile`

Player and GM play-mode shell. Owns mobile/PWA/session UX, offline ledger, sync client, and play-safe live-session surfaces.

### `chummer6-hub`

Hosted orchestration and community plane. Owns identity mapping, user/community accounts, generic groups and memberships, sponsorship/booster UX, fact/reward/entitlement ledgers, public landing/home projection for `chummer.run`, play API aggregation, relay, approvals, memory, Coach/Spider/Director orchestration, and hosted service policy. The next major product sequencing rule is Hub-first: account/group/ledger backbone before more booster-specific Fleet product behavior.

### `chummer6-ui-kit`

Shared design system package. Owns tokens, themes, shell primitives, accessibility primitives, and Chummer-specific reusable UI components.

### `chummer6-hub-registry`

Artifact catalog and publication system. Owns immutable artifacts, publication workflows, release channels, install/update truth, reviews, compatibility, and runtime-bundle head metadata.

### `chummer6-media-factory`

Dedicated media execution plant. Owns render jobs, previews, manifests, asset lifecycle, and provider isolation for documents, portraits, and bounded video.

## Reference-only repo

### `chummer5a`

Legacy/oracle repo. Used for migration, regression fixtures, and compatibility reference. It is not the vNext product lane.

## Adjacent repos

These inform the program but are not part of the main release train:

* `fleet` — worker orchestration/control plane, mirrored from this repo for execution policy, parity automation, and queue synthesis
* `executive-assistant` — governed assistant runtime and synthesis/petition reference pattern, including proactive horizon scans, human-edit reflection, bounded replanning, interruption-budget throttling, and explicit design-governance skills such as `design_petition`, `design_synthesis`, and `mirror_status_brief`
* `Chummer6` — downstream public guide and Horizons explainer repo; useful for public storytelling, but not canonical design truth

## Current program priorities

1. Keep canonical design files concise, machine-readable where useful, and clearly above operational evidence noise.
2. Keep Hub’s user/group/ledger/sponsorship model canonical so community participation, premium bursts, and later GM-group tooling all grow from one reusable platform.
3. Maintain Fleet’s cheap-first execution plane and premium-burst policy through mirrored design truth rather than repo-local invention.
4. Give workers a legal petition path when the blueprint is missing a seam, and synthesize repeated findings before they become queue truth.
5. Treat future repo work as additive product evolution, not split-wave cleanup or contract-canon repair.
6. Keep sponsored participation generic: Hub grows the reusable user/group/ledger platform first, and Fleet stays the worker execution plane underneath it.
7. Keep `chummer.run` as the product front door and proof shelf, while `Chummer6` remains the deeper downstream explainer.
8. Keep release/build/install/update truth split cleanly: Core emits runtime bundles, UI emits installer-ready desktop heads, Fleet orchestrates the release lane, Registry owns promoted channel truth, and Hub renders downloads from registry state.

The foundational closure wave is materially finished. Future design work is maintenance or net-new product evolution rather than unresolved split, contract, or release-governance debt.

`PARTICIPATION_AND_BOOSTER_WORKFLOW.md` is the first-class canon for user language, ownership, state transitions, receipts, recognition, and package/bootstrap truth for the bounded participation lane.

`COMMUNITY_SPONSORSHIP_BACKLOG.md` is the implementation-ordered source for the Hub-first community/accounting wave. It distinguishes what already landed in Hub/Fleet/EA from the remaining durable-storage, convergence, and product-depth deltas.

## Non-goal

The immediate goal is not to add endless new features while the architecture is still blurry.

The immediate goal is:

* clean ownership
* package-based contracts
* real split completion
* durable design truth
* repeatable release governance
