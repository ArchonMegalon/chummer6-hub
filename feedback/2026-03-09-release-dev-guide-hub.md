# Release Dev Guide Split: run-services / Hub

Source: 2026-03-09 Project Chummer release dev guide. This is the `chummer.run-services` slice only.

## Your authority

`chummer.run-services` must own:

- identity/authz/authn
- Hub registry, publication, moderation, install history, and runtime references
- session relay, DeliveryOutbox, Spider, and GM operations flows
- AI gateway, governed skill runtime, approvals, memory, lore, and media jobs
- hosted APIs, background workers, audit trails, and operational observability

It must not privately reimplement engine mechanics.

## Immediate corrections

1. Publish and own `Chummer.Run.Contracts` as the single source for hosted-service contract families.
2. Take ownership of AI/media/transcription/approval/publication/Hub contracts currently leaking from core.
3. Converge the session relay on one canonical event envelope shared with core reducer and client cache.
4. Expand public test ownership here; smoke-only coverage is not enough for this repo’s responsibility.

## What to finish next

- canonical relay API with idempotency keys, scene identity, and convergence diagnostics
- runtime bundle issuance for session/mobile heads
- Hub artifact registry with immutable version/state machine rules
- approval-backed publication and audit trails
- DeliveryOutbox with stale/invalidation semantics
- governed skill runtime with tool adapters and approval classes
- memory candidate, lore retrieval, NPC persona, and canonization flows
- async asset-job pipeline backed by object storage and signed URLs

## Guardrails

- do not compute core rules truth here
- do not let feature endpoints call providers directly
- do not bypass approval for canon-affecting or player-visible actions
- do not treat generated media/text as canonical truth without review
- do not stream large media blobs through app servers

## Test and CI guidance

- move AI gateway, Hub publication, media queue, approval, provider-router, registry, and relay tests into this repo
- add contract fixture tests for SessionEventEnvelope, ApprovalRequest, MemoryCandidate, AssetJobStatus, and Hub artifact metadata
- add observability, backup/restore, idempotency, and dead-letter verification before RC
- add repo-boundary checks so mechanics code does not drift into hosted services

## Definition of done for this repo

Run-services is not done until:

- Hub, relay, approvals, skills, memory, lore, and media are fully owned here
- hosted contract families are versioned and explicit
- relay/review/approval/media pipelines are audited and observable
- asset lifecycle and object-store policy are operational
- RC operational drills pass
