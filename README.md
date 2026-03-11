# chummer6-hub

Hosted orchestration and play API boundary for Chummer6.

## What this repo is

`chummer6-hub` owns the hosted Chummer surface:

- `Chummer.Play.Contracts`
- `Chummer.Media.Contracts`
- `Chummer.Run.Contracts`
- `Chummer.Run.Api`
- `Chummer.Run.Identity`
- `Chummer.Run.Registry`
- `Chummer.Run.AI`

This repo is the orchestrator shell for identity, relay, approvals, memory,
AI orchestration, hosted play APIs, registry-facing publication seams, and
media orchestration contracts.

## What this repo is not

This repo is not the legacy WinForms app, not a compatibility archive, and not
the home for retired desktop helpers or sample plugins.

It does not own:

- the engine/runtime reducer truth
- the player/GM/mobile shell
- shared UI-kit primitives
- render-only media execution ownership
- a preserved GPL oracle tree

## Boundary truth

Canonical hosted boundary guidance lives in:

- `docs/HOSTED_BOUNDARY.md`
- `docs/HUB_EXTRACTION_ACCEPTANCE.md`
- `tests/RunServicesVerification/CompatibilityVerification.cs`

The active build and verification path is:

```bash
bash scripts/ai/verify.sh
```
