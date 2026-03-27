# Hub Extraction Acceptance

`docs/hosted-boundary.manifest`, `docs/HOSTED_BOUNDARY.md`, and `tests/RunServicesVerification/CompatibilityVerification.cs` keep the active hosted boundary limited to the canonical `Chummer.Play.Contracts`, `Chummer.Campaign.Contracts`, `Chummer.Control.Contracts`, and `Chummer.Run.*` surface, require media-factory and hub-registry contracts to flow through external owner-package seams, target the hosted runtime on `net10.0`, and block retired legacy roots (`Chummer`, `Chummer.Api`, `ChummerDataViewer`, `ChummerHub`, `Plugins`, `TextblockConverter`, and `Translator`) from re-entering the repo.

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
- 21818
- 53652
- 53653
- 53654
- 53655

## WL-207 runnable publication outputs

- Inventory source: `docs/LEGACY_ROOT_SURFACE_INVENTORY.md`
- Queue anchors for boundary moves: `WL-209`, `WL-210`, `WL-211`, `WL-212`
- Acceptance requirement: each queued boundary item must preserve hosted ownership seams (`Chummer.Run.*`, `Chummer.Play.Contracts`) while keeping extracted owner packages (`Chummer.Media.Contracts`, `Chummer.Hub.Registry.Contracts`) outside the active hosted project set.
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
- `A3` contract-canon anchor: `Chummer.Run.Contracts` remains the hosted orchestration contract plane, with registry/media execution split out to sibling owner packages instead of local hosted-project ownership.
- Executable proof path:
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs`
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `scripts/ai/verify.sh`

## WL-217 orchestration-side external adapter materialization (`C1b`)

- `C1b` scope is adapter ownership for approval/docs/survey/automation/research routes under `Chummer.Run.AI`.
- Acceptance rule: orchestration-side external adapters must stay switchable, receipt-bearing, and kill-switchable without pushing third-party provider ownership into client repos.
- Authority matrix:
  - `docs/HOSTED_ADAPTER_AUTHORITY.md`
- Executable proof path:
  - `Chummer.Run.AI/Program.cs`
  - `Chummer.Run.AI/Services/Gateway/HttpProviderAdapters.cs`
  - `Chummer.Run.AI/Services/Gateway/GovernedSkillRuntimeService.cs`
  - `Chummer.Run.AI/Services/Gateway/AiGatewayService.cs`
  - `Chummer.Run.AI/Controllers/AiGatewayController.cs`
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs`
  - `tests/RunServicesVerification/PipelineProjectionVerification.cs`
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `scripts/ai/verify.sh`

## WL-231 media-contract mirror deletion follow-through

- Scope: the repo-local `Chummer.Media.Contracts` source mirror must stay deleted now that hosted code consumes the owner-repo media contracts/runtime assemblies.
- Acceptance rule: any media compatibility surface that remains here must be an explicit compatibility wrapper, not a second source-owned media contract project.
- Executable proof path:
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs`
  - `scripts/ai/run_services_verification.sh`
  - `docs/HOSTED_BOUNDARY.md`

## WL-218 session semantic canon materialization (`D1`)

- `D1` scope is semantic session canon alignment across play/run transport wrappers.
- Acceptance rule: semantic session mutation DTOs must keep a single canonical owner, and transport wrappers must not invent a second semantic event family.
- Executable proof path:
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `tests/RunServicesVerification/PipelineProjectionVerification.cs`
  - `scripts/ai/verify.sh`
  - `CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/ai/run_services_verification.sh`

## WL-219 docs / feedback / operator projection materialization (`E2b`)

- `E2b` scope is hosted-boundary-safe docs/help, feedback, and operator projection integration.
- Acceptance rule: docs/help surfaces, feedback collection, and operator projections may integrate here without becoming a second system of record.
- Executable proof path:
  - `docs/HOSTED_BOUNDARY.md`
  - `.codex-design/review/REVIEW_CONTEXT.md`
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs`

## WL-240 campaign and control middle-plane materialization (`N1`)

- Scope: make the campaign-spine and product-control contract families executable inside Hub without regrowing a hidden monorepo blob.
- Acceptance rule: `Chummer.Campaign.Contracts` owns runner dossier, crew, campaign, run, scene, objective, continuity, and roaming restore DTOs; `Chummer.Control.Contracts` owns support, crash, and closure DTOs; `Chummer.Run.Contracts` must not re-absorb those families.
- Executable proof path:
  - `Chummer.Campaign.Contracts/*`
  - `Chummer.Control.Contracts/*`
  - `Chummer.Run.Api/Services/Community/CampaignSpineService.cs`
  - `Chummer.Run.Api/Controllers/CampaignSpineController.cs`
  - `tests/RunServicesVerification/CompatibilityVerification.cs`
  - `tests/RunServicesSmoke/Program.cs`
  - `scripts/ai/verify.sh`

## WL-220 observability / DR / replay-safety materialization (`F1`)

- `F1` scope is observability, disaster-recovery, restore, and replay-safety hardening.
- Acceptance rule: restore, replay, runtime-bundle integrity, and verification-runbook flows must stay explicitly runnable and auditable.
- Executable proof path:
  - `scripts/ai/run_services_restore_drill.sh`
  - `scripts/ai/run_services_smoke.sh`
  - `scripts/ai/run_services_verification.sh`
  - `scripts/ai/verify.sh`
- Operator runbook:
  - `docs/HOSTED_RESTORE_RUNBOOK.md`
- `tests/RunServicesVerification/StateStoreBackupVerification.cs`
- `tests/RunServicesVerification/RuntimeBundleVerification.cs`

## WL-228 legacy root-clutter milestone mapping materialization (`C2` / `R0`)

- Source publication candidates: `21818`, `53655` (`project.uncovered_scope`, `project.queue_exhausted_with_uncovered_scope`).
- Scope: explicit milestone/backlog mapping for the finding "Legacy desktop/tooling clutter still shares the run-services repo root with hosted-service code."
- Mapping decision: this lane is already executable through the completed legacy-root boundary move set, so no new queue IDs were opened.
- Executable backlog anchors already closed:
  - `WL-207` publication/inventory lane (`docs/LEGACY_ROOT_SURFACE_INVENTORY.md`)
  - `WL-209` (`Docker/` and `docker-compose.yml` moved under `legacy/tooling/docker/`)
  - `WL-210` (`docker-compose.dcproj` and `settings/` moved behind `legacy/...` boundaries)
  - `WL-211` (`Plugins/` moved behind legacy interoperability boundary)
  - `WL-212` (legacy architecture document moved out of repo root)
- Milestone alignment:
  - Program milestone: `C2` (run-services shrink)
  - Repo milestone spine: `R0` (shrink-to-boundary reset)
- Executable verification path:
  - `tests/RunServicesVerification/HubExtractionReadinessVerification.cs` (`VerifyLegacyRootBoundaryMoves`)
  - `scripts/ai/verify.sh`

## Boundary artifacts that must stay aligned

- Chummer.Run.Registry
- Chummer.Play.Contracts
- Chummer.Campaign.Contracts
- Chummer.Control.Contracts
- Chummer.Media.Contracts
- Chummer.Hub.Registry.Contracts
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
