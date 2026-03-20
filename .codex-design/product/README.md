# Project Chummer

Project Chummer is a multi-repo modernization of the legacy Chummer 5 application into a deterministic engine, workbench experience, play/mobile session shell, hosted orchestration plane, shared design system, artifact registry, and dedicated media execution service.

## Product entry

Read in this order:

1. `VISION.md`
2. `HORIZONS.md`
3. `HORIZON_REGISTRY.yaml`
4. `ARCHITECTURE.md`
5. `PUBLIC_LANDING_POLICY.md`
6. `PUBLIC_LANDING_MANIFEST.yaml`
7. `PUBLIC_FEATURE_REGISTRY.yaml`
8. `PUBLIC_LANDING_ASSET_REGISTRY.yaml`
9. `PUBLIC_USER_MODEL.md`
10. `PUBLIC_AUTH_FLOW.md`
11. `IDENTITY_AND_CHANNEL_LINKING_MODEL.md`
12. `PUBLIC_MEDIA_BRIEFS.yaml`
13. `PARTICIPATION_AND_BOOSTER_WORKFLOW.md`
14. `COMMUNITY_SPONSORSHIP_BACKLOG.md`
15. `EXTERNAL_TOOLS_PLANE.md`
16. `LTD_CAPABILITY_MAP.md`
17. `PUBLIC_GUIDE_POLICY.md`
18. `PUBLIC_GUIDE_PAGE_REGISTRY.yaml`
19. `PUBLIC_PART_REGISTRY.yaml`
20. `PUBLIC_FAQ_REGISTRY.yaml`
21. `PUBLIC_HELP_COPY.md`
22. `PUBLIC_GUIDE_EXPORT_MANIFEST.yaml`
23. `HORIZON_SIGNAL_POLICY.md`
24. `PUBLIC_MEDIA_AND_GUIDE_ASSET_POLICY.md`
25. `OWNERSHIP_MATRIX.md`
26. `PROGRAM_MILESTONES.yaml`
27. `CONTRACT_SETS.yaml`
28. `GROUP_BLOCKERS.md`
29. `projects/*.md` for repo-specific scope

`HORIZON_REGISTRY.yaml` is the machine-readable source for horizon existence, order, public-guide eligibility, and eventual build path.
The current horizon set covers knowledge fabric, spatial/runsite artifacts, creator press, replay/forensics, and bounded table coaching in addition to the earlier continuity and simulation lanes.
`PUBLIC_LANDING_MANIFEST.yaml`, `PUBLIC_FEATURE_REGISTRY.yaml`, and `PUBLIC_LANDING_ASSET_REGISTRY.yaml` are the machine-readable source for the `chummer.run` landing structure, CTA routing, public proof shelf, asset slots, and signed-in overlay posture.
`PUBLIC_AUTH_FLOW.md` defines the first-wave login/signup/logout posture, guest fallbacks, and which provider surfaces may appear publicly in the hosted shell.
`IDENTITY_AND_CHANNEL_LINKING_MODEL.md` is the canonical source for email hygiene, social bootstrap, linked identities, official companion channels, and the rule that EA stays the orchestrator brain behind those channels.
`PUBLIC_GUIDE_PAGE_REGISTRY.yaml`, `PUBLIC_PART_REGISTRY.yaml`, `PUBLIC_FAQ_REGISTRY.yaml`, and `PUBLIC_HELP_COPY.md` are the machine-readable and public-safe source of truth for downstream guide generation outside the landing surface, including the generated download/build shelf.

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

Hosted orchestration and community plane. Owns identity mapping, user/community accounts, generic groups and memberships, sponsorship/booster UX, fact/reward/entitlement ledgers, public landing/home projection for `chummer.run`, play API aggregation, relay, approvals, memory, Coach/Spider/Director orchestration, and hosted service policy. The next major product sequencing rule is Hub-first: account/group/ledger backbone before more booster-specific Fleet product behavior.

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
