# chummer6-hub

Hosted orchestration and play API boundary for Chummer6.

## What this repo is

`chummer6-hub` is the hosted backbone for:

- identity, relay, approvals, and memory
- hosted play APIs and orchestration
- governed AI, docs/help, and automation bridges
- orchestration-side registry and media adapters

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

- the hosted boundary story is good
- the physical repo body is still broader than that story
- closing `A2`, `A3`, `C0`, and `C1` requires more shrinkage, not more adjectives

## Go deeper

- `docs/HOSTED_BOUNDARY.md`
- `docs/HUB_EXTRACTION_ACCEPTANCE.md`
- `.codex-design/repo/IMPLEMENTATION_SCOPE.md`

## Verification

Run:

```bash
bash scripts/ai/verify.sh
```
