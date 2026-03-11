# Hub Extraction Acceptance

`WL-089` closes the Contract Reset follow-up for Hub acceptance by turning auditor finding `25` (`project.uncovered_scope`) and the related split blockers into repo-local verification checks.
`WL-148` extends that acceptance lane so hosted play package/API seam findings remain explicit extraction-readiness dependencies instead of resurfacing as uncovered Hub scope.
`WL-149` extends the same acceptance lane so resurfaced `chummer-hub-registry` package-boundary findings stay tied to the completed registry extraction seam instead of reopening queue coverage.
`WL-161` reconfirms that the same hub-registry runnable-backlog overlays stay resolved in explicit Hub execution tracks and that milestone-coverage finding `28` remains mapped instead of resurfacing as partial registry truth.
`WL-150` extends the same acceptance lane so resurfaced `chummer-media-factory` render-only boundary findings stay tied to the completed media extraction seam instead of reopening queue coverage.
`WL-153` extends the same acceptance lane so the hosted contract-family split and overlay-compatibility retirement findings stay tied to the completed contract-reset backlog instead of resurfacing as fresh Hub extraction blockers.
`WL-152` extends the same acceptance lane so resurfaced legacy desktop/tooling clutter findings stay tied to the hosted-topology boundary checks instead of reopening uncovered-scope or queue-exhausted Hub work.
`WL-155` extends the same acceptance lane so the repo-local design mirror and review context stay explicit extraction-readiness dependencies instead of surfacing again as stale local context.
The explicit executable mapping for this acceptance lane lives in `.codex-design/product/PROGRAM_MILESTONES.yaml` under `repo_execution_tracks -> project: hub -> P0`, where candidates `25`, `11709`, `1926`, and `3948` stay mapped as explicit Hub acceptance work instead of resurfacing as uncovered scope, stale mirror drift, or compatibility drift.

The acceptance checks for this repo are:

1. Hosted topology stays narrow.
This closes auditor findings `4367`, `21818`, and `53655` across `project.hub_legacy_host_clutter_present`, `project.uncovered_scope`, and `project.queue_exhausted_with_uncovered_scope`.
`docs/hosted-boundary.manifest`, `docs/HOSTED_BOUNDARY.md`, and `tests/RunServicesVerification/CompatibilityVerification.cs` keep the oracle root (`Chummer`) outside `Chummer.Run.sln`, require the active hosted boundary to run through `Chummer.Run.Api`, and block retired hosted clutter (`Chummer.Api`, `ChummerDataViewer`, `ChummerHub`, `Plugins/ChummerHub.Client`, `TextblockConverter`, and `Translator`) from re-entering the repo.

2. Registry extraction readiness stays explicit.
`Chummer.Run.Registry` must own `PublicationsController` and `PublicationWorkflowService`, while `Chummer.Run.Api` must not regain them. `tests/RunServicesVerification/HubExtractionReadinessVerification.cs` also enforces that `Chummer.Run.Registry` keeps a single project-reference seam to `Chummer.Run.Contracts`.
This closes auditor findings `4334` and `4339` by keeping the Hub acceptance lane explicitly dependent on the completed `chummer-hub-registry` split work (`WL-085`) for catalog, publication, installs, and runtime bundle heads instead of treating that seam as uncovered scope again.

3. Hosted play package/API seam readiness stays explicit.
This closes auditor findings `4333` and `4338` by keeping Hub extraction acceptance tied to the already-completed hosted play seam lane instead of letting the mirror treat `Chummer.Play.Contracts` or `/api/play/*` as uncovered scope again.
`Chummer.Play.Contracts` remains the canonical hosted play package, `docs/legacy-interop-boundary.manifest` keeps it inside the active hosted boundary, `tests/RunServicesVerification/CompatibilityVerification.cs` blocks play-side overlay wrapper regressions and shape drift, and `tests/RunServicesSmoke/Program.cs` keeps hosted play consumers exercised under `scripts/ai/verify.sh`.

4. Media extraction readiness stays explicit.
This closes auditor findings `8667`, `8668`, `21817`, `53652`, `53653`, `53654`, `8697`, `8698`, and `21924` across `project.uncovered_scope`, `project.queue_exhausted_with_uncovered_scope`, and `project.media_contracts_mix_render_and_narrative`.
`Chummer.Media.Contracts` must remain the dependency-light render-only seam with no project or package references, and Hub `P0` stays explicitly dependent on the already-completed media-factory backlog (`WL-088`, `WL-095`, `WL-098`, `WL-102`, `WL-104`, `WL-111`, `WL-125`, `WL-137`, and `WL-140`) plus the acceptance-trace refresh in `WL-151` instead of treating that package-only boundary as newly uncovered scope.
Narrative, delivery, and session-aware orchestration DTOs stay in `Chummer.Run.Contracts.Media`, and the readiness verification blocks render-only DTO families from drifting back across that boundary while keeping the `Chummer.Run.Contracts.Media` split findings explicitly mapped to Hub `P0` instead of resurfacing as fresh queue or uncovered-scope work.

5. Contract-reset hosted DTO seams stay explicit.
This closes auditor findings `1926` and `3948` across `project.ai_platform_contract_catchall` and `project.session_overlay_compat_shim_present`.
Hub `P0` stays explicitly dependent on the completed hosted contract split and overlay retirement backlog (`WL-086`, `WL-118`, `WL-120`, and `WL-145`) instead of treating those regressions as new extraction blockers.
`tests/RunServicesVerification/CompatibilityVerification.cs` keeps `AIPlatformContracts.cs` absent as a catch-all seam and blocks `SessionOverlayEventDto` from reappearing in `Chummer.Run.Contracts` or `Chummer.Play.Contracts`.

6. Repo-local design mirror readiness stays explicit.
This closes auditor finding `11709` (`project.design_mirror_missing_or_stale`).
Hub `P0` stays explicitly dependent on the approved local mirror under `.codex-design/`, including `.codex-design/product/README.md`, `.codex-design/repo/IMPLEMENTATION_SCOPE.md`, and `.codex-design/review/REVIEW_CONTEXT.md`, so package-seam and extraction-readiness checks keep running against current Chummer canon instead of stale local context.
`tests/RunServicesVerification/HubExtractionReadinessVerification.cs` blocks those mirrored files from dropping out of the acceptance surface.

7. Group-level publication seams stay mapped.
This closes auditor finding `2369` (`project.queue_exhausted_with_uncovered_scope`) by keeping the publication lane explicit under `.codex-design/product/PROGRAM_MILESTONES.yaml` `repo_execution_tracks -> project: hub -> P3`.
`tests/RunServicesVerification/PublicationVerification.cs` and `tests/RunServicesSmoke/Program.cs` keep review, publication, immutable retention, and moderation timeline behavior covered without moving publication workflow ownership back into `Chummer.Run.Api`.

8. Verification remains one command.
Run `scripts/ai/verify.sh` to execute the clean-room build, the Hub extraction readiness checks, and the existing smoke coverage together.

These checks model extraction readiness inside `chummer.run-services`; they do not replace the later cross-repo cutover to canonical `Chummer.Hub.Registry.Contracts` and the dedicated `chummer-media-factory` repo.
