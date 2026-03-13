# Hub Extraction Acceptance

`docs/hosted-boundary.manifest`, `docs/HOSTED_BOUNDARY.md`, and `tests/RunServicesVerification/CompatibilityVerification.cs` keep the hosted boundary limited to the canonical `Chummer.Run.*`, `Chummer.Play.Contracts`, and `Chummer.Media.Contracts` surface, require the active hosted boundary to run through `Chummer.Run.Api`, target the hosted runtime on `net10.0`, and block retired legacy roots (`Chummer`, `Chummer.Api`, `ChummerDataViewer`, `ChummerHub`, `Plugins`, `TextblockConverter`, and `Translator`) from re-entering the repo.

## Worklist and issue anchors

This acceptance gate closes the hosted split/purification work tracked under:

- WL-085
- WL-086
- WL-088
- WL-089
- WL-095
- WL-098
- WL-102
- WL-104
- WL-111
- WL-118
- WL-120
- WL-125
- WL-137
- WL-140
- WL-145
- WL-148
- WL-149
- WL-150
- WL-151
- WL-153
- WL-155
- WL-207
- WL-209
- WL-210
- WL-211
- WL-212

Issue and migration anchors preserved in this acceptance narrative:

- 1926
- 2367
- 2369
- 3948
- 4333
- 4334
- 4338
- 4339
- 4367
- 8667
- 8668
- 8697
- 8698
- 11709
- 21817
- 21924
- 53652
- 53653
- 53654

## WL-207 runnable publication outputs

- Inventory source: `docs/LEGACY_ROOT_SURFACE_INVENTORY.md`
- Queue anchors for boundary moves: `WL-209`, `WL-210`, `WL-211`, `WL-212`
- Acceptance requirement: each queued boundary item must preserve hosted ownership seams (`Chummer.Run.*`, `Chummer.Play.Contracts`, `Chummer.Media.Contracts`) while moving non-hosted legacy/tooling surfaces behind an explicit legacy/interoperability boundary.
- Completed handoff: `WL-209` moved `Docker/` + `docker-compose.yml` into `legacy/tooling/docker/` with compose/script/workflow handoff paths updated.
- Completed handoff: `WL-210` moved `docker-compose.dcproj` to `legacy/tooling/vs-compose/docker-compose.dcproj` and `settings/` to `legacy/interoperability/settings/` with bridge paths updated inside the `.dcproj`.
- Completed handoff: `WL-211` moved root `Plugins/` under `legacy/interoperability/plugins/` and tightened hosted-boundary verification so `Plugins` is blocked from returning as a hosted root.
- Completed handoff: `WL-212` moved `chummer-run-services.design.v2.md` to `legacy/architecture-archive/chummer-run-services.design.v2.md` and replaced active references with `.codex-design/*` plus `docs/HOSTED_BOUNDARY.md`.

## WL-208 milestone/backlog publication outputs (candidate 2367)

- Candidate: `2367` (`project.queue_exhausted_with_uncovered_scope`)
- Scope: contract reset plus relay/runtime alignment milestone coverage in Hub extraction tracks.
- Explicit contract-reset backlog mapping: `WL-089`, `WL-097`, `WL-099`, `WL-121`, `WL-131`, `WL-179`, `WL-185`.
- Explicit relay/runtime alignment backlog mapping: `WL-090`, `WL-099`, `WL-121`, `WL-131`, `WL-152`, `WL-179`, `WL-185`.
- Execution note: this publication lane is mapping-only; no new implementation backlog IDs were opened because the runnable work remains completed and verified in the IDs above.

## WL-216 contract-canon milestone-family materialization (`A2` / `A3`)

- Source publication candidates: `26`, `2368`.
- `A2` contract-canon anchor: `Chummer.Play.Contracts` remains the canonical play/session transport seam, with ownership guarded by hosted-boundary verification and compatibility checks.
- `A3` contract-canon anchor: `Chummer.Run.Contracts` remains the hosted orchestration contract plane, with registry/media execution split out of the canonical orchestration surface.
- Executable proof path:
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs`
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `scripts/ai/verify.sh`

## WL-217 orchestration-side external adapter materialization (`C1b`)

- `C1b` scope is adapter ownership for approval/docs/survey/automation/research routes under `Chummer.Run.AI`.
- Acceptance rule: orchestration-side external adapters must stay switchable, receipt-bearing, and kill-switchable without pushing third-party provider ownership into client repos.
- Executable proof path:
  - `tests/RunServicesVerification/PipelineProjectionVerification.cs`
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `scripts/ai/verify.sh`

## WL-218 session semantic canon materialization (`D1`)

- `D1` scope is semantic session canon alignment across play/run transport wrappers.
- Acceptance rule: semantic session mutation DTOs must keep a single canonical owner, and transport wrappers must not invent a second semantic event family.
- Executable proof path:
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `tests/RunServicesVerification/PipelineProjectionVerification.cs`
  - `scripts/ai/verify.sh`

## WL-219 docs / feedback / operator projection materialization (`E2b`)

- `E2b` scope is hosted-boundary-safe docs/help, feedback, and operator projection integration.
- Acceptance rule: docs/help surfaces, feedback collection, and operator projections may integrate here without becoming a second system of record.
- Executable proof path:
  - `docs/HOSTED_BOUNDARY.md`
  - `.codex-design/review/REVIEW_CONTEXT.md`
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs`

## WL-220 observability / DR / replay-safety materialization (`F1`)

- `F1` scope is observability, disaster-recovery, restore, and replay-safety hardening.
- Acceptance rule: restore, replay, runtime-bundle integrity, and verification-runbook flows must stay explicitly runnable and auditable.
- Executable proof path:
  - `scripts/ai/run_services_smoke.sh`
  - `scripts/ai/run_services_verification.sh`
  - `scripts/ai/verify.sh`
  - `tests/RunServicesVerification/StateStoreBackupVerification.cs`
  - `tests/RunServicesVerification/RuntimeBundleVerification.cs`

## Boundary artifacts that must stay aligned

- Chummer.Run.Registry
- Chummer.Play.Contracts
- Chummer.Media.Contracts
- LEGACY_ROOT_SURFACE_INVENTORY.md
- PublicationVerification.cs
- CompatibilityVerification.cs
- HOSTED_BOUNDARY.md
- hosted-boundary.manifest
- .codex-design/product/README.md
- .codex-design/repo/IMPLEMENTATION_SCOPE.md
- .codex-design/review/REVIEW_CONTEXT.md
- PROGRAM_MILESTONES.yaml
- scripts/ai/verify.sh
