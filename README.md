# chummer6-hub

Hosted relationship, campaign, control, and play API boundary for Chummer6.

## What this repo is

`chummer6-hub` is the hosted backbone for:

- identity, relay, approvals, and memory
- campaign spine truth for living dossiers, crews, campaigns, runs, scenes, objectives, and replay-safe continuity
- product-control truth for support intake, case status, crash normalization, closure notices, and operator-facing case packets
- hosted play APIs and orchestration
- governed AI, docs/help, and automation bridges
- orchestration-side registry and media adapters
- user accounts, groups, access/support state, and the canonical community ledger
- the `chummer.run` landing page, proof shelf, downloads/support/account surfaces, and thin signed-in home overlay
- grant-bound install continuity surfaces, including account-scoped roaming workspace snapshots for claimed desktop installs

## What this repo is not

This repo does not own:

- engine/runtime reducer truth
- the player/GM/mobile shell
- shared UI-kit primitives
- render-only media execution ownership

## Current mission

The job here is shrink-to-fit:

- keep the hosted boundary sharp
- stop speaking like a hidden super-repo
- push registry and render-only ownership out to their dedicated homes

Current honesty clause:

- registry and render-only execution ownership are now physically out-of-repo
- the remaining shrinkage is orchestration polish, not hidden service ownership
- closing the remaining hosted milestones is now about contract cleanup and adapter depth, not where registry/media code lives

The public-facing customer and access spine now lives here too:

- `Chummer.Run.Api` owns the customer account backbone first: product-level users, groups, support/access flows, device/install linking, and the canonical community ledger.
- Optional join/boost codes, sponsor sessions, leaderboards, rewards, and entitlements sit on top of that shared account and access plane.
- `Chummer.Campaign.Contracts` is the shared middle-plane package for runner dossier, crew, campaign, run, scene, objective, continuity, and roaming restore projections
- `Chummer.Control.Contracts` is the shared middle-plane package for support cases, crash intake, clustered signals, routing decisions, and closure truth
- `Chummer.Run.Api` also owns linked identity and channel-link state for email hygiene, Google/Facebook social bootstrap, and official Telegram companion routing
- `Chummer.Run.Identity` remains the principal/session boundary below that account layer
- `Chummer.Run.AI` ingests validated participation receipts and projects guided-lane activity
- Fleet executes optional guided-contribution lanes, but Hub owns the canonical customer/account ledger and accounting truth
- EA remains the orchestrator brain behind companion and assistant channels; Telegram, Google, Facebook, and transactional email are adapters around that hub-owned account plane

## Go deeper

- `docs/HOSTED_BOUNDARY.md`
- `docs/HUB_EXTRACTION_ACCEPTANCE.md`
- `docs/HUB_COMMUNITY_LEDGER_PLANE.md`
- `docs/HUB_BOUNDED_CONTEXT_MAP.md`
- `docs/HUB_IDENTITY_AND_CHANNEL_MODEL.md`
- `docs/PUBLIC_LANDING_SURFACE.md`
- `docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md`
- `.codex-design/repo/IMPLEMENTATION_SCOPE.md`

## Verification

Run:

```bash
bash scripts/ai/verify.sh
```

For the signed-in Hub browser journey proof, run:

```bash
CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/ai/run_services_verification.sh
```
