# chummer6-hub

Hosted orchestration and play API boundary for Chummer6.

## What this repo is

`chummer6-hub` is the hosted backbone for:

- identity, relay, approvals, and memory
- hosted play APIs and orchestration
- governed AI, docs/help, and automation bridges
- orchestration-side registry and media adapters
- user accounts, groups, sponsorship sessions, and the canonical community ledger

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

The public-facing community spine now lives here too:

- `Chummer.Run.Api` owns product-level users, groups, join/boost codes, sponsor sessions, leaderboards, rewards, and entitlements
- `Chummer.Run.Identity` remains the principal/session boundary below that account layer
- `Chummer.Run.AI` ingests sponsor receipts and projects sponsored-lane activity
- Fleet executes sponsored participant lanes, but Hub owns the canonical community/accounting truth

## Go deeper

- `docs/HOSTED_BOUNDARY.md`
- `docs/HUB_EXTRACTION_ACCEPTANCE.md`
- `docs/HUB_COMMUNITY_LEDGER_PLANE.md`
- `.codex-design/repo/IMPLEMENTATION_SCOPE.md`

## Verification

Run:

```bash
bash scripts/ai/verify.sh
```
