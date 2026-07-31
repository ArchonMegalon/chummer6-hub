# Next Session Handoff

Updated: 2026-07-31T20:32:02+02:00

## Handoff refresh (2026-07-31T20:32:02+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `proof:user_journey_tester_audit`
  - `proof:core_release_receipts`
  - `release_truth:public_edge_postdeploy_gate`
  - `release_truth:release_ready`
  - `release_truth:google_oauth_linking_proof`
  - `release_truth:windows_installer_visual_audit`
  - `blocked_route:avalonia:macos:osx-arm64`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-31T18:35:08Z`
    - `load_status=loaded`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260731-095000 RELEASE_PUBLISHED_AT=2026-07-31T07:59:45Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-31T18:34:45Z`
    - `status=fail`
    - stale source digest still recorded: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - promoted digest still required: `17a02613f7d91e66c4077c09b9a6ddd80fbcc5fa51ebfbabe62266fe4cead45d`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-17a02613f7d9.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-31T18:35:08Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-31T18:35:08Z`
    - `status=not_running`
    - `pid=missing`
    - `process_alive=False`
    - `matching_process_count=0`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-31T18:35:08Z`
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-31T18:34:37Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-31T18:34:37Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-31T18:35:10Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=69`
    - `coverage_gap_keys=desktop_client`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Goal Refinement Sync (2026-07-10T06:14:14+02:00)

- Current controller/root blocker truth remains:
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
- Origin-dialog lane Blazor workbench polish and dialog/UI copy hardening advanced without changing release-controller truth:
  - `.codex-studio/published/BLAZOR_WORKBENCH_POLISH_STAGED_PROOF.generated.json` now reports `status=passed`, generated `2026-07-10T04:03:40.197492+00:00`, with `30` checks and `0` failed checks.
  - the Blazor Preview/App/Workbench source now keeps header navigation on local href properties while preserving the proof-visible relative route markers for `home`, `app`, `workbench`, `preview`, `showcase`, and `health`.
  - output workbench links for save-as/export/print now use the local workbench command href helper and local command constants instead of drifting through the app command helper.
  - desktop home/build/campaign/dialog/default-localization copy now consistently uses the staged dossier and campaign-dossier language required by the current polish contract.
  - `docs/BLAZOR_WORKBENCH_POLISH_STAGED_PROOF.md` now records the setup/rules command-link source contract and keyboard-visible primary startup focus.
- Focused verification:
  - `bash scripts/ai/milestones/blazor-workbench-polish-staged-proof-check.sh` -> pass.
  - `dotnet build Chummer.Blazor/Chummer.Blazor.csproj -c Debug --no-restore -m:1 --disable-build-servers -p:UseSharedCompilation=false -p:BuildInParallel=false` -> pass, `0` warnings, `0` errors.
  - focused Debug test-host build for `AccessibilitySignoffSmokeTests` and `DesktopHomeCampaignProjectorTests` with the roster parity support file and `BuildProjectReferences=false` -> pass.
  - `Chummer.Tests/bin/Debug/net10.0/Chummer.Tests --minimum-expected-tests 3 --output Normal` -> `3` passed, `0` failed, `0` skipped.
- Caveat for the other Codexes:
  - a broad Release test-host build attempt fanned out through project references and failed on generated-output disk pressure (`No space left on device`). Prefer focused baseline-host builds for this repo until workspace cache/staging pressure is cleaned up.
- Other Codex readout:
  - SR6 workflow-family frontier and Blazor polish staged proof are both lane-local green now, but root release blockers still control merge/deploy/nightly decisions.
  - release-controller/publish lanes must keep treating the blockers above as authoritative and unchanged.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker(s) above remain.

## Goal Refinement Sync (2026-07-10T05:54:08+02:00)

- Current controller/root blocker truth remains:
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
- Origin-dialog lane SR6 shell/dialog parity and workflow-proof hardening advanced again without changing release-controller truth:
  - `Chummer.Tests/Chummer.Tests.csproj` now normalizes `FocusedTestBaselineHostDir` and `OutDir` with `MSBuild::EnsureTrailingSlash(...)`, fixing the focused baseline-host copy seam that could fail before execution and leave stale workflow-family TRX files in place.
  - `scripts/ai/milestones/materialize-sr-workflow-family-execution-receipts.sh` now treats `Chummer.Presentation` baseline-host freshness as explicit receipt evidence instead of silently trusting old cached outputs.
  - `tests/test_chummer5a_parity_tester.py` now pins both of those contracts.
- Current lane-local live-state is now green:
  - `SR6_DESKTOP_WORKFLOW_PARITY.generated.json` -> `status=pass`
  - `SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json` -> `status=pass`
  - SR6 workflow-family executed, verification, and published family receipts are all current `status=pass`
- Focused verification:
  - `python3 -m pytest -q tests/test_chummer5a_parity_tester.py` -> `20 passed`
  - focused baseline-host build command with `BuildProjectReferences=false` -> pass
  - `materialize-sr-workflow-family-execution-receipts.sh sr6` -> pass
  - `materialize-sr-workflow-family-verification-receipts.sh sr6` -> pass
  - `materialize-sr-workflow-family-receipts.sh sr6` -> pass
  - `sr6-desktop-workflow-parity-check.sh` -> pass
  - `sr4-sr6-desktop-parity-frontier-receipt.sh` -> pass
- Other Codex readout:
  - release-controller/publish lanes should keep treating the root blockers above as authoritative and unchanged.
  - the origin-dialog lane is now clean on the SR4/SR6 workflow-family frontier, but that does not authorize merge-to-main, deploy, or nightly publication because the shared external blocker set still controls those decisions.
  - if another Codex picks up this repo lane next, it should move to the next SR6 shell/dialog polish or portability hardening slice rather than revisiting the now-cleared workflow-family stale-TRX seam.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker(s) above remain.

## Goal Refinement Sync (2026-07-10T05:15:31+02:00)

- Current controller/root blocker truth remains:
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
- Origin-dialog lane SR6 shell/dialog parity and workflow-proof hardening advanced in the current repo without changing release-controller truth:
  - the SR4 / SR6 / Chummer5a workflow parity wrappers now use process-group timeout enforcement and focused `WorkflowParityGateTests.cs` compilation with the `Chummer.Tests` baseline-host fast path, rather than broad `Chummer.Tests.csproj` builds.
  - `ruleset-ui-adaptation-check.sh` now uses the same process-group timeout enforcement, focused ruleset-shell unit compilation, and an exact `23`-test MTP inventory gate.
  - `AccessibilitySignoffSmokeTests.cs` was updated to match the current SR6 home spotlight copy (`Sixth World dossier editor`).
- Current lane-local live-state is materially narrower:
  - `RULESET_UI_ADAPTATION.generated.json` now passes when bound to the canonical hub-registry release channel.
  - `SR4_DESKTOP_WORKFLOW_PARITY.generated.json` and `CHUMMER5A_DESKTOP_WORKFLOW_PARITY.generated.json` were refreshed with canonical hub-registry release-channel metadata.
  - `SR6_DESKTOP_WORKFLOW_PARITY.generated.json` was refreshed and now fails only because the current SR6 workflow-family receipts remain failing.
  - `SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json` still fails, but its reasons are now reduced to the genuine SR6 workflow-family receipt failures only; the stale SR4 / Chummer5a / ruleset release-channel drift reasons are cleared.
- Focused verification:
  - `bash -n scripts/ai/milestones/sr4-desktop-workflow-parity-check.sh scripts/ai/milestones/sr6-desktop-workflow-parity-check.sh scripts/ai/milestones/chummer5a-desktop-workflow-parity-check.sh scripts/ai/milestones/ruleset-ui-adaptation-check.sh` -> pass
  - `python3 -m pytest -q tests/test_chummer5a_parity_tester.py` -> `20 passed`
  - `ruleset-ui-adaptation-check.sh` -> pass with canonical `CHUMMER_DESKTOP_WORKFLOW_RELEASE_CHANNEL_PATH`
  - `sr4-desktop-workflow-parity-check.sh` -> pass with `CHUMMER_SR4_WORKFLOW_PARITY_SKIP_DEPENDENCY_MATERIALIZE=1`
  - `chummer5a-desktop-workflow-parity-check.sh` -> pass
  - `sr6-desktop-workflow-parity-check.sh` -> exit `43`, refreshed current fail reason limited to SR6 workflow-family receipts
  - `sr4-sr6-desktop-parity-frontier-receipt.sh` -> exit `43`, refreshed frontier reasons limited to SR6 workflow-family receipt failures
- Other Codex readout:
  - release-controller/publish lanes should keep treating the root blockers above as authoritative and unchanged.
  - this origin-dialog lane is now a clean consumer of the canonical hub-registry release channel, but it is not merge/deploy/nightly ready because the SR6 workflow-family frontier remains open.
  - if another Codex picks up this lane, the next honest slice is SR6 workflow-family receipt reduction, not more stale-receipt cleanup.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker(s) above remain.

## Goal Refinement Sync (2026-07-10T03:55:35+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh above:
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
- Origin-dialog lane SR6 shell/dialog parity and workflow-proof hardening:
  - `scripts/ai/milestones/sr4-desktop-workflow-parity-check.sh`, `sr6-desktop-workflow-parity-check.sh`, and `chummer5a-desktop-workflow-parity-check.sh` now run their targeted `dotnet build` legs with `-m:1`, `--disable-build-servers`, `-p:UseSharedCompilation=false`, and `-p:BuildInParallel=false` in addition to the previously landed timeout wrappers.
  - `scripts/ai/milestones/ruleset-ui-adaptation-check.sh` now applies the same build-server suppression and single-threaded build flags to both build legs.
  - `tests/test_chummer5a_parity_tester.py` now pins the hardened build command contract across the SR4, SR6, Chummer5a, and ruleset-adaptation wrappers.
- Current lane-local live-state note remains unchanged:
  - the active `SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json` receipt is still `status=fail`.
  - remaining lane-local evidence debt is still SR6 workflow-family parity plus stale aligned refresh on the older SR4 / Chummer5a / ruleset-adaptation receipts; this slice hardens the build command path but does not claim those receipts are regenerated.
- Focused verification:
  - `bash -n scripts/ai/milestones/sr4-desktop-workflow-parity-check.sh scripts/ai/milestones/sr6-desktop-workflow-parity-check.sh scripts/ai/milestones/chummer5a-desktop-workflow-parity-check.sh scripts/ai/milestones/ruleset-ui-adaptation-check.sh` -> pass
  - `tests/test_chummer5a_parity_tester.py` -> `19 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-workflow-build-server-hardening-20260710T0356.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker(s) above remain.

## Goal Refinement Sync (2026-07-10T03:52:14+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh above:
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
- Origin-dialog lane SR6 shell/dialog parity and workflow-proof hardening:
  - `scripts/ai/milestones/sr4-desktop-workflow-parity-check.sh`, `sr6-desktop-workflow-parity-check.sh`, and `chummer5a-desktop-workflow-parity-check.sh` now wrap their targeted `dotnet build` and direct MTP runner legs in bounded timeout helpers.
  - those workflow parity scripts now support per-script build/test timeout env vars with shared fallback roots and record timeout evidence plus explicit timed-out reasons (`exit 124`) in their receipts.
  - `scripts/ai/milestones/ruleset-ui-adaptation-check.sh` now applies the same bounded timeout pattern to its build legs and signoff runner, with timeout evidence recorded in the receipt.
  - `tests/test_chummer5a_parity_tester.py` now pins the timeout contract across all four parity-refresh scripts.
- Current lane-local live-state note remains unchanged from the prior frontier refresh:
  - the active `SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json` receipt is still `status=fail`.
  - remaining lane-local evidence debt is still SR6 workflow-family parity plus stale aligned refresh on the older SR4 / Chummer5a / ruleset-adaptation receipts; this slice hardens the refresh path but does not claim those receipts are regenerated.
- Focused verification:
  - `bash -n scripts/ai/milestones/sr4-desktop-workflow-parity-check.sh scripts/ai/milestones/sr6-desktop-workflow-parity-check.sh scripts/ai/milestones/chummer5a-desktop-workflow-parity-check.sh scripts/ai/milestones/ruleset-ui-adaptation-check.sh` -> pass
  - `tests/test_chummer5a_parity_tester.py` -> `19 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-workflow-timeout-hardening-20260710T0352.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker(s) above remain.

## Handoff refresh (2026-07-10T03:43:37+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-10T01:44:05Z`
    - `load_status=loaded`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-10T01:43:57Z`
    - `status=pass`
    - stale source digest still recorded: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-10T01:43:43Z`
    - `status=pass`
    - `actionable_candidate_count=missing`
    - `all_discovery_roots_checked=missing`
    - `matching_promoted_directory_candidate_count=missing`
    - `matching_promoted_zip_candidate_count=missing`
    - `stale_directory_candidate_count=missing`
    - `stage_visual_proof_receipt_count=missing`
    - `matching_promoted_stage_visual_proof_receipt_count=missing`
    - `stage_startup_smoke_receipt_count=missing`
    - `matching_promoted_stage_startup_smoke_receipt_count=missing`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-10T01:43:43Z`
    - `status=not_running`
    - `pid=missing`
    - `process_alive=False`
    - `matching_process_count=0`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=pass`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-10T01:43:43Z`
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-10T01:44:19Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=2`
    - `coverage_gap_keys=desktop_client`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from the current blocker sheet
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Goal Refinement Sync (2026-07-10T03:33:15+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane SR6 shell/dialog polish and release-posture portability hardening:
  - added `scripts/resolve-fleet-root.sh` so current-lane gates resolve Fleet roots through `CHUMMER_FLEET_ROOT`, `GITHUB_WORKSPACE`, workspace-relative checkout, then legacy `/docker/...` fallbacks instead of embedding direct Fleet tool paths inside the gate scripts.
  - added `scripts/resolve-chummer5a-root.sh` so current-lane Chummer5a baseline checks resolve the legacy repo through `CHUMMER_CHUMMER5A_ROOT`, `GITHUB_WORKSPACE`, workspace-relative checkout, then legacy `/docker/...` fallbacks instead of embedding a direct FrmCareer designer path.
  - `scripts/ai/milestones/materialize-desktop-visual-familiarity-exit-gate.sh` and `scripts/ai/milestones/chummer5a-layout-hard-gate.sh` now resolve the legacy FrmCareer baseline through the Chummer5a resolver.
  - `scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh`, `scripts/ai/milestones/materialize-desktop-workflow-execution-gate.sh`, and `scripts/ai/milestones/b14-flagship-ui-release-gate.sh` now resolve flagship readiness dependencies through the Fleet resolver, and the flagship gate no longer embeds `/docker/fleet` defaults inside its shell or embedded Python proof packet.
  - `tests/test_desktop_executable_exit_gate_contract.py` and `tests/test_desktop_downloads_local_release_policy.py` now pin the resolver contract and the removal of the direct `/docker/fleet` and `/docker/chummer5a` gate defaults.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/resolve-fleet-root.sh scripts/resolve-chummer5a-root.sh scripts/ai/milestones/materialize-desktop-visual-familiarity-exit-gate.sh scripts/ai/milestones/chummer5a-layout-hard-gate.sh scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh scripts/ai/milestones/materialize-desktop-workflow-execution-gate.sh scripts/ai/milestones/b14-flagship-ui-release-gate.sh` -> pass
  - `bash scripts/resolve-fleet-root.sh` -> `/docker/fleet`
  - `bash scripts/resolve-chummer5a-root.sh` -> `/docker/chummer5a`
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `25 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `87 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-fleet-chummer5a-roots-20260710T0333.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T03:22:49+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now resolves the live public-edge downloads shelf and redeploy root from `CHUMMER_RUN_SERVICES_ROOT` when explicitly set, otherwise from `WORKSPACE_ROOT/chummer.run-services`.
  - it no longer hardcodes the sibling run-services root directly into `DEPLOY_DIR`, `LIVE_PUBLIC_EDGE_DOWNLOADS_DIR`, or the `docker compose` public-edge redeploy step.
  - this closes the nightly publish run-services seam: the nightly publish lane could previously only target and redeploy one sibling workspace layout even though the surrounding release-script hardening work had already moved to workspace-relative or explicit root resolution.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the explicit run-services root contract in the nightly publish script, and `tests/test_windows_installer_payload_gate.py` still passes as the behavior-level publish lane check after the root-resolution change.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/publish-latest-nightly-to-downloads.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `86 passed`
  - `tests/test_windows_installer_payload_gate.py` -> `62 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-nightly-run-services-root-20260710T0328.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T03:16:31+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/ai/milestones/materialize-desktop-workflow-execution-gate.sh` now resolves the human-side rule-authority gold approval receipt from `CHUMMER_CORE_ENGINE_ROOT` when explicitly set, otherwise from `WORKSPACE_ROOT/chummer-core-engine`.
  - it no longer hardcodes `/docker/chummercomplete/chummer-core-engine/.codex-studio/published/HUMAN_SIDE_RULE_AUTHORITY_GOLD_APPROVAL.generated.json`.
  - this closes the desktop workflow execution-gate approval seam: the workflow execution gate could previously only resolve that approval receipt from one absolute workspace layout even though adjacent flagship and shell/dialog gates had already moved to workspace-relative or explicit root resolution.
  - `tests/test_desktop_executable_exit_gate_contract.py` now pins the workspace-relative or explicit core-engine approval root in the workflow gate, and `tests/test_desktop_downloads_local_release_policy.py` now pins the same contract in the maintained release-policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/ai/milestones/materialize-desktop-workflow-execution-gate.sh` -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `24 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `86 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-workflow-gate-core-root-20260710T0324.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T03:13:40+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/materialize-macos-desktop-exit-gate.sh` now resolves startup-smoke receipts through `CHUMMER_PORTAL_SUPPORT_SOURCE_ROOT` when explicitly set, then repo-local `Docker/Downloads/startup-smoke` and `Chummer.Portal/downloads/startup-smoke`.
  - it no longer silently falls back to a sibling `chummer.run-services/Chummer.Portal/downloads/startup-smoke` tree.
  - this closes the macOS startup-smoke proof seam: the macOS exit gate could previously source host-proof receipts from a sibling workspace checkout outside the repo-local lane being verified.
  - `tests/test_desktop_executable_exit_gate_contract.py` now pins the explicit support-root and repo-local startup-smoke contract, and `tests/test_desktop_downloads_local_release_policy.py` now pins the same contract in the maintained release-policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/materialize-macos-desktop-exit-gate.sh` -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `24 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `86 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-macos-startup-smoke-root-20260710T0320.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T03:08:41+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-posture portability hardening:
  - `scripts/ai/milestones/b14-flagship-ui-release-gate.sh` now resolves the human-side rule-authority gold approval receipt from `CHUMMER_CORE_ENGINE_ROOT` when explicitly set, otherwise from `WORKSPACE_ROOT/chummer-core-engine`.
  - it no longer hardcodes `/docker/chummercomplete/chummer-core-engine/.codex-studio/published/HUMAN_SIDE_RULE_AUTHORITY_GOLD_APPROVAL.generated.json`.
  - this closes the flagship-gate approval seam: the current flagship/release-posture gate could previously only resolve that approval receipt from one absolute workspace layout even though the rest of the current lane had already moved toward alias-safe and workspace-relative root resolution.
  - `tests/test_desktop_executable_exit_gate_contract.py` now pins the workspace-relative or explicit core-engine approval root in the flagship gate, and `tests/test_desktop_downloads_local_release_policy.py` now pins the same contract in the maintained release-policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/ai/milestones/b14-flagship-ui-release-gate.sh` -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `23 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `85 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-flagship-gate-core-root-20260710T0318.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T03:03:31+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane SR6 shell/dialog parity hardening:
  - `scripts/ai/milestones/desktop-shell-dialog-chrome-check.sh` now uses an alias-safe repo root plus workspace-relative dependency roots for baseline contract DLL outputs.
  - `CHUMMER_CORE_ENGINE_ROOT` and `CHUMMER_RUN_SERVICES_ROOT` can now override the core-engine and run-services dependency roots explicitly; otherwise the script resolves them from `WORKSPACE_ROOT`.
  - it no longer hardcodes `/docker/chummercomplete/chummer-core-engine` and `/docker/chummercomplete/chummer.run-services` for the BuildProjectReferences=false baseline outputs.
  - this closes the shell/dialog chrome portability seam: the focused SR6 shell parity gate could previously only run against one absolute workspace layout even though the rest of the lane had already moved to alias-safe and workspace-relative root resolution.
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` now pins the alias-safe repo root, the explicit dependency-root overrides, and the removal of the hardcoded absolute dependency DLL paths.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/ai/milestones/desktop-shell-dialog-chrome-check.sh` -> pass
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` -> `5 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-shell-dialog-chrome-roots-20260710T0313.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T03:01:04+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/generate-releases-manifest.sh` now resolves hub local release-proof generator and proof candidates through workspace-relative hub roots instead of hardcoded `/docker/chummercomplete/chummer.run-services` and `/docker/chummercomplete/chummer6-hub` paths.
  - the embedded receipt-backed artifact restore now honors `CHUMMER_PORTAL_SUPPORT_SOURCE_ROOT` when explicitly set, then repo-local `Chummer.Portal/downloads/files`, `Docker/Downloads/files`, and `files`.
  - it no longer silently restores missing receipt-backed artifacts from sibling `chummer.run-services` portal shelves, legacy tooling downloads roots, or sibling `chummer-presentation` downloads roots.
  - this closes the manifest-regeneration shelf/proof seam: release manifest repair could previously pass while sourcing proof or artifact bytes from hardcoded or sibling worktrees outside the repo-local lane being verified.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the workspace-relative hub-proof roots, the explicit support-root override, and the removal of hardcoded/sibling restore roots in the maintained policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/generate-releases-manifest.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `84 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-release-manifest-portability-20260710T0310.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:54:02+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh` now resolves desktop files roots through `CHUMMER_PORTAL_SUPPORT_SOURCE_ROOT` when explicitly set, then repo-local `Chummer.Portal/downloads/files`, `Docker/Downloads/files`, and `files`.
  - it no longer silently falls back to sibling `chummer.run-services/Chummer.Portal/downloads/files` or the hardcoded `/docker/chummercomplete/chummer.run-services/...` portal shelf.
  - this closes the desktop executable exit-gate shelf seam: the gate could previously validate promoted desktop installers against bytes outside the repo-local lane being verified.
  - `tests/test_desktop_executable_exit_gate_contract.py` now pins the explicit override and repo-local files-root contract, and `tests/test_desktop_downloads_local_release_policy.py` now pins the same contract in the maintained policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh` -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `22 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `83 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-exit-gate-files-root-20260710T0254.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:48:11+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/materialize_windows_visual_proof_handoff.py` now uses exact stage-local files roots first, then `CHUMMER_PORTAL_SUPPORT_SOURCE_ROOT` when explicitly set, then repo-local `Chummer.Portal/downloads/files` and `Docker/Downloads/files`.
  - it no longer silently falls back to a sibling `chummer.run-services/Chummer.Portal/downloads/files` tree.
  - this closes the Windows visual-proof handoff files-root seam: the handoff packet could previously source installer/payload candidates from a sibling downloads shelf that was outside the repo-local lane being verified.
  - `tests/test_windows_visual_proof_handoff.py` now proves the repo-local portal default and the explicit support-root override, and `tests/test_desktop_downloads_local_release_policy.py` now pins the same contract in the maintained policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `tests/test_windows_visual_proof_handoff.py` -> `6 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `82 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-visual-handoff-files-root-eta-20260710T0249.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:43:43+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/desktop_install_update_recovery_matrix.py` no longer hardcodes sibling `chummer-hub-registry` and `chummer.run-services` evidence paths.
  - `scripts/desktop_hardware_wide_common.py` now resolves the canonical release channel through `scripts/resolve-hub-registry-root.sh` and resolves `HUB_LOCAL_RELEASE_PROOF.generated.json` through repo-local/workspace-relative paths or explicit `CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH`.
  - this closes the recovery-matrix evidence seam: desktop install/update/recovery scope could previously read release truth only from fixed sibling repo names instead of the repo’s shared resolver and override contracts.
- Origin-dialog lane release-posture claim hardening:
  - `scripts/final_desktop_hardware_wide_flagship_verdict.py` no longer emits `DESKTOP_WINDOWS_LINUX_GOLD_READY` unconditionally.
  - the verdict now downgrades to `DESKTOP_WINDOWS_LINUX_NOT_GOLD` when root release blockers or the top of this handoff report active `release_truth:*` blockers, and downgrades to `DESKTOP_WINDOWS_LINUX_RELEASE_TRUTH_UNVERIFIED` when both blocker inputs are missing.
  - this closes a direct claim-risk seam: the repo had a generator that could still produce a flagship/gold-ready verdict document despite the standing external blocker rule.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `tests/test_desktop_install_update_recovery_matrix.py tests/test_desktop_downloads_local_release_policy.py` -> `84 passed`
  - `tests/test_final_desktop_hardware_wide_flagship_verdict.py` -> `4 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-recovery-and-verdict-eta-20260710T0245.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:35:51+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/verify-release-channel-is-authoritative-or-fixture.py` now resolves the canonical registry root through `scripts/resolve-hub-registry-root.sh` before falling back to legacy sibling-name discovery.
  - this closes an authority-resolution drift seam: the release-channel authority verifier had its own hardcoded sibling lookup while the rest of the lane already depended on the shared registry-root resolver contract.
  - `tests/test_verify_release_channel_authority.py` now proves the verifier accepts a canonical manifest through a custom registry root returned by the shared resolver, and `tests/test_desktop_downloads_local_release_policy.py` now pins the shared-resolver dependency in the maintained release-policy lane.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `tests/test_desktop_downloads_local_release_policy.py` -> `80 passed`
  - `tests/test_verify_release_channel_authority.py tests/test_verified_release_channel_mirror.py` -> `14 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-authority-resolver-eta-20260710T0238.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:32:33+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/materialize-verified-release-channel-mirror.py` no longer silently pulls portal support files and startup-smoke receipts from a sibling `chummer.run-services` checkout.
  - repo-local `Chummer.Portal/downloads` is now the default support root, with `Docker/Downloads` as the local fallback; external source roots now require explicit `CHUMMER_PORTAL_SUPPORT_SOURCE_ROOT`.
  - this closes the hidden sibling-workspace seam in mirror regeneration: the release-channel mirror materializer could previously pass while sourcing support artifacts from another checkout that was not part of the repo under test.
  - `tests/test_verified_release_channel_mirror.py` now proves the repo-local default, the explicit external override, and the no-override failure path when only a sibling-style external source exists.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `python3 -m py_compile scripts/materialize-verified-release-channel-mirror.py` -> pass
  - `tests/test_verified_release_channel_mirror.py` -> `3 passed`
  - `tests/test_verify_release_channel_authority.py` -> `10 passed`
  - tracked current-lane focused slice, including dialog chrome contracts, live Windows payload verifier contracts, and external deploy readiness -> `175 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-mirror-portability-eta-20260710T0232.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:23:44+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless any configured `CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL` exactly matches `CHUMMER_CANONICAL_PORTAL_DOWNLOADS_S3_ENDPOINT_URL`.
  - this closes the custom object-storage endpoint seam: release mode could already bind the bucket/prefix and live public-edge verification to the canonical surface while still steering `aws --endpoint-url` toward a different S3/R2 account.
  - `scripts/verify-desktop-external-deploy-readiness.py` now rejects missing, malformed, or mismatched canonical endpoint pairs; `docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md` and `docs/examples/self-hosted-downloads.env.example` now expose the same release-mode endpoint authority contract.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new endpoint helper ordering and adds release-mode subprocess smoke for missing, malformed, and mismatched endpoint inputs; `tests/test_desktop_external_deploy_readiness.py` now fails readiness when the custom endpoint override does not match the canonical endpoint exactly.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/publish-download-bundle-s3.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - `tests/test_desktop_external_deploy_readiness.py` -> `17 passed`
  - tracked current-lane focused slice, including dialog chrome contracts, live Windows payload verifier contracts, and external deploy readiness -> `175 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-s3-endpoint-authority-eta-20260710T0224.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:16:05+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless both `CHUMMER_RELEASE_UPLOAD_URL` and `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL` share the same origin as the configured release public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}`.
  - this closes the HTTP upload control-plane shadow-host seam: release mode could already keep public route and manifest verification on the live public edge while still sending authenticated bundle upload/session traffic to a different host.
  - `scripts/verify-desktop-external-deploy-readiness.py` now rejects shadow HTTP upload/session origins against the inferred public surface, and `docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md` plus `docs/examples/self-hosted-downloads.env.example` now expose the same live-origin upload contract.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new upload/session origin helper ordering and adds direct release-mode subprocess smoke for mismatched upload/session hosts; `tests/test_desktop_external_deploy_readiness.py` now fails the readiness receipt when upload/session URLs drift off the public surface origin.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/publish-download-bundle-http.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - `tests/test_desktop_external_deploy_readiness.py` -> `15 passed`
  - tracked current-lane focused slice, including dialog chrome contracts, live Windows payload verifier contracts, and external deploy readiness -> `173 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T02:08:42+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PORTAL_DOWNLOADS_S3_URI` exactly matches `CHUMMER_CANONICAL_PORTAL_DOWNLOADS_S3_URI`, and any configured latest alias target exactly matches `CHUMMER_CANONICAL_PORTAL_DOWNLOADS_S3_LATEST_URI`.
  - this closes the object-storage shadow-bucket seam: release mode could already verify the live public edge while still copying bundle bytes into a different S3/R2 bucket or prefix, which left room for a shadow object-storage publish to pass against stale live-edge bytes.
  - `scripts/verify-desktop-external-deploy-readiness.py`, `docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md`, and `docs/examples/self-hosted-downloads.env.example` now expose the same canonical object-storage contract so external deploy readiness stops treating an unspecified shadow bucket as a complete release lane.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new canonical-target helper/ordering and adds release-mode subprocess smoke for missing, mismatched, and alias-drift S3 authority inputs; `tests/test_desktop_external_deploy_readiness.py` now requires the canonical target in object-storage readiness.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/publish-download-bundle-s3.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - `tests/test_desktop_external_deploy_readiness.py` -> `13 passed`
  - tracked current-lane focused slice, including dialog chrome contracts, live Windows payload verifier contracts, and external deploy readiness -> `171 passed`
- Telegram/update note:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-s3-authority-eta-20260710T0208.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:57:01+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PUBLIC_EDGE_VERIFY_BASE_URL` itself is an absolute loopback http(s) URL before the postdeploy open-public installer probe runs.
  - this closes the nightly postdeploy verifier seam: release mode already bound the public host/proto and live verify URL to the canonical public edge, but the internal probe target itself could still be redirected to an arbitrary external verifier host that returned forged redirect behavior.
  - the new guard keeps release-mode postdeploy route verification on a loopback-only verifier target and now fires before release-build handoff refresh or any stage-driven publish work.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new loopback helper/ordering and adds direct release-mode subprocess smoke for a shadow `CHUMMER_PUBLIC_EDGE_VERIFY_BASE_URL`.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/publish-latest-nightly-to-downloads.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `158 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:54:02+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/generate-releases-manifest.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless both `CHUMMER_EXTERNAL_PROOF_BASE_URL` and the effective `CHUMMER_PUBLIC_DOWNLOADS_PREFIX` share the same origin as the configured release public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}`.
  - this closes the manifest-generation shadow-host seam: multiple publish lanes already bound their verify targets to the live public edge, but they could still feed a shadow proof/download host into manifest generation and emit public links that drifted away from the canonical release origin.
  - release-mode preflight now rejects malformed proof/download base URLs before any manifest generation work, and same-origin validation rejects shadow proof/download hosts before file-driven generation begins.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new generator helper/ordering and adds direct release-mode subprocess smoke for malformed and mismatched `CHUMMER_EXTERNAL_PROOF_BASE_URL` / `CHUMMER_PUBLIC_DOWNLOADS_PREFIX` inputs.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/generate-releases-manifest.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `158 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:48:35+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PUBLIC_BASE_URL` itself shares the same origin as the configured release public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}` before route or manifest verification runs.
  - this closes the HTTP upload shadow-host seam: release mode already forced `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` and any explicit verify routes to stay on the same origin as `CHUMMER_PUBLIC_BASE_URL`, but the publisher could still be pointed at an arbitrary shadow public base and treat that surface as release evidence.
  - the new guard adds explicit public-edge host/proto validation plus same-origin binding for `CHUMMER_PUBLIC_BASE_URL`, and it now fires before bundle-layout, token-resolution, or network work.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new public-edge helper/ordering and adds direct release-mode subprocess smoke for a mismatched `CHUMMER_PUBLIC_BASE_URL` host while preserving the separate `VERIFY_URL`-vs-`PUBLIC_BASE_URL` mismatch proof.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `bash -n scripts/publish-download-bundle-http.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `158 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:43:14+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/verify-live-windows-bootstrap-payloads.py` now fails closed in `CHUMMER_VERIFY_MODE=release` unless the direct `--manifest-url`, the manifest row installer `downloadUrl`, and the manifest row `payloadDownloadUrl` all share the same origin as the configured release public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}`.
  - this closes the standalone live-payload verifier seam left below the publish wrappers: release mode already bound the wrapper verify URL and manifest verifier to the live public edge, but the direct verifier could still be run against an arbitrary host or follow payload bytes on a different origin.
  - release-mode preflight now rejects non-http/relative manifest inputs before any fetch, and row validation rejects installer/payload origin drift before downloading the live ZIP bytes.
  - `tests/test_live_windows_bootstrap_payloads.py` now covers release-mode manifest-origin mismatch and payload-origin drift, and `tests/test_desktop_downloads_local_release_policy.py` now pins the direct verifier helper/ordering plus release-mode subprocess smoke for a mismatched manifest host.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - `tests/test_live_windows_bootstrap_payloads.py` -> `7 passed`
  - `tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `158 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:34:39+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/verify-releases-manifest.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless a direct URL target shares the same origin as the configured release public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}`.
  - this closes the standalone verifier seam: the publish wrappers already bound their live verify URLs to the expected public edge, but the direct verifier itself could still be pointed at an arbitrary public host and report that as release evidence.
  - the new guard reuses the shared host/proto and same-origin validation model, and it now fires before registry verifier lookup so release-mode verifier entry fails at the authority boundary first.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the direct verifier origin helper/ordering and adds direct release-mode subprocess smoke for a mismatched verify URL host.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - manifest verifier syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:31:08+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` shares the same origin as the configured object-storage public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}`.
  - this closes the object-storage split-target seam: release mode already required an S3 target and an absolute verify URL, but the verify URL could still point at a different public host than the configured public edge.
  - the new guard reuses the shared host/proto and same-origin validation model, and it now fires before bundle layout or existence checks so object-storage release preflight fails at the authority boundary first.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the object-storage verify-origin helper/ordering and adds direct release-mode subprocess smoke for a mismatched object-storage verify host.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - object-storage publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:26:36+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` shares the same origin as the configured bundle public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}`.
  - this closes the direct bundle split-target seam left below the nightly wrapper: release mode already required a release-truth-aligned deploy root and a live verify URL, but the verify URL could still point at a different public host.
  - the new guard reuses the same host/proto and same-origin validation model as the nightly wrapper, and it runs before bundle existence checks or deeper manifest/materialization work.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the bundle verify-origin helper/ordering and adds direct release-mode subprocess smoke for a mismatched bundle verify host.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:21:54+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` shares the same origin as the configured nightly public-edge origin `${CHUMMER_PUBLIC_EDGE_VERIFY_PROTO}://${CHUMMER_PUBLIC_EDGE_VERIFY_HOST}` when the nightly lane is targeting the live public-edge downloads shelf.
  - this closes the nightly wrapper split-target seam left above the bundle publisher: release mode already forced the live downloads shelf and required a verify URL, but the verify URL could still point at a different public host than the configured public edge.
  - the new guard reuses the shared same-origin helper, runs before stage scanning, and keeps the nightly wrapper aligned with the stricter HTTP upload lane beneath it.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the nightly verify-origin helper/ordering and adds direct release-mode subprocess smoke for a mismatched nightly verify host.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - nightly publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:17:09+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` when an upload session returns `filesUrl`, `chunksUrl`, or `completeUrl` on a different origin than `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL`.
  - this closes the post-session redirect seam inside the HTTP upload lane: preflight could already lock local config and custom route verification to the intended authority, but the server response could still redirect file, chunk, or completion uploads to some other host.
  - the new guard runs immediately after `join_url(...)` normalizes the session response URLs and before any direct file upload, chunk upload, or session-complete call.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the response-URL same-origin helper/ordering against the real upload call sites and completion call.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - HTTP upload publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:13:25+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` when any explicit `CHUMMER_RELEASE_UPLOAD_VERIFY_URLS` entry resolves to a different origin than `CHUMMER_PUBLIC_BASE_URL`.
  - this closes the remaining custom-route split-target seam inside the HTTP upload lane: release mode could already pin the manifest verify URL to the public base, but an override list could still point route verification at some other host.
  - the custom-route same-origin guard reuses the shared URL-origin helper, fires before bundle existence checks or dry-run branching, and complements the existing absolute-URL validation for every explicit route entry.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the custom-route same-origin helper/ordering and adds direct release-mode subprocess smoke for a mismatched explicit route origin.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - HTTP upload publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T01:09:35+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` shares the same origin as `CHUMMER_PUBLIC_BASE_URL` whenever route verification is enabled.
  - this closes the HTTP upload split-target seam: release mode could verify manifest bytes against one host while route verification still targeted a different public base.
  - the absolute-URL and same-origin guards now fire before bundle existence checks or deeper upload work, and `tests/test_desktop_downloads_local_release_policy.py` was updated so its subprocess smoke reaches the new origin guard instead of stopping at token preflight.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the same-origin helper/ordering and direct release-mode subprocess smoke for mismatched verify/public-base origins.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - HTTP upload publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
  - ETA/status was sent to Telegram through `chummer.run-services/scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-http-upload-eta-20260710T0109.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:57:46+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless `DEPLOY_DIR` resolves to one of the known release-truth-aligned downloads shelves before live external verification is allowed to proceed.
  - this closes the bundle-level split-target seam left below the nightly wrapper: release mode already required deploy intent plus `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL`, but could still target an arbitrary shadow shelf where no recognized public-edge mirror sync would occur.
  - the guard reuses the same alias-safe path normalization as the live-downloads root discovery logic, and `deploy_dir_is_live_downloads_root()` now defers to that single release-truth-aligned root helper to avoid drift.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new bundle target guard ordering and adds direct release-mode subprocess smoke proving a non-live, non-recognized bundle deploy target fails before bundle existence checks or deeper mutation.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:52:48+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` unless the nightly publish target itself resolves to the live `chummer.run-services/Chummer.Portal/downloads` shelf.
  - this closes the remaining split-target nightly seam: release mode already required external publish intent plus a live verify URL, but could still write a refreshed nightly manifest into some other shelf while verification kept reading the live public edge.
  - the guard is alias-safe, reuses the same normalized deploy/live-shelf comparison used by the redeploy path, and fires before publish-window or stage-discovery work.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new target-match guard ordering and adds direct release-mode subprocess smoke proving a non-live `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR` fails before stage discovery.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - nightly publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:42:45+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now resolves the deploy target path and, in `CHUMMER_VERIFY_MODE=release`, requires `CHUMMER_REDEPLOY_PUBLIC_EDGE_AFTER_NIGHTLY_PUBLISH=true` whenever the nightly lane is publishing directly into the live `chummer.run-services/Chummer.Portal/downloads` shelf.
  - this closes a stronger nightly publication posture gap: release mode already required external publish intent and a live verify URL, but could still skip the public-edge reload and therefore leave served bytes stale while verification kept reading the old public edge.
  - the redeploy-path guard is alias-safe and reuses the same normalized live-shelf comparison for both the preflight config check and the post-publish redeploy branch.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new live-shelf redeploy guard ordering and adds direct release-mode subprocess smoke proving `CHUMMER_REDEPLOY_PUBLIC_EDGE_AFTER_NIGHTLY_PUBLISH=false` fails before stage discovery.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - nightly publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:39:29+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now requires `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_ENABLED=true` in `CHUMMER_VERIFY_MODE=release`, instead of only requiring the variable to parse as some boolean.
  - this closes a stronger bundle-publication posture gap: release mode already required external publish intent and a live verify URL, but could still proceed as a local-shelf update when deploy mode was explicitly false, leaving room for stale-edge verification against unchanged public bytes.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the stronger bundle-publisher guard ordering and adds direct release-mode subprocess smoke proving `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_ENABLED=false` fails before any deeper bundle checks.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:34:14+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/generate-releases-manifest.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER` is explicitly set to a malformed value and when `CHUMMER_SKIP_STARTUP_SMOKE_HYDRATION` is anything other than boolean false.
  - this removes a remaining generator seam where malformed values such as `maybe` were previously accepted, then later coerced by `to_bool(...)` into a false posture while the release lane still proceeded.
  - release mode still permits an empty `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER` so the generator can derive its default false value, but an explicit override must now be boolean false.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new guard ordering and adds direct release-mode subprocess smoke for malformed startup-smoke filter and startup-smoke hydration overrides.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - generator syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:28:02+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/ai/milestones/materialize-desktop-workflow-execution-gate.sh` now canonicalizes `CHUMMER_DESKTOP_WORKFLOW_SKIP_FLAGSHIP_DEPENDENCY_REFRESH` and `CHUMMER_DESKTOP_WORKFLOW_REFRESH_DEPENDENCY_RECEIPTS` truthy/falsy aliases at the shell boundary instead of only treating literal `1` as enabled.
  - in `CHUMMER_VERIFY_MODE=release`, the workflow gate now requires `CHUMMER_DESKTOP_WORKFLOW_SKIP_FLAGSHIP_DEPENDENCY_REFRESH` to be explicit boolean false and requires `CHUMMER_DESKTOP_WORKFLOW_REFRESH_DEPENDENCY_RECEIPTS` to be boolean true when overridden, so malformed values such as `maybe` or an explicit `0` can no longer weaken dependency refresh posture during release-mode runs.
  - this also removes a shell/receipt truth mismatch where `true/yes/on` could skip the shell-side refresh while the downstream Python evidence still reported dependency refresh as enabled.
  - `tests/test_desktop_executable_exit_gate_contract.py` now pins the canonicalization/guard strings and adds direct release-mode subprocess smoke for malformed skip values plus malformed and explicit-false dependency refresh overrides.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - workflow gate syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `21 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `155 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:19:30+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/ai/milestones/next90-m141-ui-direct-import-route-proof-check.sh` and `scripts/ai/milestones/chummer5a-screenshot-review-gate.sh` now require their flagship-dependency skip flags to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`, instead of only forbidding literal `=1` while the downstream Python logic still treated `true/yes/on` as enabled.
  - broader truthy values can no longer silently skip flagship-gate dependencies inside the M141 direct-import proof lane or the screenshot-review gate during release-mode runs.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the stronger guard strings and adds direct release-mode subprocess smoke for truthy and malformed flagship-dependency skip values at both script entrypoints.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - milestone script syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `78 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `154 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:14:47+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh` and `scripts/materialize-linux-desktop-exit-gate.sh` now require `CHUMMER_LINUX_DESKTOP_EXIT_GATE_SKIP_DESIGN_SUPERVISOR_REFRESH` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`, instead of only forbidding literal `=1` while silently accepting malformed values such as `maybe`.
  - malformed values now fail closed at both the desktop-executable wrapper and the underlying Linux desktop exit gate before any deeper gate work, rather than drifting into the release lane as an implicit false posture.
  - `tests/test_desktop_executable_exit_gate_contract.py` now pins the new guard strings and adds direct release-mode subprocess smoke proving malformed `CHUMMER_LINUX_DESKTOP_EXIT_GATE_SKIP_DESIGN_SUPERVISOR_REFRESH` values fail early at both entrypoints.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - desktop executable/linux gate syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `20 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `153 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:10:18+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/generate-releases-manifest.sh` now enforces direct release-mode boolean parity for generator-owned release guards instead of relying only on nightly or bundle entrypoints to pre-validate them.
  - release mode now requires `CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE` to be explicit boolean true, requires `CHUMMER_GENERATE_EXTERNAL_HOST_PROOF_BLOCKERS` to be explicit boolean true, and requires `CHUMMER_PROMOTE_PROOF_BACKED_QUARANTINED_INSTALLERS` to be explicit boolean false at the generator boundary.
  - malformed values such as `maybe` can no longer drift into generator-local `!= "0"` or `to_bool(...)` branches that would otherwise treat quarantined-installer promotion as enabled or external-host blocker generation as disabled during a direct release-mode manifest build.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new generator guard ordering and adds direct release-mode smoke for malformed complete-desktop-coverage values, truthy/malformed quarantined-installer promotion values, and malformed external-host-blocker generation values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - generator syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `77 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `152 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-10T00:05:23+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/resolve-desktop-release-context.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE` is truthy or malformed, instead of silently treating malformed values such as `maybe` as false while still resolving a public release channel and signing posture.
  - `scripts/sign-windows-artifacts.ps1` now enforces the same release-mode unsigned-public-release guard directly, and `scripts/build-desktop-installer.sh` now forwards `CHUMMER_VERIFY_MODE` into the PowerShell signer so the shared Windows signing lane preserves the bash-side release posture instead of relying only on the installer wrapper.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the builder forwarding contract, the release-context helper guard ordering, the PowerShell signer guard contract, and direct release-mode smoke for truthy and malformed unsigned-public-release overrides at the shared helper boundary.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - helper/builder syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `77 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `152 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:55:24+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/build-desktop-installer.sh` now requires both `CHUMMER_ALLOW_LOCAL_RELEASE_VERSION` and `CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`, instead of only forbidding explicit truthy overrides while silently accepting malformed values such as `maybe`.
  - malformed values now fail closed before placeholder-version acceptance, unsigned-public-release allowance, or any later packaging step can quietly interpret those release-mode escape hatches as false.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new fail-early ordering for both installer-builder false-required flags and adds direct release-mode smoke for malformed `CHUMMER_ALLOW_LOCAL_RELEASE_VERSION` and malformed `CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE` values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - desktop installer builder syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:51:58+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now requires both `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK` and `CHUMMER_RELEASE_UPLOAD_DRY_RUN` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`, instead of only forbidding explicit truthy values while silently accepting malformed strings such as `maybe`.
  - malformed values now fail closed before local bundle layout checks, URL validation, token resolution, or any later HTTP publication branch can quietly treat those release-mode escape hatches as false.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the new fail-early ordering for both HTTP false-required flags and adds direct release-mode smoke for malformed `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK` and malformed `CHUMMER_RELEASE_UPLOAD_DRY_RUN` values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - HTTP publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:46:26+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/verify-releases-manifest.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_VERIFY_SKIP_STARTUP_SMOKE_FILTER` is malformed and when `CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE` is not explicit boolean true.
  - `scripts/publish-download-bundle-s3.sh` and `scripts/publish-download-bundle-http.sh` now also require `CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE` to be explicit boolean true in release mode, instead of only forbidding explicit false values while letting malformed inputs drift deeper into object-storage or HTTP publication flows.
  - malformed values such as `maybe` now fail closed before local bundle layout checks, URL validation, network work, or downstream registry verification, keeping direct verification lanes aligned with the stricter nightly/bundle publish lane posture.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the direct verifier fail-early ordering plus direct release-mode smoke for malformed verify skip-filter and complete-coverage values, and adds matching malformed-complete-coverage release-mode smoke for both object-storage and HTTP publication entrypoints.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - verifier/object-storage/http syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:38:49+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh`, `scripts/publish-download-bundle.sh`, and `scripts/generate-releases-manifest.sh` now validate `CHUMMER_RELEASE_REQUIRE_STARTUP_SMOKE_PROOF` directly in `CHUMMER_VERIFY_MODE=release`.
  - release mode now forbids `CHUMMER_RELEASE_REQUIRE_STARTUP_SMOKE_PROOF=0` and requires malformed values such as `maybe` to fail closed before nightly stage scanning, bundle scanning, or manifest generation, instead of silently disabling installer startup-smoke proof enforcement or relying on non-boolean shell truthiness.
  - the nightly publisher now forwards `CHUMMER_RELEASE_REQUIRE_STARTUP_SMOKE_PROOF` into the bundle publisher, and the bundle publisher forwards it explicitly into `generate-releases-manifest.sh`, so the validated release-mode value survives the full publish chain.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the nightly fail-early ordering, the bundle fail-early ordering, the env forwarding contracts, and direct release-mode smoke for both disabled and malformed startup-smoke-proof values across nightly, bundle, and generator entrypoints.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - nightly/bundle/generator syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:31:11+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now validates `CHUMMER_PROMOTE_PROOF_BACKED_QUARANTINED_INSTALLERS` directly in `CHUMMER_VERIFY_MODE=release`.
  - release mode now forbids `CHUMMER_PROMOTE_PROOF_BACKED_QUARANTINED_INSTALLERS=1` and requires malformed values such as `maybe` to fail closed before bundle scanning begins, instead of silently flowing into the downstream manifest generator where any non-`0` value acts enabled.
  - the bundle publisher now forwards `CHUMMER_PROMOTE_PROOF_BACKED_QUARANTINED_INSTALLERS` explicitly into `generate-releases-manifest.sh`, so release-mode false stays false instead of falling back to the generator's promotion-enabled default.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the bundle fail-early ordering, the downstream env forwarding contract, and direct release-mode smoke for both truthy and malformed quarantined-installer promotion values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:22:33+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now validates `CHUMMER_PROMOTE_PROOF_BACKED_QUARANTINED_INSTALLERS` directly in `CHUMMER_VERIFY_MODE=release`.
  - release mode now forbids `CHUMMER_PROMOTE_PROOF_BACKED_QUARANTINED_INSTALLERS=1` and requires malformed values such as `maybe` to fail closed before nightly stage scanning begins, instead of silently flowing into the downstream manifest generator where any non-`0` value acts enabled.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the nightly fail-early ordering plus direct release-mode smoke for both truthy and malformed quarantined-installer promotion values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:19:25+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now validates `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER` directly in `CHUMMER_VERIFY_MODE=release` instead of deferring that failure to the downstream bundle publisher.
  - release mode now forbids `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER=true` and requires malformed values such as `maybe` to fail closed before nightly stage scanning begins.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the nightly fail-early ordering plus direct release-mode smoke for both truthy and malformed startup-smoke-filter values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:14:42+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now requires `CHUMMER_ALLOW_STABLE_CHANNEL_FROM_NIGHTLY_PUBLISH` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`.
  - malformed values such as `maybe` now fail closed before nightly stage scanning or channel normalization can silently fall through into the preview-handoff logic.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the fail-early ordering plus direct release-mode smoke for malformed stable-channel override values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:12:10+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now requires `CHUMMER_SKIP_STARTUP_SMOKE_HYDRATION` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`.
  - `scripts/publish-download-bundle.sh` now requires `CHUMMER_ALLOW_BUNDLE_FILES_SOURCE_FALLBACK` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`.
  - malformed values such as `maybe` now fail closed before nightly stage scanning, bundle scanning, or any later skip/fallback branch can silently treat those escape hatches as disabled.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the fail-early ordering plus direct release-mode smoke for malformed startup-smoke-hydration and bundle-files-fallback values.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:09:07+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` and `scripts/publish-download-bundle.sh` now require `CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE` to be explicit boolean true in `CHUMMER_VERIFY_MODE=release`.
  - malformed values such as `maybe` now fail closed before nightly stage scanning, bundle scanning, or any later publish path can silently treat coverage as enabled.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the fail-early ordering plus direct release-mode smoke for malformed complete-desktop-coverage allowance in both publishers.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T23:03:45+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` and `scripts/publish-download-bundle.sh` now require `CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH` to be explicit boolean false in `CHUMMER_VERIFY_MODE=release`.
  - malformed values such as `maybe` now fail closed before nightly stage scanning, bundle scanning, or any later Windows visual-proof handoff branch can silently treat them as false.
  - `tests/test_desktop_downloads_local_release_policy.py` now pins the fail-early ordering plus direct release-mode smoke for malformed visual-proof-handoff allowance in both publishers.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - bundle publisher syntax -> pass
  - touched-file whitespace check -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog chrome contracts and live Windows payload verifier contracts -> `151 passed`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T22:55:41+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now requires an unmodified primary-button backdrop click through `IsPrimaryBackdropDismissClick(...)` before dismissing the dialog.
  - right-click and modifier-assisted primary clicks such as `Ctrl+click` no longer dismiss the dialog, while plain left-click backdrop close still works.
  - BUnit now pins the full backdrop behavior: inner click no-op, secondary-button backdrop no-op, `Ctrl+click` backdrop no-op, plain primary backdrop close; the fast source contract pins the modifier guard.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for unmodified-primary backdrop close behavior and existing dialog event tests -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; this slice saw long but successful Blazor and focused `Chummer.Tests` builds with no warnings.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T22:46:06+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now closes only on primary-button backdrop clicks through `HandleDialogBackdropClickAsync(...)`.
  - secondary-button backdrop clicks no longer dismiss the dialog, and clicks inside `.desktop-dialog` still do not propagate to the backdrop close path.
  - BUnit now pins the three-way behavior: inner click no-op, right-click backdrop no-op, left-click backdrop close; the fast source contract pins the backdrop handler and `args.Button == 0` guard.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for primary-backdrop close behavior and existing dialog event tests -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; this slice saw long but successful package-plane and focused test builds with no warnings.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T22:25:41+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now accepts both `Escape` and legacy `Esc` as close keys through `IsDialogCloseKey(...)`, while still ignoring repeated keydown events.
  - this keeps close-key behavior aligned across browser/event-source differences without reopening the repeated-close bug.
  - BUnit now pins the repeated `Escape` no-op path plus the legacy `Esc` alias close path; the fast source contract pins the `IsDialogCloseKey(...)` helper and both key literals.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for `Escape` repeat suppression and `Esc` alias close -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; this slice saw shared package-plane and sibling `Chummer.Tests` contention, but the focused builds completed without warnings.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T22:05:17+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now ignores repeated Escape keydown events, so holding Escape does not emit a stream of close intents.
  - normal Escape still invokes the dialog close callback once.
  - BUnit now pins repeated Escape as a no-op followed by one normal Escape close; the fast source contract pins the `!args.Repeat` guard.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for repeated Escape and existing dialog event tests -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; this slice saw concurrent .NET compiler load, so focused `Chummer.Tests` build was slow but completed.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T21:54:04+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now collapses whitespace runs in dialog titles before deriving the close button `title` and `aria-label`, so tab/newline-heavy titles produce a clean accessible name.
  - whitespace-only dialog titles still fall back to `Close dialog`.
  - BUnit now pins the collapsed-title path with `Save\tCharacter\nNow`, plus the blank-title fallback; the fast source contract pins the normalization helper and whitespace-collapse loop.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for the close-label whitespace normalization and existing dialog event tests -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; this slice saw concurrent .NET compiler load, so focused Blazor build was slow but completed.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T21:38:00+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now trims the active dialog title before deriving the close button `title` and `aria-label`.
  - whitespace-only dialog titles still fall back to the generic `Close dialog` accessible name instead of producing an empty or padded label.
  - BUnit now pins both the padded-title normalization path and the blank-title fallback; the fast source contract pins the trim seam in `BuildDialogCloseLabel(...)`.
- Current lane-local receipt note:
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` currently reports `status=pass`, generated `2026-07-09T15:13:50.947487Z`; older stale-receipt warnings below are no longer current evidence.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for the close-label normalization and existing dialog event tests -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; this slice saw concurrent .NET compiler load, so focused builds were slow but completed.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T21:17:48+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `DialogHost.razor` now derives the close button `title` and `aria-label` from the active dialog title through `BuildDialogCloseLabel(...)`, with the generic `Close dialog` fallback preserved for blank titles.
  - executable BUnit assertions now use the normalized per-dialog title IDs emitted by the shared accessibility helpers, including `dialog-title-dialog.new_character.origin_build` and `dialog-title-save-dialog`.
  - the source contract pins the close-label helper, the close-button bindings, per-dialog title/body IDs, and the Escape-to-close wiring.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - touched-file whitespace check -> pass
  - Blazor head build -> pass
  - focused `Chummer.Tests` compile -> pass
  - direct MSTest filter for the two affected BUnit tests -> `2 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Operator status:
  - ETA/status was sent to Telegram through `chummer.run-services/scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-dialog-close-eta-20260709T2116.receipt.json`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T21:06:48+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `AccessibilityPrimitiveBoundary.BuildDialogTitleId(...)` and `BuildDialogDescriptionId(...)` now normalize dialog ID segments before rendering aria target IDs.
  - whitespace becomes `-`, safe ID characters are preserved, punctuation such as `#` is dropped, and blank/whitespace-only IDs still fall back to the stable base title/description IDs.
  - `DialogHost.razor` continues to bind `aria-labelledby` and `aria-describedby` through the shared helpers, so the dialog target IDs remain paired after normalization.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - Blazor head build -> pass
  - `MigrationComplianceTests.Accessibility_boundary_falls_back_when_ui_kit_payload_omits_expected_attributes` -> `1 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `151 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T21:00:42+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now rejects malformed `CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE` values in `CHUMMER_VERIFY_MODE=release` before nightly stage scanning, publish-window evaluation, bundle publication, or public-edge route verification.
  - release-mode nightly publication now accepts only explicit false for skipped-startup-smoke allowance; true and malformed values both fail closed.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the fail-early ordering and direct release-mode smoke for malformed skipped-startup-smoke allowance.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `151 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:58:30+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now rejects malformed `CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE` values in `CHUMMER_VERIFY_MODE=release` before bundle inspection, handoff materialization, manifest generation, local publication, or external verification.
  - release-mode bundle publication now accepts only explicit false for skipped-startup-smoke allowance; true and malformed values both fail closed.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the fail-early ordering and direct release-mode smoke for malformed skipped-startup-smoke allowance.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `151 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:56:43+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now rejects malformed `CHUMMER_PORTAL_DOWNLOADS_DEPLOY_ENABLED` values in `CHUMMER_VERIFY_MODE=release` before bundle inspection, handoff materialization, manifest generation, deploy-mode branching, local publication, or external verification.
  - explicit true/false deploy mode values remain accepted; malformed values no longer fall through as false.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the fail-early ordering and direct release-mode smoke for malformed deploy-mode input.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `151 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:54:58+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now rejects `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER=true` and malformed values in `CHUMMER_VERIFY_MODE=release` before bundle inspection, handoff materialization, manifest generation, local publication, or external verification.
  - empty release-mode skip-filter input still defaults to false; explicit false is accepted.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the fail-early ordering plus direct release-mode smokes for true and malformed startup-smoke skip-filter values.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `76 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `151 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:52:51+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now rejects malformed `CHUMMER_GENERATE_EXTERNAL_HOST_PROOF_BLOCKERS` values in `CHUMMER_VERIFY_MODE=release` before bundle inspection, handoff materialization, manifest generation, local publication, or external verification.
  - release-mode bundle publication now requires blocker-proof generation to be explicitly true, not merely non-false or malformed.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the fail-early ordering and direct release-mode smoke for malformed blocker-proof values.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:51:10+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now rejects invalid `CHUMMER_FORCE_NIGHTLY_PUBLISH` values in `CHUMMER_VERIFY_MODE=release` before nightly stage scanning, publish-window evaluation, bundle publication, or public-edge route verification.
  - this prevents a typo such as `maybe` from being treated as false by the publish guard and silently changing release-mode behavior.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the source ordering and direct release-mode smoke for the invalid force-publish boolean path.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:48:56+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now rejects invalid `CHUMMER_REDEPLOY_PUBLIC_EDGE_AFTER_NIGHTLY_PUBLISH` values in `CHUMMER_VERIFY_MODE=release` before nightly stage scanning, publish guards, bundle publication, or public-edge route verification.
  - this prevents a typo such as `maybe` from being treated as false and silently skipping the public-edge redeploy/probe path.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the source ordering and direct release-mode smoke for the invalid boolean path.
- Focused verification:
  - latest-nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:46:31+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now requires release-mode object-storage targets to be `s3://bucket/path`, not bucket-only `s3://bucket` values, before bundle layout, payload checks, manifest regeneration, object-storage sync, or network verification.
  - the stricter shape is enforced both in the fail-early release-mode precheck and the shared `validate_s3_uri` helper.
  - `tests/test_desktop_downloads_local_release_policy.py` pins direct pre-bundle smokes for bucket-only target and latest-alias S3 URIs.
- Focused verification:
  - S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:44:41+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_RELEASE_UPLOAD_TOKEN_FILE` token lines containing whitespace in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload checks, token prompts, curl auth config generation, upload-session work, or network verification.
  - token-file line endings are still tolerated; whitespace inside or around the token itself is not.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smoke for spaced token-file values.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:41:19+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_RELEASE_UPLOAD_TOKEN` values containing any whitespace in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload checks, token prompts, curl auth config generation, upload-session work, or network verification.
  - blank env tokens remain rejected by the existing "must contain a token" guard; this new guard catches surrounding or embedded whitespace that would otherwise be written into the bearer header.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smoke for env tokens with whitespace.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:39:01+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects whitespace-only `CHUMMER_RELEASE_UPLOAD_TOKEN` values in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload checks, token prompts, upload-session work, curl auth config generation, or network verification.
  - this closes the env-token counterpart to the existing missing-token, missing-token-file, and empty-token-file fail-early guards.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smoke for the blank env-token path.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog accessibility and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:36:55+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane verification-only refresh:
  - the new `AccessibilityPrimitiveBoundary.BuildDialogTitleId(...)` C# assertions in `Chummer.Tests/Compliance/MigrationComplianceTests.cs` are now directly executed, not only compiled or covered by Python source-contract checks.
  - a full package-plane test build initially waited behind another active Chummer test build, so this refresh used a no-dependencies `Chummer.Tests` build against existing references plus a direct MSTest filter for the targeted method.
- Focused verification:
  - no-dependencies `Chummer.Tests` build -> pass
  - `MigrationComplianceTests.Accessibility_boundary_falls_back_when_ui_kit_payload_omits_expected_attributes` -> `1 passed`
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `150 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:18:08+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `Chummer.Presentation/UiKit/ShellChromeBoundary.cs` now exposes `AccessibilityPrimitiveBoundary.BuildDialogTitleId(...)` alongside the existing per-dialog description ID helper.
  - `Chummer.Blazor/Components/Shell/DialogHost.razor` now uses per-dialog title IDs for `aria-labelledby` and the title span, matching the existing per-dialog `aria-describedby` linkage.
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` and `Chummer.Tests/Compliance/MigrationComplianceTests.cs` pin the helper, fallback IDs, dialog-specific IDs, and markup ordering.
- Focused verification:
  - dialog chrome contract -> `5 passed`
  - Blazor head build -> pass
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `150 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:11:02+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now validates release-mode HTTP route-verification inputs before bundle layout, payload checks, token checks, upload-session work, or network verification.
  - `CHUMMER_PUBLIC_BASE_URL` must be an absolute `http(s)` URL when route verification is enabled, and every custom `CHUMMER_RELEASE_UPLOAD_VERIFY_URLS` entry must also be an absolute `http(s)` URL.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smokes for malformed public base URL and malformed custom route entries.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:08:48+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects malformed `CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES` and `CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES` values in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload checks, token checks, upload-session work, arithmetic comparisons, `split -b`, or network verification.
  - both values must be positive integers for release-mode HTTP publication.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smokes for malformed chunk size and direct-limit values.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:07:04+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_VERIFY_MODE=release` when neither `CHUMMER_RELEASE_UPLOAD_TOKEN` nor a valid `CHUMMER_RELEASE_UPLOAD_TOKEN_FILE` is present before bundle layout, payload checks, manifest validation, token prompts, upload-session work, or network verification.
  - release mode also rejects missing and empty token files before bundle inspection, keeping credential readiness fail-closed and side-effect-free.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smokes for missing token, missing token file, and empty token file paths.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:04:51+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects malformed `CHUMMER_RELEASE_UPLOAD_URL`, `CHUMMER_RELEASE_UPLOAD_SESSIONS_URL`, and `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` values in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload checks, manifest validation, token prompts, upload-session work, or network verification.
  - this brings HTTP publish URL preflight timing in line with the S3 fail-early preflight posture.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smokes for all three malformed URL paths.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:02:39+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now rejects malformed optional `CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI` and `CHUMMER_PORTAL_DOWNLOADS_S3_ENDPOINT_URL` values in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload, manifest regeneration, AWS, or live-verifier work.
  - required target/verify URL preflight remains unchanged; optional latest-alias and endpoint configuration can no longer fail only after bundle/tooling checks.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smokes for both malformed optional values.
- Focused verification:
  - S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T20:00:28+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now rejects malformed `CHUMMER_PORTAL_DOWNLOADS_S3_URI` in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload, manifest regeneration, AWS, or live-verifier work.
  - this completes the adjacent early S3 publish-target preflight next to the existing missing S3 target, missing verify URL, and malformed verify URL guards.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smoke so a malformed S3 target fails with exit `2` before any bundle inspection.
- Focused verification:
  - S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:57:01+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle-s3.sh` now preflights `CHUMMER_PORTAL_DOWNLOADS_S3_URI` and `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` in `CHUMMER_VERIFY_MODE=release` before bundle layout, payload, manifest regeneration, AWS, or live-verifier work.
  - malformed release verify URLs now fail with exit `2` before any bundle inspection.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the ordering and direct pre-bundle smokes for missing S3 target, missing verify URL, and malformed verify URL.
- Focused verification:
  - S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:54:35+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/generate-releases-manifest.sh` and `scripts/publish-download-bundle.sh` now default blank `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER` to `false` in `CHUMMER_VERIFY_MODE=release`.
  - preview/slice lanes still keep the existing preview auto-skip default, but release mode can no longer pass the early explicit-skip guard and then re-enable `--skip-startup-smoke-filter` later through the preview fallback.
  - `tests/test_desktop_downloads_local_release_policy.py` pins both defaulting blocks and their release-before-preview ordering.
- Focused verification:
  - manifest/bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:52:25+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI shell parity polish:
  - `Chummer.Blazor/Components/App.razor` now gives the SSR fallback `.desktop-dialog` a stable `data-dialog-id` derived from `workbenchFallback.ActiveWorkflow`.
  - this mirrors the interactive dialog host’s stable identity marker without extending the fallback dialog model.
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` pins the fallback dialog identity marker and ordering before the origin-wizard marker.
- Focused verification:
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` -> `4 passed`
  - Blazor head build -> pass
  - tracked current-lane focused slice, including release-script portability and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:49:00+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now fails closed in `CHUMMER_VERIFY_MODE=release` if release build handoff materialization is missing or fails for a bundle/shelf that has `RELEASE_CHANNEL.generated.json`.
  - scaffold/slice lanes still print the existing skip messages for early local work, but release mode can no longer treat a missing or failed handoff refresh as publish evidence.
  - `tests/test_desktop_downloads_local_release_policy.py` pins both missing-materializer and failed-materializer branches plus the bundle/deploy handoff refresh ordering.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `75 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `149 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:45:30+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-script portability hardening:
  - `scripts/publish-download-bundle.sh` now rejects `CHUMMER_VERIFY_MODE=release` when the bundle has no Windows installer candidates before passing `--allow-empty` to `verify-windows-installer-payloads.py`.
  - scaffold/slice lanes keep the empty-Windows tolerance for early local bundle work; release mode now matches the stricter nightly/HTTP/S3 publish lanes.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the guard ordering and runs a direct temp-bundle smoke proving no deploy shelf is written before the failure.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `74 passed`
  - tracked current-lane focused slice, including dialog and live Windows payload verifier contracts -> `148 passed`
  - touched-file whitespace check -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:39:22+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI accessibility polish:
  - `Chummer.Blazor/Components/App.razor` now gives the SSR fallback `.desktop-dialog` modal semantics matching the interactive shell path: `aria-modal`, `aria-labelledby`, `aria-describedby`, and focusable `tabindex="-1"`.
  - the fallback dialog title/body now have stable `fallbackDialogTitle` and `fallbackDialogBody` IDs instead of relying on only `aria-label`.
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` pins the fallback modal/title/body linkage.
- Focused verification:
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` -> `4 passed`
  - Blazor head build -> pass
  - tracked current-lane focused slice -> `147 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:36:24+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release manifest verifier target hardening:
  - `scripts/verify-releases-manifest.sh` now rejects `CHUMMER_VERIFY_MODE=release` when the verify target is neither an existing local manifest/shelf path nor an absolute `http(s)` URL.
  - this prevents ambiguous missing relative targets from being forwarded to the registry verifier as release evidence.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the guard and a direct release-mode smoke.
- Focused verification:
  - release manifest verifier syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice, including live Windows payload verifier contracts -> `146 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:34:31+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP/S3 live payload verifier availability hardening:
  - `scripts/publish-download-bundle-http.sh` and `scripts/publish-download-bundle-s3.sh` now check that `verify-live-windows-bootstrap-payloads.py` exists before upload/session/token or AWS work.
  - this makes missing live-payload verifier tooling fail before network/object-storage side effects.
  - `tests/test_live_windows_bootstrap_payloads.py` and `tests/test_desktop_downloads_local_release_policy.py` pin the check and its ordering.
- Focused verification:
  - HTTP/S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` + `tests/test_live_windows_bootstrap_payloads.py` -> `78 passed`
  - tracked current-lane focused slice, including live Windows payload verifier contracts -> `146 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:32:32+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane nightly stage Windows payload preflight smoke coverage:
  - `tests/test_desktop_downloads_local_release_policy.py` now runs a direct `CHUMMER_VERIFY_MODE=release` smoke against a temporary publishable nightly stage with no Windows installer candidates.
  - the smoke proves `scripts/publish-latest-nightly-to-downloads.sh` exits `2` with the new Windows installer requirement before startup-smoke, deploy, or publish output.
- Focused verification:
  - nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice, including live Windows payload verifier contracts -> `146 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:30:46+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane nightly stage Windows payload preflight hardening:
  - `scripts/publish-latest-nightly-to-downloads.sh` now collects staged Windows installer candidates from the stage root and `files/` before invoking `verify-windows-installer-payloads.py`.
  - `CHUMMER_VERIFY_MODE=release` rejects a selected nightly stage with no Windows installer candidates before publish work.
  - scaffold/slice lanes still append `--allow-empty` for early stages before Windows installers exist.
- Focused verification:
  - nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice, including live Windows payload verifier contracts -> `146 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:28:14+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane object-storage/S3 live Windows payload verification parity:
  - `scripts/publish-download-bundle-s3.sh` now runs `verify-live-windows-bootstrap-payloads.py` after `verify-releases-manifest.sh`.
  - release mode omits `--allow-empty`; scaffold/slice lanes keep the tolerant empty Windows bootstrap coverage behavior.
  - this aligns S3 post-upload verification with the HTTP publish lane.
- Focused verification:
  - HTTP/S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` + `tests/test_live_windows_bootstrap_payloads.py` -> `78 passed`
  - tracked current-lane focused slice, including live Windows payload verifier contracts -> `146 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:25:30+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP upload preflight Windows installer coverage guard:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_VERIFY_MODE=release` when the staged HTTP upload bundle has no Windows installer candidates.
  - outside release mode, the preflight still passes `--allow-empty` for scaffold/slice lanes before Windows installers are added.
  - this aligns HTTP upload publish preflight with the object-storage/S3 release-mode Windows installer presence guard.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice, including live Windows payload verifier contracts -> `145 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:23:51+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP live Windows payload verification hardening:
  - `scripts/publish-download-bundle-http.sh` now omits `--allow-empty` when invoking `verify-live-windows-bootstrap-payloads.py` in `CHUMMER_VERIFY_MODE=release`.
  - outside release mode, the helper still allows empty Windows bootstrap coverage for scaffold/slice lanes.
  - release-mode live publish verification now fails if the served manifest exposes no Windows bootstrap installers instead of accepting empty coverage.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` + `tests/test_live_windows_bootstrap_payloads.py` -> `77 passed`
  - tracked current-lane focused slice, now including live Windows payload verifier contracts -> `145 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:22:04+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP release-publish dry-run guard:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_VERIFY_MODE=release` when `CHUMMER_RELEASE_UPLOAD_DRY_RUN=true|1|yes|on`.
  - this keeps dry-run output out of release publish evidence and fails before bundle layout checks, token resolution, or network work.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the guard, its pre-bundle ordering, and the direct smoke behavior.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice -> `141 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:17:30+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP release-publish portability hardening:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_VERIFY_MODE=release` when `CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK=true|1|yes|on`.
  - this keeps release-mode HTTP publishing on the upload-session path and prevents silent fallback to direct bundle upload after upload-session creation failure.
  - `tests/test_desktop_downloads_local_release_policy.py` pins the guard, its pre-bundle ordering, and the direct smoke behavior.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice -> `141 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:13:51+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI accessibility polish:
  - `Chummer.Blazor/Components/Shell/DialogHost.razor` now exposes `aria-keyshortcuts="Escape"` on both the focused dialog surface and the close button.
  - this makes the newly restored classic Escape-to-close shortcut discoverable to assistive technology.
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` pins the shortcut metadata and ordering next to the Escape handler.
- Focused verification:
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` -> `3 passed`
  - Blazor head build -> pass
  - tracked current-lane focused slice -> `141 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:11:15+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane dialog/UI polish:
  - `Chummer.Blazor/Components/Shell/DialogHost.razor` now handles Escape on the focused `.desktop-dialog` surface and delegates to the existing close path.
  - this restores classic desktop dialog parity for keyboard users while keeping roster-specific Escape behavior scoped to roster rows.
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` pins the Razor handler and ordering before click propagation suppression.
- Focused verification:
  - Blazor head build -> pass
  - `tests/test_desktop_shell_dialog_chrome_check_contract.py` -> `3 passed`
  - tracked current-lane focused slice -> `141 passed`
  - touched-file `git diff --check` -> pass
- Note:
  - a direct bUnit focused compile attempt for `BlazorShellComponentTests.DialogHost_renders_dialog_and_emits_events` was stopped after the large C# test compile stalled; the C# test edit was reverted and this slice is covered by Blazor build plus lightweight source contract.
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:02:48+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane S3 object-storage publish release-mode Windows installer presence guard:
  - `scripts/publish-download-bundle-s3.sh` still allows an empty Windows payload gate outside release mode before installers are added.
  - in `CHUMMER_VERIFY_MODE=release`, the same empty Windows installer set now exits `2` before object-storage/S3 configuration or network work.
  - this prevents release-mode object-storage publish from relying on later manifest verification to discover a missing Windows installer lane.
- Runtime smoke:
  - with a temp bundle containing `releases.json`, `RELEASE_CHANNEL.generated.json`, and `files/` but no Windows installer, `CHUMMER_VERIFY_MODE=release bash scripts/publish-download-bundle-s3.sh <bundle>` exits `2` before asking for `CHUMMER_PORTAL_DOWNLOADS_S3_URI`.
- Focused verification:
  - S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice -> `140 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T19:00:32+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP upload helper release-mode proof-skip guards:
  - `scripts/publish-download-bundle-http.sh` now rejects `CHUMMER_VERIFY_MODE=release` when `CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST=false|0|no|off`.
  - it also rejects release mode when `CHUMMER_RELEASE_UPLOAD_VERIFY_WINDOWS_PAYLOADS=false|0|no|off`.
  - it also rejects release mode when `CHUMMER_RELEASE_UPLOAD_VERIFY_ROUTES=false|0|no|off`.
  - these checks run before bundle layout checks, dry-run checks, upload-token resolution, or network work.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST=false bash scripts/publish-download-bundle-http.sh /tmp/nonexistent-bundle` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_UPLOAD_VERIFY_WINDOWS_PAYLOADS=false bash scripts/publish-download-bundle-http.sh /tmp/nonexistent-bundle` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_UPLOAD_VERIFY_ROUTES=false bash scripts/publish-download-bundle-http.sh /tmp/nonexistent-bundle` exits `2` before bundle inspection.
- Focused verification:
  - HTTP publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice -> `140 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:58:09+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane HTTP/S3 publish helper release verification coverage guard:
  - `scripts/publish-download-bundle-http.sh` and `scripts/publish-download-bundle-s3.sh` now reject `CHUMMER_VERIFY_MODE=release` when `CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=false|0|no|off`.
  - the HTTP publisher no longer forces `CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0` when invoking `scripts/verify-releases-manifest.sh`.
  - both helpers propagate `CHUMMER_VERIFY_MODE` and `CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE` into the verifier explicitly.
  - the release-mode guards run before bundle layout checks, upload dry-run checks, or network/object-storage work.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=false bash scripts/publish-download-bundle-s3.sh /tmp/nonexistent-bundle` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 bash scripts/publish-download-bundle-http.sh /tmp/nonexistent-bundle` exits `2` before bundle inspection.
- Focused verification:
  - HTTP/S3 publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice -> `140 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:55:26+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane desktop installer builder release-mode escape-hatch guard:
  - `scripts/build-desktop-installer.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_LOCAL_RELEASE_VERSION=true|1|yes|on`.
  - it also exits `2` in release mode when `CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE=true|1|yes|on`.
  - these checks run before array/package work, so release-mode installer builds cannot use local placeholder versions or unsigned public-release overrides as release evidence.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_ALLOW_LOCAL_RELEASE_VERSION=true bash scripts/build-desktop-installer.sh /tmp/nonexistent-publish-dir avalonia linux-x64 Chummer.Avalonia` exits `2` before missing publish-dir work.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE=yes bash scripts/build-desktop-installer.sh /tmp/nonexistent-publish-dir avalonia win-x64 Chummer.Avalonia.exe` exits `2` before missing publish-dir work.
- Focused verification:
  - desktop installer builder syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `73 passed`
  - tracked current-lane focused slice -> `140 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:52:32+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane external-host proof blocker generation is now fail-closed in release mode:
  - `scripts/generate-releases-manifest.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_GENERATE_EXTERNAL_HOST_PROOF_BLOCKERS=false|0|no|off`.
  - `scripts/publish-download-bundle.sh` now defaults `CHUMMER_GENERATE_EXTERNAL_HOST_PROOF_BLOCKERS` to `1` in release mode and keeps the local shelf-sync default at `0` outside release mode.
  - release-mode bundle publishing now rejects an explicit blocker-generation skip before bundle layout checks.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_GENERATE_EXTERNAL_HOST_PROOF_BLOCKERS=false bash scripts/generate-releases-manifest.sh` exits `2`.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=true CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=https://chummer.run/downloads CHUMMER_GENERATE_EXTERNAL_HOST_PROOF_BLOCKERS=false bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
- Focused verification:
  - generator/bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `72 passed`
  - tracked current-lane focused slice -> `139 passed`
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:49:22+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane nightly publisher external verification release preflight:
  - `scripts/publish-latest-nightly-to-downloads.sh` now rejects `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true|1|yes|on`.
  - release-mode nightly publication now also requires `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` before publish-guard/stage scanning work.
  - malformed/no-host verify URLs such as `https:///missing-host` are rejected before stage scanning.
  - the nightly publisher now passes `CHUMMER_VERIFY_MODE`, `CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH`, and `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` explicitly into `scripts/publish-download-bundle.sh`.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=true CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH=false CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=false bash scripts/publish-latest-nightly-to-downloads.sh` exits `2` before stage discovery.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=true CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH=false CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true bash scripts/publish-latest-nightly-to-downloads.sh` exits `2` before stage discovery because the live verify URL is missing.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=true CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH=false CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=https:///missing-host bash scripts/publish-latest-nightly-to-downloads.sh` exits `2` before stage discovery.
- Focused verification:
  - nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `72 passed`
  - tracked current-lane focused slice -> `139 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:44:45+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane live verification URL host guard:
  - `scripts/publish-download-bundle.sh` now rejects no-host URLs such as `http:///missing-host` and `https:///missing-host` in `CHUMMER_VERIFY_MODE=release`.
  - the early release-mode regex now requires a non-slash, non-space host character after `http(s)://`, before bundle layout checks and before the later Python URL parser.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=http:///missing-host bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=https:///missing-host bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` also exits `2`.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `15G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:43:23+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane malformed live verification URL release guard:
  - `scripts/publish-download-bundle.sh` now exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` is not an absolute `http(s)://...` URL.
  - this runs before bundle layout checks and before the later Python URL validator/deploy mutation path, so release-mode bundle publication cannot start with an obviously malformed live verification target.
  - the existing Python validator remains the stricter URL parser later in the script.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=not-a-url bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL=ftp://example.invalid/downloads bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` also exits `2`.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `10G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:41:31+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane live external verification URL release guard:
  - `scripts/publish-download-bundle.sh` now exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` is missing.
  - release mode already requires `CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true|1|yes|on`; this slice closes the companion gap so release-mode bundle publication must also name the live verify target before bundle layout checks or deploy mutation.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=yes bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` also exits `2`.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `10G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:39:40+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane external publish release guard:
  - `scripts/publish-download-bundle.sh` now exits `2` in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=true|1|yes|on`.
  - this prevents release-mode bundle publication from presenting local-only downloads shelf updates as release evidence.
  - existing downstream checks still require `CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL` when external publish is required, so release-mode bundle publication must enter the live verification lane before mutation.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_DOWNLOADS_REQUIRE_EXTERNAL_PUBLISH=false bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` also exits `2`.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `10G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:37:56+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane Windows visual-proof handoff publish release guard:
  - `scripts/publish-latest-nightly-to-downloads.sh` now exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH=true|1|yes|on`.
  - `scripts/publish-download-bundle.sh` now exits `2` in release mode for the same truthy values.
  - this prevents release-mode publish helpers from continuing after a Windows desktop exit-gate failure just because a preview visual-proof handoff was materialized.
  - preview/non-release handoff lanes remain available outside release verification.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=1 CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH=true bash scripts/publish-latest-nightly-to-downloads.sh` exits `2` before stage discovery.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_ALLOW_WINDOWS_VISUAL_PROOF_HANDOFF_PUBLISH=true bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
- Focused verification:
  - nightly/bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `9.9G` free; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:35:56+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane skipped startup-smoke release guard normalization:
  - `scripts/publish-latest-nightly-to-downloads.sh` now exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE=true|1|yes|on`.
  - `scripts/publish-download-bundle.sh` now exits `2` in release mode for the same truthy values.
  - this closes the gap where downstream Python treated `true|yes|on` as allowing skipped startup-smoke evidence while the shell guard only rejected `1`.
- Runtime smokes:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=1 CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE=true bash scripts/publish-latest-nightly-to-downloads.sh` exits `2` before stage discovery.
  - `CHUMMER_VERIFY_MODE=release CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE=true bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before bundle inspection.
- Focused verification:
  - nightly/bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `10G` free after prior cleanup; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:34:25+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane bundle file-source fallback release guard:
  - `scripts/publish-download-bundle.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_BUNDLE_FILES_SOURCE_FALLBACK=true|1|yes|on`.
  - release-mode bundle publish can no longer fall back to unrelated sibling/download roots when the bundle `files/` directory is missing.
  - non-release explicit fallback behavior remains available for local repair/smoke work.
- Runtime smoke:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_ALLOW_BUNDLE_FILES_SOURCE_FALLBACK=true bash scripts/publish-download-bundle.sh /tmp/nonexistent-bundle /tmp/nonexistent-deploy` exits `2` before checking the missing bundle path.
- Focused verification:
  - bundle publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage has about `10G` free after prior cleanup; still prefer focused tests unless a larger build is necessary.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:32:56+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane nightly preview-lane release guard:
  - `scripts/publish-latest-nightly-to-downloads.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_STABLE_CHANNEL_FROM_NIGHTLY_PUBLISH=true|1|yes|on`.
  - the nightly publisher remains a preview handoff lane in release verification; stable/public-stable promotion must use the explicit stable release path.
- Runtime smoke:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=1 CHUMMER_ALLOW_STABLE_CHANNEL_FROM_NIGHTLY_PUBLISH=true bash scripts/publish-latest-nightly-to-downloads.sh` exits `2` before stage discovery.
- Focused verification:
  - nightly publisher syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage remains tight (`~1.8G` free); prefer focused tests and avoid large rebuilds unless needed.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:31:18+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane direct release-manifest verification guard:
  - `scripts/verify-releases-manifest.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0|false|no|off`.
  - direct release-mode verification can no longer disable complete desktop tuple coverage while presenting release evidence.
- Runtime smoke:
  - `CHUMMER_VERIFY_MODE=release CHUMMER_VERIFY_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0 bash scripts/verify-releases-manifest.sh /tmp/nonexistent-release-shelf` exits `2` before target inspection or registry verifier invocation.
- Focused verification:
  - verifier syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - root storage remains tight (`~1.8G` free after prior `/tmp` cleanup); prefer focused tests and avoid large rebuilds unless needed.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:29:05+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane complete desktop coverage release guard:
  - `scripts/generate-releases-manifest.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_RELEASE_REQUIRE_COMPLETE_DESKTOP_COVERAGE=0|false|no|off`.
  - `scripts/publish-latest-nightly-to-downloads.sh` exits `2` in release mode when complete desktop coverage is disabled.
  - `scripts/publish-download-bundle.sh` exits `2` in release mode when complete desktop coverage is disabled.
  - release-mode manifest/publish helpers can no longer downgrade desktop tuple completeness while presenting release evidence.
- Runtime smokes:
  - all three complete-coverage-disable release-mode paths exit `2` before stage discovery, bundle checks, deployment, or manifest generation.
- Focused verification:
  - manifest/nightly/bundle syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Host note:
  - pytest initially failed before collection because root storage was full; clearing disposable `/tmp` entries restored about `1.7G` free and tests then passed.
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:24:05+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane startup-smoke hydration release guard:
  - `scripts/generate-releases-manifest.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_SKIP_STARTUP_SMOKE_HYDRATION=1`.
  - `scripts/publish-latest-nightly-to-downloads.sh` also exits `2` in release mode when `CHUMMER_SKIP_STARTUP_SMOKE_HYDRATION=1`.
  - direct release-mode manifest generation and nightly publish helpers can no longer bypass startup-smoke hydration.
- Runtime smokes:
  - both hydration-skip release-mode paths exit `2` before stage discovery or manifest generation.
- Focused verification:
  - generator/nightly syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:22:04+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane release-manifest startup-smoke filter hardening:
  - `scripts/generate-releases-manifest.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER=true`.
  - `scripts/verify-releases-manifest.sh` exits `2` in release mode when `CHUMMER_VERIFY_SKIP_STARTUP_SMOKE_FILTER=true` or `CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER=true`.
  - direct release-mode manifest generation/verification can no longer opt out of startup-smoke filtering.
- Runtime smokes:
  - both manifest helper release-mode startup-smoke-filter skip paths exit `2` before generation/registry verification work.
- Focused verification:
  - manifest helper syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `71 passed`
  - tracked current-lane focused slice -> `138 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:19:26+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane publish-script skipped startup-smoke release guard:
  - `scripts/publish-latest-nightly-to-downloads.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE=1`.
  - `scripts/publish-download-bundle.sh` also exits `2` in release mode when `CHUMMER_ALLOW_SKIPPED_STARTUP_SMOKE=1`.
  - release-mode publish helpers can no longer opt into accepting skipped startup-smoke receipts as public evidence.
- Runtime smokes:
  - both publish helper release-mode skipped-startup-smoke paths exit `2` before stage discovery/deployment work.
- Focused verification:
  - publish helper syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `70 passed`
  - tracked current-lane focused slice -> `137 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:17:11+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane B7 browser isolation runtime-skip release guard:
  - `scripts/ai/milestones/b7-browser-isolation-check.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_B7_ALLOW_RUNTIME_SKIP=1`.
  - direct B7 release-mode proof can no longer skip the portal runtime deployment probe.
- Runtime smoke:
  - release mode plus `CHUMMER_B7_ALLOW_RUNTIME_SKIP=1` exits `2` with a fail-closed message.
- Focused verification:
  - B7 syntax -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `19 passed`
  - tracked current-lane focused slice -> `137 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:15:16+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane portal release-mode shortcut hardening:
  - `scripts/e2e-portal.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_PORTAL_E2E_SKIP_EDGE_REBUILD=1`.
  - release-mode portal E2E proof now cannot reuse stale self-host portal containers through the direct skip switch.
- Runtime smoke:
  - release mode plus `CHUMMER_PORTAL_E2E_SKIP_EDGE_REBUILD=1` exits `2` with a fail-closed message.
- Focused verification:
  - portal E2E script syntax -> pass
  - `tests/test_blazor_portal_e2e_script.py` -> `4 passed`
  - tracked current-lane focused slice, now including portal E2E script contracts -> `136 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:13:10+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane additional direct release-mode shortcut hardening:
  - `materialize-desktop-visual-familiarity-exit-gate.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_DESKTOP_VISUAL_SKIP_FLAGSHIP_GATE_DEPENDENCY=1`.
  - `materialize-desktop-executable-exit-gate.sh` now defaults `CHUMMER_LINUX_DESKTOP_EXIT_GATE_SKIP_DESIGN_SUPERVISOR_REFRESH` to `0` in release mode instead of `1`.
  - `materialize-desktop-executable-exit-gate.sh` exits `2` in release mode when `CHUMMER_LINUX_DESKTOP_EXIT_GATE_SKIP_DESIGN_SUPERVISOR_REFRESH=1`.
  - `scripts/materialize-linux-desktop-exit-gate.sh` also exits `2` in release mode when `CHUMMER_LINUX_DESKTOP_EXIT_GATE_SKIP_DESIGN_SUPERVISOR_REFRESH=1`.
- Runtime smokes:
  - all three new release-mode skip paths exit `2` with fail-closed messages.
- Focused verification:
  - visual, executable, and Linux desktop gate syntax -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `18 passed`
  - tracked current-lane focused slice -> `132 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:10:28+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane direct downstream release-mode skip guards:
  - `chummer5a-screenshot-review-gate.sh` exits `2` in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_SCREENSHOT_REVIEW_SKIP_FLAGSHIP_GATE_DEPENDENCY=1`.
  - `next90-m141-ui-direct-import-route-proof-check.sh` exits `2` in release mode when `CHUMMER_NEXT90_M141_SKIP_FLAGSHIP_GATE_DEPENDENCY=1`.
  - `veteran-task-time-evidence-gate.sh` exits `2` in release mode when `CHUMMER_VETERAN_TASK_TIME_SKIP_FLAGSHIP_GATE_DEPENDENCY=1`.
  - `next90-m143-ui-direct-output-proof-check.sh` exits `2` in release mode when `CHUMMER_NEXT90_M143_SKIP_FLAGSHIP_GATE_DEPENDENCY=1`.
- Runtime smokes:
  - all four direct-script release-mode skip paths exit `2` with fail-closed messages.
- Focused verification:
  - B14 plus four guarded downstream-script syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `70 passed`
  - tracked current-lane focused slice -> `131 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:07:58+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane B14 remaining downstream skip delegation cleanup:
  - in `CHUMMER_VERIFY_MODE=release`, B14 no longer passes `CHUMMER_SCREENSHOT_REVIEW_SKIP_FLAGSHIP_GATE_DEPENDENCY=1` into `chummer5a-screenshot-review-gate.sh`.
  - in release mode, B14 no longer passes `CHUMMER_NEXT90_M141_SKIP_FLAGSHIP_GATE_DEPENDENCY=1` into `next90-m141-ui-direct-import-route-proof-check.sh`.
  - in release mode, B14 no longer passes `CHUMMER_VETERAN_TASK_TIME_SKIP_FLAGSHIP_GATE_DEPENDENCY=1` into `veteran-task-time-evidence-gate.sh`.
  - in release mode, B14 no longer passes `CHUMMER_NEXT90_M143_SKIP_FLAGSHIP_GATE_DEPENDENCY=1` into `next90-m143-ui-direct-output-proof-check.sh`.
  - non-release modes retain the local shortcut branches.
  - the top-level `CHUMMER_FLAGSHIP_UI_RELEASE_GATE_SKIP_DOWNSTREAM_RECEIPTS=1` release-mode fail-closed guard remains in place.
- Focused verification:
  - B14 syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `69 passed`
  - tracked current-lane focused slice -> `130 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:06:30+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane B14 downstream receipt skip hardening update:
  - `scripts/ai/milestones/b14-flagship-ui-release-gate.sh` now exits `2` in `CHUMMER_VERIFY_MODE=release` if `CHUMMER_FLAGSHIP_UI_RELEASE_GATE_SKIP_DOWNSTREAM_RECEIPTS=1`.
  - non-release screenshot-refresh-only behavior remains available through the existing downstream skip path.
- Runtime smoke:
  - release mode plus `CHUMMER_FLAGSHIP_UI_RELEASE_GATE_SKIP_DOWNSTREAM_RECEIPTS=1` exits `2` with a fail-closed message.
- Focused verification:
  - B14 syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py` -> `68 passed`
  - tracked current-lane focused slice -> `129 passed`
  - touched-file `git diff --check` -> pass
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:02:42+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane B14 downstream release-mode compatibility update:
  - B14 now calls the desktop visual familiarity gate without its release-gate-lock skip in release mode.
  - B14 now calls the desktop workflow execution gate without the flagship dependency refresh skip or forced dependency-refresh disable in release mode.
  - non-release modes retain the local shortcut branches.
- Focused verification:
  - B14/visual/workflow syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py tests/test_desktop_executable_exit_gate_contract.py` -> `84 passed`
  - tracked current-lane focused slice -> `128 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T18:00:04+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane desktop workflow execution release-mode hardening update:
  - `materialize-desktop-workflow-execution-gate.sh` now fails in release mode if flagship dependency refresh is skipped.
- Runtime smoke:
  - release mode plus `CHUMMER_DESKTOP_WORKFLOW_SKIP_FLAGSHIP_DEPENDENCY_REFRESH=1` exits `2` with a fail-closed message.
- Focused verification:
  - workflow/B14 syntax -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `17 passed`
  - tracked current-lane focused slice -> `127 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T17:57:38+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane desktop visual familiarity release-mode hardening update:
  - `materialize-desktop-visual-familiarity-exit-gate.sh` now fails in release mode if release-gate lock waiting is skipped.
  - it also fails in release mode if prerequisite receipt refresh is skipped.
- Runtime smoke:
  - both desktop visual release-mode skip paths exit `2` with fail-closed messages.
- Focused verification:
  - visual/B14 syntax -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py` -> `16 passed`
  - tracked current-lane focused slice -> `126 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Goal Refinement Sync (2026-07-09T17:55:10+02:00)

- Current controller/root blocker truth is inherited from the handoff refresh below:
  - `release_truth:public_edge_postdeploy_gate`
- Origin-dialog lane verify-mode evidence cleanup:
  - stale local untracked `tests/test_verify_mode_contract.py` was removed from the active checkout.
  - critical verify-mode and desktop executable release-mode assertions remain covered by tracked `tests/test_desktop_executable_exit_gate_contract.py`.
  - `scripts/ai/verify.sh` still routes desktop executable gate calls through release-aware `run_verify_desktop_executable_gate`.
- Focused verification:
  - verify/desktop/B14 syntax -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py tests/test_desktop_downloads_local_release_policy.py` -> `81 passed`
  - tracked current-lane focused slice -> `125 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blocker above remains.

## Handoff refresh (2026-07-09T17:54:23+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_truth:public_edge_postdeploy_gate`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-09T15:54:51Z`
    - `load_status=loaded`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-09T15:54:44Z`
    - `status=pass`
    - stale source digest still recorded: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-09T15:54:32Z`
    - `status=pass`
    - `actionable_candidate_count=missing`
    - `all_discovery_roots_checked=missing`
    - `matching_promoted_directory_candidate_count=missing`
    - `matching_promoted_zip_candidate_count=missing`
    - `stale_directory_candidate_count=missing`
    - `stage_visual_proof_receipt_count=missing`
    - `matching_promoted_stage_visual_proof_receipt_count=missing`
    - `stage_startup_smoke_receipt_count=missing`
    - `matching_promoted_stage_startup_smoke_receipt_count=missing`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-09T15:54:32Z`
    - `status=not_running`
    - `pid=missing`
    - `process_alive=False`
    - `matching_process_count=0`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=pass`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-09T15:54:32Z`
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-09T15:55:23Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=2`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from the current blocker sheet
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Goal Refinement Sync (2026-07-09T17:51:38+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane verify-script release-mode hardening update:
  - `scripts/ai/verify.sh` now routes desktop executable gate calls and mutation probes through `run_verify_desktop_executable_gate`.
  - release mode invokes the desktop executable gate without `CHUMMER_DESKTOP_EXECUTABLE_SKIP_DEPENDENCY_MATERIALIZE=1`.
  - non-release modes retain the fast mutation path.
  - verify cleanup restores the desktop executable receipt only outside release mode.
- Focused verification:
  - `bash -n scripts/ai/verify.sh scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh` -> pass
  - `tests/test_verify_mode_contract.py tests/test_desktop_executable_exit_gate_contract.py tests/test_desktop_downloads_local_release_policy.py` -> `83 passed`
  - expanded current-lane focused slice -> `127 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:47:47+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane desktop executable release-mode hardening update:
  - `materialize-desktop-executable-exit-gate.sh` now fails in release mode if dependency materialization is skipped.
  - it also fails in release mode if release-gate lock waiting is skipped.
  - B14 now calls the desktop executable gate without those skip switches in release mode; non-release modes retain the local shortcut.
- Runtime smoke:
  - both desktop executable release-mode skip paths exit `2` with fail-closed messages.
- Focused verification:
  - desktop executable/B14 syntax -> pass
  - `tests/test_desktop_executable_exit_gate_contract.py tests/test_desktop_downloads_local_release_policy.py` -> `79 passed`
  - expanded current-lane focused slice -> `126 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:45:09+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane B14 flagship release-gate release-mode hardening update:
  - B14 now reads `CHUMMER_VERIFY_MODE`.
  - in `CHUMMER_VERIFY_MODE=release`, B14 runs the SR4/SR6 desktop parity frontier without `CHUMMER_SR4_SR6_FRONTIER_SKIP_SUBGATE_REFRESH=1` and without delegated SR4/SR6/Chummer5a workflow parity skip flags.
  - non-release modes retain the cached frontier shortcut for slice speed.
- Focused verification:
  - B14/frontier wrapper syntax -> pass
  - `tests/test_desktop_downloads_local_release_policy.py tests/test_chummer5a_parity_tester.py` -> `83 passed`
  - combined current-lane focused slice -> `112 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:40:45+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane SR4/SR6 desktop parity frontier release-mode hardening update:
  - `CHUMMER_VERIFY_MODE=release` now forbids `CHUMMER_SR4_SR6_FRONTIER_SKIP_SUBGATE_REFRESH=1`.
  - release mode also forbids delegated SR4, SR6, and Chummer5a workflow parity dependency-materialization skip switches at the frontier wrapper.
- Runtime smoke:
  - all four frontier release-mode skip paths exit `2` with fail-closed messages.
- Focused verification:
  - frontier wrapper syntax -> pass
  - `tests/test_chummer5a_parity_tester.py` -> `18 passed`
  - combined current-lane focused slice -> `111 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:38:33+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane SR4/SR6 workflow parity release-mode hardening update:
  - SR6 workflow parity now fails in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_SR6_WORKFLOW_PARITY_SKIP_DEPENDENCY_MATERIALIZE=1`.
  - SR4 workflow parity now fails in `CHUMMER_VERIFY_MODE=release` when `CHUMMER_SR4_WORKFLOW_PARITY_SKIP_DEPENDENCY_MATERIALIZE=1`.
  - `tests/test_chummer5a_parity_tester.py` pins both wrapper contracts.
- Runtime smoke:
  - release mode plus `CHUMMER_SR6_WORKFLOW_PARITY_SKIP_DEPENDENCY_MATERIALIZE=1` -> exit `2`.
  - release mode plus `CHUMMER_SR4_WORKFLOW_PARITY_SKIP_DEPENDENCY_MATERIALIZE=1` -> exit `2`.
- Focused verification:
  - workflow parity wrapper syntax -> pass
  - `tests/test_chummer5a_parity_tester.py` -> `17 passed`
  - combined current-lane focused slice -> `110 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:34:59+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane day1 milestone release-mode hardening update:
  - `scripts/ai/day1-all-milestones.sh` now fails immediately in `CHUMMER_VERIFY_MODE=release` when `DAY1_MILESTONE_MODE` is not `strict`.
  - it also fails immediately in release mode when `DAY1_ALLOW_MISSING_GATES=1`.
- Runtime smoke:
  - release mode plus `DAY1_MILESTONE_MODE=warn` -> exit `2`.
  - release mode plus `DAY1_ALLOW_MISSING_GATES=1` -> exit `2`.
- Focused verification:
  - `bash -n scripts/ai/day1-all-milestones.sh` -> pass
  - `tests/test_desktop_downloads_local_release_policy.py tests/test_verify_mode_contract.py` -> `67 passed`
  - combined current-lane focused slice -> `110 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:32:11+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane release-mode hardening update:
  - `scripts/ai/verify.sh` now fails in release mode if `CHUMMER_VERIFY_AVALONIA_PRIMARY_ROUTE_PROOF` disables the Avalonia primary-route proof guard.
  - `tests/test_verify_mode_contract.py` pins the proof-toggle fail-closed behavior.
- Focused verification:
  - `bash -n scripts/ai/verify.sh` -> pass
  - `tests/test_verify_mode_contract.py` -> `3 passed`
  - combined current-lane focused slice -> `109 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:30:23+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane release-mode hardening update:
  - `scripts/ai/verify.sh` now fails in `CHUMMER_VERIFY_MODE=release` unless `CHUMMER_VERIFY_CROSS_REPO_BUILDS=1`.
  - this prevents release verification from silently avoiding hub-registry/run-services contract build evidence.
- Focused verification:
  - `bash -n scripts/ai/verify.sh` -> pass
  - `tests/test_verify_mode_contract.py tests/test_audit_compliance_script.py tests/test_chummer5a_parity_tester.py` -> `23 passed`
  - combined current-lane focused slice -> `109 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:28:32+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane audit compliance hardening update:
  - `scripts/audit-compliance.sh` now defaults migration compliance expected tests to `195` and life-modules expected tests to `5`.
  - the repo-local script no longer uses `--minimum-expected-tests 1`.
  - `tests/test_audit_compliance_script.py` pins both source inventories and rejects weak `1`-test gates.
- Focused verification:
  - `bash -n scripts/audit-compliance.sh` -> pass
  - `tests/test_audit_compliance_script.py tests/test_chummer5a_parity_tester.py` -> `20 passed`
  - combined current-lane focused slice -> `109 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:26:09+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane workflow parity hardening update:
  - SR6, SR4, and Chummer5a desktop workflow parity wrappers now require the current `WorkflowParityGateTests` inventory count (`17`) instead of `--minimum-expected-tests 1`.
  - `tests/test_chummer5a_parity_tester.py` pins the source inventory at 17 unique `[TestMethod]` methods.
- Runtime smoke:
  - direct MTP runner for `WorkflowParityGateTests` with `--minimum-expected-tests 17` passed: `total: 17`, `succeeded: 17`, `skipped: 0`.
- Focused verification:
  - workflow parity wrapper syntax -> pass
  - `python3 -m pytest -q tests/test_chummer5a_parity_tester.py` -> `17 passed`
  - combined current-lane focused slice -> `106 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:22:50+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane release-script portability update:
  - `scripts/ai/verify.sh` now validates `CHUMMER_VERIFY_MODE=scaffold|slice|integration|release`.
  - default `slice` mode prints `VERIFY MODE: slice - not valid release evidence`.
  - `release` mode prints `VERIFY MODE: release`.
  - optional proof, manifest-target, cross-repo build, and Avalonia startup-smoke receipt skips now route through `skip_or_fail`.
  - release mode fails instead of silently skipping those checks.
- Runtime smoke:
  - `CHUMMER_VERIFY_MODE=release bash scripts/ai/verify.sh` fails closed at the missing local rule-environment proof with `release verification cannot skip: ...`.
- Focused verification:
  - `bash -n scripts/ai/verify.sh` -> pass
  - combined current-lane focused slice -> `89 passed`
- Generated-dialog parity remains fresh passing:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T17:19:43+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane status update:
  - generated-dialog parity is no longer stale or timing out.
  - fresh receipt: `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json`
  - `status: pass`
  - `generatedAt: 2026-07-09T15:13:50.947487Z`
  - the verifier now uses focused build steps for `Chummer.Presentation`, `Chummer.Avalonia`, and the required generated-dialog `Chummer.Tests` files while preserving the same fully-qualified parity test filters.
  - all 14 generated-dialog parity test slices passed with no no-match or timeout results.
- Focused fast proof remains green:
  - `python3 -m pytest -q tests/test_generated_dialog_parity_timeout_contract.py tests/test_with_package_plane_bootstrap_cache.py tests/test_desktop_shell_dialog_chrome_check_contract.py tests/test_blazor_portal_route_probe_contract.py` -> `21 passed`
- Process hygiene:
  - no origin-dialog generated-dialog parity/build process remains running.
- Next controller-facing action:
  - generated-dialog parity can now be treated as fresh passing evidence for its lane, but it does not clear the controller/root blockers above.
  - continue desktop executable/gold/release-truth blocker work before any release-route, merge, deploy, or nightly decision.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above remain.

## Goal Refinement Sync (2026-07-09T16:33:47+02:00)

- Current controller/root blocker truth remains:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Origin-dialog lane status update:
  - an additional `bash scripts/ai/milestones/generated-dialog-element-parity-check.sh` attempt was made after verifier hardening.
  - the run entered package-plane `flock` wait and did not start `Chummer.Tests` build.
  - the run was stopped manually to avoid leaving an idle queued process.
  - no fresh `GENERATED_DIALOG_ELEMENT_PARITY.generated.json` was written.
- Current origin-dialog full parity receipt remains stale:
  - `status: fail`
  - `generatedAt: 2026-07-09T10:46:48.353882Z`
  - reason remains `Generated dialog parity build slice failed with exit code -15.`
- Focused fast proof remains green:
  - `python3 -m pytest -q tests/test_generated_dialog_parity_timeout_contract.py tests/test_with_package_plane_bootstrap_cache.py tests/test_desktop_shell_dialog_chrome_check_contract.py tests/test_blazor_portal_route_probe_contract.py` -> `19 passed`
- Process hygiene:
  - no origin-dialog generated-dialog parity/build process remains running.
- Next controller-facing action:
  - wait for shared package-plane contention to clear, then rerun `bash scripts/ai/milestones/generated-dialog-element-parity-check.sh` in the origin-dialog repo and require a fresh receipt before any release-route, merge, deploy, or nightly decision.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above or stale generated-dialog parity evidence remains.

## Goal Refinement Sync (2026-07-09T16:28:09+02:00)

- Current controller/root blocker truth remains the newer handoff state below:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Read `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/docs/WORKBENCH_SESSION_HANDOFF.md` before any publish-route, release-posture, source-of-truth, or evidence action from the origin-dialog lane.
- The active origin-dialog lane remains on SR6 parity/dialog hardening with release-script portability, but its full generated-dialog parity receipt is still stale (`status: fail`) and no fresh full gate has landed.
- Focused verifier hardening landed in the origin-dialog lane:
  - generated-dialog parity now defaults package-plane lock wait to the effective build timeout when the caller does not set `CHUMMER_PACKAGE_PLANE_LOCK_WAIT_SECONDS`.
  - generated-dialog parity timeout handlers now normalize `TimeoutExpired` output so build timeouts write structured evidence instead of crashing on bytes/str output.
- Focused fast proof slice is green:
  - `python3 -m pytest -q tests/test_generated_dialog_parity_timeout_contract.py tests/test_with_package_plane_bootstrap_cache.py tests/test_desktop_shell_dialog_chrome_check_contract.py tests/test_blazor_portal_route_probe_contract.py` -> `19 passed`
- Full generated-dialog parity remains unresolved:
  - an attempted run queued behind `.linux-desktop-exit-gate-source.8xax5U` and timed out after 1800s before the build could start.
  - a second clean rerun reached the same shared package-plane lock wait and was stopped manually to avoid leaving an idle queued process running.
  - `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` is still stale (`status: fail`, generated `2026-07-09T10:46:48.353882Z`, reason `exit code -15`).
- Operator notification:
  - ETA/status was sent to Telegram through `scripts/send_telegram_message_via_ea.py`.
  - receipt: `/docker/chummercomplete/_completion/telegram_text_delivery/chummer-origin-parity-eta-20260709T1558.receipt.json`
- Next controller-facing action:
  - wait for external package-plane contention to clear, then rerun `bash scripts/ai/milestones/generated-dialog-element-parity-check.sh` in the origin-dialog repo and report the fresh receipt here before any release-route, merge, deploy, or nightly decision.
- Hard stop:
  - no stable/flagship-ready/merge-ready/deployed/nightly-published claim while the controller blockers above or stale generated-dialog parity evidence remains.

## Handoff refresh (2026-07-09T14:43:16+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `proof:desktop_executable_exit_gate`
  - `proof:desktop_gold_gate`
  - `release_truth:release_ready`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-09T12:43:37Z`
    - `load_status=loaded`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-09T12:43:32Z`
    - `status=pass`
    - stale source digest still recorded: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-09T12:43:22Z`
    - `status=pass`
    - `actionable_candidate_count=missing`
    - `all_discovery_roots_checked=missing`
    - `matching_promoted_directory_candidate_count=missing`
    - `matching_promoted_zip_candidate_count=missing`
    - `stale_directory_candidate_count=missing`
    - `stage_visual_proof_receipt_count=missing`
    - `matching_promoted_stage_visual_proof_receipt_count=missing`
    - `stage_startup_smoke_receipt_count=missing`
    - `matching_promoted_stage_startup_smoke_receipt_count=missing`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-09T12:43:22Z`
    - `status=not_running`
    - `pid=missing`
    - `process_alive=False`
    - `matching_process_count=0`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=pass`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-09T12:43:22Z`
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-09T12:44:19Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=2`
    - `coverage_gap_keys=desktop_client`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from the current blocker sheet
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Goal Refinement Sync (2026-07-09T12:55:39+02:00)

- Shared blocker truth remains controlled by release/controller lane:
  - `release_truth:public_edge_postdeploy_gate` is still the active root gate.
- Active hardening lane remains:
  - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`
  - focus remains SR6 shell parity, dialog/UI polish, and release-script portability.
- Active design/policy inputs to keep aligned:
  - `chummer-design/products/chummer/FEATURE_AND_OPPORTUNITY_GUIDE_FOR_DEVELOPERS.md`
  - `chummer-design/products/chummer/WHAT_WE_MISSED_LTD_UTILIZATION_OPPORTUNITIES_FOR_CHUMMER6_EXECUTIVE_ASSISTANT.md`
  - `chummer-design/products/chummer/LTD_UTILIZATION_MATRIX.md`
  - `chummer-design/products/chummer/LTD_CAPABILITY_MESH_OPERATING_MODEL.md`
- Current handoff state:
  - focused proof slice remains green: `python3 -m pytest -q tests/test_generated_dialog_parity_timeout_contract.py tests/test_with_package_plane_bootstrap_cache.py tests/test_desktop_shell_dialog_chrome_check_contract.py tests/test_blazor_portal_route_probe_contract.py` -> `17 passed`
  - release-script authority/hardening evidence remains healthy from prior passes: `11 passed`, `161 passed` on the expanded verification slice.
  - full generated-dialog parity proof is still stale/blocked by package-plane lock contention; `.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` currently reports `status: fail` from a wait-for-lock failure.
- Hard constraints still hold:
  - this lane does not clear the release gate.
  - no stable/flagship-ready/merge-ready claim while the external gate is unresolved and parity evidence remains stale.
- Next action:
  - rerun `bash scripts/ai/milestones/generated-dialog-element-parity-check.sh` when contention clears, then refresh parity evidence before any publish/release-route decision.

## Goal Refinement Sync (2026-07-09T12:23:54+02:00)

- Cross-lane objective remains:
  - continue `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean` through a verified hardening lane focused on SR6 shell parity, dialog/UI polish, and release-script portability.
  - keep each meaningful change behind focused test/build slices.
  - retain blocker alignment to this handoff and `release_truth:public_edge_postdeploy_gate`.
- Hard stop rule:
  - no stable/flagship-ready/merge-ready signal from this repo while parity evidence is stale or external blockers are unresolved.
- Design/policy inputs for this lane are now treated as active:
  - `chummer-design/products/chummer/FEATURE_AND_OPPORTUNITY_GUIDE_FOR_DEVELOPERS.md`
  - `chummer-design/products/chummer/WHAT_WE_MISSED_LTD_UTILIZATION_OPPORTUNITIES_FOR_CHUMMER6_EXECUTIVE_ASSISTANT.md`
  - `chummer-design/products/chummer/LTD_UTILIZATION_MATRIX.md`
  - `chummer-design/products/chummer/LTD_CAPABILITY_MESH_OPERATING_MODEL.md`
- Execution fabric reference:
  - `1min.AI` = low-risk background capacity
  - `Teable` = live operations/proof-debt cockpit
  - `vexp.dev` = cross-repo opportunity index
- Consumer instruction:
  - keep this goal and blocker text synchronized in the receiving handoff before publish/release-route actions.

## Goal Refinement Sync (2026-07-09T12:22:51+02:00)

- Cross-lane objective refresh remains unchanged: controller/release lane owns blocker truth, while `chummer-presentation-sr6-origin-dialog-clean` continues focused parity and release-script hardening slices.
- Current objective-alignment inputs remain active in this cycle:
  - `chummer-design/products/chummer/FEATURE_AND_OPPORTUNITY_GUIDE_FOR_DEVELOPERS.md`
  - `chummer-design/products/chummer/WHAT_WE_MISSED_LTD_UTILIZATION_OPPORTUNITIES_FOR_CHUMMER6_EXECUTIVE_ASSISTANT.md`
  - `chummer-design/products/chummer/LTD_CAPABILITY_MESH_OPERATING_MODEL.md`
  - `chummer-design/products/chummer/LTD_UTILIZATION_MATRIX.md`
- `chummer-presentation-sr6-origin-dialog-clean` evidence check this turn:
  - attempted `bash scripts/ai/milestones/generated-dialog-element-parity-check.sh` and again hit shared build contention before completion; command was interrupted while still running.
  - `.../.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` still `status: fail` with stale pre-fix `Name~...` reasons.
  - focused contract slice remains green: `python3 -m pytest -q tests/test_generated_dialog_parity_timeout_contract.py tests/test_with_package_plane_bootstrap_cache.py tests/test_desktop_shell_dialog_chrome_check_contract.py tests/test_blazor_portal_route_probe_contract.py` -> `17 passed`.
- Release posture constraints remain unchanged:
  - `release_truth:public_edge_postdeploy_gate` is still the active root gate.
  - continue to treat this as non-blocker-clearing from this repo and do not claim stable/flagship-ready/merge-ready based on this repo alone.
- Coordination instruction:
  - continue to read this handoff and keep parity evidence in sync before publish/route-proof/release-posture actions.

## Goal Refinement (2026-07-09T12:13:47+02:00)

- Refined operating objective stays cross-lane: release/controller remains the gatekeeper for blocker truth, while `chummer-presentation-sr6-origin-dialog-clean` continues focused shell/dialog parity and release-script portability hardening.
- The design/governance objective is now explicitly the same as current `chummer-design` lane inputs:
  - `FEATURE_AND_OPPORTUNITY_GUIDE_FOR_DEVELOPERS.md`
  - `WHAT_WE_MISSED_LTD_UTILIZATION_OPPORTUNITIES_FOR_CHUMMER6_EXECUTIVE_ASSISTANT.md`
  - `LTD_CAPABILITY_MESH_OPERATING_MODEL.md`
  - `LTD_UTILIZATION_MATRIX.md`
- Core operating-fabric trio now treated as shared product strategy in all design signaling:
  - `1min.AI` as background capacity,
  - `Teable` as live operations/proof-debt cockpit,
  - `vexp.dev` as cross-repo opportunity index.
- Release posture remains unchanged:
  - `release_truth:public_edge_postdeploy_gate` is still the active root gate.
  - no stable, flagship-ready, or merge-ready status should be inferred from lane-local evidence while parity receipt or external blocker remains unresolved.
- Immediate coordination instruction to the other lanes:
  - continue sharing this updated objective and blocker truth before touching publish-lane, evidence ingestion, or any release promotion command.

## Cross-Lane Sync (2026-07-09T12:10:50+02:00)

- Shared blocker truth remains controlled by the release/controller lane.
- `release_truth:public_edge_postdeploy_gate` is still the current root gate; this repo is not the blocker-clearing path.
- `chummer-presentation-sr6-origin-dialog-clean` advanced its local parity/verifier lane again:
  - `scripts/ai/with-package-plane.sh` now skips engine-contract feed bootstrap when callers pass `--no-restore`, removing another hidden rebuild source from narrow proof scripts.
  - `scripts/ai/milestones/desktop-shell-dialog-chrome-check.sh` is now green on the current tree: focused `Chummer.Blazor` + `Chummer.Tests` builds passed and the two targeted DesktopShell runtime assertions passed.
  - `scripts/ai/milestones/generated-dialog-element-parity-check.sh` no longer uses the broken `dotnet test --filter Name~...` execution path; it now targets the built test host via `dotnet exec .../Chummer.Tests.dll` with `FullyQualifiedName~...` filters after the stale receipt exposed zero-test failures.
  - two representative repaired filters were exercised directly and passed:
    - `DesktopDialogFactoryTests.CreateCommandDialog_all_factory_mapped_commands_surface_named_fields_and_actions`
    - `CharacterOverviewPresenterTests.ExecuteCommandAsync_all_catalog_commands_are_handled`
- Verification completed for this pass:
  - `bash scripts/ai/milestones/desktop-shell-dialog-chrome-check.sh` -> pass (`Chummer.Blazor` build `00:00:01.91`, `Chummer.Tests` build `00:00:08.77`, direct runner `2 succeeded`)
  - `python3 -m pytest -q tests/test_generated_dialog_parity_timeout_contract.py tests/test_with_package_plane_bootstrap_cache.py tests/test_desktop_shell_dialog_chrome_check_contract.py tests/test_blazor_portal_route_probe_contract.py` -> `17 passed`
  - representative direct runner filters on `Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll` -> `1 succeeded` each
- Current lane status still remains constrained by the full parity receipt:
  - `chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` is still `status: fail` from the last completed pre-fix run.
  - a post-fix full rerun was started, but it was interrupted while the shared `Chummer.Tests` build remained busy under workspace contention; the remaining issue is compile availability for a fresh receipt, not the earlier timeout-floor or zero-match filter bugs.

## Cross-Lane Sync (2026-07-09T12:23:54+02:00)

- Shared blocker truth remains controlled by the release/controller lane.
- `release_truth:public_edge_postdeploy_gate` is still the current root gate; this repo is not the blocker-clearing path.
- `chummer-presentation-sr6-origin-dialog-clean` completed release-channel authority hardening in this pass:
  - added `scripts/verify-release-channel-is-authoritative-or-fixture.py` and wired it into `scripts/ai/verify.sh` for fixture/public manifest authority checks.
  - added/expanded tests for authority and mirror parity (`tests/test_verify_release_channel_authority.py`, `tests/test_verified_release_channel_mirror.py`).
  - updated `scripts/materialize-verified-release-channel-mirror.py` to synchronize manifest-adjacent `files/` trees and startup checks.
- Verification completed for this pass:
  - `python3 -m pytest -q tests/test_verify_release_channel_authority.py tests/test_verified_release_channel_mirror.py` -> `11 passed`
  - `python3 -m pytest -q tests/test_startup_smoke_bash_portability.py tests/test_ai_test_runner_portability.py tests/test_audit_compliance_script.py tests/test_desktop_release_matrix_gate.py tests/test_public_windows_payload_metadata.py tests/test_windows_bootstrap_payload_gate_support.py tests/test_windows_installer_payload_gate.py tests/test_windows_installer_update_handoff_gate.py tests/test_desktop_downloads_local_release_policy.py tests/test_downloads_publication_scope.py tests/test_verified_release_channel_mirror.py tests/test_verify_release_channel_authority.py` -> `161 passed`
- Current lane status remains blocked by parity execution timeout:
  - `chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` is still `status: fail` due timeout in generated-dialog parity execution (`Generated dialog parity build slice timed out after 300s`).

## Cross-Lane Sync (2026-07-09T08:33:28+02:00)

- Shared blocker truth remains controlled by the release/controller lane.
- `release_truth:public_edge_postdeploy_gate` is still the current root gate; this repo is not the blocker-clearing path.
- `chummer-presentation-sr6-origin-dialog-clean` completed release-channel authority hardening in this pass:
  - added `scripts/verify-release-channel-is-authoritative-or-fixture.py` and wired it into `scripts/ai/verify.sh` for fixture/public manifest authority checks.
  - updated `scripts/materialize-verified-release-channel-mirror.py` to synchronize `Docker/Downloads/files/` and `Chummer.Portal/downloads/files/` trees with mirror manifests.
  - added `tests/test_verify_release_channel_authority.py` and expanded `tests/test_verified_release_channel_mirror.py` coverage for fixture and mirror-file parity.
- Verification completed for this hardening handoff:
  - `python3 scripts/verify-release-channel-is-authoritative-or-fixture.py` on Docker/Portal canonical and fixture-style manifest paths -> `release_channel_authority:ok`
  - `python3 -m pytest -q tests/test_verify_release_channel_authority.py tests/test_verified_release_channel_mirror.py` -> `11 passed`
  - `python3 -m pytest -q tests/test_startup_smoke_bash_portability.py tests/test_ai_test_runner_portability.py tests/test_audit_compliance_script.py tests/test_desktop_release_matrix_gate.py tests/test_public_windows_payload_metadata.py tests/test_windows_bootstrap_payload_gate_support.py tests/test_windows_installer_payload_gate.py tests/test_windows_installer_update_handoff_gate.py tests/test_desktop_downloads_local_release_policy.py tests/test_downloads_publication_scope.py tests/test_verified_release_channel_mirror.py tests/test_verify_release_channel_authority.py` -> `161 passed`
- Current design/release-slice state is not yet stable: `chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` is still `status: fail` from slice execution; do not infer green release posture from this repo alone.
- For next handoff actions, keep design/product work focused, clear MSBuild/file-lock contention, then rerun the parity lane before any merge-ready declaration.
- Canonical references: `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`, `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`.

## Cross-Lane Sync (2026-07-09T07:49:21+02:00)

- Shared blocker truth remains controlled by the release/controller lane.
- `release_truth:public_edge_postdeploy_gate` is still the current root gate; this repo is not the blocker-clearing path.
- `chummer-presentation-sr6-origin-dialog-clean` added release-channel authority checks for fixture/public manifest separation and mirror validation in its verify flow.
- Current design/release-slice state is not yet stable: `chummer-presentation-sr6-origin-dialog-clean/.codex-studio/published/GENERATED_DIALOG_ELEMENT_PARITY.generated.json` is still `status: fail` from slice execution, so do not infer green release posture from this repo alone.
- For next handoff actions, keep design/product work focused and re-run this lane after clearing file-lock contention, then rerun the slice verify chain before any merge-ready declaration.
- Canonical references: `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`, `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`.

## Handoff refresh (2026-07-09T06:26:53+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_truth:public_edge_postdeploy_gate`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-09T04:28:08Z`
    - `load_status=loaded`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-09T04:27:49Z`
    - `status=pass`
    - stale source digest still recorded: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-09T04:27:17Z`
    - `status=pass`
    - `actionable_candidate_count=missing`
    - `all_discovery_roots_checked=missing`
    - `matching_promoted_directory_candidate_count=missing`
    - `matching_promoted_zip_candidate_count=missing`
    - `stale_directory_candidate_count=missing`
    - `stage_visual_proof_receipt_count=missing`
    - `matching_promoted_stage_visual_proof_receipt_count=missing`
    - `stage_startup_smoke_receipt_count=missing`
    - `matching_promoted_stage_startup_smoke_receipt_count=missing`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-09T04:27:17Z`
    - `status=not_running`
    - `pid=missing`
    - `process_alive=False`
    - `matching_process_count=0`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=pass`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-09T04:27:17Z`
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-09T04:28:46Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=2`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from the current blocker sheet
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
    - incorporate the updated LTD goal to make 1min.AI, Teable, and vexp.dev the core operating trio for background capacity, cockpit proof debt, and cross-repo opportunity index
    - treat `WHAT_WE_MISSED_LTD_UTILIZATION_OPPORTUNITIES_FOR_CHUMMER6_EXECUTIVE_ASSISTANT.md` and `LTD_UTILIZATION_MATRIX.md` as active design inputs
    - do not alter flagship-ready claims while any root blocker remains
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T15:13:58+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/auto_import_windows_installer_gold_proof.py`:
  - non-preferred `*windows-installer-gold-proof*.zip` bundles are no longer ignored just because the filename differs from the preferred drop name
  - the auto-importer now inspects zip candidates by embedded proof contents before treating them as ready, using the bundled visual-source digest and startup receipt semantics instead of filename shape alone
  - exact-name zips still fail closed if they are malformed, but a valid differently named bundle can now clear the blocker without a manual rename step
  - waiting receipts now report `matching_promoted_zip_candidate_count` from import-ready zip proof truth rather than exact filename equality
- Regression coverage landed in `tests/test_windows_installer_visual_audit.py`:
  - invalid generic zip candidates still stay non-actionable
  - valid non-preferred zip bundles now auto-select when their embedded proof matches the promoted installer digest
  - mixed candidate discovery now prefers a valid matching directory over a corrupt preferred-name zip
  - waiting payload coverage now includes matching promoted zip candidates
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'generic_zip or matching_nonpreferred_zip or without_path_rglob or waiting_payload_surfaces_matching_directory_candidates or waiting_payload_surfaces_matching_zip_candidates or main_writes_fail_receipt_for_invalid_selected_bundle'` -> `6 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py` -> `79 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py -k 'windows_installer_visual_audit_semantic_contradictions'` -> `1 passed`
  - `python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json --wait-seconds 0 --refresh-intake-request` -> `waiting`; refreshed receipt still reports `actionable_candidate_count=0`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - a valid gold-proof zip no longer has to be renamed to the preferred filename before the watcher/importer can use it
    - the blocker is still external: there is still no matching zip or directory candidate in the watched roots
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - Windows auto-import zip readiness now follows embedded proof truth instead of exact filename equality
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T14:37:57+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/verify_windows_installer_visual_audit.py`:
  - the Windows source audit no longer trusts the raw intake-request `status` when it reports `proof_request_status`
  - `proof_request_status` is now derived from the current in-memory audit failures; the raw intake-request status is preserved separately as `proof_request_raw_status`
  - this means a stale raw `not_required` receipt no longer suppresses the “gold proof artifact is still missing” failure when the live audit still fails
  - it also means a stale raw `external_artifact_required` receipt no longer leaves the source audit implying proof follow-up after the live audit already passes
  - embedded `operator_request_artifacts` now carry `request_effective_status` and `operator_action_still_required` that match the current audit truth
- Regression coverage landed in `tests/test_windows_installer_visual_audit.py`:
  - digest-mismatch Windows audit now proves that stale raw `not_required` still yields effective `external_artifact_required`
  - passing Windows audit now proves that stale raw `external_artifact_required` yields effective `not_required`
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/verify_windows_installer_visual_audit.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'digest_mismatch_surfaces_missing_bundle_and_auto_import_hint_details or passing_visual_audit_ignores_stale_external_artifact_required_request_status'` -> `2 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py` -> `77 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py -k 'windows_installer_visual_audit_semantic_contradictions'` -> `1 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - `proof_request_status` in the Windows source audit now reflects effective current audit truth, with the raw request status retained only for diagnostics
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T14:31:13+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening expanded across the Windows request/operator surfaces:
  - `scripts/verify_windows_installer_visual_audit_intake_request.py`
    - the verifier now exposes effective request truth from the live `current_blocker.receipt`, not just the raw intake-request status
    - `operator_action_still_required` and `effective_status` now follow the live audit state
    - the live-audit pass check now fail-closes not only digest-flag contradictions but also broader pass-shaped semantic contradictions such as artifact-byte mismatch, incompatible-host startup receipts, non-Windows visual sources, incomplete surfaces, and too-low screenshot counts
  - `scripts/materialize_operator_release_dashboard.py`
    - the Windows operator-request surface now applies verifier truth after loading the raw receipt
    - if a stale raw `not_required` receipt is contradicted by the live audit, hidden Windows operator actions are restored instead of staying suppressed
  - `scripts/final_gold_janitor.py`
    - the final gold janitor now imports and applies the Windows intake-request verifier before shaping operator-request artifacts
    - Windows request visibility in the final gold verdict now follows effective verifier truth instead of raw receipt status
  - `scripts/materialize_release_ready_receipt.py`
    - shared operator-action suppression/restore logic now honors `request_effective_status` when present
- Regression coverage landed in:
  - `tests/test_windows_installer_visual_audit.py`
    - stale `not_required` and stale `external_artifact_required` Windows request receipts now assert effective-status behavior
  - `tests/test_operator_release_dashboard_participate_billing.py`
    - restored Windows operator actions are covered when verifier truth requires follow-up
  - `tests/test_final_gold_janitor.py`
    - restored Windows operator actions are covered when verifier truth requires follow-up
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/verify_windows_installer_visual_audit_intake_request.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_operator_release_dashboard.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/final_gold_janitor.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py` -> `76 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py` -> `58 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_final_gold_janitor.py` -> `88 passed, 9 subtests passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - Windows operator-request visibility now follows verifier-effective truth across the dashboard and final-gold surfaces
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T14:18:39+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/verify_windows_installer_visual_audit_intake_request.py`:
  - the Windows intake-request verifier no longer trusts the request receipt `status` on its own
  - it now cross-checks the live `current_blocker.receipt` Windows audit payload and fail-closes stale `not_required` receipts when the live audit still fails semantically
  - it also fail-closes stale `external_artifact_required` receipts when the live audit is already semantically pass
  - verifier results now expose the live audit path, effective-pass state, raw status, and semantic issue list for downstream debugging
- Regression coverage landed in `tests/test_windows_installer_visual_audit.py`:
  - stale `not_required` request with semantically failing live audit now fails verification
  - stale `external_artifact_required` request with semantically passing live audit now fails verification
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/verify_windows_installer_visual_audit_intake_request.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'stale_not_required_when_live_audit_fails or stale_external_artifact_required_when_live_audit_passes or accepts_structural_recovery_pack'` -> `3 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py` -> `76 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - the Windows intake-request verifier now cross-checks the live audit receipt before accepting `not_required` or `external_artifact_required`
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T14:10:06+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/auto_import_windows_installer_gold_proof.py`:
  - the auto-import waiting payload no longer marks digest-matching stage startup-smoke receipts as “startup already proven” from `status=pass` alone
  - pass-shaped matching startup receipts now fail closed there when embedded failures or failed gates contradict the top-level pass shape
  - the waiting note now says startup is already proven only when a matching stage receipt is semantically clean; otherwise it explicitly says not to treat the matching receipt as startup proof
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'startup_smoke_receipt_hints_separately or rejects_pass_shaped_stage_startup_receipt'` -> `2 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py` -> `74 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - the auto-import waiting payload now fail-closes pass-shaped stage startup hints before telling the operator startup is already proven
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T14:05:42+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/materialize_windows_installer_visual_audit_intake_request.py`:
  - the Windows intake-request materializer no longer marks the operator proof request `not_required` from `WINDOWS_INSTALLER_VISUAL_AUDIT.status=pass` alone
  - pass-shaped Windows audit receipts now fail closed there when nested promoted-digest or nested receipt-status fields contradict the top-level pass shape
  - this keeps the operator ask / recovery-pack lane aligned with the stricter verifier, dashboard, final gold janitor, Teable exporter, blocker generator, readonly snapshot audit, and flagship handoff
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_windows_installer_visual_audit_intake_request.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'materialize_windows_installer_visual_audit_intake_request_keeps_external_blocker_honest or materialize_windows_installer_visual_audit_intake_request_rejects_pass_shaped_audit_wrapper or materialize_windows_installer_visual_audit_intake_request_resolves_relative_output_path'` -> `3 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py` -> `73 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - the Windows intake-request materializer now fail-closes pass-shaped Windows audit wrappers with nested contradictions
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T14:00:36+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/sync_important_work_to_teable.py`:
  - the Teable/live-ops important-work exporter no longer treats `WINDOWS_INSTALLER_VISUAL_AUDIT.status=pass` as sufficient on its own
  - pass-shaped Windows audit receipts now fail closed there when nested promoted-digest or nested receipt-status fields contradict the top-level pass shape
  - this keeps Teable/operator planning surfaces aligned with the stricter blocker generator, dashboard, final gold janitor, flagship verifier, readonly snapshot audit, and flagship handoff
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/sync_important_work_to_teable.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_teable_important_work_projection.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_teable_important_work_projection.py -k 'windows_installer_rows_track_passing_visual_audit or windows_installer_rows_track_visual_audit_digest_mismatch or reject_pass_shaped_visual_audit_with_nested_digest_mismatch'` -> `3 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_teable_important_work_projection.py` -> `25 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - the Teable/live-ops exporter now fail-closes pass-shaped Windows audit wrappers with nested contradictions
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T13:57:01+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/release/_release_gate_common.py`:
  - the canonical blocker/snapshot generator no longer trusts `WINDOWS_INSTALLER_VISUAL_AUDIT.status=pass` alone inside `release_truth_state(...)`
  - pass-shaped Windows audit receipts now fail closed there when nested promoted-digest or nested receipt-status fields contradict the top-level pass shape
  - this prevents `current_release_snapshot()` and `RELEASE_BLOCKERS.generated.json` from silently dropping the Windows blocker if a future receipt arrives as a pass-shaped wrapper with only nested contradictions
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/release/_release_gate_common.py`
  - `python3 -m py_compile /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py -k 'pass_shaped_windows_visual_audit_with_nested_digest_mismatch or release_truth_blockers or release_truth_failed_receipts'` -> `2 passed`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `37 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - the canonical blocker generator now fail-closes pass-shaped Windows audit wrappers with nested contradictions
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T13:47:12+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/release/audit_public_release_snapshot_readonly.py`:
  - the authoritative readonly launch-truth audit no longer trusts `WINDOWS_INSTALLER_VISUAL_AUDIT.status=pass` alone
  - `windows_audit_release_truth_pass(...)` now fail-closes pass-shaped Windows audit receipts when nested promoted-digest or nested receipt-status fields contradict the top-level pass shape
  - this aligns the authoritative snapshot auditor with the stricter Windows truth already enforced in the flagship verifier, release-ready materializer, operator dashboard, final gold janitor, and flagship handoff
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/release/audit_public_release_snapshot_readonly.py`
  - `python3 -m py_compile /docker/chummercomplete/tests/test_public_release_snapshot_readonly_audit.py`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_readonly_audit.py` -> `11 passed`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `36 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - the authoritative readonly snapshot audit is now stricter about pass-shaped Windows wrappers with nested digest contradictions
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T13:42:49+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T11:43:15Z`
    - `load_status=loaded`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-07T11:43:01Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T11:43:20Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T11:43:20Z`
    - `status=running`
    - `pid=2639572`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T11:43:20Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-07T05:01:36Z`
    - `message_ids=3525`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-07T11:43:18Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-07T11:43:20Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-07T11:43:20Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=6`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- Runtime caveat: the long-running Windows proof watcher may advance the standalone auto-import/watcher receipts after the canonical blocker snapshot; treat `RELEASE_BLOCKERS.generated.json` as the blocker-truth anchor.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T13:36:09+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T11:37:25Z`
    - `load_status=loaded`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-07T11:36:50Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T11:37:31Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T11:37:31Z`
    - `status=running`
    - `pid=2639572`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T11:37:31Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-07T05:01:36Z`
    - `message_ids=3525`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-07T11:37:30Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-07T11:37:31Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-07T11:37:32Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=6`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- Runtime caveat: the long-running Windows proof watcher may advance the standalone auto-import/watcher receipts after the canonical blocker snapshot; treat `RELEASE_BLOCKERS.generated.json` as the blocker-truth anchor.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T13:24:55+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/materialize_release_ready_receipt.py`:
  - nested `current_receipt_states()` rows now have focused regression coverage for pass-shaped contradictory receipts that must fail closed while preserving `raw_status`
  - nested `current_blocking_gate_artifacts()["public_release_snapshot_readonly_audit"]` now has focused regression coverage for pass-shaped contradictory snapshot-audit payloads, with effective `status=fail`, preserved `raw_status=pass`, and `pass=False`
  - workspace-portal release-channel drift assertions in `tests/test_materialize_release_ready_receipt.py` now follow the authoritative `display_path(...)` behavior instead of assuming raw absolute temp paths
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/tests/test_materialize_release_ready_receipt.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_materialize_release_ready_receipt.py -k 'fail_close_pass_shaped'` -> `2 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_materialize_release_ready_receipt.py` -> `40 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - release-ready receipt coverage is now stricter about pass-shaped contradictory nested receipts and drift-path display normalization
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T13:13:14+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T11:14:10Z`
    - `load_status=loaded`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-07T11:13:50Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T11:14:19Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T11:14:19Z`
    - `status=running`
    - `pid=2639572`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T11:14:19Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-07T05:01:36Z`
    - `message_ids=3525`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-07T11:14:17Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-07T11:14:19Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-07T11:14:19Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=6`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- Runtime caveat: the long-running Windows proof watcher may advance the standalone auto-import/watcher receipts after the canonical blocker snapshot; treat `RELEASE_BLOCKERS.generated.json` as the blocker-truth anchor.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T12:51:17+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/release/_release_gate_common.py`:
  - synthesized `desktop_update_rollback_revoke` no longer hardcodes `status=pass`
  - it now derives pass vs `review_required` from current primary desktop route truth and records route counts for audit visibility
  - this closes a gap where a channel with no promoted primary desktop tuple could otherwise keep the route/update alias green and avoid a `proof:desktop_update_rollback_revoke` blocker
  - focused regression landed in `tests/test_public_release_snapshot_truth_gate.py`
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/release/_release_gate_common.py`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `35 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - synthesized route/update proof truth is now stricter about missing promoted primary desktop routes
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T12:36:13+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/release/_release_gate_common.py`:
  - synthesized desktop alias receipts now fail closed on pass-shaped contradictory component receipts instead of inheriting raw component `status` fields
  - `desktop_first_minute_gate` now records both effective status and raw source status
  - `desktop_gold_gate` now derives component and aggregate status from fail-closed component truth while preserving raw source status separately for audit visibility
  - `proof_state(...)` now honors alias-declared `source_status` / `sourceStatus`, so aggregate proof rows can show raw-vs-effective truth instead of collapsing them
  - this closes a gap where `desktop_gold_gate` could otherwise stay apparently green while one of its source receipts was only pass-shaped
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/release/_release_gate_common.py`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `34 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - synthesized proof aliases are now stricter about pass-shaped contradictory component receipts
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T12:25:32+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/release/_release_gate_common.py`:
  - `proof_state(...)` no longer treats published proof receipts as passing on `status=pass` alone
  - contradictory pass-shaped proof receipts now fail closed when they carry `failures` or `failed_gates`, while preserving the raw source status separately for audit visibility
  - this closes a gap where `current_release_snapshot()` could otherwise let pass-shaped proof receipts evade the `failing_proofs` / `proof:*` blocker path
  - focused regressions landed in `tests/test_public_release_snapshot_truth_gate.py`
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/release/_release_gate_common.py`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `34 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - proof freshness / blocker materialization is now stricter about pass-shaped contradictory proof receipts
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T12:15:01+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `scripts/release/_release_gate_common.py`:
  - live public-edge runtime observations no longer count as passing on `status=pass` alone
  - contradictory pass-shaped runtime observations now fail closed when they carry blocking findings or a non-zero observer exit code
  - `public_edge_release_truth_state(...)` now also rechecks the runtime observation shape before trusting it, so monkeypatched or future observer payloads cannot clear release truth by `status=pass` alone
  - focused regressions landed in `tests/test_public_release_snapshot_truth_gate.py`
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/release/_release_gate_common.py`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `32 passed`
  - no new canonical blocker snapshot was accepted in this slice; blocker truth still anchors to the previously published receipts
- Operator caution:
  - `python3 scripts/release/_release_gate_common.py --help` is not a help path; the script ignores CLI args and starts the full blocker materializer chain
  - an accidental invocation was interrupted and is not part of release truth for this slice
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - live public-edge runtime truth is now stricter about pass-shaped contradictory observations
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T12:04:49+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `chummer.run-services/scripts/verify_flagship_product_readiness_gate.py`:
  - `release_ready_gate_failures(...)` no longer drops per-gate `RELEASE_READY` failure detail on `status=pass` alone
  - contradictory pass-shaped wrappers now keep gate detail when `failures` or `failed_gates` are present, so current live release-truth summaries do not silently lose nested blocker evidence
  - focused regression added in `chummer.run-services/tests/test_flagship_product_readiness_gate.py` for pass-shaped Windows wrapper detail preservation
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/verify_flagship_product_readiness_gate.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_flagship_product_readiness_gate.py` -> `21 passed`
  - standalone verifier rerun still failed with the same launch-blocker families and `launch_critical_nested_blocker_count=6`; this did not change blocker truth
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - live release-truth summaries are now stricter about contradictory pass-shaped `RELEASE_READY` wrappers
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T11:57:37+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T09:58:17Z`
    - `load_status=loaded`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-07T09:57:56Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T09:58:23Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T09:58:23Z`
    - `status=running`
    - `pid=2639572`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T09:58:23Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-07T05:01:36Z`
    - `message_ids=3525`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-07T09:58:21Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-07T09:58:23Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-07T09:58:24Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=6`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- Runtime caveat: the long-running Windows proof watcher may advance the standalone auto-import/watcher receipts after the canonical blocker snapshot; treat `RELEASE_BLOCKERS.generated.json` as the blocker-truth anchor.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:59:04+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane consistency hardening landed in `scripts/materialize_codex_flagship_handoff.py`:
  - the shared handoff/web-book materializer now refreshes `FLAGSHIP_PRODUCT_READINESS_GATE.generated.json` after the live release-controller chain, not before it
  - this keeps the Codex read-aloud surfaces aligned with the freshest blocker snapshot instead of a pre-chain flagship-gate view
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/scripts/materialize_codex_flagship_handoff.py`
  - `pytest -q /docker/chummercomplete/tests/test_materialize_codex_flagship_handoff.py` -> `8 passed`
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - shared Codex truth surfaces are tighter, but release truth is still not cleared
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:55:40+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane hardening landed in `chummer.run-services/scripts/verify_flagship_product_readiness_gate.py`:
  - the fallback release-truth wrapper path no longer treats a pass-shaped `RELEASE_READY.generated.json` as trustworthy on `status=pass` alone
  - it now requires the release-ready receipt semantics already enforced elsewhere, including the exact `RELEASE_READY` verdict
  - when direct release-truth receipts are missing, a pass-shaped release-ready wrapper with an unexpected verdict now remains launch-blocking instead of silently clearing the fallback path
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/verify_flagship_product_readiness_gate.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_flagship_product_readiness_gate.py` -> `18 passed`
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - fallback wrapper semantics are tighter, but release truth is still not cleared
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:51:36+02:00)

- Canonical live handoffs for the release/controller lane remain:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
- Repo-local `NEXT_SESSION_HANDOFF.md` files were reread across `_scratch`, `_work`, deploy mirrors, and adjacent repos. They are older lane-local history and do not override release truth.
- Current root blocker truth remains exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Runtime note:
  - `WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json` advanced to `generated_at_utc=2026-07-07T08:49:35Z` and still reports `status=waiting_for_artifact`
  - `RELEASE_BLOCKERS.generated.json` remains the blocker-truth anchor at `generated_at=2026-07-07T08:48:31Z`
- Prior in-flight controller sessions are no longer running:
  - `95541` gone
  - `56084` gone
  - `28843` gone
- Controller-lane audit in this slice:
  - reread `chummer.run-services/scripts/materialize_release_ready_receipt.py`
  - reread `chummer.run-services/scripts/verify_flagship_product_readiness_gate.py`
  - no additional release-blocking or release-truth reader in the canonical blocker path was found that still accepts a contract-defined pass receipt on `status=pass` alone
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane:
    - no blocker-shape change
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:48:10+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T08:48:31Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-07T08:48:20Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T08:48:34Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T08:48:34Z`
    - `status=running`
    - `pid=2639572`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T08:48:34Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-07T05:01:36Z`
    - `message_ids=3525`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-07T08:48:33Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-07T08:48:34Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-07T08:48:34Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=6`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- Runtime caveat: the long-running Windows proof watcher may advance the standalone auto-import/watcher receipts after the canonical blocker snapshot; treat `RELEASE_BLOCKERS.generated.json` as the blocker-truth anchor.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:38:04+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane dashboard hardening continued:
  - `DESIGN_QUALITY_GATE` is release-blocking in the operator dashboard and its producer contract emits `DESIGN_READY` / `DESIGN_NOT_READY`
  - `chummer.run-services/scripts/materialize_operator_release_dashboard.py` now rejects pass-shaped design-gate receipts unless `verdict=DESIGN_READY`
  - the operator-dashboard test fixtures were normalized to the real design-gate contract verdict
  - focused regression landed in `chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py`
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_operator_release_dashboard.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py` -> `54 passed`
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - continue only if another release-blocking or truth-reader receipt has a contract-defined pass verdict that is still accepted on `status=pass` alone
    - do not claim flagship-ready and do not advance stable promotion while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:34:21+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane dashboard hardening landed after the adjacent pass-verdict audit:
  - `PUBLIC_EDGE_POSTDEPLOY_GATE` and `PUBLIC_COPY_LEAK_GATE` were re-audited and do not define a top-level pass verdict, so no verdict gate was added there
  - `PARTICIPATE_BILLING_HONESTY` and `ACCOUNT_HANDOFF_RUNTIME_CONFIG` do define `READY` / `NOT_READY`, and `chummer.run-services/scripts/materialize_operator_release_dashboard.py` now rejects pass-shaped receipts whose verdict is not exactly `READY`
  - focused regressions landed in `chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py`
- Verification completed for this controller slice:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_operator_release_dashboard.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py` -> `53 passed`
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - continue only if another release/controller receipt has a contract-defined pass verdict that is still accepted on `status=pass` alone
    - do not claim flagship-ready and do not advance stable promotion while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:29:24+02:00)

- No blocker-shape change. Root blockers remain exactly:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Shared release truth remains:
  - startup proof already matches the promoted digest
  - manual Windows installer success remains corroborating runtime information only; it does not clear release truth
  - missing proof bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Controller-lane receipt-reader hardening landed:
  - `scripts/release/_release_gate_common.py` now requires the expected pass verdicts when reader-level truth evaluates wrapper receipts
  - `scripts/release/audit_public_release_snapshot_readonly.py` now enforces the same expected pass verdicts in the readonly audit
  - `FINAL_GOLD_JANITOR` only reads pass-shaped when `status` is pass-like and `verdict=GOLD_READY`
  - `RELEASE_READY` only reads pass-shaped when `status` is pass-like and `verdict=RELEASE_READY`
  - focused regressions landed in:
    - `tests/test_public_release_snapshot_truth_gate.py`
    - `tests/test_public_release_snapshot_readonly_audit.py`
- Verification completed for this controller slice:
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_readonly_audit.py` -> `8 passed`
  - `pytest -q /docker/chummercomplete/tests/test_public_release_snapshot_truth_gate.py` -> `29 passed`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_materialize_release_ready_receipt.py /docker/chummercomplete/chummer.run-services/tests/test_final_gold_janitor.py /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py` -> `170 passed`
  - canonical receipts and handoffs were refreshed afterward
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle from the missing promoted proof path
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain already recorded in the canonical receipts
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - continue a narrow audit of adjacent pass-verdict contracts only:
      - `PUBLIC_EDGE_POSTDEPLOY_GATE`
      - `PUBLIC_COPY_LEAK_GATE`
      - `PARTICIPATE_BILLING_HONESTY`
      - `ACCOUNT_HANDOFF_RUNTIME_CONFIG`
    - do not claim flagship-ready and do not advance stable promotion while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T10:26:45+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T08:27:09Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-07T08:26:59Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T08:27:14Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=0`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T08:27:14Z`
    - `status=running`
    - `pid=2639572`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T08:27:14Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-07T05:01:36Z`
    - `message_ids=3525`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-07T08:27:12Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-07T08:27:14Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-07T08:27:13Z`
    - `status=fail`
    - `verdict=NOT_FLAGSHIP_PRODUCT_READY`
    - `launch_critical_nested_blocker_count=6`
    - `coverage_gap_keys=none`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- Runtime caveat: the long-running Windows proof watcher may advance the standalone auto-import/watcher receipts after the canonical blocker snapshot; treat `RELEASE_BLOCKERS.generated.json` as the blocker-truth anchor.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T05:16:46+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `proof:ui_localization_release_gate`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-07T03:16:46Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - stable promotion guard: The public_stable publisher fails closed unless RELEASE_BLOCKERS.generated.json is fresh and contains no root blockers other than release_posture:non_flagship_channel.
      - `stable_promotion_guard_max_age_seconds=86400`
      - `stable_promotion_guard_env=CHUMMER_PUBLIC_STABLE_BLOCKERS_MAX_AGE_SECONDS`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-07T02:41:06Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=9`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=28`
    - `matching_promoted_stage_startup_smoke_receipt_count=3`
    - stale directory digest summary sample: `digest=c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51 count=9 sample_path=/tmp/windows-installer-gold-proof-27864339393`
    - auto-import directory note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-07T03:16:46Z`
    - `status=not_running`
    - `pid=missing`
    - `process_alive=False`
    - `matching_process_count=0`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-07T02:41:06Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-07T04:57:10+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - aligned the desktop-home recent-workspace intro, empty-state note, recents heading, and open/help action labels with the current dossier wording across the shipped locales by updating `DesktopLocalizationCatalog.cs` for `en-us`, `de-de`, `fr-fr`, `ja-jp`, `pt-br`, and `zh-cn`.
  - this removed the remaining stale runner/workspace wording from `desktop.home.section.recent_workspaces`, `desktop.home.intro.ready_recent_workspaces`, `desktop.home.workspace_summary.empty`, `desktop.home.button.open_current_workspace`, `desktop.home.button.open_work_support`, and `desktop.home.button.open_workspace_followthrough`.
  - expanded `DesktopLocalizationCatalogTests` so the direct localization proof now pins the exact dossier-facing strings for both the recent-workspace copy and the desktop-home action labels across the shipped locales.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)` in `1m 47.93s`, and the focused localization direct `Chummer.Tests` pack finished `14 total`, `14 succeeded`, `0 failed`, `0 skipped` in `7s 090ms`.
  - this strengthens repo-local desktop-home wording parity only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:43:59+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - aligned the public preview/browser-shell import and staging labels with the current dossier/staging naming by changing `Preview.razor` to `Import an existing dossier`, `Open Dossier`, `Open Print Staging`, `Open Export Staging`, `Keep recent dossiers one click away`, and `Bring desktop and self-hosted dossier files forward.`
  - refreshed the direct preview proof in `PublicPreviewSurfaceTests` and the preview-source compliance guard in `MigrationComplianceTests` to pin those labels.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)` in `3m 07.67s`, and the focused preview direct `Chummer.Tests` pack finished `257 total`, `257 succeeded`, `0 failed`, `0 skipped` in `20s 892ms`.
  - this strengthens repo-local public preview/browser-shell wording parity only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:36:49+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - aligned the startup-workbench copy with the dossier-open shell language by changing the intro to `reopen a saved dossier`, the recents heading to `Recent Dossiers`, the empty-state note to `No recent dossiers yet`, and the recent-item subtitle to `Restore this Chummer Online dossier continuation.`
  - refreshed the direct BUnit proof so the populated and empty startup-workbench states now pin that dossier wording.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)` in `1m 30.26s`, and the focused startup-workbench direct `Chummer.Tests` pack finished `2 total`, `2 succeeded`, `0 failed`, `0 skipped` in `1s 614ms`.
  - this strengthens repo-local startup-workbench wording consistency only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:32:11+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - aligned the classic shell labels for local open/print/export with the current dossier and staging language by changing `ShellChromeBoundary` to `Open Dossier...`, `Open Print Staging...`, and `Open Export Staging...`.
  - updated the startup-workbench empty-recents note in `SectionPane.razor` to match that same `Open Dossier...` wording.
  - expanded the focused direct proof so `DesktopInstallLinkingShellChromeTests` now pins the three shell labels, and `BlazorShellComponentTests` now pins the empty-recents startup note.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)` in `3m 43.54s`, and the focused shell/UI direct `Chummer.Tests` pack finished `29 total`, `29 succeeded`, `0 failed`, `0 skipped` in `652ms`.
  - this strengthens repo-local shell wording and startup-workbench copy parity only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:26:46+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - aligned the classic shell `character_settings` label with the rest of the current product surface by changing `ShellChromeBoundary` from `Runner Settings` to `Character Settings`.
  - expanded the existing direct shell-chrome proof so `DesktopInstallLinkingShellChromeTests` now also pins the `character_settings` wording alongside `runtime_inspector` and the newer rules-data commands.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, and the focused shell-chrome direct `Chummer.Tests` pack finished `28 total`, `28 succeeded`, `0 failed`, `0 skipped` in `819ms`.
  - this strengthens repo-local shell-chrome wording parity only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:22:46+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - fixed the missing classic-shell `runtime_inspector` label in `Chummer.Presentation/UiKit/ShellChromeBoundary.cs`, so the desktop shell no longer falls back to the lowercased raw command id.
  - added direct presenter-side proof in `DesktopInstallLinkingShellChromeTests` that `ShellChromeBoundary.FormatCommandLabel(...)` stays human-facing for `runtime_inspector` and the newer rules-data commands.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, and the focused shell-chrome direct `Chummer.Tests` pack finished `28 total`, `28 succeeded`, `0 failed`, `0 skipped` in `637ms`.
  - this strengthens repo-local shell-chrome fidelity only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:19:43+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - expanded the repo-local shell portability guard so `scripts/publish-download-bundle-http.sh` is now pinned alongside the manifest/build/S3/verify scripts.
  - the new guard locks the bash3-safe `array_count()` / `array_values_nul()` usage, the `windows_payload_gate_args_count` and `upload_file_count` branches, and the NUL-safe direct-upload loop while forbidding the old raw array-length checks and array `for` loop.
  - the same focused pack re-verified the portable release-channel normalization in `generate-releases-manifest.sh` and the public-stable root-blocker fail-closed contract.
  - verification: the focused script pack passed `bash -n` for `build-desktop-installer.sh`, `generate-releases-manifest.sh`, `publish-download-bundle-http.sh`, `publish-download-bundle-s3.sh`, and `verify-releases-manifest.sh`; the focused Python pack finished `5 passed`, `40 deselected` in `0.25s`.
  - this strengthens repo-local release-script portability and public-stable blocker guardrails only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:15:16+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller verification slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - added direct presenter proof that `print_preview` uses the print receipt lane and that the rules-data commands publish their shared notice without an open workspace.
  - re-verified the retryable download/export/print receipt path in `DesktopShellDownloadDispatchTests` and the shared command-policy additions in `OverviewCommandPolicyTests`.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, and the focused shell/dispatcher direct `Chummer.Tests` pack finished `43 total`, `43 succeeded`, `0 failed`, `0 skipped` in `1s 644ms`.
  - this strengthens repo-local shell/dispatcher evidence only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:11:59+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - added a focused repo-local portability guard for the new bash3-safe `upper_ascii()` path in `scripts/ai/milestones/materialize-desktop-executable-exit-gate.sh`, so tuple-specific receipt paths stay portable without bash4 `^^` expansion.
  - re-verified the `publish-download-bundle.sh` public-stable blocker-clearance contract in the same focused pack.
  - verification: `bash -n` passed for `materialize-desktop-executable-exit-gate.sh` and `publish-download-bundle.sh`; the focused Python pack covering the new executable-gate portability guard, the existing milestone collector guard, and the public-stable blocker-clearance contract finished `3 passed`, `25 deselected`.
  - this strengthens repo-local release-script portability and publication guardrails only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:09:47+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller verification slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - re-verified the current Origin Dossier remount/scroll-restore lane after the latest `App.razor` and `DesktopDialogWindow.axaml.cs` changes.
  - the focused pack covered Blazor dialog-host persistence plus Avalonia origin-dialog contrast/anchor proofs, including the active-field-anchor preference and the longer transient refresh grace window.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, and the focused origin-dialog direct `Chummer.Tests` pack finished `22 total`, `22 succeeded`, `0 failed`, `0 skipped` in `12s 884ms`.
  - this strengthens repo-local dialog/UI evidence only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:07:22+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller verification slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - re-verified the PWA/public-edge/browser-shell contract lane with the focused repo-local Python pack covering `test_blazor_pwa_contract.py`, `test_blazor_public_edge_execution_contract.py`, `test_desktop_release_matrix_gate.py`, and `test_public_windows_payload_metadata.py`.
  - also parse-checked `scripts/e2e-public-edge-playwright.cjs` after the latest retry and continuation-query changes.
  - verification: `node --check scripts/e2e-public-edge-playwright.cjs` parsed cleanly, and the focused Python contract pack finished `18 passed`.
  - this strengthens repo-local contract evidence only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T04:05:22+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - re-verified the current public-route/browser-shell lane with the focused `AppRouteSurfaceTests` + `PublicPreviewSurfaceTests` + `PortalAppRouteContractTests` + `AppShellBaseHrefTests` direct binary pack and the live portal/runtime Python pack; both stayed green on the current tree.
  - added repo-local regression coverage at `tests/test_workflow_family_execution_receipts_contract.py` for the local-API autostart and missing-API retry contract inside `scripts/ai/milestones/materialize-sr-workflow-family-execution-receipts.sh`.
  - the same test also pins the SR6 workflow parity wrapper chain in `scripts/ai/milestones/sr6-desktop-workflow-parity-check.sh`, so the execution/verification/aggregate workflow-family materializers remain guarded behind the single skip switch and lock path.
  - verification: the focused route/base-href direct `Chummer.Tests` pack finished `756 total`, `756 succeeded`, `0 failed`, `0 skipped` in `22s 322ms`; the portal/runtime Python pack finished `12 passed`; the two workflow-family scripts passed `bash -n`; and the new contract test plus the existing desktop executable gate contract test finished `4 passed`.
  - this hardens repo-local route/runtime and script-regression coverage only; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T03:59:58+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller verification slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - brought up `chummer-api` locally so the previously skipped dual-head parity class could run as a real receipt instead of external runtime fallout.
  - verified the API on host port `8088`, then normalized the remaining volatile ids in `Chummer.Tests/Presentation/DualHeadAcceptanceTests.cs` for the `Runner:` export preview token and `autoAliceWorkspaceId`.
  - this turned the old `DualHeadAcceptanceTests` skip bucket into a clean pass and upgraded the full Presentation receipt from `1587 succeeded / 30 skipped` to a complete no-skip proof.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, the isolated dual-head receipt at `/tmp/chummer_dual_head_20260707_r3.log` finished `30 total`, `30 succeeded`, `0 failed`, `0 skipped` in `2m 16s 161ms`, and the authoritative full Presentation receipt at `/tmp/chummer_presentation_full_20260707_r4.log` finished `1617 total`, `1617 succeeded`, `0 failed`, `0 skipped` in `6m 23s 060ms`.
  - this strengthens only repo-local product verification; it does not change the shared Windows visual-audit blocker or release posture.

## Handoff refresh (2026-07-07T03:30:42+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller verification slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - added `Chummer.Tests/Presentation/AvaloniaHeadlessSessionGate.cs` and wired it into `Chummer.Tests/Chummer.Tests.csproj`.
  - moved the remaining Avalonia-only test harnesses onto gated `HeadlessUnitTestSession` execution so the full Presentation pack no longer flakes on `Call from invalid thread` across `AvaloniaFlagshipUiGateTests`, `DesktopWindowContrastTests`, `DesktopTrustPanelFactoryTests`, and `AvaloniaHeadlessSmokeTests`.
  - refreshed stale Presentation assertions to current product truth across the claim/support/workflow parity tests plus `CharacterOverviewPresenterTests`, `DesktopHomeCampaignProjectorTests`, and the desktop foreground-contract gate.
  - verification: `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, the focused stale/contrast pack finished `84 passed`, the interference-heavy headless pack finished `28 passed`, and the authoritative full Presentation receipt at `/tmp/chummer_presentation_full_20260707_r3.log` finished `1617 total`, `1587 succeeded`, `0 failed`, `30 skipped` in `6m 07s 638ms`.
  - the `30` skips remain the external `DualHeadAcceptanceTests` `chummer-api:8080` socket availability issue (`Resource temporarily unavailable`), not a blocker change for release truth in this repo slice.

## Handoff refresh (2026-07-07T02:26:51+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hardened `scripts/ai/day1-p1-setup.sh` to remove its remaining bash4-only constructs.
  - the setup script now uses `collect_solution_projects()` plus `array_contains_exact()` instead of `mapfile` and associative-array lookup when pruning and re-adding projects in `Chummer.Presentation.sln`.
  - added `tests/test_day1_setup_bash_portability.py` and verified the combined portability micro-pack, then re-scanned `scripts/` plus `scripts/ai`; there are now no remaining `mapfile`, `readarray`, or associative-array hits in that tree.
  - verification: setup script passed `bash -n`, the new focused setup portability test finished `1 passed`, the combined portability micro-pack finished `6 passed`, and the repo-wide portability grep returned no matches.
  - this slice widened slightly beyond the release/proof lane because milestone checks and `day1-p1-run.sh` still route through this helper setup path.

## Handoff refresh (2026-07-07T02:24:36+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - removed the remaining release-lane associative-array set from `scripts/materialize-linux-desktop-exit-gate.sh`.
  - `prune_old_run_roots()` now uses a temp-file-backed keep-list plus `grep -Fqx` membership checks instead of `declare -A keep_roots`, keeping the Linux desktop exit gate on the same bash3-safe portability posture as the rest of the hardened release scripts.
  - expanded `tests/test_desktop_exit_gate_bash_portability.py` with a Linux-specific guard that pins the new keep-list pattern and forbids the old associative-array set.
  - verification: the Linux exit gate passed `bash -n`, the exit-gate portability test finished `2 passed`, and the combined portability micro-pack finished `5 passed`.
  - remaining bash4-only scope after this slice is limited to `scripts/ai/day1-p1-setup.sh`, which is outside the active release/controller lane.

## Handoff refresh (2026-07-07T02:22:23+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - removed the remaining milestone-lane `mapfile -d ''` collector from `scripts/ai/milestones/chummer5a-ultimate-parity-tester.sh`.
  - the Chummer5a full-fixture parity tester now uses the same bash3-safe null-delimited read loop pattern as the other hardened release/proof scripts.
  - expanded `tests/test_release_gate_milestone_bash_portability.py` so the portability guard now covers the parity tester alongside the two release-gate materializers.
  - verification: the parity tester passed `bash -n`, the milestone portability test finished `1 passed`, and the combined portability micro-pack finished `4 passed`.
  - remaining `mapfile` scope after this slice is limited to `scripts/ai/day1-p1-setup.sh`, which is outside the active release/controller lane.

## Handoff refresh (2026-07-07T02:20:54+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - removed the remaining bash4 `mapfile` collectors from the milestone release-gate scripts `materialize-desktop-visual-familiarity-exit-gate.sh` and `materialize-desktop-workflow-execution-gate.sh`.
  - both scripts now use bash3-safe `while IFS= read -r ...; do array+=(...)` collectors in the same release portability style as the previously hardened publish/exit/startup scripts.
  - added `tests/test_release_gate_milestone_bash_portability.py` to keep those release-gate collectors portable and to block `mapfile -t` regressions.
  - verification: both scripts passed `bash -n`, the new focused portability test finished `1 passed`, and the combined portability micro-pack finished `4 passed`.

## Handoff refresh (2026-07-07T02:16:50+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - refreshed `tests/test_blazor_public_edge_execution_contract.py` so the release-lane Python contract matches the live `Preview.razor` route contract instead of older pre-normalization/pre-staging literals.
  - workbench committed-result assertions now pin normalized hyphenated tokens like `(_, "create-entry", "add")`, and startup-label assertions now pin the tuple-switched staging-aware labels `Open Print Staging` and `Open Export Staging`.
  - this was a test-contract correction, not a product-surface fix: the Blazor route surface already carried the intended normalization and labels.
  - verification: focused contract file finished `9 passed`, and the broader release-policy/portal/download/portability Python pack finished `68 passed`.

## Handoff refresh (2026-07-07T02:11:56+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - public `/app` and `/online` plus compatibility `/workbench` startup routes now fail closed for shared commands that require an open runner, instead of rendering optimistic shell copy and then letting the browser shell try to dispatch them.
  - the route surface now marks these continuations with `data-startup-command-state="blocked"`, withholds `DemoStartupCommandId` through `EffectiveStartupCommandId`, and renders explicit open-runner guidance for `character_settings`, `copy`, and `data_exporter`.
  - added matching public-route and compatibility-route proof that the shared shell stays visible while the presenter never receives the blocked startup command.
  - verification: `Chummer.Blazor` build succeeded with `0 Warning(s)` / `0 Error(s)`, focused `Chummer.Tests` build succeeded with `0 Warning(s)` / `0 Error(s)`, and the combined route/shell availability pack finished `132 passed`.
  - stale-binary trap: a focused `Chummer.Tests` build with `-p:BuildProjectReferences=false` can leave an older `Chummer.Blazor.dll` in `Chummer.Tests/bin` after Razor edits; rebuild `Chummer.Blazor` first or re-enable project references before treating a route-surface failure as real.
  - `dotnet test` itself still is not the authoritative receipt under the .NET 10 SDK here; the direct `Chummer.Tests` binary run remains the source of truth for this lane.

## Handoff refresh (2026-07-07T01:52:33+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - the browser desktop shell now enforces shared command availability before forwarding startup/query commands into the overview presenter bridge, so a no-workspace route can no longer dispatch `data_exporter` just because the shell surface tried to open it.
  - the same slice keeps `xml_editor` startup-safe by proving it still forwards without an open workspace while `data_exporter` stops at the shell contract boundary.
  - startup workbench component coverage no longer bypasses availability with `_ => true`; it now uses the shared evaluator for the first-class startup actions it renders.
  - verification: focused build succeeded with `0 Warning(s)` / `0 Error(s)`, and the targeted startup-shell pack (`DesktopShellStartupSyncTests` startup route pair, `BlazorShellComponentTests` startup workbench proof, `CommandAvailabilityEvaluatorTests` shared utility gating proof) finished `5 passed`.
  - `dotnet test` itself now errors under the .NET 10 SDK unless the Microsoft Testing Platform new experience is enabled, so the authoritative receipt for this slice is the direct `Chummer.Tests` binary run rather than the `dotnet test` wrapper.

## Handoff refresh (2026-07-07T01:35:21+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - aligned shared command metadata across the compatibility resolver and the hosting/SR5/SR6 catalogs so command ids no longer match while menu placement or workspace gating drifts underneath.
  - the shared shell contract now keeps `switch_ruleset` in `special`, `report_bug` / `update` / `restart` in `help`, `xml_editor` startup-safe without a workspace, and `data_exporter` gated behind an open workspace.
  - added metadata parity proof across the compatibility resolver, hosting app catalog, and SR5/SR6 shell providers, plus explicit availability proof for the `xml_editor` and `data_exporter` gating split.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, catalog resolver suite `5 passed`, command availability suite `6 passed`, focused presenter pack `3 passed`, focused factory/seam pack `2 passed`.
  - attempted extra engine-side verification on `chummer-core-engine/Chummer.Tests` for `ShellCatalogAndRulesetDetectionTests`; compilation completed, but the `dotnet test` host stalled post-build, so that wrapper run is not a completion proof for this slice.

## Handoff refresh (2026-07-07T01:19:54+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - added `runtime_inspector` to the compatibility resolver command inventory so the hosted `/workbench` fallback no longer lags the core hosting/browser diagnostics command set.
  - brought the hosting SR5 app command catalog plus the SR5/SR6 ruleset shell catalogs forward to include the missing shared browser-shell commands: `auto_alice`, `new_character_origin`, the six rules-data commands, and `show_login_video`, with the hosting catalog also restoring `exit`.
  - added a parity guard that compares compatibility command ids against `AppCommandCatalog.All` and the SR5/SR6 ruleset shell providers, plus presenter/dialog proof that `auto_alice` and `new_character_origin` stay on non-generic dialog templates.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, catalog resolver suite `4 passed`, command-policy suite `25 passed`, presenter command coverage `1 passed`, presenter non-generic dialog coverage `1 passed`, dialog factory mapped-command coverage `1 passed`, ruleset seam catalog filter proof `1 passed`.

## Handoff refresh (2026-07-07T01:04:11+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `copy` and `paste` now have explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `copy` and `paste`, relay-specific shell copy, and workspace-preserving clean `/app?workspace=...&command=copy|paste` continuations instead of letting those editor relays degrade to generic startup or profile chrome.
  - added explicit command-policy proof that `copy` and `paste` remain known shared editor-relay commands while staying outside dialog-command handling.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, focused AppShell suite `175 passed`, route/parity pack `571 passed`, command-policy suite `25 passed`.

## Handoff refresh (2026-07-07T00:53:31+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller hardening slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - refreshed the catalog-resolver compatibility inventory test so it now covers the already-shipped rules-data commands alongside the existing tool/help/action command set.
  - added explicit command-policy proof that the rules-data family and the `new_critter` / `restart` / `exit` / `close_window` / `close_all` family remain known shared commands while staying outside dialog-command handling.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, focused catalog/policy suite `26 passed`.

## Handoff refresh (2026-07-07T00:48:52+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `new_critter`, `restart`, `exit`, `close_window`, and `close_all` now have explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `new-critter`, `restart`, `exit`, `close-window`, and `close-all`, plus command-specific shell copy and clean `/app?command=...` continuations, instead of letting those startup action routes degrade to generic startup or dossier chrome.
  - the hosted SSR fallback keeps those routes non-dialog and preserves workspace on the public continuation for `restart`, `close_window`, and `close_all`.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, focused AppShell suite `169 passed`, route/parity pack `563 passed`.

## Handoff refresh (2026-07-07T00:34:45+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `dice_roller`, `data_exporter`, `print_setup`, `print_multiple`, `update`, `new_window`, `wiki`, `discord`, `show_login_video`, `revision_history`, and `dumpshock` now have explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `dice-roller`, `data-exporter`, `print-setup`, `print-multiple`, `update`, `new-window`, `wiki`, `discord`, `login-video`, `revision-history`, and `issue-tracker`, plus command-specific shell copy and clean `/app?command=...` continuations, instead of letting those dialog-backed tool/help routes degrade to generic startup or dossier chrome.
  - the browser/public startup panels for that family now use the same `Open the shared ...` contract as the earlier route-parity slices, and the hosted SSR fallback now preserves dialog-backed posture for the same commands.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, focused AppShell suite `154 passed`, route/parity pack `543 passed`.

## Handoff refresh (2026-07-07T00:14:22+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `open_sourcebooks`, `open_errata`, `open_custom_data`, `update_data_packs`, `validate_data_scope`, and `open_data_folder` now have explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `sourcebooks`, `errata`, `custom-data`, `update-pack`, `validation-scope`, and `data-folder`, plus command-specific shell copy and clean `/app?command=...` continuations, instead of letting those rules/data routes degrade to generic startup or dossier chrome.
  - the visible workbench rules/data strip now publishes compatibility command links and same-origin `/help`, and the shared command contract/shell catalog now recognize the six-command data-pack family as real browser startup commands.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, staged data-pack proof `passed`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused AppShell suite `121 passed`, route/parity pack `499 passed`.

## Handoff refresh (2026-07-06T23:43:34+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `auto_alice` now has explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `assistant`, assistant-specific shell copy, and clean `/app?command=auto_alice` continuation behavior instead of letting the command degrade to generic startup/dossier chrome.
  - the hosted SSR fallback now keeps the shorter `Assistant` workflow label in its classic shell while preserving the full `Auto ALICE` dialog title in the section body.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused AppShell suite `103 passed`, route/parity pack `474 passed`.

## Handoff refresh (2026-07-06T23:34:39+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `character_settings`, `switch_ruleset`, `report_bug`, `about`, and `runtime_inspector` now have explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `character-settings`, `switch-ruleset`, `support`, `about`, and `runtime-inspector`, plus command-specific shell copy and clean `/app?command=...` continuations, instead of letting those commands degrade to generic startup/dossier chrome.
  - the hosted SSR fallback now keeps the shorter `Support` workflow label in its classic shell while preserving the full `Support and bug reporting` dialog title in the section body.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused AppShell suite `100 passed`, route/parity pack `469 passed`.

## Handoff refresh (2026-07-06T23:08:50+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- No blocker truth changed in this slice; keep release posture non-flagship until the shared `release_truth:windows_installer_visual_audit` blocker is resolved.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `global_settings`, `translator`, `xml_editor`, and `hero_lab_importer` now have explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `global-settings`, `translator`, `xml-editor`, and `hero-lab-importer`, plus tool-specific shell copy and clean `/app?command=...` continuations, instead of letting those commands degrade to generic startup/dossier chrome.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused AppShell suite `85 passed`, route/parity pack `444 passed`.

## Handoff refresh (2026-07-06T22:55:50+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - `master_index` now has explicit workflow identity across the hosted `/workbench` compatibility fallback and the clean public `/app` and `/online` route surfaces.
  - compatibility/public proofs now pin `master-index`, `Master Index`, `Master Index shell`, and clean `/app?command=master_index` continuation behavior instead of letting the command degrade to generic dossier/profile chrome.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused AppShell suite `73 passed`, route/parity pack `424 passed`.

## Handoff refresh (2026-07-06T22:40:33+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback posture/contract metadata is now directly covered for roster/dossier state, validation/privacy/hosting posture, auth/session posture, and shared calculation/recommendation metadata.
  - helper and rendered SSR proofs now pin origin, character-roster, open, save/download, export, new-character, and control-dialog compatibility metadata instead of stopping at the earlier high-level output/route attrs.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `72 passed`, route/parity pack `420 passed`.

## Handoff refresh (2026-07-06T22:26:26+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback now publishes the same high-level compatibility/output metadata family as the interactive compatibility shell.
  - added `data-output-workflow`, `data-output-state`, `data-output-target`, `data-route-family`, `data-route-surface`, `data-route-alias`, `data-client-kind`, and `data-parity-target` to the SSR shell contract.
  - helper and rendered SSR proofs now cover non-output, save, export, origin, new-character, and control-dialog compatibility metadata.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `70 passed`, route/parity pack `420 passed`.

## Handoff refresh (2026-07-06T22:18:25+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback classic chrome now mirrors the interactive compatibility shell more closely for dialog-bearing routes.
  - workflow/status chrome now stays workflow scoped instead of reusing dialog titles, so `new_character` shows `Build Lab` while keeping the `New runner` dialog title, and `complex_form_add` shows `Matrix` while keeping `Add Complex Form`.
  - added the classic status footer to the SSR fallback and covered the workflow-vs-dialog split with helper and rendered SSR proofs.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `66 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback visible output labels now match the interactive compatibility shell for save/print/export command routes while workflow metadata stays category-level.
  - non-download output routes now use command-specific titlebar and section headings such as `Prepare Runner Download`, `Prepare Print Preview`, `Open Print Preview`, `Open Print Staging`, `Open Export Staging`, and `Prepare Export Package`.
  - `open_for_printing` and `open_for_export` dialog titles now use the staging labels too, with helper and rendered SSR proofs covering the updated visible chrome.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `64 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output download routes now use download-specific visible section headings instead of generic prepared-state headings.
  - `save_character_as&dialog_action=download` now renders `Download Runner`; `export_character&dialog_action=download` now renders `Download Export Package`.
  - added rendered hosted-blazor heading proof and helper-level fallback assertions for both routes while preserving clean `/app` continuation hrefs.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `61 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output routes now preserve supported `dialog_action=download` continuations for `save_character_as` and `export_character`.
  - fallback copy now distinguishes prepared output from final download handoff, preserves custom `fixture=` on clean `/app` continuations, and keeps unsupported `runner=` out of `/app`.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `48 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback committed-result coverage now matches the interactive restored-action committed-result set for contact add and critter power add.
  - added missing fallback results for `contact_add&dialog_action=add` and `critter_power_add&dialog_action=add`, plus helper and rendered SSR proofs across the full supported committed-result set.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `59 passed`, route/parity pack `420 passed`.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T19:37:33Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T19:36:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=9`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=32`
    - `matching_promoted_stage_startup_smoke_receipt_count=3`
    - stale directory digest summary sample: `digest=c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51 count=9 sample_path=/tmp/windows-installer-gold-proof-27864339393`
    - auto-import directory note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T19:37:34Z`
    - `status=running`
    - `pid=3297638`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T19:36:47Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T22:05:56+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback visible output labels now match the interactive compatibility shell for save/print/export command routes while workflow metadata stays category-level.
  - non-download output routes now use command-specific titlebar and section headings such as `Prepare Runner Download`, `Prepare Print Preview`, `Open Print Preview`, `Open Print Staging`, `Open Export Staging`, and `Prepare Export Package`.
  - `open_for_printing` and `open_for_export` dialog titles now use the staging labels too, with helper and rendered SSR proofs covering the updated visible chrome.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `64 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output download routes now use download-specific visible section headings instead of generic prepared-state headings.
  - `save_character_as&dialog_action=download` now renders `Download Runner`; `export_character&dialog_action=download` now renders `Download Export Package`.
  - added rendered hosted-blazor heading proof and helper-level fallback assertions for both routes while preserving clean `/app` continuation hrefs.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `61 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output routes now preserve supported `dialog_action=download` continuations for `save_character_as` and `export_character`.
  - fallback copy now distinguishes prepared output from final download handoff, preserves custom `fixture=` on clean `/app` continuations, and keeps unsupported `runner=` out of `/app`.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `48 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback committed-result coverage now matches the interactive restored-action committed-result set for contact add and critter power add.
  - added missing fallback results for `contact_add&dialog_action=add` and `critter_power_add&dialog_action=add`, plus helper and rendered SSR proofs across the full supported committed-result set.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `59 passed`, route/parity pack `420 passed`.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T19:37:33Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T19:36:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=9`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=32`
    - `matching_promoted_stage_startup_smoke_receipt_count=3`
    - stale directory digest summary sample: `digest=c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51 count=9 sample_path=/tmp/windows-installer-gold-proof-27864339393`
    - auto-import directory note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T19:37:34Z`
    - `status=running`
    - `pid=3297638`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T19:36:47Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T21:52:56+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output download routes now use download-specific visible section headings instead of generic prepared-state headings.
  - `save_character_as&dialog_action=download` now renders `Download Runner`; `export_character&dialog_action=download` now renders `Download Export Package`.
  - added rendered hosted-blazor heading proof and helper-level fallback assertions for both routes while preserving clean `/app` continuation hrefs.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `61 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output routes now preserve supported `dialog_action=download` continuations for `save_character_as` and `export_character`.
  - fallback copy now distinguishes prepared output from final download handoff, preserves custom `fixture=` on clean `/app` continuations, and keeps unsupported `runner=` out of `/app`.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `48 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback committed-result coverage now matches the interactive restored-action committed-result set for contact add and critter power add.
  - added missing fallback results for `contact_add&dialog_action=add` and `critter_power_add&dialog_action=add`, plus helper and rendered SSR proofs across the full supported committed-result set.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `59 passed`, route/parity pack `420 passed`.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T19:37:33Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T19:36:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=9`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=32`
    - `matching_promoted_stage_startup_smoke_receipt_count=3`
    - stale directory digest summary sample: `digest=c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51 count=9 sample_path=/tmp/windows-installer-gold-proof-27864339393`
    - auto-import directory note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T19:37:34Z`
    - `status=running`
    - `pid=3297638`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T19:36:47Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T21:37:33+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback output routes now preserve supported `dialog_action=download` continuations for `save_character_as` and `export_character`.
  - fallback copy now distinguishes prepared output from final download handoff, preserves custom `fixture=` on clean `/app` continuations, and keeps unsupported `runner=` out of `/app`.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `48 passed`, route/parity pack `420 passed`.
- Origins controller slice completed in `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`:
  - hosted `/workbench` SSR fallback committed-result coverage now matches the interactive restored-action committed-result set for contact add and critter power add.
  - added missing fallback results for `contact_add&dialog_action=add` and `critter_power_add&dialog_action=add`, plus helper and rendered SSR proofs across the full supported committed-result set.
  - verification: build succeeded with `0 Warning(s)` / `0 Error(s)`, static fallback parity stayed clean at continuations `6/6` and actions `68/68`, focused SSR/portal suite `59 passed`, route/parity pack `420 passed`.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T19:37:33Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T19:36:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `all_discovery_roots_checked=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof; /tmp; ~/Downloads; ~/pCloud Drive/EA`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=9`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=32`
    - `matching_promoted_stage_startup_smoke_receipt_count=3`
    - stale directory digest summary sample: `digest=c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51 count=9 sample_path=/tmp/windows-installer-gold-proof-27864339393`
    - auto-import directory note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T19:37:34Z`
    - `status=running`
    - `pid=3297638`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T19:36:47Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T19:23:07Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T21:13:51+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T19:13:20Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T19:13:36Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=28`
    - `matching_promoted_stage_startup_smoke_receipt_count=3`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T19:13:51Z`
    - `status=running`
    - `pid=3236100`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T19:13:36Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T19:11:16Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T19:11:16Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T19:32:21+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T17:32:21Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T17:31:55Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T17:32:22Z`
    - `status=running`
    - `pid=2676754`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T17:31:55Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T17:01:02Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T17:01:17Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T19:20:49+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T17:20:49Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T17:20:44Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T17:20:50Z`
    - `status=running`
    - `pid=2676754`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T17:20:44Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T17:01:02Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T17:01:17Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T19:15:19+02:00)

- Canonical live handoffs for the release/controller lane are:
  - `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md`
  - `/docker/chummercomplete/chummer.run-services/NEXT_SESSION_HANDOFF.md`
  - Repo-local deploy and scratch NEXT_SESSION_HANDOFF.md files are mirrors or stale history; do not treat them as release truth.
- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T17:15:11Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T16:12:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T17:14:52Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T17:15:19Z`
    - `status=running`
    - `pid=2086931`
    - `process_alive=True`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - watcher sees `auto_import_receipt_status=waiting_for_artifact`
    - watcher sees `auto_import_receipt_generated_at_utc=2026-07-06T17:14:52Z`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T17:01:02Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T17:01:17Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T16:39:13+02:00)

- No blocker-shape change. Current root blocker truth still remains:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Windows watcher-manager hardening landed after the first manager pass:
  - process discovery now uses the correct wide `ps` format and reports:
    - `matching_process_pids`
    - `matching_process_count`
    - `duplicate_process_pids`
    - `duplicate_process_count`
  - `stop` now terminates the full matching watcher set instead of only one pid
  - focused manager tests now pass:
    - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_manage_windows_installer_gold_proof_watcher.py`
    - result: `5 passed`
- Canonical watcher runtime truth after duplicate cleanup and sequential relaunch:
  - manager status receipt:
    - `.state/windows_installer_gold_proof_watcher.generated.json`
    - `generated_at_utc=2026-07-06T14:39:02Z`
    - `status=running`
    - `pid=1866861`
    - `matching_process_count=1`
    - `duplicate_process_count=0`
    - `auto_import_receipt_status=waiting_for_artifact`
  - matching watcher process check now agrees:
    - exactly one live watcher pid: `1866861`
- Canonical operator/runtime commands remain:
  - start:
    - `python3 scripts/manage_windows_installer_gold_proof_watcher.py start --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --state-path /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json --pid-file /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.pid --log-file /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_auto_import_watch.log`
  - status:
    - `python3 scripts/manage_windows_installer_gold_proof_watcher.py status --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --state-path /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json --pid-file /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.pid --log-file /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_auto_import_watch.log`
  - stop:
    - `python3 scripts/manage_windows_installer_gold_proof_watcher.py stop --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --state-path /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json --pid-file /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.pid --log-file /docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_auto_import_watch.log`
- Controller lane: this session
  - do not trust the older handoff watcher pid `1837882`; the clean current watcher is `1866861`
  - the real blocker is still the missing promoted-digest proof bundle or extracted visual-proof directory, not watcher control-plane drift

## Handoff refresh (2026-07-06T16:33:34+02:00)

- No blocker-shape change. Current root blocker truth still remains:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- The Windows intake contract now has a canonical watcher-management surface:
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json`
    - `generated_at_utc=2026-07-06T14:32:52Z`
    - `status=external_artifact_required`
  - `python3 scripts/verify_windows_installer_visual_audit_intake_request.py --receipt .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json`
    - `status=pass`
    - `structural_issues=[]`
  - canonical runtime watcher commands now live under `artifact_intake` and `operator_request_artifacts`:
    - `watcher_start_command`
    - `watcher_status_command`
    - `watcher_stop_command`
    - `watcher_state_path=/docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
    - `watcher_pid_file=/docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.pid`
    - `watcher_log_path=/docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_auto_import_watch.log`
    - `watcher_launch_mode=python_subprocess_start_new_session`
- The Windows audit receipt was refreshed to carry the same watcher-management artifacts:
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T14:32:50Z`
    - `status=fail`
    - `proof_request_status=external_artifact_required`
    - `source_digest_matches_promoted=False`
    - `expected_bundle_path_exists=False`
- Watcher runtime truth:
  - exactly one manager-owned watcher is now active after duplicate cleanup
  - PID: `1837882`
  - state file: `/docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_watcher.generated.json`
  - last status refresh:
    - `generated_at_utc=2026-07-06T14:33:25Z`
    - `status=running`
    - `auto_import_receipt_status=waiting_for_artifact`
  - do not start another watcher while that state file still reports a live PID
- Controller lane: this session
  - prefer the watcher manager commands from the canonical intake receipt over manual `nohup` or raw PID handling
  - the actual blocker is still the missing promoted-digest proof bundle or extracted visual-proof directory; watcher management is now hardened, not cleared

## Handoff refresh (2026-07-06T16:23:51+02:00)

- No blocker-shape change. Current root blocker truth still remains:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Active automation upgrade landed in this canonical lane:
  - one long-running Windows gold-proof auto-import watcher is now active
  - PID: `1793996`
  - command:
    - `/usr/bin/python3 /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --wait-seconds 43200 --poll-seconds 30 --refresh-intake-request`
  - runtime log:
    - `/docker/chummercomplete/chummer.run-services/.state/windows_installer_gold_proof_auto_import_watch.log`
    - current contents begin with `START 2026-07-06T16:23:34.940074`
  - do not start a second watcher while PID `1793996` is still live
- Host/runtime note for other Codexes:
  - plain shell `nohup ... &` launches were not durable enough to trust in this host
  - the active watcher was spawned via Python `subprocess.Popen(..., start_new_session=True)`
- Practical effect:
  - this lane no longer depends on a human manually rerunning import discovery after the bundle lands
  - release truth is still blocked until the watcher imports a promoted-digest proof bundle or extracted directory and the follow-up gates refresh to pass

## Handoff refresh (2026-07-06T16:18:32+02:00)

- No blocker-shape change. Current root blocker truth still remains:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Fresh workspace-local salvage scan completed across the repo tree:
  - `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json` files found: `20`
  - promoted-digest matches among those source receipts: `0`
  - every scanned source receipt still points at stale visual source digest:
    - `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
  - `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` files found: `18`
  - promoted-digest matches among those proof receipts: `0`
- Practical effect:
  - there is still no workspace-local extracted visual-proof directory or published proof receipt that can clear the promoted digest blocker
  - other Codexes should not spend more time rescanning sibling worktrees for a hidden promoted-digest proof artifact unless a new file lands
- The canonical external-artifact state from the prior refresh still holds:
  - expected bundle path is still missing:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - auto-import receipt is still:
    - `generated_at_utc=2026-07-06T14:15:45Z`
    - `status=waiting_for_artifact`

## Handoff refresh (2026-07-06T16:16:17+02:00)

- No blocker-shape change. Current root blocker truth remains:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Fresh external-artifact intake check completed in this canonical lane:
  - exact expected bundle path is still missing:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - direct discover across the allowed roots still found nothing:
    - `.state/incoming_windows_installer_gold_proof`
    - `/tmp`
    - `/home/tibor/Downloads`
    - `/home/tibor/pCloud Drive/EA`
  - no persistent Windows auto-import watcher is active
  - a new bounded watch/import cycle completed and refreshed:
    - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T14:15:45Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
- Startup proof still already matches the promoted digest.
- User-reported manual Windows installer success still remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - wait for the digest-bound bundle or extracted visual-proof directory to land
    - do not reopen startup-smoke capture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - do not run stable promotion while `release_truth:windows_installer_visual_audit` remains uncleared
  - Lane C: design/product only
    - keep product/PWA/Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - this lane is now cleanly waiting on external artifact arrival; there is no local salvage candidate yet

## Handoff refresh (2026-07-06T16:10:09+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T14:10:09Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T14:07:25Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T14:09:45Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - Windows proof operator ask currentness (advisory only; not a root blocker):
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T14:07:14Z`
    - `message_ids=3514`
    - resend is no longer required for the current ask
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T14:07:26Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T14:07:26Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T15:15:17+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:google_oauth_linking_proof`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T13:15:17Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T11:37:40Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T13:02:59Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - Windows proof operator ask currentness:
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T11:36:40Z`
    - `message_ids=3513`
    - resend is no longer required
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T12:07:57Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T12:08:00Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T14:56:42+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Windows gold-proof auto-import now accepts the operator’s documented visual-only extracted directory shape when startup proof is already optional:
  - patched:
    - `scripts/auto_import_windows_installer_gold_proof.py`
    - `tests/test_windows_installer_visual_audit.py`
  - new runtime invariant now covered:
    - when the intake says startup proof is already satisfied, the watcher can auto-select an extracted directory that contains `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json` directly, instead of requiring a zip or a repo-root-shaped `Chummer.Portal/downloads/...` tree
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'auto_selects_visual_only_directory_candidates_when_startup_bundle_optional or auto_selects_portable_visual_only_directory_candidates_when_startup_bundle_optional or imports_and_runs_follow_up_commands or main_passes_downloads_root_into_ensure_intake_request'`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py /docker/chummercomplete/chummer.run-services/scripts/import_windows_installer_gold_proof_artifact.py`
  - results:
    - focused Windows auto-import regressions: `4 passed`
    - compile check passed
- Current intake truth rechecked live:
  - direct discover across the allowed roots returned no bundle:
    - `.state/incoming_windows_installer_gold_proof`
    - `/tmp`
    - `/home/tibor/Downloads`
    - `/home/tibor/pCloud Drive/EA`
  - canonical auto-import receipt refreshed:
    - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T12:56:12Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `intake_visual_source_count=0`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
- Practical effect for the other Codexes:
  - the blocker is still the missing native Windows proof bundle or extracted visual-proof directory for digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - startup proof is still already satisfied for the promoted digest
  - this still does not clear either flagship root blocker
  - the preferred drop path is still `.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T14:51:34+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Google OAuth proof receipts now separate operator-evidence truth from first-party signed-in preflight failures:
  - patched:
    - `scripts/materialize_google_oauth_linking_proof.py`
    - `tests/test_google_oauth_linking_proof.py`
  - new runtime invariants now covered:
    - if operator-backed Google evidence already passes but the live signed-in preflight fails, the receipt summary says that explicitly instead of claiming operator evidence is still missing
    - in that same state, `next_actions` now point at refreshing the first-party signed-in preflight rather than recapturing screenshots or redoing operator evidence
    - the receipt rerun hint now preserves the active `base_url` instead of hardcoding `https://chummer.run`
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_google_oauth_linking_proof.py /docker/chummercomplete/chummer.run-services/tests/test_verify_google_oauth_linking_proof.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_google_oauth_linking_proof.py /docker/chummercomplete/chummer.run-services/scripts/verify_google_oauth_linking_proof.py`
  - results:
    - Google proof regression suite: `13 passed`
    - compile check passed
- Practical effect for the other Codexes:
  - do not spend operator time recapturing Google screenshots if the evidence receipt is already green and only the deployed owner-session or inline-preview preflight is failing
  - this pass did not rematerialize the live Google proof receipt, so canonical blocker truth stays where the shared packet left it
  - this still does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T14:41:20+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Google OAuth operator-proof request and auto-import contracts are now base-URL-bound end to end, and the request verifier no longer crashes on malformed JSON during operator-draft reads:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/scripts/materialize_google_oauth_linking_operator_evidence_request.py`
    - `/docker/chummercomplete/chummer.run-services/scripts/verify_google_oauth_linking_operator_evidence_request.py`
    - `/docker/chummercomplete/chummer.run-services/scripts/auto_import_google_oauth_linking_operator_evidence.py`
  - new runtime invariants now covered:
    - request `post_import_gates` are derived from the live request `base_url`, not a hardcoded `https://chummer.run`
    - generated Google auto-import commands now carry `--base-url`
    - Google auto-import receipts now preserve `base_url`
    - malformed Google operator request JSON or malformed `CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json` returns a structured verifier failure instead of a traceback
  - regression coverage:
    - `tests/test_google_oauth_linking_operator_evidence_request.py`
      - custom-base-url request command binding
    - `tests/test_verify_google_oauth_linking_operator_evidence_request.py`
      - custom-base-url verifier pass
      - malformed request receipt fail-cleanly
      - malformed operator-ask metadata fail-cleanly
    - `tests/test_auto_import_google_oauth_linking_operator_evidence.py`
      - auto-import receipt preserves `base_url`
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_google_oauth_linking_operator_evidence_request.py /docker/chummercomplete/chummer.run-services/tests/test_verify_google_oauth_linking_operator_evidence_request.py /docker/chummercomplete/chummer.run-services/tests/test_auto_import_google_oauth_linking_operator_evidence.py`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_google_oauth_linking_operator_evidence_request.py /docker/chummercomplete/chummer.run-services/scripts/verify_google_oauth_linking_operator_evidence_request.py /docker/chummercomplete/chummer.run-services/scripts/auto_import_google_oauth_linking_operator_evidence.py`
  - live receipt refresh:
    - `GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json`
      - `generated_at_utc=2026-07-06T12:38:10.749606Z`
      - `status=not_required`
      - `base_url=https://chummer.run`
    - `verify_google_oauth_linking_operator_evidence_request.py --receipt .../GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json`
      - `status=pass`
      - `issues=[]`
    - `GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json`
      - `generated_at_utc=2026-07-06T12:41:10Z`
      - `status=pass`
      - `request_status=not_required`
      - `base_url=https://chummer.run`
- Practical effect for the other Codexes:
  - any future Google operator-proof lane running against a non-default public base will keep that base URL all the way through request refresh, auto-import, and post-import verification
  - malformed operator draft metadata no longer turns the verifier into a crash-only path
  - this still does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T14:32:31+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Auto-import intake refresh now preserves the active runtime context instead of silently falling back to request-script defaults:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py`
    - `/docker/chummercomplete/chummer.run-services/scripts/auto_import_google_oauth_linking_operator_evidence.py`
  - new runtime invariants now covered:
    - Windows gold-proof auto-import rematerializes the intake request with the active `--downloads-root`
    - Google OAuth operator-evidence auto-import rematerializes the intake request with the active `--base-url`
  - regression coverage:
    - `tests/test_windows_installer_visual_audit.py`
      - `test_auto_import_windows_installer_gold_proof_main_passes_downloads_root_into_ensure_intake_request`
    - `tests/test_auto_import_google_oauth_linking_operator_evidence.py`
      - `test_main_passes_base_url_into_ensure_intake_request`
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_auto_import_google_oauth_linking_operator_evidence.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'auto_import_windows_installer_gold_proof_imports_and_runs_follow_up_commands or auto_import_windows_installer_gold_proof_main_passes_downloads_root_into_ensure_intake_request'`
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/auto_import_google_oauth_linking_operator_evidence.py /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py`
  - results:
    - Google auto-import regressions: `12 passed`
    - Windows focused auto-import regressions: `2 passed`
    - compile check passed
- Practical effect for the other Codexes:
  - Lane A can safely use `--refresh-intake-request` without rebinding the Windows proof watch/import loop to the wrong downloads root
  - any future Google OAuth operator-proof refresh against a non-default base URL no longer snaps back to the default request context during the watch/import loop
  - this still does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T14:08:02+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T12:06:59Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py && python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "$(date --iso-8601=seconds)"`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T11:37:40Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T11:37:16Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - Windows proof operator ask currentness:
    - latest delivery receipt now matches the current ask text
    - `generated_at_utc=2026-07-06T11:36:40Z`
    - `message_ids=3513`
    - resend is no longer required
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T12:07:57Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T12:08:00Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T13:27:57+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T11:27:52Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:38:58Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T11:14:53Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T11:27:23Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T11:27:21Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`, `OPERATOR_RELEASE_DASHBOARD.generated.json`, or `FINAL_GOLD_JANITOR.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T08:41:12+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Stable promotion is now explicitly runtime-locked against inheriting the preview-only Windows visual-proof bypass:
  - patched test:
    - `/docker/chummercomplete/chummer6-ui/tests/test_windows_installer_payload_gate.py`
  - new runtime invariant now covered:
    - if `CHUMMER_FORCE_NIGHTLY_PUBLISH=1` is set but `RELEASE_CHANNEL=public_stable`, the real `chummer6-ui/scripts/publish-download-bundle.sh` path still fails closed on missing Windows visual proof instead of continuing through the preview-only handoff allowance
  - this complements the existing static policy test in:
    - `/docker/chummercomplete/chummer6-ui/tests/test_desktop_downloads_local_release_policy.py`
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer6-ui/tests/test_windows_installer_payload_gate.py -k 'stable_publish_download_bundle_does_not_honor_forced_preview_visual_handoff_override'`
  - `pytest -q /docker/chummercomplete/chummer6-ui/tests/test_desktop_downloads_local_release_policy.py -k 'forced_preview_nightly_can_publish_only_visual_proof_handoff'`
  - results:
    - stable-promotion runtime regression: `1 passed`
    - preview-only policy regression: `1 passed`
- Practical effect for the other Codexes:
  - Lane B cannot accidentally claim that setting the nightly override env is enough to slip a public-stable promotion past the outstanding Windows visual-proof blocker
  - the remaining blocker path is still the same external artifact import followed by the documented stable promotion command and post-promotion verify chain
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T08:35:35+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- The non-`ai/` desktop release entrypoints in the main app repos and SR6 mirror repos are now clear of the remaining bash4-only `readarray` / `mapfile` collectors that could still break on macOS bash 3:
  - patched release publish / manifest entrypoints:
    - `/docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer-presentation/scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer6-ui/scripts/generate-releases-manifest.sh`
    - `/docker/chummercomplete/chummer-presentation/scripts/generate-releases-manifest.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/generate-releases-manifest.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/generate-releases-manifest.sh`
  - patched desktop exit-gate tuple collectors:
    - `/docker/chummercomplete/chummer6-ui/scripts/materialize-{macos,linux,windows}-desktop-exit-gate.sh`
    - `/docker/chummercomplete/chummer-presentation/scripts/materialize-{macos,linux,windows}-desktop-exit-gate.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/materialize-{macos,linux,windows}-desktop-exit-gate.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/materialize-{macos,linux,windows}-desktop-exit-gate.sh`
  - publish scripts now replace bash4-only `mapfile` / `readarray` with bash3-safe `while IFS= read -r ...; do ... done`
  - exit-gate scripts now replace `mapfile -t RELEASE_PROMOTED_TUPLE` with the same bash3-safe tuple collection loop
- Static portability coverage was tightened again:
  - `tests/test_release_shell_array_portability.py`
    - now also requires bash3-safe array initialization/collection on the patched publish and manifest entrypoints
    - now forbids `mapfile -t artifacts` and the patched `readarray -t ...` collector forms on those surfaces
  - new:
    - `tests/test_desktop_exit_gate_bash_portability.py`
    - locks all 12 desktop exit-gate materializers against `mapfile -t RELEASE_PROMOTED_TUPLE`
- Focused verification completed:
  - `rg -n '\breadarray\b|\bmapfile\b' /docker/chummercomplete/chummer6-ui/scripts /docker/chummercomplete/chummer-presentation/scripts /docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts -g '!**/ai/**'`
    - no matches in the targeted non-`ai/` release scripts after the patch
  - `bash -n` on the 20 patched publish / manifest / exit-gate scripts
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_release_shell_array_portability.py /docker/chummercomplete/chummer.run-services/tests/test_desktop_exit_gate_bash_portability.py`
  - results:
    - shell syntax check passed
    - portability tests: `2 passed`
- Practical effect for the other Codexes:
  - the main release entrypoints, SR6 release mirrors, and desktop exit-gate selectors are now bash3-safe on the known array/collector paths that had been drifting
  - this still does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T08:21:41+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- The remaining repo-local desktop publish mirrors now use the same nounset-safe NUL iteration path as the already-hardened main desktop publish scripts:
  - patched:
    - `scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle.sh`
  - each now uses `array_values_nul()` plus `while IFS= read -r -d ''` for the publish-time loops over:
    - `artifacts`
    - `promoted_file_names`
    - `live_downloads_mirror_dirs`
  - this removes the remaining raw `for ... in "${artifacts[@]}"`, `for ... in "${promoted_file_names[@]}"`, and `for ... in "${live_downloads_mirror_dirs[@]}"` paths from the repo-local desktop publish mirrors that other Codexes were still likely to touch
- Static portability coverage was tightened again:
  - `tests/test_release_shell_array_portability.py`
    - now explicitly requires `array_values_nul` iteration on those three arrays for the canonical repo-local publish script and the two SR6 mirror publish scripts
    - now forbids the raw `for ... in "${array[@]}"` forms for those same arrays
- Focused verification completed:
  - `bash -n /docker/chummercomplete/chummer.run-services/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle.sh`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_release_shell_array_portability.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_mac_release_bootstrap_array_safety.py /docker/chummercomplete/chummer.run-services/tests/test_desktop_startup_smoke_bash_compat.py /docker/chummercomplete/chummer6-ui/tests/test_startup_smoke_bash_portability.py`
  - results:
    - shell syntax check passed
    - portability test: `1 passed`
    - bootstrap/startup-smoke portability tests: `4 passed`
- Practical effect for the other Codexes:
  - the known publish-time shell hardening now covers the canonical repo-local desktop publish script, both SR6 mirror publish scripts, the HTTP publish path, the bootstrap direct-URL path, and the startup-smoke case-handling path
  - this still does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T08:14:31+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Main desktop publish scripts are now locked against the same nounset/empty-array iteration hazard on the promoted-artifact and mirror-sync loops:
  - patched:
    - `/docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh`
    - `/docker/chummercomplete/chummer-presentation/scripts/publish-download-bundle.sh`
  - both now use `array_values_nul()` plus `while IFS= read -r -d ''` for:
    - `live_downloads_mirror_dirs`
    - `promoted_file_names`
    - `artifacts`
  - this specifically removes raw `for ... in "${artifacts[@]}"`, `for ... in "${promoted_file_names[@]}"`, and `for ... in "${live_downloads_mirror_dirs[@]}"` from the main desktop publish path
- Static shell portability coverage was tightened for those surfaces:
  - `tests/test_release_shell_array_portability.py`
    - now explicitly checks the main `chummer6-ui` and `chummer-presentation` desktop publish scripts for `array_values_nul` iteration on those arrays
    - now forbids the raw `for ... in "${array[@]}"` forms for those same arrays
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_release_shell_array_portability.py`
  - result: `1 passed`
- Practical effect for the other Codexes:
  - the main desktop publish path is less likely to surface the earlier strict-shell empty-array warnings during mirror sync and promoted-artifact copy stages
  - this does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T08:05:05+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Release HTTP publish scripts are now nounset-safe on the upload-files iteration path that could previously emit shell warnings under strict mode:
  - patched:
    - `scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer-presentation/scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle-http.sh`
  - each now uses `array_values_nul()` plus `while IFS= read -r -d ''` instead of raw `for file_path in "${upload_files[@]}"`, which is safer under `set -u` when the array may be empty or mirrored scripts drift
- Static shell portability coverage was tightened:
  - `tests/test_publish_download_bundle_http_bash_portability.py`
    - now also requires the `array_values_nul upload_files` iteration path
    - now forbids raw `for file_path in "${upload_files[@]}"` iteration
- Focused verification completed:
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_publish_download_bundle_http_bash_portability.py /docker/chummercomplete/chummer.run-services/tests/test_mac_release_bootstrap_array_safety.py /docker/chummercomplete/chummer.run-services/tests/test_desktop_startup_smoke_bash_compat.py`
  - result: `4 passed`
  - `pytest -q /docker/chummercomplete/chummer6-ui/tests/test_startup_smoke_bash_portability.py`
  - result: `1 passed`
- Practical effect for the other Codexes:
  - the repo-local HTTP publish/upload scripts are less likely to emit the earlier empty-array shell warnings during release publication
  - this does not clear either flagship root blocker
  - the missing Windows gold-proof bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T08:00:08+02:00)

- Controller lane hardening only. Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Windows proof intake is now fail-closed before published proof files are overwritten:
  - `scripts/import_windows_installer_gold_proof_artifact.py`
    - now rejects bundles whose `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json` digest does not match the promoted installer digest before copying anything into `Chummer.Portal/downloads`
    - now rejects bundled startup receipts whose digest does not match the promoted installer digest before copying anything into `Chummer.Portal/downloads`
  - `scripts/auto_import_windows_installer_gold_proof.py`
    - no longer auto-selects arbitrary generic `*windows-installer-gold-proof*.zip` files when the digest-bound required filename is already known from the intake request
- Focused verification completed:
  - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/import_windows_installer_gold_proof_artifact.py /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`
  - `pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'rejects_visual_source_digest_mismatch_before_copying or rejects_bundled_startup_digest_mismatch_before_copying or does_not_auto_select_generic_zip_when_required_filename_is_known or auto_selects_matching_directory_candidates or waiting_payload_surfaces_expected_bundle_details or imports_and_runs_follow_up_commands'`
  - result: `6 passed`
- Practical effect for the other Codexes:
  - Lane A can still import the missing digest-bound bundle once it exists, but stale or generic zip noise should no longer clobber the published proof shelf first
  - manual Windows installer success still does not clear release truth
  - the missing bundle path is still `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T07:53:44+02:00)

- Controller lane addendum only. Release blocker truth below remains authoritative and unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Stayed out of release posture / Windows proof lanes again.
- Follow-up EA hardening completed upstream under `/docker/EA` for the published My Media receipt boundary:
  - patched:
    - `/docker/EA/scripts/materialize_mymedia_alexa_readiness.py`
    - `/docker/EA/scripts/verify_mymedia_alexa_readiness.py`
    - `/docker/EA/tests/test_mymedia_alexa_readiness.py`
    - `/docker/EA/README.md`
    - `/docker/EA/RUNBOOK.md`
  - fixed a real live leak where the published receipt embedded raw nested Telegram dry-run identity payload:
    - `pairing_telegram_delivery.telegram_delivery.principal_id`
  - publication boundary now re-sanitizes:
    - nested Telegram delivery principal/binding ids -> `*_present`
    - nested Telegram `message_ids` -> `message_ids_present`
    - loopback My Media and WhatsApp action URLs -> host-local/public-safe hrefs
    - source refs through the same public-source normalization used elsewhere
- Focused verification completed:
  - `pytest -q /docker/EA/tests/test_mymedia_alexa_readiness.py` -> `4 passed`
  - `pytest -q /docker/EA/tests/test_operator_contracts.py -k 'mymedia_background_scan_status_is_documented or mymedia_alexa_readiness_scripts_help_and_wiring'` -> `2 passed`
  - `python3 /docker/EA/scripts/materialize_mymedia_alexa_readiness.py`
  - `python3 /docker/EA/scripts/verify_mymedia_alexa_readiness.py` -> `status=pass`
  - `rg -n '"principal_id"|"binding_id"|"message_ids"|127\.0\.0\.1:52051|127\.0\.0\.1:8098|tibor-wa-web|cf-email:tibor\.girschele@gmail\.com' /docker/EA/.codex-studio/published/mymedia_alexa_readiness.generated.json` -> no matches
- Current live EA receipt truth:
  - `/docker/EA/.codex-studio/published/mymedia_alexa_readiness.generated.json`
    - `generated_at=2026-07-06T05:53:32Z`
    - `status=ready`
    - `pairing_telegram_delivery.status=already_paired`
    - nested telegram delivery now exposes only `principal_id_present=true`, not the raw principal id
- Do not treat this as clearing either flagship release blocker.

## Handoff refresh (2026-07-06T07:49:09+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T05:49:09Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:38:58Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T05:39:17Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T05:48:46Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T05:48:45Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T07:46:49+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T05:46:49Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:38:58Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T05:39:17Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T05:42:43Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T05:46:30Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T07:29:29+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T05:18:22Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:05:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T04:51:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T05:27:26Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T05:24:57Z`
    - `release_lane_posture` now carries the exact stable promotion command and post-promotion verify chain
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T07:25:13+02:00)

- This block supersedes the 07:20 block below when they disagree.
- The published final-gold surfaces now also carry the exact release-posture follow-through commands directly.
- Current authoritative receipts:
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T05:24:57Z`
    - `root_blockers[0].id=release_lane_posture`
    - now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `.codex-studio/published/FINAL_GOLD_VERDICT.md`
    - now prints `stable promotion command` and `post-promotion verify command` under `release_lane_posture`
- Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Read this to the other Codexes:
  - Lane B can now use any of `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`, `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`, or `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json` to get the exact post-Windows stable-promotion step
  - Lane A is still blocked only on the digest-bound Windows gold-proof bundle at `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - Controller lane: do not claim flagship-ready while either root blocker remains

## Handoff refresh (2026-07-06T07:20:41+02:00)

- This block supersedes the 07:18 block below when they disagree.
- The published operator dashboard now carries the exact release-posture follow-through commands directly.
- Current authoritative receipts:
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T05:18:15Z`
    - `root_blockers[0].id=release_lane_posture`
    - now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - now prints `stable promotion command` and `post-promotion verify command` under `release_lane_posture`
- Root blocker truth is unchanged:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Read this to the other Codexes:
  - Lane B can now use either `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json` or this published operator dashboard JSON to get the exact post-Windows stable-promotion step
  - Lane A is still blocked only on the digest-bound Windows gold-proof bundle at `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - Controller lane: do not claim flagship-ready while either root blocker remains

## Handoff refresh (2026-07-06T07:18:22+02:00)

- Current root blocker truth is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T05:18:22Z`
    - `release_posture:non_flagship_channel` now includes:
      - `stable_promotion_command=RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
      - `post_promotion_verify_command=python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:05:30Z`
    - `status=fail`
    - stale source digest still recorded: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path: `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T04:51:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - published markdown surfaces still split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `chummer.run-services/.codex-studio/published/FINAL_GOLD_VERDICT.md`
- Startup proof already matches the promoted digest.
- User-reported manual Windows installer success remains corroborating runtime information only. It does not clear release truth.
- Read this to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable promotion command and post-promotion verify chain from `RELEASE_BLOCKERS.generated.json`
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship-ready while any root blocker remains in `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T07:07:19+02:00)

- This block supersedes the 07:05 block below when they disagree.
- Current root blocker truth is still only:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T05:07:26Z`
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:05:30Z`
    - `status=fail`
    - stale source digest still recorded:
      - `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - promoted digest still required:
      - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing gold-proof bundle path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T04:51:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
  - published markdown surfaces now split the hint families cleanly:
    - `RELEASE_BLOCKERS.generated.md`
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `.codex-studio/published/FINAL_GOLD_VERDICT.md`
    - each now prints separate `windows stage-proof hint paths` and `windows startup-smoke hint paths`
- User-reported manual Windows installer success is runtime corroboration only. It does not replace the digest-bound gold-proof bundle or clear release truth.
- Read this literally to the other Codexes:
  - Lane A: Windows visual audit only
    - import the digest-bound bundle
    - do not spend time on startup-smoke recapture unless intentionally replacing the already-matching startup proof
  - Lane B: release posture only
    - wait for Lane A to clear `release_truth:windows_installer_visual_audit`
    - then run the stable-promotion command already documented below
  - Lane C: design/product only
    - keep Runner Cockpit / GM PWA / character viewer / Origin Dossier work isolated from release receipts and stable-promotion work
  - Controller lane: this session
    - do not claim flagship ready until both blocker ids disappear from `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T07:05:55+02:00)

- This block supersedes the 06:57 block below when they disagree.
- The published base Windows verifier now carries the full blocker truth directly.
- Refreshed receipts:
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `generated_at_utc=2026-07-06T05:05:30Z`
    - `status=fail`
    - failures now include all three of:
      - `Windows installer visual audit source digest does not match promoted installer`
      - `windows installer visual audit source still targets c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b instead of promoted digest 80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a: /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`
      - `windows installer gold proof artifact is still missing: /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - operator artifacts now also surface:
      - `request_status=external_artifact_required`
      - `preferred_drop_path_exists=false`
      - `auto_import_receipt_status=waiting_for_artifact`
      - `auto_import_stage_visual_proof_receipt_count=8`
      - `auto_import_stage_startup_smoke_receipt_count=43`
  - `chummer.run-services/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-06T05:05:36Z`
    - launch-critical nested blockers now include the detailed stale-digest line and the missing-bundle line directly
- Read this literally to the other Codexes:
  - Lane A does not need higher-level receipts to understand the Windows blocker anymore; the base verifier now says exactly which stale digest is recorded and which bundle path is still missing
  - Lane B still waits for Lane A to clear `release_truth:windows_installer_visual_audit` before running the stable-promotion command already documented below
  - The blocker order remains unchanged:
    1. import the Windows digest-bound gold-proof bundle
    2. run the stable-promotion command
    3. rerun the blocker chain

## Handoff refresh (2026-07-06T06:57:11+02:00)

- This block supersedes the 06:55 block below when they disagree.
- There is no direct cross-agent send tool here. These handoff files are the read-aloud packet for the other Codex sessions.
- Keep the blocker order literal:
  1. Windows digest-bound gold-proof bundle import
  2. stable promotion command
  3. blocker-chain rerun
- Current authoritative handoff commands:
  - Windows proof packet:
    - `chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json`
    - `status=ready_for_windows_host`
    - required bundle path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - Stable promotion command, only after the Windows blocker is green:
    - `RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260704-170602 RELEASE_PUBLISHED_AT=2026-07-04T17:48:20Z bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads`
  - Blocker rerun chain, immediately after stable promotion:
    - `python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && python3 scripts/materialize_operator_release_dashboard.py && python3 scripts/final_gold_janitor.py && python3 ../scripts/release/_release_gate_common.py`
- Read this literally to the other Codexes:
  - Lane A: Windows visual audit only
    - own the digest-bound zip import lane
    - do not treat startup-smoke hints or stage-local proof copy-back as completion
  - Lane B: release posture only
    - wait until Lane A clears `release_truth:windows_installer_visual_audit`
    - then run the exact stable promotion command and rerun chain above
  - Lane C: design/product only
    - Runner Cockpit / GM PWA / character viewer / Origin Dossier stays isolated from release receipts, deploy artifacts, and live release truth
  - Controller lane: this session
    - do not claim flagship ready until both blocker ids disappear from `RELEASE_BLOCKERS.generated.json`

## Handoff refresh (2026-07-06T06:55:32+02:00)

- This block supersedes every older section below when they disagree.
- Chummer is still not flagship-launch ready.
- The current root blockers are still only:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative Windows watcher truth is now:
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T04:51:47Z`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `stage_visual_proof_receipt_count=8`
    - `stage_startup_smoke_receipt_count=43`
    - `matching_promoted_stage_startup_smoke_receipt_count=4`
    - `stale_stage_startup_smoke_receipt_count=39`
    - startup note says startup is already proven for the matching staged bytes; only the visual-audit bundle still needs packaging or recapture
  - `.codex-studio/published/RELEASE_READY.generated.json`
    - `generated_at_utc=2026-07-06T04:53:28Z`
    - next actions now say `visual-proof receipts=8, startup-smoke receipts=43`
  - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T04:54:59Z`
    - carries the same startup-smoke counts and note at the root blocker layer

- Read this literally to the other Codexes:
  - Lane A: Windows visual audit only
    - do not let the watcher stop on raw startup-smoke receipts; `actionable_candidate_count` is now correctly `0`
    - there are already `4` matching promoted startup-smoke hints on disk
    - the missing artifact is still the digest-bound visual proof bundle at `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - Lane B: release posture / stable-lane prep only
  - Lane C: third Codex design/product lane only
  - Stand down `/play`, Google no-op, and My Media as flagship blockers unless fresh failing receipts appear

## Handoff refresh (2026-07-06T06:48:39+02:00)

- This block supersedes older My Media / EA notes below when they disagree.
- My Media is no longer blocked on Amazon connection or stale mount state.
- Current live truth after the refresh:
  - `/docker/EA/scripts/ea_live_ops.py probe-mymedia-alexa --format json`
    - `status=ready_library_scan_in_progress`
    - `ready=true`
    - `connection_status=connected`
    - `next_action=wait_for_mymedia_library_scan`
    - `watch_folder_states=["scanning","serving"]`
    - `tracks=37836`
  - `/docker/EA/.runtime/mymedia-amazon-pairing`
    - now absent after the probe
    - the old private pairing bundle was scrubbed successfully
- Hardening landed in `/docker/EA`:
  - `scripts/ea_live_ops.py`
    - added automatic cleanup of obsolete My Media pairing artifacts (`storage_state.json`, `session.json`, `surface.png`) once the runtime confirms pairing is complete
    - probe output now exposes cleanup counters without leaking any private paths or tokens
  - `tests/test_ea_live_ops.py`
    - paired path now proves the stale pairing bundle is removed
    - pairing-required path now proves an active resumable handoff is preserved
  - `README.md`
  - `RUNBOOK.md`
    - both now document that successful pairing scrubs the old `.runtime/mymedia-amazon-pairing/` bundle automatically
- Focused verification completed in `/docker/EA`:
  - `python3 -m py_compile /docker/EA/scripts/ea_live_ops.py /docker/EA/tests/test_ea_live_ops.py`
  - `cd /docker/EA && pytest -q tests/test_ea_live_ops.py -k 'probe_mymedia_alexa_reports_pairing_required_and_scan_blocked_by_pairing or probe_mymedia_alexa_reports_ready_without_leaking_pairing_material or probe_mymedia_alexa_prefers_wait_when_scan_is_already_progressing'`
    - result: `3 passed`
  - `cd /docker/EA && pytest -q tests/test_operator_contracts.py -k 'mymedia_background_scan_status_is_documented or mymedia_alexa_readiness_scripts_help_and_wiring'`
    - result: `2 passed`
- Refreshed receipts:
  - `/docker/EA/.codex-studio/published/mymedia_alexa_readiness.generated.json`
    - `generated_at=2026-07-06T04:48:17Z`
    - `status=ready_library_scan_in_progress`
    - `pairing_resume_ready=false`
    - `pairing_telegram_delivery.status=already_paired`
  - `.codex-studio/published/MYMEDIA_PUBLIC_SURFACE.generated.json`
    - `status=pass`
    - `mymedia_status=ready_library_scan_in_progress`
    - `runtime_status=ready`
    - `public_surface_status=access_protected`
  - `.codex-studio/published/EA_OPERATOR_READINESS.generated.json`
    - `generated_at_utc=2026-07-06T04:48:05Z`
    - `operator_status=ready_with_actions`
    - `runtime_status=blocked`
    - `blocked_component_keys=["google_workspace_oauth","whatsapp_pairing"]`
    - `advisory_action_component_keys=["mymedia_alexa","proactive_route"]`
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - EA line now reads:
      - `attention=3 blocked=2 next=google_workspace_oauth,pushbullet,whatsapp_pairing advisory=mymedia_alexa,proactive_route`
    - My Media line now reads:
      - `ready=true status=access_protected runtime_status=ready`
- Important coordination note:
  - do not reopen the old My Media Amazon-pairing blocker unless a fresh live probe shows `pairing_ready=false`, `connection_status!=connected`, or the private pairing bundle reappears with a new actionable handoff
  - current remaining EA blockers are outside My Media: `google_workspace_oauth` and `whatsapp_pairing`
  - host workload is still separately `degraded` on cache headroom / mirror long-run posture; that is not a My Media regression

## Handoff refresh (2026-07-06T06:47:27+02:00)

- Windows proof lane packet was tightened. This does not clear the blocker, but it removes the current operator-handoff ambiguity.
- Refreshed artifacts now include the promoted-digest bundle path directly:
  - `Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json`
    - `generated_at=2026-07-06T04:46:59Z`
    - `status=ready_for_windows_host`
    - now includes:
      - `operator_artifact_intake.gold_proof_bundle_intake.preferred_zip_name=windows-installer-gold-proof-80655fd79a09.zip`
      - `preferred_drop_path=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
      - the promoted-digest PowerShell capture command
      - the `Compress-Archive` bundle command
      - the import command
      - the auto-import watch command
  - `Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.md`
    - now has a `Release-Truth Bundle Intake` section with the same data
  - `Chummer.Portal/downloads/RELEASE_BUILD_HANDOFF.generated.json`
    - now embeds the same `gold_proof_bundle_intake` block and next actions

- Read this literally to the other Codexes:
  - if you own the Windows lane, use `Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json` as the current operator packet
  - do not stop at stage-local `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` copy-back; the live release-truth gate still needs the zip bundle at the drop path above
  - the blocker is still active until that bundle is imported and the audit flips green

## Handoff refresh (2026-07-06T06:43:46+02:00)

- This block supersedes every older section below when they disagree.
- Chummer is still not flagship-launch ready.
- The current root blockers are still only:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T04:29:50Z`
    - `status=fail`
    - `verdict=NOT_GOLD`
    - current failures are only the Windows visual-proof chain
  - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T04:33:11Z`
    - only blocker ids:
      - `release_posture:non_flagship_channel`
      - `release_truth:windows_installer_visual_audit`
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json`
    - `status=external_artifact_required`
    - `promoted_installer_sha256=80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - `startup_receipt_bundle_required=false`
    - `preferred_drop_path=/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `status=waiting_for_artifact`
    - `stage_visual_proof_receipt_count=8`
    - `matching_promoted_stage_visual_proof_receipt_count=0`
    - `stale_stage_visual_proof_receipt_count=8`
  - `.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json`
    - `status=pass`
    - `request_status=not_required`
  - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=pass`
  - `.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `status=pass`
    - `/play phone-390 overflow_x=0`

- Read this literally to the other Codexes:
  - Lane A: Windows visual audit only
    - promoted digest:
      - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - required bundle path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - do not recapture startup smoke unless you are intentionally replacing the already-matching published startup receipt
    - the remaining evidence gap is install-progress and completion visual proof for the promoted digest
    - do not hand-edit receipts; either import the bundle or improve the operator handoff around that exact digest-bound intake
  - Lane B: release posture / stable-lane prep only
    - keep public-stable work isolated
    - do not claim flagship, gold, or public-stable while the Windows visual-proof blocker or preview posture remains
  - Lane C: third Codex design/product lane only
    - Runner Cockpit / GM PWA / character-viewer / Origin Dossier design-product work stays owned by the third Codex unless reassigned
    - keep that lane out of generated release receipts, Windows proof receipts, deploy artifacts, and Teable/live release truth unless the assignment changes
  - Stand down these lanes unless fresh failing receipts appear again:
    - `/play` mobile overflow
    - Google OAuth operator-evidence auto-import no-op
    - My Media / Amazon connection work as a Chummer flagship-launch blocker

## Handoff refresh (2026-07-06T06:37:19+02:00)

- This is the current cross-Codex read-aloud block. Treat older sections below as history only when they conflict with this block.
- Chummer is still not flagship-launch ready.
- The current root blockers are still only:
  - `release_posture:non_flagship_channel`
  - `release_truth:windows_installer_visual_audit`
- Current authoritative receipts:
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T04:29:50Z`
    - `status=fail`
    - current failures are only the Windows visual-proof chain
  - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T04:33:11Z`
    - only blocker ids:
      - `release_posture:non_flagship_channel`
      - `release_truth:windows_installer_visual_audit`
  - `.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json`
    - `status=pass`
    - `request_status=not_required`
  - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=pass`
  - `.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `status=pass`
    - `/play phone-390 overflow_x=0`

- Read this literally to the other Codexes:
  - Lane A: Windows proof only
    - promoted digest:
      - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - required bundle path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - do not hand-edit receipts; either import the bundle or improve the operator handoff around that exact digest-bound intake
  - Lane B: release posture / stable-lane prep only
    - keep public-stable work isolated
    - do not claim flagship, gold, or public-stable while the Windows proof blocker or preview posture remains
  - Lane C: third Codex design/product lane only
    - Runner Cockpit / GM PWA / character-viewer / Origin Dossier design-product work stays owned by the third Codex unless reassigned
    - keep that lane out of generated release receipts, Windows proof receipts, deploy artifacts, and Teable/live release truth unless the assignment changes
  - Stand down these lanes unless fresh failing receipts appear again:
    - `/play` mobile overflow
    - Google OAuth operator-evidence auto-import no-op
    - My Media / Amazon connection work as a Chummer flagship-launch blocker

- Coordination note:
  - there is no direct cross-agent send tool here
  - this file, `docs/CODEX_FLAGSHIP_HANDOFF_WEB_BOOK.md`, and `/docker/chummercomplete/CODEX_HANDOFF_2026-07-06.md` are the read-aloud packet for the other Codex sessions

## Handoff refresh (2026-07-06T06:30:15+02:00)

- The latest end-to-end rerun cleared the temporary public-edge and Google-auto-import blocker story.
- Current authoritative receipts now read:
  - `.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json`
    - `generated_at_utc=2026-07-06T04:29:29Z`
    - `status=pass`
    - `request_status=not_required`
    - `operator_action_still_required=false`
  - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `generatedAtUtc=2026-07-06T04:26:07.416941+00:00`
    - `status=pass`
    - `mobilePwaViewportStatus=pass`
  - `.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `generated_at_utc=2026-07-06T04:22:17.992Z`
    - `status=pass`
    - `/play phone-390 overflow_x=0`
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T04:29:50Z`
    - `status=fail`
    - failures are now only:
      - `windows_installer_visual_audit failed`
      - `windows installer visual audit source still targets c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b instead of promoted digest 80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a: /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`
      - `windows installer gold proof artifact is still missing: /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

- Interpretation:
  - the `/play` mobile overflow lane is currently green
  - the Google auto-import false positive is fixed
  - do not keep workers on either of those two lanes unless fresh failing receipts appear again
  - the live blocker story is back to the two durable launch blockers:
    - release posture is still preview-only
    - Windows promoted-digest visual proof is still missing

- Read this literally to the other Codexes:
  - Lane A: Windows proof only
    - promoted digest:
      - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - expected intake path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - current visual source is still stale:
      - `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
  - Lane B: release posture / stable-lane prep only
    - keep stable-lane work isolated
    - do not claim flagship/public-stable while preview posture or the missing Windows proof remains
  - Stand down these lanes:
    - `/play` phone-390 overflow
    - Google OAuth operator-evidence auto-import no-op
    - both are currently resolved by published receipts
  - do not re-open them from history-only handoff notes lower in this file

## Handoff refresh (2026-07-06T06:31:00+02:00)

- Finished the live My Media stale-namespace hardening pass and deployed it to the host watchdog:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/ops/host-workload/rclone-mount-watchdog.sh`
    - `/docker/chummercomplete/chummer.run-services/scripts/host_workload_guardrails_common.py`
    - `/docker/chummercomplete/chummer.run-services/tests/test_host_workload_guardrails.py`
    - `/docker/chummercomplete/chummer.run-services/tests/test_sync_host_workload_guardrails.py`
    - `/docker/chummercomplete/chummer.run-services/tests/test_rclone_mount_watchdog_script.py`
  - focused verification:
    - `python3 scripts/verify_host_workload_guardrails.py --repo-only`
    - `pytest -q tests/test_rclone_mount_watchdog_script.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py -k 'rclone_mount_watchdog or guardrail or sync_host_workload_guardrails'`
    - result: `10 passed`
  - live sync:
    - `printf 'rangersofB5\n' | sudo -S python3 scripts/sync_host_workload_guardrails.py --apply`
    - changed host asset:
      - `/usr/local/bin/rclone-mount-watchdog.sh`

- What changed in the watchdog:
  - stale-namespace recovery no longer assumes every consumer mounts the same host path as the cloud mountpoint
  - `mymediaalexa` now uses explicit probe/destination overrides:
    - mount destination: `/medialibrary`
    - probe target: `/medialibrary`
  - this lets the watchdog restart only `mymediaalexa` when its bind namespace goes stale while the host `/mnt/pcloud` mount itself is still healthy

- Live proof after deploying the watchdog:
  - `printf 'rangersofB5\n' | sudo -S systemctl start rclone-mount-watchdog.service`
  - journal now shows the exact repaired condition:
    - `Jul 06 06:24:59 ... mymediaalexa: mount namespace for /medialibrary is stale -> restarting container`
  - container/runtime proof after that restart:
    - `docker exec mymediaalexa sh -lc 'stat /medialibrary >/dev/null 2>&1 && ls -1A /medialibrary | sed -n "1,10p"'`
      - returned directories like `Audiobooks`, `Liz`, `Noah`, `Requested`, `Sonos`
    - `python3 scripts/ea_live_ops.py probe-mymedia-alexa --format json`
      - watch folders now read:
        - `watch_folder_states=["serving","serving"]`
        - `watch_folder_error_count=0`
      - current remaining blocker is now:
        - `status=blocked_connection_not_ready`
        - `reason=amazon_connection_not_ready`
      - this means the mount/watch-folder fault is fixed; the next recovery lane is the Amazon connection itself

- I also removed a noisy false-positive from the host workload receipt:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/scripts/materialize_host_workload_runtime_health.py`
    - `/docker/chummercomplete/chummer.run-services/tests/test_host_workload_runtime_health.py`
  - new behavior:
    - when the mirror is still in journal-fallback mode on one long-running current entry and ETA is suppressed as `journal_current_entry_long_running`, the receipt no longer also reports the contradictory advisory `plex_internxt_mirror_progress_stale`
  - focused verification:
    - `python3 -m py_compile scripts/materialize_host_workload_runtime_health.py tests/test_host_workload_runtime_health.py`
    - `pytest -q tests/test_host_workload_runtime_health.py -k 'host_workload_runtime_health or long_running_journal_entry_as_stale_progress or mirror_long_entry or mirror_failed'`
    - result: `11 passed`

- Refreshed published runtime truth after both fixes:
  - `.codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
    - `generated_at_utc=2026-07-06T04:29:13Z`
    - `runtime_status=degraded`
    - `advisory_findings=['internxt_cache_budget_exceeds_host_headroom']`
    - mirror line now honestly stays:
      - `mirror_eta_seconds=suppressed:journal_current_entry_long_running`
      - and no longer adds `plex_internxt_mirror_progress_stale`
  - `.codex-studio/published/MYMEDIA_PUBLIC_SURFACE.generated.json`
    - `generated_at_utc=2026-07-06T04:25:54Z`
    - `surface_status=access_protected`
    - `runtime_status=ready`
    - `mymedia_status=blocked_connection_not_ready`
  - `.codex-studio/published/EA_OPERATOR_READINESS.generated.json`
    - `generated_at_utc=2026-07-06T04:25:55Z`
    - `runtime_status=blocked`
    - My Media component now fails for:
      - `blocked:mymedia_alexa:blocked_connection_not_ready`
    - current My Media next action is:
      - `inspect_mymedia_amazon_connection`
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - host workload line now shows:
      - `advisory=internxt_cache_budget_exceeds_host_headroom`
      - `mirror_eta_seconds=suppressed:journal_current_entry_long_running`
    - My Media line now shows:
      - `mymedia public surface verifier: structural_status=pass mymedia_status=blocked_connection_not_ready runtime_status=ready`

- Read this literally to the other Codexes:
  - do not reopen the old My Media watch-folder bug; it has been repaired live
  - do not bounce the pCloud mount just because My Media is blocked; the current blocker is Amazon connection readiness, not `/medialibrary`
  - if you touch host workload receipts, preserve the new rule that long-running journal-fallback entries suppress stale-progress noise instead of reintroducing it

## Handoff refresh (2026-07-06T06:27:08+02:00)

- The mobile/public-edge lane is green in the current published receipts, and the top-level janitor truth has been refreshed from current evidence.
- Current end-to-end receipts now read:
  - `.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `generated_at_utc=2026-07-06T04:22:17.992Z`
    - `status=pass`
  - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `generatedAtUtc=2026-07-06T04:24:54.011937+00:00`
    - `status=pass`
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T04:26:13Z`
    - `status=fail`
    - root blockers are now only:
      - `release_lane_posture`
      - `windows_native_visual_proof`
    - `summary.local_surface_all_passing=true`
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T04:26:44Z`
    - `status=fail`
    - current top failures are now only:
      - `windows_installer_visual_audit failed`
      - stale Windows visual-audit source digest target
      - missing promoted Windows gold-proof bundle

- Interpretation:
  - do not keep working the earlier `/play phone-390` overflow story from the older section below; that artifact is now pass
  - do not reopen Google operator evidence; Google proof is already pass and no longer appears in the current top-level janitor failures
  - current blocker truth is narrowed to preview release posture plus the external Windows proof chain
  - the best authoritative blocker summary for the next Codex is `OPERATOR_RELEASE_DASHBOARD.generated.json`, not the older 06:12 readout below

## Handoff refresh (2026-07-06T06:18:54+02:00)

- Local flagship gate honesty is now hardened. Before this refresh, the direct `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json` receipt only exposed the digest mismatch, so the published flagship gate could underreport the current Windows blocker chain.
- Patched and verified:
  - `../chummer6-hub/scripts/verify_flagship_product_readiness_gate.py`
  - `../chummer6-hub/tests/test_flagship_product_readiness_gate.py`
  - focused result:
    - `3 passed`
- Reran:
  - `python3 /docker/chummercomplete/chummer6-hub/scripts/verify_flagship_product_readiness_gate.py --summary-output /docker/chummercomplete/chummer6-hub/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
- Current published flagship gate truth now reads:
  - `.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `generated_at_utc=2026-07-06T04:16:52Z`
    - launch-critical Windows details now include all three current blockers:
      - `Windows installer visual audit source digest does not match promoted installer`
      - `windows installer visual audit source still targets c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b instead of promoted digest 80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a: /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`
      - `windows installer gold proof artifact is still missing: /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
- Read this literally to the other Codexes:
  - do not assign Windows-proof work from the direct `WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json` failure list alone
  - the missing gold-proof bundle path above is again part of the published flagship truth
  - this did not clear any blocker; it only restored complete and honest gate reporting

## Handoff refresh (2026-07-06T06:12:07+02:00)

- The last full `final_gold_janitor.py` rerun changed the live blocker story again. Keep the 06:10:22 flagship-readiness note below, but do not let it hide the newer public-edge and Google-auto-import truth from the full chain.
- Current end-to-end receipts now read:
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T04:08:17Z`
    - `status=fail`
    - failures now include:
      - `public_edge_postdeploy_gate semantic proof failed`
      - `public_edge_postdeploy_gate failed`
      - `windows_installer_visual_audit failed`
      - `google oauth operator evidence bundle is still missing: /docker/chummercomplete/chummer.run-services/.state/incoming_google_oauth_linking_operator_evidence/google-oauth-linking-operator-evidence-run-20260704-170602.zip`
  - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `generatedAtUtc=2026-07-06T04:03:28.029874+00:00`
    - `status=fail`
    - failure:
      - `mobile PWA viewport Playwright proof is not pass`
  - `.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
    - `generated_at_utc=2026-07-06T04:02:39.093Z`
    - `status=fail`
    - exact failure:
      - `/play phone-390 has 130px horizontal overflow`
  - `.codex-studio/published/GOOGLE_OAUTH_LINKING_PROOF.generated.json`
    - `generated_at_utc=2026-07-06T04:07:45.305465Z`
    - `status=pass`
    - `operator_request_artifacts.request_status=not_required`

- Interpretation:
  - `/play` on `phone-390` is a real current public-edge blocker
  - the Google missing-bundle line in final gold is a false positive
    - Google proof is already `pass`
    - the no-op path in `scripts/auto_import_google_oauth_linking_operator_evidence.py --wait-seconds 0` is still being counted as a failed materializer
    - do not reopen Google operator intake or ask for fresh screenshots
  - the root blocker sheet at `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T04:33:11Z`
    - now matches the current narrowed blocker story again:
      - `release_posture:non_flagship_channel`
      - `release_truth:windows_installer_visual_audit`

- Independent launch truth that still remains:
  - release posture is still preview-only:
    - `channel=preview`
    - `supportability=preview_supported`
    - `rollout=promoted_preview`
  - the promoted Windows gold proof bundle is still missing:
    - digest:
      - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - expected intake path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

- Read this literally to the other Codexes:
  - Lane A: Windows proof only
    - own only promoted-digest bundle discovery/import or fresh Windows recapture
    - do not hand-edit receipts
  - Lane B: `/play` overflow only
    - start from:
      - `.codex-studio/published/public-edge-browser-proofs/mobile-viewport/MOBILE_PWA_VIEWPORT_SMOKE.generated.json`
      - `mobile-pwa-public.spec.ts`
      - `public-responsive-gold.spec.ts`
      - `../chummer-play/src/Chummer.Play.Web/wwwroot/index.html`
    - fix the `phone-390` horizontal overflow on `/play`
    - do not revive the older alias/build-lock story unless fresh receipts say so
  - Lane C: Google auto-import no-op only
    - start from:
      - `scripts/auto_import_google_oauth_linking_operator_evidence.py`
      - `tests/test_auto_import_google_oauth_linking_operator_evidence.py`
      - `scripts/final_gold_janitor.py`
      - `tests/test_final_gold_janitor.py`
    - make `request_status=not_required` exit cleanly without producing a fake missing-bundle blocker
    - do not ask for new Google operator evidence
  - Lane D: release posture / stable-lane prep only
    - do not claim flagship/public-stable while preview posture or any live blocker above remains

## Handoff refresh (2026-07-06T06:10:22+02:00)

- Fixed an upstream flagship receipt truth bug so the published readiness reason no longer contradicts the remaining Windows host-proof backlog:
  - patched:
    - `/docker/fleet/scripts/materialize_flagship_product_readiness.py`
    - `/docker/fleet/tests/test_materialize_flagship_product_readiness.py`
  - stale reason strings like
    - `No unresolved external desktop host-proof requests remain.`
    - `Journey proof is steady on current published evidence.`
  - are now rejected whenever `external_host_proof.unresolved_request_count > 0`

- Focused verification passed:
  - `python3 -m pytest -q /docker/fleet/tests/test_materialize_flagship_product_readiness.py -k 'ignores_stale_empty_external_host_reason or release_proof_journey_override_for_public_and_fleet_lanes'`
    - result: `2 passed`

- Refreshed receipt truth:
  - `/docker/fleet/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json`
  - `.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json`
  - synced local/current values now show:
    - `generated_at=2026-07-06T04:08:48Z`
    - `external_host_proof.status=fail`
    - `external_host_proof.unresolved_request_count=1`
    - `external_host_proof.reason=Run the missing windows proof lane for 1 desktop tuple(s), ingest receipts, and then republish release truth.`

- Gate verification still fail-closes for the real blockers only:
  - `python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - exit status: `1`
    - current launch-critical nested blockers:
      - `release channel channel is preview, not a flagship stable lane`
      - `release channel supportability is not gold_supported`
      - `release channel rollout is promoted_preview, not public_stable`
      - `Windows installer visual audit source digest does not match promoted installer`

## Handoff refresh (2026-07-06T06:01:00+02:00)

- Hardened the mirror ETA honesty for the exact live condition we hit on host:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/scripts/materialize_host_workload_runtime_health.py`
    - `/docker/chummercomplete/chummer.run-services/scripts/materialize_operator_release_dashboard.py`
    - `/docker/chummercomplete/chummer.run-services/ops/host-workload/README.md`
    - focused tests in:
      - `/docker/chummercomplete/chummer.run-services/tests/test_host_workload_runtime_health.py`
      - `/docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py`
  - new behavior:
    - when the mirror is still on an old pre-status-file run and the current journal item has turned into a long-running large directory copy, the receipt suppresses `mirror_eta_seconds` instead of inventing a count-based ETA from older phase markers
    - the receipt now exposes:
      - `eta_suppressed_reason`
      - `current_entry_source_bytes`
      - `current_entry_dest_bytes`
      - `current_entry_progress_ratio`
    - the operator dashboard now renders that as:
      - `mirror_eta_seconds=suppressed:journal_current_entry_long_running`
      - instead of `mirror_eta_seconds=0`

- Focused verification passed for this honesty slice:
  - `python3 -m py_compile scripts/materialize_host_workload_runtime_health.py tests/test_host_workload_runtime_health.py scripts/materialize_operator_release_dashboard.py tests/test_operator_release_dashboard_participate_billing.py`
  - `pytest -q tests/test_host_workload_runtime_health.py tests/test_operator_release_dashboard_participate_billing.py -k 'host_workload_runtime_health or host_workload_mirror_eta or host_workload_mirror or suppressed_host_workload_mirror_eta'`
  - result: `12 passed, 42 deselected in 0.36s`

- Current live mirror truth after refreshing the receipt/dashboard:
  - `.codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
    - `runtime_status=degraded`
    - `advisory_findings=['cache_filesystem_below_reserve_threshold']`
    - mirror fields now show:
      - `status=running`
      - `phase=tv`
      - `overall_current=1655`
      - `overall_total=2235`
      - `eta_seconds=null`
      - `eta_suppressed_reason=journal_current_entry_long_running`
      - `current_name=Grey's Anatomy {tmdb-1416}`
      - `current_entry_source_bytes=916924061767`
      - `current_entry_dest_bytes=46207396343`
      - `current_entry_progress_ratio=0.0504`
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - host workload line now prints:
      - `mirror_eta_seconds=suppressed:journal_current_entry_long_running`

- Live runtime nuance behind that suppression:
  - the mirror is not idle or hung; it is actively chewing through a very large TV directory
  - `rclone rc --rc-addr 127.0.0.1:5574 vfs/stats` still showed:
    - `uploadsInProgress=1`
    - live `CacheMaxSize=8589934592`
  - a 30-second live size sample on the current destination directory showed growth of `2376184885` bytes
  - because the mirror is still active and Internxt still has an upload in progress, the watchdog is correctly continuing to defer the mount restart onto the new 4G live cache budget

## Handoff refresh (2026-07-06T05:59:08+02:00)

- I finished the blocker-chain propagation for the Windows proof watcher so the truth is no longer stuck only in code/tests or mid-level receipts:
  - root blocker surface:
    - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.json`
    - `generated_at=2026-07-06T03:57:36Z`
    - Windows blocker now includes:
      - `auto_import_stage_visual_proof_receipt_count=8`
      - `auto_import_matching_promoted_stage_visual_proof_receipt_count=0`
      - `auto_import_stale_stage_visual_proof_receipt_count=8`
      - `auto_import_stage_visual_proof_receipt_note=Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.`
      - sample `auto_import_stage_visual_proof_hint_paths`
  - release-ready surface:
    - `.codex-studio/published/RELEASE_READY.generated.json`
    - `generated_at_utc=2026-07-06T03:54:14Z`
    - `blocking_gate_artifacts.public_release_snapshot_readonly_audit.status=pass`
  - final janitor surface:
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T03:56:57Z`
    - Windows gate now carries the same stale-hint counts plus `stageVisualProofHintAdvisory`
  - operator dashboard surface:
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T03:58:49Z`
    - failed release-blocking checks remain only:
      - `flagship_product_readiness`
      - `release_channel`
      - `release_ready`
      - `windows_installer_visual_audit`

- Current canonical release truth did not change:
  - the two root flagship blockers are still:
    - `release_posture:non_flagship_channel`
    - `release_truth:windows_installer_visual_audit`
  - the remaining external artifact gap is still the promoted-digest Windows gold proof bundle for:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - expected intake path remains:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

- New coordination note from the user:
  - on 2026-07-06, the user reported that the Windows installer worked during manual testing
  - preserve that as corroborating startup truth only
  - do not convert that report into release-green status unless it is attached to the digest-bound visual proof bundle/import chain

- Read this literally to any other Codex touching release truth:
  - do not hand-edit generated receipts
  - do not treat stage/nightly Windows proof hints as importable gold evidence
  - do not reopen already-green Google proof work without fresh failing receipts
  - if you work the Windows lane, own only bundle discovery/import or fresh promoted-digest recapture

## Handoff refresh (2026-07-06T05:58:00+02:00)
- Hardened the Plex->Internxt mirror ETA so operator surfaces stop extrapolating TV/requested phases from fast Movies throughput:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/scripts/materialize_host_workload_runtime_health.py`
    - `/docker/chummercomplete/chummer.run-services/tests/test_host_workload_runtime_health.py`
  - behavior change:
    - `journal` fallback ETA is now phase-aware
    - when at least two progress markers exist in the current phase, ETA uses that phase's own observed rate
    - when a new phase has only one marker so far, ETA is suppressed instead of emitting a misleading carry-over estimate from the previous phase
    - first-phase runs can still use the original overall-from-start fallback
  - receipt now carries:
    - `items_per_minute_source`

- Focused verification for the ETA hardening passed:
  - `python3 -m py_compile scripts/materialize_host_workload_runtime_health.py`
  - `pytest -q tests/test_host_workload_runtime_health.py tests/test_operator_release_dashboard_participate_billing.py -k 'host_workload_runtime_health or host_workload_mirror_eta or host_workload_mirror'`
  - result: `10 passed, 42 deselected in 0.22s`

- Refreshed the live host-workload receipt after the ETA fix:
  - `python3 scripts/materialize_host_workload_runtime_health.py --output .codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
  - `python3 scripts/verify_host_workload_runtime_health.py --receipt .codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
  - current mirror truth in the published receipt:
    - `status=running`
    - `phase=tv`
    - `overall_current=1655`
    - `overall_total=2235`
    - `items_per_minute=28.29`
    - `items_per_minute_source=current_phase`
    - `eta_seconds=1230`
  - this replaced the earlier misleading TV-phase estimate that had been inherited from the end of the Movies segment

- Refreshed the operator dashboard after the host-workload ETA fix:
  - `python3 scripts/materialize_operator_release_dashboard.py`
    - still exits nonzero because of the real global release blockers
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - host workload line now reports:
      - `mirror_phase=tv`
      - `mirror_progress=1655/2235`
      - `mirror_eta_seconds=1230`

## Handoff refresh (2026-07-06T05:56:00+02:00)

- Hardened the EA/MyMedia operator receipt verifiers so older published receipts no longer fail just because they predate the newer derived runtime fields:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/scripts/verify_ea_operator_readiness.py`
    - `/docker/chummercomplete/chummer.run-services/scripts/verify_mymedia_public_surface.py`
  - behavior change:
    - if `runtime_status`, `runtime_ready`, `blocking_count`, `advisory_count`, `blocking_findings`, or `advisory_findings` are absent from older receipts, the verifiers now derive those values from the receipt's already-present component/public-surface truth instead of fail-closing on blank defaults
    - explicit mismatched values still fail; only omitted legacy fields are backfilled

- Added focused regression coverage for that backward-compatible verifier behavior:
  - `/docker/chummercomplete/chummer.run-services/tests/test_ea_operator_readiness.py`
  - `/docker/chummercomplete/chummer.run-services/tests/test_verify_mymedia_public_surface.py`
  - focused verification passed:
    - `pytest -q tests/test_ea_operator_readiness.py tests/test_verify_mymedia_public_surface.py tests/test_operator_release_dashboard_participate_billing.py -k 'ea_operator_readiness or mymedia_public_surface'`
    - result: `19 passed, 40 deselected in 0.50s`
    - `python3 -m py_compile scripts/verify_ea_operator_readiness.py scripts/verify_mymedia_public_surface.py`

- Proved the live payoff on the existing published receipts without rematerializing them first:
  - `python3 scripts/verify_ea_operator_readiness.py --receipt .codex-studio/published/EA_OPERATOR_READINESS.generated.json`
    - now returns `status=pass`
    - derived runtime truth:
      - `runtime_status=blocked`
      - `blocking_count=3`
      - `advisory_count=2`
  - `python3 scripts/verify_mymedia_public_surface.py --receipt .codex-studio/published/MYMEDIA_PUBLIC_SURFACE.generated.json`
    - now returns `status=pass`
    - derived runtime truth:
      - `runtime_status=ready`
      - `runtime_ready=true`

- Refreshed the operator dashboard after that verifier hardening:
  - `python3 scripts/materialize_operator_release_dashboard.py`
    - still exits nonzero because the repo still has real global release blockers
    - but the EA/MyMedia operator sections are now honest
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
    - `ea_operator_readiness` now shows:
      - `ea operator receipt verifier: structural_status=pass operator_status=ready_with_actions runtime_status=blocked`
      - no stale mismatch failures
    - `mymedia_public_surface` now shows:
      - `mymedia public surface verifier: structural_status=pass mymedia_status=blocked_watch_folder_error runtime_status=ready`
      - no stale runtime mismatch failures

- Current live-host nuance at handoff time:
  - the Plex->Internxt mirror was still active after switching into the TV phase
  - latest observed marker:
    - `TV progress 100/496: Grey's Anatomy {tmdb-1416} -> G`
  - the host-workload advisory remains the same honest one until the mirror is idle and the watchdog can restart the Internxt mount onto the new 4G live cache budget

## Handoff refresh (2026-07-06T05:50:00+02:00)

- Closed the live host-workload asset drift on the rclone mount watchdog:
  - patched repo asset:
    - `/docker/chummercomplete/chummer.run-services/ops/host-workload/rclone-mount-watchdog.sh`
  - small hardening:
    - `STATE_DIR` and `LOCKFILE` are now env-overridable so the watchdog can be function-tested without writing to `/run`
    - verifier snippet coverage now explicitly includes the config-drift recovery path
  - new focused tests:
    - `/docker/chummercomplete/chummer.run-services/tests/test_rclone_mount_watchdog_script.py`
    - expanded assertions in:
      - `/docker/chummercomplete/chummer.run-services/tests/test_host_workload_guardrails.py`
      - `/docker/chummercomplete/chummer.run-services/tests/test_sync_host_workload_guardrails.py`
  - focused verification passed:
    - `bash -n ops/host-workload/rclone-mount-watchdog.sh`
    - `pytest -q tests/test_rclone_mount_watchdog_script.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py -k 'rclone_mount_watchdog or guardrail or sync_host_workload_guardrails'`
    - result: `9 passed in 0.65s`

- Re-synced the repo-managed watchdog asset onto the live host:
  - `python3 scripts/sync_host_workload_guardrails.py --apply`
  - changed asset:
    - `ops/host-workload/rclone-mount-watchdog.sh` -> `/usr/local/bin/rclone-mount-watchdog.sh`
  - result:
    - `changed_count=1`
    - `status=pass`

- Proved the new live config-drift deferral path under real runtime conditions:
  - manually started:
    - `systemctl start rclone-mount-watchdog.service`
  - current live blocker was still active:
    - `plex-internxt-mirror.service`
  - watchdog journal now shows the intended behavior:
    - `internxt: runtime cache max size 8589934592 != configured 4294967296, but blocker units are active -> deferring mount restart`
  - practical meaning:
    - the watchdog will no longer require a human to remember the deferred Internxt mount bounce
    - once the mirror lane is idle and Plex is not actively serving sessions, the timer-driven watchdog can restart the mount automatically so the live process picks up the repo-installed `4G` cap

- Current live host-workload truth after the watchdog sync and receipt refresh:
  - `python3 scripts/verify_host_workload_guardrails.py`
    - `status=pass`
    - no remaining live-host guardrail drift/failures
  - `.codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
    - `runtime_status=degraded`
    - `guardrail_verifier_status=pass`
    - `guardrail_failures=[]`
    - only remaining advisory:
      - `internxt_cache_budget_exceeds_host_headroom`
    - current live Internxt process still reports:
      - `internxt_cache_max_size_bytes=8589934592`
      - `internxt_cache_bytes_used=7434294814`
    - mirror still running:
      - `mirror_status=running`
      - `mirror_progress=1450/2235`
      - `mirror_eta_seconds=244`

- Net result:
  - the fake/red herring host-workload degradation is gone
  - the only remaining host-workload issue is the honest one: the active Internxt mount still needs its post-mirror idle restart to shed the old 8G runtime cache ceiling

## Handoff refresh (2026-07-06T05:48:08+02:00)

- Propagated the Windows stage-proof hint hardening into the published operator/blocker surfaces:
  - reran:
    - `python3 scripts/materialize_release_ready_receipt.py`
    - `python3 scripts/materialize_operator_release_dashboard.py`
  - current published receipt truth:
    - `.codex-studio/published/RELEASE_READY.generated.json`
      - `generated_at_utc=2026-07-06T03:47:21Z`
      - `status=fail`
      - `blocking_gate_artifacts.windows_installer_visual_audit.auto_import_stage_visual_proof_receipt_count=8`
      - `blocking_gate_artifacts.windows_installer_visual_audit.auto_import_stage_visual_proof_receipt_note=Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.`
      - `nextActions` now includes:
        - review the surfaced Windows stage/nightly proof hints in `WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
        - sample stale hint paths for old capture output recovery
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
      - `generated_at_utc=2026-07-06T03:47:29Z`
      - `status=fail`
      - Windows advisory action now explicitly says the stage/nightly proof hints are locator-only and must not be treated as importable gold-proof bundles
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
      - now prints:
        - `windows stage-proof hints: total=8 matching_promoted=0 stale=8`
        - sample stale hint paths
        - the stage-proof hint note

- Practical effect:
  - the blocker did not clear
  - the operator-facing surfaces are now honest and actionable without requiring manual JSON spelunking
  - the remaining ask is still the promoted-digest Windows gold bundle, not any surfaced stage/nightly proof receipt

## Handoff refresh (2026-07-06T05:39:49+02:00)

- Landed the missing watcher hardening in `scripts/auto_import_windows_installer_gold_proof.py`:
  - standalone `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` files are now surfaced as non-actionable stage/nightly hints
  - the watcher still keeps gold import fail-closed:
    - `selected_candidate(...)` ignores those receipt rows
    - `actionable_waiting_candidates(...)` excludes them
    - `build_waiting_payload(...)` reports them separately instead of treating them as importable artifacts
  - focused verification passed:
    - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py -k 'surfaces_stage_visual_proof_receipts_without_auto_selecting_them or waiting_payload_surfaces_stage_visual_proof_receipt_hints_separately or waiting_payload_surfaces_expected_bundle_details or waiting_payload_surfaces_matching_directory_candidates or does_not_auto_select_stale_directory_candidates or auto_selects_matching_directory_candidates'`
    - result: `6 passed, 49 deselected in 0.12s`
    - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py`

- Refreshed the real waiting receipt with the patched watcher:
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
  - `status=waiting_for_artifact`
  - `actionable_candidate_count=0`
  - `directory_candidate_count=11`
  - `matching_promoted_directory_candidate_count=0`
  - `stale_directory_candidate_count=11`
  - `stage_like_stale_directory_candidate_count=1`
  - `stage_visual_proof_receipt_count=8`
  - `matching_promoted_stage_visual_proof_receipt_count=0`
  - `stale_stage_visual_proof_receipt_count=8`
  - `suppressed_stale_stage_visual_proof_receipt_count=3`
  - `stage_visual_proof_receipt_note=Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.`

- Practical outcome:
  - the blocker did not change
  - there is still no matching promoted-digest gold bundle
  - the repo now exposes stale stage/nightly proof receipt paths as locator hints instead of hiding them
  - do not import those hint receipts as if they were the flagship gold visual-audit bundle


## Handoff refresh (2026-07-06T05:39:30+02:00)

- Closed the stale `qbittorrent-staging-hygiene-watchdog.timer` runtime failure on the live host:
  - before:
    - `qbittorrent-staging-hygiene-watchdog.timer`
    - `Loaded: ... disabled`
    - `Active: inactive (dead)`
  - applied live:
    - `systemctl enable --now qbittorrent-staging-hygiene-watchdog.timer`
  - current verifier truth after enable:
    - `python3 scripts/verify_host_workload_guardrails.py`
    - `status=pass`
    - no remaining live-host guardrail failures

- Tightened the Internxt rclone cache budget in the repo-managed host guardrails:
  - patched:
    - `/docker/chummercomplete/chummer.run-services/ops/host-workload/rclone-mount-internxt-cache-tuning.conf`
    - `/docker/chummercomplete/chummer.run-services/scripts/host_workload_guardrails_common.py`
    - related focused tests and docs
  - new target:
    - `--vfs-cache-max-size 4G`
    - previous value was `8G`
  - reason:
    - the old Internxt cache budget plus the pCloud write-cache budget could consume essentially the whole remaining rootfs headroom on this host
    - that made the host-workload receipt degrade with a generic cache-reserve warning even though the real issue was the Internxt cache lane

- Applied that new Internxt cache budget file onto the host without restarting the live mount:
  - `printf 'rangersofB5\n' | sudo -S python3 scripts/sync_host_workload_guardrails.py --apply`
  - changed asset:
    - `ops/host-workload/rclone-mount-internxt-cache-tuning.conf` -> `/etc/systemd/system/rclone-mount@internxt.service.d/zz-cache-budget.conf`
  - `systemctl daemon-reload` completed and `NeedDaemonReload=no`
  - important live nuance:
    - the currently running `rclone-mount@internxt.service` process still reports the old live VFS option set until that mount is restarted in an idle window
    - the on-disk host config is now correct; the live process has not yet been bounced because the mirror lane is active

- Made the host-workload receipt more specific and operator-useful around cache pressure:
  - `materialize_host_workload_runtime_health.py` now samples both:
    - pCloud VFS stats via `127.0.0.1:5572`
    - Internxt VFS stats via `127.0.0.1:5574`
  - when root/cache free space is below the reserve and Internxt cache bytes are materially high with no queued uploads, the receipt now emits:
    - `internxt_cache_budget_exceeds_host_headroom`
    - instead of the older generic `cache_filesystem_below_reserve_threshold`
  - dashboard summary now includes:
    - `internxt_cache_bytes=<bytes>`

- Current live EA/operator receipt truth after that refresh:
  - `.codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
    - `runtime_status=degraded`
    - `advisory_findings=['internxt_cache_budget_exceeds_host_headroom']`
    - `advisory_action_component_keys=['internxt']`
    - `disk_free_gib_root=18.94`
    - `internxt_cache_bytes_used=6654880097`
    - `internxt_cache_max_size_bytes=8589934592`
  - the receipt is now honest about the real remaining operator action:
    - restart the Internxt rclone mount in an idle window so the live process picks up the new `4G` cap and sheds old cache pressure

- Current live dashboard truth after refresh:
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
  - host-workload line now reads:
    - `advisory=internxt_cache_budget_exceeds_host_headroom`
    - `internxt_cache_bytes=6654880097`
    - `mirror=running`
    - `mirror_phase=movies`
  - global dashboard status is still `fail`, but only because of the pre-existing Windows release-proof blockers, not because of the host-workload lane

- Focused verification passed for this cache/receipt hardening slice:
  - `python3 -m py_compile scripts/materialize_host_workload_runtime_health.py scripts/materialize_operator_release_dashboard.py scripts/host_workload_runtime_health_contract.py`
  - `pytest -q tests/test_host_workload_runtime_health.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py tests/test_operator_release_dashboard_participate_billing.py -k 'host_workload_runtime_health or host_workload_mirror_eta or guardrail or host_workload_mirror or host_workload_runtime'`
  - result: `15 passed, 41 deselected in 0.93s`

## Handoff refresh (2026-07-06T05:33:39+02:00)

- Re-audited the exact remaining Windows flagship blocker so concurrent Codex sessions stop guessing at the intake state:
  - `RELEASE_BLOCKERS.generated.json` still reduces to only:
    - `release_posture:non_flagship_channel`
    - `release_truth:windows_installer_visual_audit`
  - the live Windows ask remains the same promoted digest:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - preferred bundle path is still:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

- Rechecked local artifact discovery with the current intake contract:
  - no matching gold-proof zip exists yet under:
    - `chummer.run-services/.state/incoming_windows_installer_gold_proof`
    - `/tmp`
    - `~/Downloads`
    - `~/pCloud Drive/EA`
  - current watcher receipt before the watcher hardening refresh:
    - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `status=waiting_for_artifact`
    - `directory_candidate_count=11`
    - `matching_promoted_directory_candidate_count=0`
    - `stale_directory_candidate_count=11`
    - `stage_like_stale_directory_candidate_count=1`
  - stale directory digest summary is still only:
    - `c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51` across 9 directories
    - `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b` across 2 directories

- The key integration mismatch is now explicit:
  - the Windows host handoff and `chummer6-ui/scripts/capture-windows-installer-visual-proof.ps1` produce `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json`
  - the flagship import/audit lane here still requires `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json` in a gold bundle or extracted proof directory
  - at that earlier point in the session, `scripts/auto_import_windows_installer_gold_proof.py` still detected full gold bundles/directories only
  - that mismatch has since been patched in the newer `2026-07-06T05:39:49+02:00` refresh above

- Current staged proof receipt is stale and not sufficient for gold import:
  - `Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json`
  - `status=pass`
  - `releaseVersion=run-20260701-124648`
  - `artifactDigest=sha256:4d14c414fcd46f4cf5d2b06ac12d02d8492431f19924bffa97390af5f1c68bf3`
  - `installerDigest=sha256:5836ae868913c862266a18d091bae77953c67e9d7162b52040bf9cd22c881642`
  - it contains only `progress` and `completion` screenshot roles and does not satisfy the richer gold visual-audit contract by itself

- Safe lane guidance for the next Codex:
  - do not hand-edit digests or downgrade the gold-proof requirement
  - do not import a raw `WINDOWS_INSTALLER_VISUAL_PROOF.generated.json` receipt as if it were the flagship gold bundle
  - either:
    - obtain the real promoted-digest bundle and run:
      - `python3 scripts/import_windows_installer_gold_proof_artifact.py /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify`
    - or, after the later watcher hardening now landed, use the surfaced stale stage/nightly receipt paths as locator hints while still keeping gold import fail-closed

## Handoff refresh (2026-07-06T05:28:48+02:00)

- Added a machine-readable runtime status surface for the Plex-to-Internxt mirror lane:
  - repo/host script:
    - `/docker/chummercomplete/chummer.run-services/ops/host-workload/plex-internxt-mirror.sh`
    - installed host target updated:
      - `/usr/local/sbin/plex-internxt-mirror.sh`
  - new behavior:
    - writes `/run/plex-internxt-mirror/status.json` atomically
    - state includes `status`, `phase`, `phase_current`, `phase_total`, `overall_current`, `overall_total`, `current_name`, `current_detail`, `run_started_at`, `updated_at`, `last_error`, and `exit_code`
    - writes failure state on nonzero exit and completion state on success
  - important live nuance:
    - the currently running mirror process started before that host script update, so it is still progressing without a status file
    - the next timer/service run will publish the new status file natively

- `materialize_host_workload_runtime_health.py` now understands the Internxt mirror lane directly instead of leaving progress hidden in ad hoc shell checks:
  - reads `/run/plex-internxt-mirror/status.json` when present
  - falls back to recent `plex-internxt-mirror.service` journal progress when a current run predates the new status-file contract
  - derives operator-safe mirror fields:
    - `status`
    - `phase`
    - `overall_current`
    - `overall_total`
    - `items_per_minute`
    - `eta_seconds`
    - `eta_at`
    - `stale_seconds`
  - those fields now flow into:
    - `.codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
    - `scripts/materialize_operator_release_dashboard.py` host-workload summary line

- Focused verification for the new mirror observability layer passed:
  - `bash -n ops/host-workload/plex-internxt-mirror.sh`
  - `pytest -q tests/test_plex_internxt_mirror_script.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py tests/test_host_workload_runtime_health.py tests/test_operator_release_dashboard_participate_billing.py -k 'plex_internxt_mirror or host_workload_runtime_health or host_workload_mirror_eta or guardrail'`
  - result: `20 passed, 40 deselected in 2.22s`

- Live host workload receipt was refreshed after the observability patch:
  - command:
    - `python3 scripts/materialize_host_workload_runtime_health.py --output .codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
    - `python3 scripts/verify_host_workload_runtime_health.py --receipt .codex-studio/published/HOST_WORKLOAD_RUNTIME_HEALTH.generated.json`
  - current receipt truth from that live refresh:
    - `status=pass`
    - `runtime_status=degraded`
    - current advisories were unrelated to the mirror route logic:
      - `cache_filesystem_below_reserve_threshold`
      - `host_workload_guardrail_failures_present`
    - current mirror observation in the refreshed receipt:
      - `mirror_status=running`
      - `mirror_source=journal`
      - `mirror_phase=movies`
      - `mirror_overall_current=625`
      - `mirror_overall_total=2235`
      - `mirror_eta_seconds=1788`
      - `mirror_eta_at=2026-07-06T03:57:56Z`
      - `mirror_current_name=Guardians of the Galaxy Vol. 2 (2017)`

- Repo/host drift for the mirror script was already reconciled again:
  - `printf 'rangersofB5\n' | sudo -S python3 scripts/sync_host_workload_guardrails.py --apply`
  - result:
    - `status=pass`
    - `changed_count=1`
    - updated asset:
      - `ops/host-workload/plex-internxt-mirror.sh` -> `/usr/local/sbin/plex-internxt-mirror.sh`

## Handoff refresh (2026-07-06T05:20:39+02:00)

- Refreshed the mobile cross-surface evidence after the route-proof hardening so the `chummer-play` lane stops replaying resolved route/version drift as if it were current truth.
  - patched:
    - `/docker/chummercomplete/chummer-play/scripts/materialize_mobile_cross_surface_readiness.py`
    - `/docker/chummercomplete/chummer-play/scripts/materialize_mobile_local_release_proof.py`
    - `/docker/chummercomplete/chummer-play/tests/test_mobile_cross_surface_refresh_contract.py`
  - new behavior:
    - if the strict public-edge postdeploy receipt is older than the current strict preflight receipt, the mobile lane now marks that strict postdeploy receipt as stale and does not replay its old product-level failures as current blocker truth
    - this keeps the mobile lane fail-closed while making the blocker family honest
  - focused verification passed:
    - `python3 -m unittest discover -s /docker/chummercomplete/chummer-play/tests -p 'test_mobile_cross_surface_refresh_contract.py'`
    - result: `Ran 6 tests in 1.705s`
    - `python3 -m py_compile /docker/chummercomplete/chummer-play/scripts/materialize_mobile_cross_surface_readiness.py /docker/chummercomplete/chummer-play/scripts/materialize_mobile_local_release_proof.py /docker/chummercomplete/chummer-play/tests/test_mobile_cross_surface_refresh_contract.py`

- Current public-edge/mobile truth is now split cleanly into two realities instead of one stale merged story:
  - live relaxed/canonical public-edge route and surface truth is still green:
    - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=pass`
    - `generatedAtUtc=2026-07-06T01:43:39.373037+00:00`
    - `preflightStatus=pass`
    - `frontdoorNavigationPlayRoute=/mobile/player`
    - `readyMobileHandoffFrontdoorLaunchRoute=/mobile/player`
  - strict current preflight truth is currently blocked by active foreign build locks:
    - `/tmp/chummer-public-edge-deploy-preflight-current.json`
    - `status=fail`
    - `generatedAtUtc=2026-07-06T03:16:40.365067+00:00`
    - current blocker findings:
      - `bash pid 2190701 matches build-chummer6-linux`
      - `bash pid 2201485 matches build-chummer6-linux`
    - the older `191868` / `202947` pair are now only stale-looking auto-ignored locks in that current preflight receipt, not the live blocker pair

- Current `chummer-play` proof truth after refresh:
  - `.codex-studio/published/MOBILE_CROSS_SURFACE_READINESS.generated.json`
    - `status=fail`
    - `generated_at_utc=2026-07-06T03:19:11Z`
    - `public_edge.live_gate_status=pass`
    - `public_edge.strict_status=fail`
    - `public_edge.strict_preflight_status=fail`
    - `public_edge.strict_postdeploy_status=fail`
    - `public_edge.strict_postdeploy_stale=true`
    - current failure list is now narrowed to:
      - `strict public-edge preflight receipt is not pass`
      - `bash pid 2190701 matches build-chummer6-linux`
      - `bash pid 2201485 matches build-chummer6-linux`
      - `strict public-edge postdeploy receipt is older than the current strict preflight receipt`
  - `.codex-studio/published/MOBILE_LOCAL_RELEASE_PROOF.generated.json`
    - `status=passed`
    - `generated_at_utc=2026-07-06T03:19:47Z`
    - now carries that same narrowed cross-surface blocker truth downstream
  - `bash /docker/chummercomplete/chummer-play/scripts/release/verify_mobile_release_proof.sh`
    - result: `mobile release proof ok`

- Honest next action did not change:
  - do not call the mobile/public-edge lane finished while the foreign `build-chummer6-linux` locks above are still active
  - once those foreign lanes clear, rerun:
    - `python3 scripts/check_public_edge_deploy_preflight.py --output /tmp/chummer-public-edge-deploy-preflight-current.json`
    - `python3 scripts/verify_public_edge_postdeploy_gate.py --base-url https://chummer.run --output /tmp/chummer-public-edge-postdeploy-canonical-current.json`
    - `python3 /docker/chummercomplete/chummer-play/scripts/materialize_mobile_cross_surface_readiness.py`
    - `python3 /docker/chummercomplete/chummer-play/scripts/materialize_mobile_local_release_proof.py`

## Handoff refresh (2026-07-06T05:14:14+02:00)

- Corrected the Internxt mirror lane so `Requested` is no longer treated as a third destination shelf.
  - required behavior is now explicit in repo docs and tests:
    - `Requested/Movies` routes into bucketed `PLEX/Movies/<bucket>/<title>`
    - `Requested/TV` routes into bucketed `PLEX/TV/<bucket>/<show>`
    - `Requested/Unsorted` and `Requested/_inbox` are classified into movie or TV destinations before copy
  - there is intentionally no `REQUESTED_DEST` in the installed host script anymore

- Fixed the live copy failure mode on Internxt:
  - root cause was rsync's temp-file rename flow failing on the Internxt mount with `Input/output error (5)` during artwork sidecar writes
  - the host mirror now uses `rsync --inplace --partial` for the bucketed movie, TV, and requested-routing writes
  - the previously failing `Ad Astra (2019)` artwork folder now copies successfully on Internxt

- Live host rollout was applied through the repo guardrail sync path:
  - `python3 scripts/sync_host_workload_guardrails.py --apply`
  - `systemctl daemon-reload`
  - `systemctl reset-failed plex-internxt-mirror.service`
  - `systemctl start plex-internxt-mirror.service`
  - current live state during this handoff update:
    - `plex-internxt-mirror.service` is active and still processing the large movie tree
    - `systemctl status` shows the installed host command using `rsync -a --inplace --partial`

- Installed-host routing proof was verified directly with the sourced service script:
  - `_inbox/Greys.Anatomy.S22E01...mkv` resolves to:
    - `/mnt/internxt/PLEX/TV/G/Greys Anatomy/Greys.Anatomy.S22E01.1080p.WEB.h264-ETHEL[EZTVx.to].mkv`
  - `_inbox/Minions.The.Rise.of.Gru.2022...mkv` resolves to:
    - `/mnt/internxt/PLEX/Movies/M/Minions The Rise of Gru (2022)/Minions.The.Rise.of.Gru.2022.D.MVO.BDRip.1080p.seleZen.mkv`

- Focused repo verification for this lane passed:
  - `pytest -q tests/test_plex_internxt_mirror_script.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py -k 'plex_internxt_mirror or guardrail'`
  - result: `11 passed in 0.80s`

## Handoff refresh (2026-07-06T05:08:38+02:00)

- Rechecked live public-edge mobile aliases against runtime truth instead of trusting the older drift note:
  - `curl -I https://chummer.run/player`
    - current result: `302 location: /mobile/player`
  - `curl -I https://chummer.run/gm`
    - current result: `302 location: /mobile/gm`
  - `curl -I https://chummer.run/observer`
    - current result: `302 location: /mobile/observer`
  - direct role routes currently return `200`:
    - `/mobile/player`
    - `/mobile/gm`
    - `/mobile/observer`
  - the older 2026-07-05 handoff note about live `/play?role=...` redirects is now historical drift, not current runtime truth

- Refreshed the stale live route-proof artifact so current published evidence no longer contradicts runtime:
  - reran:
    - `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest /docker/chummercomplete/chummer-design/products/chummer/PUBLIC_LANDING_MANIFEST.yaml --output /docker/chummercomplete/chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json`
  - current live proof truth:
    - `.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json`
    - `status=pass`
    - `generated_at_utc=2026-07-06T03:04:53.371596Z`
    - alias entries now record redirect expectations to:
      - `/mobile/player`
      - `/mobile/gm`
      - `/mobile/observer`

- Closed the selector hardening gap that allowed an older canonical live route proof to outrank a fresher canonical published proof:
  - patched:
    - `scripts/final_chummer_run_ux_verdict.py`
    - `scripts/final_pre_gold_full_product_verdict.py`
    - `tests/test_route_proof_selection.py`
  - new behavior:
    - if both canonical live and canonical published route proofs are passable, the verdict selectors now choose the newer timestamp instead of blindly preferring `*.live.generated.json`
    - this prevents a stale live alias proof from masking fresher manifest-driven public-edge evidence
  - focused verification passed:
    - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_route_proof_selection.py`
    - result: `4 passed in 0.13s`
    - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/final_chummer_run_ux_verdict.py /docker/chummercomplete/chummer.run-services/scripts/final_pre_gold_full_product_verdict.py /docker/chummercomplete/chummer.run-services/tests/test_route_proof_selection.py`
  - current selector truth:
    - `final_pre_gold_full_product_verdict.load_live_or_local_route_proof()` now resolves to:
      - `mode=live`
      - `base_url=https://chummer.run`
      - `status=pass`
      - `generated_at_utc=2026-07-06T03:04:53.371596Z`

- Honest blocker state still did not change:
  - release posture is still preview-only
  - the remaining hard external blocker is still the missing promoted-digest Windows visual proof bundle for:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - preferred import path remains:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T05:00:45+02:00)

- Completed the broader SR6 companion release-script normalization instead of leaving the first three fixes as isolated patches:
  - both companion repos now use the bash3 / nounset-safe `array_count` pattern across:
    - `scripts/run-desktop-startup-smoke.sh`
    - `scripts/publish-download-bundle-http.sh`
    - `scripts/generate-releases-manifest.sh`
    - `scripts/publish-download-bundle.sh`
    - `scripts/publish-download-bundle-s3.sh`
    - `scripts/verify-releases-manifest.sh`
    - `scripts/build-desktop-installer.sh`
  - patched repos:
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench`

- Regression coverage is now tighter at both levels:
  - central run-services coverage expanded in:
    - `tests/test_release_shell_array_portability.py`
  - companion repo-local coverage added in:
    - `chummer-presentation-sr6-origin-dialog-clean/tests/test_release_shell_array_portability.py`
    - `chummer-presentation-sr6-attribute-workbench/tests/test_release_shell_array_portability.py`
  - updated local companion policy checks in:
    - `tests/test_desktop_downloads_local_release_policy.py` in both SR6 companion repos

- Validation passed:
  - forbidden-pattern search across the eight newly touched sibling release scripts returned clean
  - `bash -n` passed for all eight touched sibling release scripts
  - central focused suite:
    - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_desktop_startup_smoke_bash_compat.py /docker/chummercomplete/chummer.run-services/tests/test_publish_download_bundle_http_bash_portability.py /docker/chummercomplete/chummer.run-services/tests/test_release_shell_array_portability.py`
    - result: `4 passed in 0.40s`
  - repo-local companion suites:
    - `python3 -m pytest -q --import-mode=importlib /docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/tests/test_desktop_downloads_local_release_policy.py /docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/tests/test_release_shell_array_portability.py`
    - result: `26 passed in 0.29s`
    - `python3 -m pytest -q --import-mode=importlib /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/tests/test_desktop_downloads_local_release_policy.py /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/tests/test_release_shell_array_portability.py`
    - result: `26 passed in 0.69s`

- Important verification nuance:
  - when invoking pytest across both SR6 companion repos in one command, use `--import-mode=importlib`
  - both repos contain same-basename test modules, so plain pytest collection reports import-file mismatch even when the code is fine

- Honest blocker state is still unchanged:
  - release posture is still preview-only
  - the remaining hard external blocker is still the missing promoted-digest Windows visual proof bundle for:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - preferred import path remains:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T04:51:24+02:00)

- The scoped EA/qBittorrent handoff was refreshed again after the later hardening pass and now supersedes the older 04:44 section as the source of truth:
  - `EA_LIVE_OPS_QBIT_HANDOFF_20260706.md`

- What changed since that older qBit note:
  - the previously identified follow-through is no longer pending; it is landed
  - qBit receipt `stdout_tail` now uses a public source label and its verifier rejects unsafe source paths
  - the qBit watchdog now has a repo-shipped default env surface:
    - `ops/host-workload/qbittorrent-staging-hygiene-watchdog.default`
  - the operator dashboard now shows:
    - `dead_checking`
    - `requeued_meta`
    - `requeued_stalled`
    - `requeued_checking`

- Latest live truth for that lane:
  - `.codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
    - `generated_at_utc=2026-07-06T02:49:14Z`
    - `runtime_status=ready`
    - `runtime_ready=true`
    - `queueing_enabled=true`
    - `dead_meta_candidate_count=0`
    - `dead_stalled_candidate_count=0`
    - `dead_checking_candidate_count=0`
  - `python3 scripts/verify_qbittorrent_staging_hygiene.py --receipt .codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
    - `status=pass`
    - `failures=[]`
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `generated_at_utc=2026-07-06T02:49:15Z`
    - qBit lane is green there too; overall dashboard fail is still caused by preview release posture and the missing promoted Windows visual proof bundle

- Focused validation for the qBit follow-through passed:
  - `python3 -m py_compile scripts/materialize_qbittorrent_staging_hygiene.py scripts/verify_qbittorrent_staging_hygiene.py scripts/host_workload_guardrails_common.py scripts/materialize_operator_release_dashboard.py`
  - `pytest -q tests/test_qbittorrent_staging_hygiene.py tests/test_host_workload_guardrails.py tests/test_sync_host_workload_guardrails.py -q`
  - `pytest -q tests/test_operator_release_dashboard_participate_billing.py -k 'qbittorrent_staging_hygiene or mymedia_public_surface' -q`
  - `python3 scripts/verify_host_workload_guardrails.py --repo-only`

## Handoff refresh (2026-07-06T04:49:18+02:00)

- Closed the same bash3 / nounset shell-portability drift in the other SR6 companion repo so release evidence does not depend on which workbench copy a codex touches:
  - patched:
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/run-desktop-startup-smoke.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/generate-releases-manifest.sh`
  - normalized those copies to the same helper posture already fixed in the main and origin-dialog companion copies:
    - nounset-safe `array_count`
    - no raw `${#windows_payload_gate_args[@]}`
    - no raw `${#upload_files[@]}`
    - no raw `${#promoted_file_names[@]}`
    - no raw `${#portal_artifacts[@]}`
    - no old `eval "set -- \${${array_name}[@]+...}"` startup-smoke helper form

- Expanded the shared run-services regression coverage again so this sibling repo is now pinned too:
  - patched:
    - `tests/test_desktop_startup_smoke_bash_compat.py`
    - `tests/test_publish_download_bundle_http_bash_portability.py`
    - `tests/test_release_shell_array_portability.py`
  - focused validation passed:
    - `bash -n /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/run-desktop-startup-smoke.sh /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle-http.sh /docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/generate-releases-manifest.sh`
    - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_desktop_startup_smoke_bash_compat.py /docker/chummercomplete/chummer.run-services/tests/test_publish_download_bundle_http_bash_portability.py /docker/chummercomplete/chummer.run-services/tests/test_release_shell_array_portability.py`
    - result: `4 passed in 0.19s`

- Handoff hygiene follow-through:
  - `/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/docs/WORKBENCH_SESSION_HANDOFF.md` also needed the same archival correction as the origin-dialog workbench handoff
  - old April recommit / repush commands in that repo should be treated as historical context only, not as live operator instructions

- Honest blocker state still did not change:
  - release posture is still preview-only
  - the remaining hard external blocker is still the missing promoted-digest Windows visual proof bundle for:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - preferred import path remains:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T04:44:13+02:00)

- This 04:44 section is superseded by the 04:51 qBit hardening refresh above. Keep it only as historical context for how the lane moved from pending follow-through to landed state.

- EA/qBittorrent live-ops lane was rechecked live instead of left on stale assumptions:
  - reran:
    - `python3 scripts/materialize_qbittorrent_staging_hygiene.py --timeout-seconds 10 --min-dead-stalled-age-minutes 30 --apply-requeue-dead-stalled-downloads --apply-delete-dead-stalled-downloads --apply-requeue-dead-meta-downloads --apply-delete-dead-meta-downloads --apply-requeue-dead-checking-downloads --apply-delete-dead-checking-downloads --max-recovery-cycles 2 --recovery-wait-seconds 3`
    - `python3 scripts/verify_qbittorrent_staging_hygiene.py --receipt .codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
  - current live receipt truth:
    - `.codex-studio/published/QBITTORRENT_STAGING_HYGIENE.generated.json`
    - `generated_at_utc=2026-07-06T02:43:58Z`
    - `runtime_status=ready`
    - `runtime_ready=true`
    - `queueing_enabled=true`
    - `dead_meta_candidate_count=0`
    - `dead_stalled_candidate_count=0`
    - `dead_checking_candidate_count=0`
    - `orphan_partial_file_count=0`
    - `torrent_count=1`
    - `state_counts={stoppedUP:1}`
  - verifier result:
    - `status=pass`
    - `failures=[]`

- Work already present in the current worktree for this lane:
  - `scripts/materialize_qbittorrent_staging_hygiene.py`
  - `tests/test_qbittorrent_staging_hygiene.py`
  - this path already includes the meaningful recovery/hardening work:
    - dead-stalled detection now also covers long-inactive zero-speed `downloading` / `forcedDL`
    - dead metadata and long checking recovery/delete paths exist
    - recovery does `pause -> reannounce -> resume -> recheck`
    - freshly requeued downloads no longer immediately re-flag as dead-stalled in the same run
  - focused validation for that code path already passed earlier in this session:
    - `pytest -q tests/test_qbittorrent_staging_hygiene.py -q`
    - `python3 -m py_compile scripts/materialize_qbittorrent_staging_hygiene.py`

- The next safe follow-through patch set was identified but not landed yet:
  - secret-safe receipt parity:
    - add `source=script:materialize_qbittorrent_staging_hygiene.py` to qBit `stdout_tail`
    - teach `scripts/verify_qbittorrent_staging_hygiene.py` to reject unsafe `stdout_tail` sources like the EA operator and MyMedia verifiers already do
  - reusable host guardrail surface:
    - add `ops/host-workload/qbittorrent-staging-hygiene-watchdog.default`
    - load it from `ops/host-workload/qbittorrent-staging-hygiene-watchdog.service`
    - extend:
      - `scripts/host_workload_guardrails_common.py`
      - `tests/test_host_workload_guardrails.py`
      - `tests/test_sync_host_workload_guardrails.py`
    - preferred default posture: `QBIT_ENSURE_QUEUEING=1` in the default file so the watchdog re-applies queueing guardrails automatically
  - operator surface:
    - extend the qBit line in `scripts/materialize_operator_release_dashboard.py` to expose `dead_checking` and requeue counts, not only orphan/meta/stalled counts
    - add a focused dashboard test in `tests/test_operator_release_dashboard_participate_billing.py`

- Worktree caution for the next codex:
  - `scripts/materialize_operator_release_dashboard.py` is heavily modified in the current worktree; do not replay a broad stale patch there
  - `tests/test_operator_release_dashboard_participate_billing.py` also needs a fresh reread before editing
  - a combined multi-file patch attempt failed on anchor drift in that test file, so follow-up should be split into smaller surgical patches after rereading current contents

- Detailed scoped handoff for this lane:
  - `EA_LIVE_OPS_QBIT_HANDOFF_20260706.md`

## Handoff refresh (2026-07-06T04:43:08+02:00)

- Cross-codex handoff broadcast was delivered and read back by two codex agents (`Dalton`, `Ramanujan`):
  - both independently confirmed the same top live blockers:
    - preview-only release posture
    - missing promoted-digest Windows visual proof bundle for `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - both also surfaced the same stale archival inconsistency in:
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/docs/WORKBENCH_SESSION_HANDOFF.md`
    - the old April `Next exact commands` block still looked like a live recommit checklist for `Populate classic menu roots`

- Follow-through after the readback:
  - patched the SR6 workbench handoff so the old April sections are now explicitly marked archival / superseded
  - current workbench handoff now tells the next codex not to rerun the old recommit / repush flow and to start from current repo state plus this run-services handoff instead

## Handoff refresh (2026-07-06T04:41:32+02:00)

- Closed a real shell-portability drift in the SR6 companion repo instead of leaving it as an untracked sibling-surface risk:
  - patched:
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/run-desktop-startup-smoke.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/generate-releases-manifest.sh`
  - normalized those copies to the same bash3 / `set -u` safe helper posture already used in the authoritative main copies:
    - nounset-safe `array_count`
    - no raw `${#windows_payload_gate_args[@]}`
    - no raw `${#upload_files[@]}`
    - no raw `${#promoted_file_names[@]}`
    - no raw `${#portal_artifacts[@]}`
    - no older `eval "set -- \${${array_name}[@]+...}"` startup-smoke helper form

- Tightened the run-services portability regression coverage so the active sibling repo copies are now pinned too:
  - patched:
    - `tests/test_desktop_startup_smoke_bash_compat.py`
    - `tests/test_publish_download_bundle_http_bash_portability.py`
    - `tests/test_release_shell_array_portability.py`
  - expanded coverage now includes:
    - `chummer-presentation`
    - `chummer-presentation-sr6-origin-dialog-clean`
    - existing run-services script checks

- Focused validation passed:
  - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_desktop_startup_smoke_bash_compat.py /docker/chummercomplete/chummer.run-services/tests/test_publish_download_bundle_http_bash_portability.py /docker/chummercomplete/chummer.run-services/tests/test_release_shell_array_portability.py`
  - result: `4 passed in 0.09s`
  - `bash -n` passed for:
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/run-desktop-startup-smoke.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle-http.sh`
    - `/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/generate-releases-manifest.sh`

- Honest flagship blocker state is still unchanged after this pass:
  - release posture is still preview-only
  - Windows still needs the promoted-digest visual proof bundle for:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - preferred import path remains:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T04:36:13+02:00)

- Closed the remaining `release_ready` evidence gap for the Windows proof watcher so all three blocker surfaces now preserve the same auto-import truth:
  - repo changes:
    - `scripts/materialize_release_ready_receipt.py`
    - `tests/test_materialize_release_ready_receipt.py`
  - behavior change:
    - `RELEASE_READY.generated.json` now carries the same Windows watcher fields already present in the dashboard/janitor surfaces:
      - `discover_command`
      - `auto_import_command`
      - `post_import_verify_command`
      - `post_import_verify_note`
      - `expected_artifact_patterns`
      - `drop_roots_checked`
      - `auto_import_receipt_*`
      - `auto_import_stale_directory_candidate_count`
      - `auto_import_stage_like_stale_directory_candidate_count`
      - `auto_import_stale_directory_digest_summary`
      - `auto_import_directory_candidate_note`
  - focused validation passed:
    - `python3 -m py_compile /docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py /docker/chummercomplete/chummer.run-services/tests/test_materialize_release_ready_receipt.py`
    - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_materialize_release_ready_receipt.py`
    - result: `24 passed in 0.22s`

- Refreshed the published receipt after that patch:
  - reran:
    - `python3 scripts/materialize_release_ready_receipt.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current receipt truth:
    - `.codex-studio/published/RELEASE_READY.generated.json`
      - `generated_at_utc=2026-07-06T02:35:59Z`
      - `failed_gates=[release_channel, flagship_product_readiness, windows_installer_visual_audit]`
      - nested Windows blocking artifacts now include:
        - `auto_import_receipt_generated_at_utc=2026-07-06T02:31:45Z`
        - `auto_import_stale_directory_candidate_count=11`
        - `auto_import_stage_like_stale_directory_candidate_count=1`
        - `auto_import_stale_directory_digest_summary=[c41d17..., c5691dc...]`
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
      - rerun picked up the refreshed nested `release_ready` artifact block while top-level failures stayed unchanged

- Honest blocker state still did not change:
  - release posture is still preview-only
  - Windows still needs the promoted-digest visual proof bundle for:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`

## Handoff refresh (2026-07-06T04:32:50+02:00)

- Closed the stale-digest watcher hardening loop for the Windows gold-proof intake lane:
  - repo changes:
    - `scripts/auto_import_windows_installer_gold_proof.py`
    - `scripts/materialize_operator_release_dashboard.py`
    - `scripts/final_gold_janitor.py`
    - `tests/test_windows_installer_visual_audit.py`
    - `tests/test_operator_release_dashboard_participate_billing.py`
    - `tests/test_final_gold_janitor.py`
  - focused validation passed:
    - `python3 -m pytest -q /docker/chummercomplete/chummer.run-services/tests/test_windows_installer_visual_audit.py /docker/chummercomplete/chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py /docker/chummercomplete/chummer.run-services/tests/test_final_gold_janitor.py`
    - result: `164 passed in 2.05s`

- Refreshed the live watcher and downstream blocker surfaces after that patch:
  - reran:
    - `python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --output /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json --wait-seconds 0 --refresh-intake-request`
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current receipt truth:
    - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
      - `generated_at_utc=2026-07-06T02:31:45Z`
      - `status=waiting_for_artifact`
      - `stale_directory_candidate_count=11`
      - `stage_like_stale_directory_candidate_count=1`
      - `stale_directory_digest_summary` now reports:
        - `c41d17cea200... count=9 stage_like=0 sample=/tmp/windows-installer-gold-proof-27864339393`
        - `c5691dcdb517... count=2 stage_like=1 sample=/tmp/chummer-run-services-browserfix3`
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
      - `generated_at_utc=2026-07-06T02:32:22Z`
      - `root_blockers = [release_lane_posture, windows_native_visual_proof]`
      - nested Windows operator artifacts now include the refreshed watcher details:
        - `auto_import_stale_directory_candidate_count=11`
        - `auto_import_stage_like_stale_directory_candidate_count=1`
        - `auto_import_stale_directory_digest_summary=[c41d17..., c5691dc...]`
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
      - `generated_at_utc=2026-07-06T02:32:22Z`
      - top-level failures remain only:
        - `windows_installer_visual_audit failed`
        - stale visual source still targets old digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
        - missing promoted bundle `windows-installer-gold-proof-80655fd79a09.zip`

- The human-facing markdown surfaces now expose the stale-digest grouping directly instead of hiding it in the side receipt:
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.md`
  - `.codex-studio/published/FINAL_GOLD_VERDICT.md`
  - both now render:
    - `windows auto-import stale digests: c41d17cea200 count=9 stage_like=0; c5691dcdb517 count=2 stage_like=1 (stage_like_total=1)`

- Honest blocker state is unchanged by the hardening pass:
  - the user-confirmed Windows installer run still supports the already-green startup receipt
  - the missing proof is still the digest-bound visual bundle for promoted digest:
    - `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - preferred import path remains:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T04:22:51+02:00)

- Hardened the Google OAuth proof lane so a stale delivered ask no longer demands resend once the current request is already satisfied:
  - repo changes:
    - `scripts/materialize_google_oauth_linking_proof.py`
    - `scripts/materialize_release_ready_receipt.py`
    - `scripts/materialize_operator_release_dashboard.py`
    - `scripts/final_gold_janitor.py`
    - `tests/test_google_oauth_linking_proof.py`
    - `tests/test_materialize_release_ready_receipt.py`
  - behavior change:
    - if `request_status=not_required`, the receipts still preserve delivery drift as fact:
      - `operator_ask_delivery_current_text_comparable=true`
      - `operator_ask_delivery_matches_current_text=false`
    - but they no longer claim resend is required:
      - `operator_ask_delivery_needs_resend=false`
      - `operator_ask_resend_command=""`
  - targeted verification passed:
    - `python3 -m py_compile scripts/materialize_google_oauth_linking_proof.py scripts/materialize_release_ready_receipt.py scripts/materialize_operator_release_dashboard.py scripts/final_gold_janitor.py tests/test_google_oauth_linking_proof.py tests/test_materialize_release_ready_receipt.py`
    - `python3 -m pytest -q tests/test_google_oauth_linking_proof.py tests/test_materialize_release_ready_receipt.py`
    - result: `33 passed in 0.23s`

- Re-ran the live Google proof and downstream release receipts after that patch:
  - reran:
    - `python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run`
    - `python3 scripts/materialize_release_ready_receipt.py`
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current receipt truth:
    - `.codex-studio/published/GOOGLE_OAUTH_LINKING_PROOF.generated.json`
      - `generated_at_utc=2026-07-06T02:22:37.471494Z`
      - `status=pass`
      - `request_status=not_required`
      - `operator_ask_delivery_matches_current_text=false`
      - `operator_ask_delivery_needs_resend=false`
      - `operator_ask_resend_command=""`
    - `.codex-studio/published/RELEASE_READY.generated.json`
      - `generated_at_utc=2026-07-06T02:22:36Z`
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
      - `generated_at_utc=2026-07-06T02:22:36Z`
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
      - `generated_at_utc=2026-07-06T02:22:36Z`
      - nested Google blocking artifacts now also show:
        - `operator_ask_delivery_needs_resend=false`
        - `operator_ask_resend_command=""`
      - top-level failures remain only:
        - `windows_installer_visual_audit failed`
        - stale source digest still targets old installer digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
        - missing promoted bundle `windows-installer-gold-proof-80655fd79a09.zip`

## Handoff refresh (2026-07-06T04:15:43+02:00)

- Performed the live Windows-proof artifact-intake follow-up instead of leaving the lane on a stale Telegram handoff:
  - current ask text and the older Telegram receipt were mismatched before this pass:
    - current ask sha256: `92c157df51589f29221cb008dd4bf7abd34eef86e6afc08e1e415669d8fe97bf`
    - old delivery sha256: `be9e0ac57188473f29ef17eb4b48a9c6f0e0341db0df0e5caea18db4f6983498`
  - resent the current ask:
    - `python3 scripts/send_telegram_message_via_ea.py --text-file /docker/chummercomplete/chummer.run-services/_completion/windows_installer_visual_audit/windows-installer-gold-proof-80655fd79a09-operator-ask.txt --receipt-name windows-installer-gold-proof-80655fd79a09-operator-ask.receipt.json`
  - fresh delivery receipt now shows:
    - `generated_at_utc=2026-07-06T02:14:48Z`
    - `message_ids=[3504]`
    - `text_sha256=92c157df51589f29221cb008dd4bf7abd34eef86e6afc08e1e415669d8fe97bf`

- Refreshed the Windows proof lane receipts after that resend:
  - reran:
    - `python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
    - `python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json --wait-seconds 0 --refresh-intake-request`
    - `python3 scripts/materialize_release_ready_receipt.py`
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current receipt truth:
    - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
      - `generated_at_utc=2026-07-06T02:14:58Z`
      - `operator_ask_delivery_matches_current_text=true`
      - `operator_ask_delivery_needs_resend=false`
    - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
      - `generated_at_utc=2026-07-06T02:15:15Z`
      - `status=waiting_for_artifact`
      - `actionable_candidate_count=0`
      - `matching_promoted_directory_candidate_count=0`
      - `matching_promoted_zip_candidate_count=0`
      - `stale_directory_candidate_count=11`
    - `.codex-studio/published/RELEASE_READY.generated.json`
      - `generated_at_utc=2026-07-06T02:15:23Z`
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
      - `generated_at_utc=2026-07-06T02:15:24Z`
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
      - `generated_at_utc=2026-07-06T02:15:23Z`
      - top-level failures still only:
        - `windows_installer_visual_audit failed`
        - stale source digest still targets old installer digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
        - missing promoted bundle `windows-installer-gold-proof-80655fd79a09.zip`

- Discovery scan still found no usable promoted bundle after the resend:
  - used the skill discovery path across:
    - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof`
    - `/tmp`
    - `~/Downloads`
    - `~/pCloud Drive/EA`
  - result:
    - no matching promoted zip
    - no matching promoted extracted directory
    - only 11 stale `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json` candidates under `/tmp`

## Handoff refresh (2026-07-06T04:12:30+02:00)

- Extended the final-gold dependent-summary suppression so `flagship_product_readiness` is treated the same way as `release_ready` and `operator_release_dashboard` when it adds no blocker beyond the same release-lane and Windows-proof root causes:
  - repo changes:
    - `scripts/final_gold_janitor.py`
    - `tests/test_final_gold_janitor.py`
  - verifier coverage:
    - `python3 -m py_compile chummer.run-services/scripts/final_gold_janitor.py chummer.run-services/tests/test_final_gold_janitor.py`
    - `python3 -m pytest -q chummer.run-services/tests/test_final_gold_janitor.py`
    - result: `72 passed in 1.31s`

- Re-ran the real janitor after that patch and confirmed the refreshed published receipt now removes the last redundant flagship summary line too:
  - reran:
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current receipt:
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `generated_at_utc=2026-07-06T02:12:19Z`
    - top-level failures are now only:
      - `windows_installer_visual_audit failed`
      - stale source digest still targets old installer digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
      - missing promoted bundle `windows-installer-gold-proof-80655fd79a09.zip`
    - top-level failures no longer include:
      - `flagship_product_readiness failed`
      - `release_ready failed`
      - `operator_release_dashboard failed`
      - `operator_release_dashboard has failing required checks`
  - the dependent gates remain `fail`, but are now explicitly annotated as covered by the same root blockers:
    - `required_gates.flagship_product_readiness.covered_by_root_blockers_for_final_gold = [release_lane_posture, windows_native_visual_proof]`
    - `required_gates.release_ready.covered_by_root_blockers_for_final_gold = [release_lane_posture, windows_native_visual_proof]`
    - `required_gates.operator_release_dashboard.covered_by_root_blockers_for_final_gold = [release_lane_posture, windows_native_visual_proof]`

## Handoff refresh (2026-07-06T04:08:31+02:00)

- Re-ran the final-gold janitor after the dependent-summary suppression patch and confirmed the cleanup is now live in the generated receipt:
  - reran:
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current receipt:
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - top-level failures are now reduced to:
      - `flagship_product_readiness failed`
      - `windows_installer_visual_audit failed`
      - the stale visual-source digest line for old digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
      - the missing promoted bundle line for `windows-installer-gold-proof-80655fd79a09.zip`
    - top-level failures no longer include:
      - `release_ready failed`
      - `operator_release_dashboard failed`
      - `operator_release_dashboard has failing required checks`
  - downstream gate truth is still preserved, but now explicitly marked as covered by the same two root blockers:
    - `required_gates.release_ready.covered_by_root_blockers_for_final_gold = [release_lane_posture, windows_native_visual_proof]`
    - `required_gates.operator_release_dashboard.covered_by_root_blockers_for_final_gold = [release_lane_posture, windows_native_visual_proof]`

- Native Windows install success remains user-confirmed and consistent with the repo receipts, but that confirmation does not clear the digest-bound proof requirement:
  - current final-gold / dashboard root blocker text is now the honest version:
    - `Native Windows installer execution is confirmed, but the matching visual proof is still missing or mismatched for the promoted bytes.`
  - current blocker still resolves only when a real promoted-digest proof bundle is imported:
    - preferred drop path:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - import command:
      - `python3 scripts/import_windows_installer_gold_proof_artifact.py /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify`

- One live-ops detail still worth honoring on the next pass:
  - the Windows operator ask delivery receipt is now stale against the current ask text:
    - `operator_ask_delivery_matches_current_text = false`
    - resend command:
      - `python3 scripts/send_telegram_message_via_ea.py --text-file /docker/chummercomplete/chummer.run-services/_completion/windows_installer_visual_audit/windows-installer-gold-proof-80655fd79a09-operator-ask.txt --receipt-name windows-installer-gold-proof-80655fd79a09-operator-ask.receipt.json`
  - this is not a new blocker family; it is just the current handoff text being newer than the last Telegram send.

## Handoff refresh (2026-07-06T03:58:16+02:00)

- Refreshed the stale local `RELEASE_READY` receipt through the fast precheck path so it no longer drags forward the old hour-scale verifier timeout and stale Google/operator follow-up noise:
  - reran:
    - `python3 scripts/materialize_release_ready_receipt.py`
  - current receipt:
    - `.codex-studio/published/RELEASE_READY.generated.json`
    - `generated_at_utc=2026-07-06T01:57:26Z`
    - `global_verifier_skipped_due_current_blockers=true`
    - `failed_gates = [release_channel, flagship_product_readiness, windows_installer_visual_audit]`
  - current `nextActions` are now narrowed back to the real remaining path:
    - Windows proof resend / import / capture guidance
    - later stable-lane promotion after proofs are green
    - no Google operator-evidence follow-up is left in `RELEASE_READY`

- Re-ran downstream receipts after that `RELEASE_READY` refresh:
  - `python3 scripts/materialize_operator_release_dashboard.py`
  - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current effect:
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
      - top-level failures no longer include `live_surface_parity semantic proof failed`
      - `root_blockers = [release_lane_posture, windows_native_visual_proof]`
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
      - still `root_blockers = [release_lane_posture, windows_native_visual_proof]`
      - still `summary.local_surface_all_passing = true`

- Important truth after this refresh:
  - no new product blocker was introduced
  - this was a receipt-honesty cleanup pass:
    - local public-edge remains green
    - Windows watcher state remains visible and unchanged
    - final-gold no longer duplicates the preview-lane posture through the extra `live_surface_parity` failure line
  - the remaining real blockers are still exactly:
    - release-lane posture (`preview` / `preview_supported` / `promoted_preview`)
    - missing digest-bound Windows visual proof bundle for promoted installer `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`

## Handoff refresh (2026-07-06T03:55:06+02:00)

- Hardened the Windows proof blocker surfaces so the current auto-import watcher state is visible in both the operator dashboard and the final-gold handoff instead of being trapped in a side receipt:
  - patched:
    - `scripts/materialize_operator_release_dashboard.py`
    - `scripts/final_gold_janitor.py`
  - added focused assertions in:
    - `tests/test_operator_release_dashboard_participate_billing.py`
    - `tests/test_final_gold_janitor.py`
  - validation passed:
    - `python3 -m py_compile scripts/materialize_operator_release_dashboard.py scripts/final_gold_janitor.py`
    - `python3 -m pytest -q chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py chummer.run-services/tests/test_final_gold_janitor.py`
    - result: `110 passed in 10.54s`

- Refreshed the generated operator surfaces after that patch:
  - reran:
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current published markdown now explicitly shows:
    - `windows auto-import state: status=waiting_for_artifact actionable=0 matching_dirs=0 matching_zips=0 stale_dirs=11 artifact=missing receipt=/docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `windows auto-import note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.`

- Important current watcher truth:
  - `.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json`
    - `status=waiting_for_artifact`
    - `actionable_candidate_count=0`
    - `matching_promoted_directory_candidate_count=0`
    - `matching_promoted_zip_candidate_count=0`
    - `stale_directory_candidate_count=11`
  - this means the repo-side intake lane is working and honest:
    - no matching proof bundle is present anywhere in the configured roots
    - several stale temp proof directories from older digests are being detected and summarized
    - the missing blocker is still the real digest-bound Windows proof bundle, not a broken watcher path

- Remaining release truth did not change:
  - current local public-edge is still green
  - current Windows startup proof is still green for promoted digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - remaining real blockers are still:
    - release-lane posture (`preview` / `preview_supported` / `promoted_preview`)
    - missing native Windows visual proof bundle for the promoted digest

## Handoff refresh (2026-07-06T03:45:55+02:00)

- Reconfirmed the current Windows truth after the latest in-session user report (`windows installer worked. i tested it`):
  - this does not widen the blocker set; it reinforces the already-green native startup lane for the promoted installer
  - the honest remaining Windows gap is still only the digest-bound visual proof bundle for the same promoted bytes:
    - promoted digest: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - startup receipt still matches that digest:
      - `Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json`
    - stale visual source still targets:
      - `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - missing import bundle is still:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`

- Closed the stale local public-edge/mobile blocker by reusing fresh canonical browser proofs instead of the old failed temp artifact:
  - current authoritative receipt:
    - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
  - current state:
    - `status=pass`
    - `mobilePwaViewportStatus=pass`
    - `downloadsStatusBrowserStatus=pass`
    - `pwaOfflineCacheStatus=pass`
    - `frontdoorNavigationStatus=pass`
    - `generatedAtUtc=2026-07-06T01:43:39.373037+00:00`
  - repeated direct live `/play` phone-width probes were already clean; the prior failure was tied to the older temp Playwright artifact, not a current live overflow on `https://chummer.run/play`

- Refreshed downstream blocker truth after that public-edge correction:
  - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - `root_blockers = [release_lane_posture, windows_native_visual_proof]`
    - `summary.local_surface_all_passing = true`
  - `.codex-studio/published/RELEASE_READY.generated.json`
    - now fails only on:
      - release-lane posture (`preview` / `preview_supported` / `promoted_preview`)
      - Windows visual-proof mismatch / missing bundle
  - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
    - `root_blockers = [release_lane_posture, windows_native_visual_proof]`
    - no current `local_surface_regressions` blocker remains

- Honest next step remains unchanged:
  - import a real native Windows gold-proof bundle for the promoted digest with:
    - `python3 scripts/import_windows_installer_gold_proof_artifact.py /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify`
  - after that, rerun the dependent receipts if the import path does not already do it:
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/materialize_release_ready_receipt.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`

## Handoff refresh (2026-07-06T03:32:46+02:00)

- Tightened the Windows proof language so the repo now distinguishes between "installer execution is already confirmed" and "the digest-bound gold proof bundle is still missing":
  - patched:
    - `scripts/materialize_windows_installer_visual_audit_intake_request.py`
    - `scripts/materialize_operator_release_dashboard.py`
    - `scripts/final_gold_janitor.py`
  - added focused coverage in:
    - `tests/test_windows_installer_visual_audit.py`
    - `tests/test_operator_release_dashboard_participate_billing.py`
    - `tests/test_final_gold_janitor.py`
  - validation passed:
    - `python3 -m py_compile scripts/materialize_windows_installer_visual_audit_intake_request.py scripts/materialize_operator_release_dashboard.py scripts/final_gold_janitor.py`
    - `python3 -m pytest -q chummer.run-services/tests/test_windows_installer_visual_audit.py chummer.run-services/tests/test_operator_release_dashboard_participate_billing.py chummer.run-services/tests/test_final_gold_janitor.py`
    - result: `162 passed in 2.87s`

- Refreshed the dependent generated artifacts so the current operator surfaces now honor the confirmed Windows install without weakening the gold gate:
  - reran:
    - `python3 scripts/materialize_windows_installer_visual_audit_intake_request.py`
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/materialize_release_ready_receipt.py`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current Windows-facing wording now reads:
    - intake summary: `Provide the native Windows gold proof bundle for the promoted installer. Native Windows startup already matches the promoted digest; the remaining gap is digest-bound visual proof for install-progress and completion.`
    - dashboard/janitor root-blocker summary: `Native Windows installer execution is confirmed, but the matching visual proof is still missing or mismatched for the promoted bytes.`
    - current operator ask file:
      - `/_completion/windows_installer_visual_audit/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt`
      - now tells the operator to package existing screenshots if they already captured the promoted install, otherwise rerun only for the missing visual proof.

- Important current truth after the refresh:
  - Windows remains blocked only by the missing/mismatched digest-bound visual proof, not by launch uncertainty:
    - promoted digest: `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - startup receipt for that digest is still `pass`
    - stale visual source still targets:
      - `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - missing bundle path is still:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
  - operator delivery drift is advisory only:
    - the current ask text changed, but the last Telegram delivery receipt still reflects the older wording
    - `operator_ask_delivery_needs_resend=true` is expected and honest
  - there is also now a current local public-edge blocker again:
    - `.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
    - `status=fail`
    - failure: `mobile PWA viewport Playwright proof is not pass`
  - because of that refreshed public-edge truth:
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
      - `root_blockers = [release_lane_posture, windows_native_visual_proof, local_surface_regressions]`
      - `summary.local_surface_all_passing = false`
    - `.codex-studio/published/RELEASE_READY.generated.json`
      - now includes `FAIL public_edge_postdeploy_gate: mobile PWA viewport Playwright proof is not pass`
    - `.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
      - root blockers now also include `local_surface_regressions`

## Handoff refresh (2026-07-06T03:21:42+02:00)

- Hardened the hosted mac release bootstrap against the remaining `set -u` / empty-array shell hazards that were still capable of surfacing non-fatal publish warnings:
  - patched `Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh`
  - converted the remaining raw array loops to the existing bash3-safe `array_values_nul` path for:
    - `validation_errors`
    - `chunks`
    - `upload_files`
    - `bootstrap_tmp_paths`
  - this removes the last obvious class of nounset-sensitive array expansion from the hosted bootstrap upload lane, including the upload preview slice that previously depended on `"${upload_files[@]:0:8}"`.

- Strengthened the focused bootstrap guard:
  - patched `tests/test_mac_release_bootstrap_array_safety.py`
  - the test now explicitly rejects raw array loops for:
    - `validation_errors`
    - `chunks`
    - `upload_files`
    - `bootstrap_tmp_paths`
  - it also now rejects the old upload preview slice expansion `${upload_files[@]:0:8}`.

- Validation for this hardening pass:
  - `python3 -m pytest -q chummer.run-services/tests/test_mac_release_bootstrap_array_safety.py chummer.run-services/tests/test_desktop_startup_smoke_bash_compat.py chummer-presentation/tests/test_startup_smoke_bash_portability.py chummer6-ui/tests/test_startup_smoke_bash_portability.py`
  - result: `5 passed in 0.62s`
  - `bash -n` passed for:
    - `chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh`
    - `chummer-presentation/scripts/run-desktop-startup-smoke.sh`
    - `chummer6-ui/scripts/run-desktop-startup-smoke.sh`
    - `chummer-presentation-sr6-origin-dialog-clean/scripts/run-desktop-startup-smoke.sh`

- Important scope note:
  - I did not find any current bash4-only case-modifier usage (`${var,,}` / `${var^^}`) in the active startup-smoke script copies under:
    - `chummer-presentation`
    - `chummer6-ui`
    - `chummer-presentation-sr6-origin-dialog-clean`
  - so the previously observed `bad substitution` warning appears to have come from an older or alternate script copy outside the current authoritative publish paths. The active copies now parse cleanly with `bash -n`.

## Handoff refresh (2026-07-06T03:15:59+02:00)

- Tightened the release-truth semantics so stale operator-ask delivery no longer pretends to be a product blocker when the real blocker is already explicit:
  - patched:
    - `scripts/materialize_release_ready_receipt.py`
    - `scripts/materialize_operator_release_dashboard.py`
    - `scripts/final_gold_janitor.py`
  - resend drift is now preserved as operational guidance / advisory, but it is no longer promoted into:
    - `OPERATOR_RELEASE_DASHBOARD.generated.json` top-level `failures`
    - `OPERATOR_RELEASE_DASHBOARD.generated.json` root-blocker details
    - `FINAL_GOLD_JANITOR.generated.json` top-level `failures`
    - `FINAL_GOLD_JANITOR.generated.json` root-blocker details
  - the actual Windows blocker is still unchanged and still honest:
    - native Windows visual proof for promoted digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - missing bundle path remains `/docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - checked-in visual source still targets old digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`

- Tightened `RELEASE_READY` follow-through so Google does not keep showing up once Google is actually green:
  - `scripts/materialize_release_ready_receipt.py` now only emits Google follow-up actions when Google proof still needs action.
  - current `RELEASE_READY.generated.json` no longer includes any Google import / evidence next-actions.
  - current `RELEASE_READY.generated.json` next-actions now point only at:
    - Windows proof recapture / import / resend guidance
    - the later release-lane promotion after missing proofs are green

- Revalidated the semantics with focused tests:
  - `python3 -m py_compile scripts/materialize_release_ready_receipt.py scripts/materialize_operator_release_dashboard.py scripts/final_gold_janitor.py`
  - `python3 -m pytest -q tests/test_materialize_release_ready_receipt.py tests/test_operator_release_dashboard_participate_billing.py tests/test_final_gold_janitor.py`
  - result: `131 passed in 1.10s`

- Refreshed the dependent local receipts after the patch:
  - `python3 scripts/materialize_release_ready_receipt.py`
  - `python3 scripts/materialize_operator_release_dashboard.py`
  - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - current authoritative summaries are now:
    - `RELEASE_READY.generated.json`
      - still `status=fail`
      - failures are only release-lane posture plus Windows visual-proof mismatch / missing bundle
      - no Google failure lines
      - no Google next-actions
    - `OPERATOR_RELEASE_DASHBOARD.generated.json`
      - `root_blockers = [release_lane_posture, windows_native_visual_proof]`
      - `failures` no longer include `windows installer operator ask delivery is stale`
      - `summary.local_surface_all_passing = true`
    - `FINAL_GOLD_JANITOR.generated.json`
      - top-level failures no longer include `windows installer operator ask delivery is stale`
      - root blockers are still only:
        - `release_lane_posture`
        - `windows_native_visual_proof`
  - operator-ask resend is still visible in nested `operator_request_artifacts` / advisory surfaces for Windows, so the operator follow-through is not hidden.

## Handoff refresh (2026-07-06T03:01:00+02:00)

- Cleared the stale Google blocker from the current local release truth by refreshing the receipts that were lagging the already-present evidence:
  - current authoritative Google state in the worktree is now:
    - `.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json` exists and is `status=pass`
    - `.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json` is `status=not_required`
    - `.codex-studio/published/GOOGLE_OAUTH_LINKING_PROOF.generated.json` is `status=pass`
  - verified directly with:
    - `python3 scripts/verify_google_oauth_linking_operator_evidence_request.py`
    - `python3 scripts/verify_google_oauth_linking_proof.py`
    - both now pass
  - after rerunning the dependent receipts:
    - `python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run`
    - `python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json`
    - `python3 scripts/materialize_operator_release_dashboard.py`
    - `python3 scripts/materialize_release_ready_receipt.py`
  - the current dashboard root blockers no longer include Google:
    - `.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
    - root blockers are now exactly:
      - `release_lane_posture`
      - `windows_native_visual_proof`

- Refreshed the stale public-route proof and removed the last local-surface regression from the operator dashboard:
  - reran:
    - `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - current route-proof result:
    - `status=pass`
    - `generated_at_utc=2026-07-06T00:58:21.006422Z`
    - `summary.route_count=188`
    - `summary.failed_count=0`
  - after rerunning `materialize_operator_release_dashboard.py`, current local surface posture is:
    - `local_surface_all_passing=true`
    - `public_route_proof=pass`
    - `public_edge_postdeploy_gate=pass`
    - `blazor_execution_horizon_bridge=pass`
    - `participate_billing_honesty=pass`

- Refreshed two stale gold-janitor inputs so the remaining `final_gold_janitor` failure set is tighter and more honest:
  - reran:
    - `python3 scripts/verify_table_pulse_scenario_replay.py --base-url https://chummer.run`
    - `python3 scripts/ui_layout_exit_gate.py --completion-dir /docker/chummercomplete/_completion/chummer_run_redesign_closure`
    - `python3 scripts/final_gold_janitor.py --skip-materializers`
  - `table_pulse_scenario_replay stale` is gone
  - `ui_layout_exit_gate stale` is gone
  - current `FINAL_GOLD_JANITOR.generated.json` top-level failures are now narrowed to:
    - `flagship_product_readiness failed`
    - `windows_installer_visual_audit failed`
    - `windows installer visual audit source still targets c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b instead of promoted digest 80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - `windows installer gold proof artifact is still missing: /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip`
    - `windows installer operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file /docker/chummercomplete/chummer.run-services/_completion/windows_installer_visual_audit/windows-installer-gold-proof-80655fd79a09-operator-ask.txt --receipt-name windows-installer-gold-proof-80655fd79a09-operator-ask.receipt.json`
    - `operator_release_dashboard failed`
    - `operator_release_dashboard has failing required checks`
    - `release_ready failed`

- Important runtime note for future refreshes:
  - `python3 scripts/materialize_release_ready_receipt.py --force-global-verifier` is the wrong tool for ordinary truth refresh when current receipts already prove the blockers.
  - it can sit in the hour-scale global verifier unnecessarily.
  - for ordinary blocker refresh use:
    - `python3 scripts/materialize_release_ready_receipt.py`
  - that fast precheck now writes a current receipt with:
    - `generated_at_utc=2026-07-06T00:58:31Z`
    - failures narrowed to release-lane posture plus Windows visual-proof gaps only

- Current authoritative remaining blockers from the refreshed local truth are:
  - release posture:
    - release channel is still `preview`
    - supportability is still `preview_supported`
    - rollout is still `promoted_preview`
  - Windows native visual proof:
    - promoted installer digest remains `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - startup-smoke for that digest is already green
    - the missing evidence is still the matching native Windows visual-audit bundle / source receipt
  - there is no current local Google blocker anymore
  - there is no current local public-route blocker anymore

## Handoff refresh (2026-07-06T02:52:10+02:00)

- The Google operator-evidence auto-import correction is now verified and should not be revisited unless the contract changes again:
  - `scripts/auto_import_google_oauth_linking_operator_evidence.py` is back to the intended posture:
    - only the dedicated Google intake root recurses deeply
    - `/tmp` remains in the discovery roots via the request artifact, but is scanned top-level only
  - targeted verification passed on this host:
    - `python3 -m py_compile chummer.run-services/scripts/auto_import_google_oauth_linking_operator_evidence.py chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py chummer.run-services/scripts/materialize_google_oauth_linking_operator_evidence_request.py`
    - `python3 -m pytest -q chummer.run-services/tests/test_auto_import_google_oauth_linking_operator_evidence.py chummer.run-services/tests/test_google_oauth_linking_operator_evidence_request.py chummer.run-services/tests/test_windows_installer_visual_audit.py`
    - result: `64 passed in 5.40s`
  - live promptness check also passed again:
    - `python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json --wait-seconds 0 --output .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json`
    - it exited promptly with `google_oauth_linking_operator_evidence_auto_import:waiting`
    - current waiting packet timestamp: `2026-07-06T00:51:57Z`
    - current waiting packet roots remain:
      - `/docker/chummercomplete/chummer.run-services/.state/incoming_google_oauth_linking_operator_evidence`
      - `/tmp`
      - `~/Downloads`
      - `~/pCloud Drive/EA`
    - no current Google candidates were found

- Native Windows install success is now user-confirmed for the promoted installer, but the repo still lacks the digest-bound visual proof bundle that the release lane requires:
  - user report in-session: the Windows installer worked on real Windows
  - this is consistent with the already-green startup lane:
    - `Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json` already matches promoted digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - the remaining Windows blocker is therefore narrower than "does it launch?":
    - the checked-in visual source still targets old digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - source path: `Chummer.Portal/downloads/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`
    - no fresh `windows-installer-gold-proof-80655fd79a09.zip` bundle was found under:
      - `chummer.run-services/.state/incoming_windows_installer_gold_proof`
      - the accessible workspace search paths that were checked this session
  - do not "clear" the Windows blocker by editing the digest or downgrading the proof requirement
  - the honest next step is still:
    - import a real bundle for the promoted digest with `python3 scripts/import_windows_installer_gold_proof_artifact.py /docker/chummercomplete/chummer.run-services/.state/incoming_windows_installer_gold_proof/windows-installer-gold-proof-80655fd79a09.zip --intake-request /docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify`

## Handoff refresh (2026-07-06T02:44:35+02:00)

- Corrected the current signed-in account route story so future release work does not inherit stale `/account/advanced` assumptions:
  - current deployed truth is:
    - anonymous `GET /account` returns `302` to `/account/access`
    - anonymous `GET /account/advanced` returns `302` to `/account/settings`
  - `/account/advanced` is no longer a deeper standalone account metadata page for verification purposes; it is a redirect alias into the current settings surface
  - the stronger signed-in checks still live in `scripts/hub-live-audit.py` and `scripts/e2e-hub-playwright.cjs`, but they now validate the redirect alias rather than an independent advanced page

- Added a focused manifest verifier lane so changed account aliases can be re-proved without rerunning the full public-route crawl:
  - `scripts/verify_public_routes_from_manifest.py` now accepts repeated `--path` filters
  - targeted live proof receipt:
    - `chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.account-alias.generated.json`
  - exact command:
    - `python3 scripts/verify_public_routes_from_manifest.py --base-url https://chummer.run --manifest .codex-design/product/PUBLIC_LANDING_MANIFEST.yaml --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.account-alias.generated.json --path /account --path /account/advanced`

- Google OAuth proof contract is also current now:
  - required operator step is `linked_provider_visible_on_signed_in_surface`
  - the first-party signed-in preflight now auto-discovers the standard deployed owner-session env files when `scripts/materialize_google_oauth_linking_proof.py` is run without `--env-file`

## Handoff refresh (2026-07-05T18:15:00+02:00)

- Re-synced the release-truth receipts after the staged nightly shelf was corrected:
  - canonical preview release channel now reflects the real `chummer.run-services/Chummer.Portal/downloads` shelf, with both promoted desktop tuples present
  - the old Linux blocker is genuinely cleared again: `blocked_route:avalonia:linux:linux-x64` is gone from `/docker/chummercomplete/RELEASE_BLOCKERS.generated.md`
  - the staged Windows handoff now truthfully blocks only on fresh visual proof from a real Windows host, not on stale release-version or digest mismatch text:
    - `chummer.run-services/Chummer.Portal/downloads/RELEASE_BUILD_HANDOFF.generated.json`
    - `chummer.run-services/Chummer.Portal/downloads/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json`
    - `chummer.run-services/Chummer.Portal/downloads/UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json`

- Refreshed the published Windows visual-audit lane against the real staged shelf instead of the stale `/tmp` test bundle:
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json` no longer points at `/tmp/chummer-download-bundle-test-*`
  - it now fails honestly on the real remaining launch blocker:
    - promoted installer digest is `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
    - current native Windows visual-audit source still records old digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - source path: `chummer.run-services/Chummer.Portal/downloads/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`

- Refreshed the dependent published receipts after that Windows audit correction:
  - `chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json`
  - `chummer.run-services/.codex-studio/published/RELEASE_READY.generated.json`
  - `chummer.run-services/.codex-studio/published/FINAL_GOLD_JANITOR.generated.json`
  - `/docker/chummercomplete/RELEASE_BLOCKERS.generated.md`
  - important runtime note: `python3 chummer.run-services/scripts/final_gold_janitor.py` currently spends a long time in the unrelated `verify_black_ledger_live_media_proof.py` materializer; for this truth refresh the usable command was `python3 chummer.run-services/scripts/final_gold_janitor.py --skip-materializers`

- Current authoritative blocker set after the refresh is now:
  - `release_posture:non_flagship_channel`
  - `release_truth:final_gold_janitor`
  - `release_truth:release_ready`
  - `release_truth:google_oauth_linking_proof`
  - `release_truth:windows_installer_visual_audit`
  - importantly, `release_truth:public_edge_postdeploy_gate` is no longer present in `RELEASE_BLOCKERS.generated.md`

- Keep this caveat in place for any further public desktop truth refresh:
  - `chummer-hub-registry/scripts/release/refresh_public_desktop_truth.sh` is currently unsafe for this workspace because it can prefer stale mirrored startup-smoke receipts over the live `Chummer.Portal/downloads/startup-smoke` receipts
  - when the preview release channel needs to be refreshed again, materialize directly from the real run-services shelf and then copy the resulting manifest/compat mirrors into the canonical published locations

## Handoff refresh (2026-07-05T17:53:04+02:00)

- Tightened the remaining Avalonia-side Origin Dossier collapse bug behind the user report "selecting another combobox value anywhere still closes the advanced story controls / jump-around persists":
  - `chummer6-ui/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` and the mirrored `chummer-presentation/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` no longer commit `Collapsed` immediately on the live Origin Dossier expander during combo-driven refresh churn.
  - the expander now defers the collapse-state commit to `CommitOriginWizardAdvancedStoryControlsCollapsedStateIfCurrentExpanderStillCollapsed(...)` and only records the advanced-story section as closed if the currently bound live expander is still collapsed after the dispatcher settle pass.
  - practical effect: changing one combo and then another no longer lets transient same-dialog expander noise flip the preserved open state or create an extra re-anchor/jump on the next refresh.

- Added direct regression proof for that exact contract:
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` now include `Origin_dossier_advanced_story_controls_only_commit_collapsed_state_when_the_live_expander_is_still_collapsed`.
  - that test proves transient combo noise leaves the advanced controls logically open while a real user collapse still commits once the live expander is genuinely closed.

- Verified clean on this host with:
  - `dotnet build Chummer.Avalonia/Chummer.Avalonia.csproj -f net10.0 --no-restore --nologo -v minimal -p:UseSharedCompilation=false` from `chummer6-ui`
  - `dotnet build Chummer.Tests/Chummer.Tests.csproj -f net10.0 --no-restore --nologo -v minimal -p:UseSharedCompilation=false` from `chummer-presentation`
  - `dotnet exec /docker/chummercomplete/chummer-presentation/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~Origin_dossier_advanced_story_controls_only_commit_collapsed_state_when_the_live_expander_is_still_collapsed|FullyQualifiedName~Origin_dossier_advanced_story_controls_ignore_stale_expander_events_after_live_combo_rebind|FullyQualifiedName~Origin_dossier_advanced_story_controls_ignore_transient_pending_collapse_before_same_dialog_rebind|FullyQualifiedName~Origin_dossier_advanced_story_controls_do_not_jump_or_collapse_across_sequential_live_combo_selections|FullyQualifiedName~DialogHost_keeps_origin_advanced_story_controls_open_across_sequential_live_origin_select_changes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_after_switching_another_combo_value" --output Detailed`
  - result: `6/6` passed

## Handoff refresh (2026-07-05T18:05:00+02:00)

- Tightened the remaining Origin Dossier advanced-story combo proof lane so "change one combo, then another one anywhere" is covered across the full rendered select set instead of a narrow subset:
  - `chummer6-ui/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` now drive sequential live changes across the full Origin Dossier select matrix:
    - `newCharacterOriginMetatypePreference`
    - `newCharacterOriginArchetypeIntent`
    - `newCharacterRulesetId`
    - `newCharacterOriginBuildPreference`
    - `newCharacterOriginBackground`
    - `newCharacterOriginTurningPoint`
    - `newCharacterOriginTrainingPath`
    - `newCharacterOriginUpgradeExposure`
    - `newCharacterOriginPressureCost`
    - `newCharacterOriginMotivation`
    - `newCharacterOriginTone`
    - `newCharacterOriginGmConstraintPreset`
  - that browser-host test now also asserts previously changed selects keep their updated values after later combo refreshes instead of only checking the active combo.

- Extended the shell-level live proof the same way:
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopShellOriginDialogTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/DesktopShellOriginDialogTests.cs` now run the same full sequential combo matrix through the live `DesktopShell` transient-null refresh lane, keep the advanced controls open throughout, and require scroll capture/restore counts to cover every combo refresh in the sequence.

- Tightened the Avalonia stale-collapse lane and delayed-settle proof:
  - `chummer6-ui/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` and the mirrored `chummer-presentation/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` now ignore `Collapsed` events while `_originWizardTransientRefreshPending` is still true, closing the remaining stale-expander path where a transient combo refresh could still flip the preserved advanced-story state.
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` add `Origin_dossier_advanced_story_controls_ignore_transient_pending_collapse_before_same_dialog_rebind` to lock that transient-pending stale-collapse contract.
  - the Avalonia sequential live-combo test in those files now also walks the full Origin Dossier select matrix, verifies previously changed combo values persist after each later refresh, and keeps the delayed settle assertion open to `440ms` so the `384ms` restore pass cannot drift the viewport unnoticed.

- Verified clean from `chummer6-ui` on this host with:
  - `dotnet build Chummer.Avalonia/Chummer.Avalonia.csproj -f net10.0 --no-restore --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet build Chummer.Tests/Chummer.Tests.csproj -f net10.0 --no-restore --no-dependencies --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet exec /docker/chummercomplete/chummer-presentation/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~DialogHost_keeps_origin_advanced_story_controls_open_across_sequential_live_origin_select_changes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_after_switching_another_combo_value|FullyQualifiedName~Origin_dossier_advanced_story_controls_ignore_transient_pending_collapse_before_same_dialog_rebind|FullyQualifiedName~Origin_dossier_advanced_story_controls_do_not_jump_or_collapse_across_sequential_live_combo_selections" --output Detailed`
  - result: `4/4` passed

## Handoff refresh (2026-07-05T17:15:00+02:00)

- Cleared the `public_guide_convergence` blocker at the source-generator level instead of hand-editing the mirrored docs:
  - `chummer-design/scripts/ai/materialize_public_guide_bundle.py` now prefers `release_truth_packet.available_platforms` / `release_truth_packet.missing_platforms` when those lists are present, so `FROM_CHUMMER5A_TO_CHUMMER6.md`, `STATUS.md`, `NOW/current-status.md`, and the root guide do not recompute platform availability from a stale raw artifact subset.
  - Added focused regression coverage in `chummer-design/scripts/ai/test_materialize_public_guide_bundle_platform_truth.py` for:
    - the migration guide using release-truth platform lists (`Windows` + `Linux`)
    - the status page not appending a stale `Still missing from the public download page ...` line when release truth explicitly says none are missing
  - Verified with:
    - `python3 -m py_compile chummer-design/scripts/ai/materialize_public_guide_bundle.py chummer-design/scripts/ai/test_materialize_public_guide_bundle_platform_truth.py`
    - `python3 chummer-design/scripts/ai/test_materialize_public_guide_bundle_platform_truth.py`
    - `bash Chummer6/scripts/regenerate_public_guide_from_design.sh`
    - `bash Chummer6/scripts/verify_public_guide.sh`
  - Result: public-guide regen + verify now pass cleanly on this host, and rerunning `python3 scripts/release/_release_gate_common.py` drops `public_guide_convergence` from `RELEASE_BLOCKERS.generated.md`.

- Refreshed the local mounted public-edge overlay and cleared the stale landing copy from the host runtime:
  - `python3 chummer.run-services/scripts/check_public_edge_deploy_preflight.py --allow-stale-foreign-build-locks` now passes.
  - `python3 chummer.run-services/scripts/publish_public_edge_portal_overlay.py --activate --reuse-staging --output /tmp/chummer-public-edge-overlay-publish.json` finished with:
    - `status=pass`
    - `activationStatus=activated`
    - staged landing verification `status=pass`
    - `receiptAllowsOverlayActivation=true`
  - `docker compose --env-file .env -p chummer6-hub -f docker-compose.public-edge.yml up -d --no-deps --force-recreate chummer-portal` successfully recreated `chummer-portal`.
  - Local runtime proof:
    - `curl -s http://127.0.0.1:8091/ | nl -ba | sed -n '88,96p'` no longer shows the stale `Watch 90 sec` badge window that was still present before the overlay refresh.
  - Combined local postdeploy gate:
    - `python3 chummer.run-services/scripts/verify_public_edge_postdeploy_gate.py --base-url http://127.0.0.1:8091 --output /tmp/chummer-public-edge-postdeploy-local.json`
    - local receipt still returns `status=fail`, but the remaining failures are now narrowed to release-channel posture only:
      - `downloads receipt expected release supportability is not launch-supported`
      - `downloads receipt expected release rollout is blocking: coverage_incomplete`
    - the local runtime-specific pieces now pass:
      - `preflightStatus=pass`
      - `preflightBlockingLockCount=0`
      - `preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource=true`
      - `participateIframeShellStatus=pass`
      - `downloadsMarker=true`
      - `statusRedirectMarker=true`
  - Important current truth: the blocker summary at `RELEASE_BLOCKERS.generated.md` still reports `release_truth:public_edge_postdeploy_gate` because the published/canonical release truth is still tied to a `preview` channel (`supportabilityState=review_required`, `rolloutState=coverage_incomplete`), not because the local overlay is still stale.

## Handoff refresh (2026-07-05T17:02:26+02:00)

- Tightened the remaining browser-host Origin Dossier combo jitter path so the first pre-selection scroll capture survives focus-only rerenders until the actual combo refresh lands:
  - `chummer6-ui/Chummer.Blazor/Components/Shell/DialogHost.razor` and the mirrored `chummer-presentation/Chummer.Blazor/Components/Shell/DialogHost.razor` now separate "capture armed" from "restore requested". Focus and pointer interactions can still arm the pending scroll capture, but `OnAfterRenderAsync` will not consume it until a real field/checkbox update requests a restore.
  - The same files also now preserve that first pending Origin Dossier select capture across later select focuses/changes in the same interaction, instead of replacing it with a later combo anchor before the refresh completes.
  - `chummer6-ui/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` now lock the new contract with:
    - `DialogHost_keeps_first_origin_select_scroll_capture_before_value_change`
    - `DialogHost_keeps_first_origin_select_scroll_capture_when_another_select_gains_focus_before_refresh`
    - `DialogHost_keeps_first_origin_select_scroll_capture_when_the_same_select_changes_after_focus`
- Verified clean on this host with:
  - `dotnet build chummer6-ui/Chummer.Tests/Chummer.Tests.csproj -f net10.0 --no-restore --nologo -v minimal -p:UseSharedCompilation=false -m:1`
  - `dotnet exec chummer6-ui/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~DialogHost_keeps_first_origin_select_scroll_capture_before_value_change|FullyQualifiedName~DialogHost_keeps_first_origin_select_scroll_capture_when_another_select_gains_focus_before_refresh|FullyQualifiedName~DialogHost_keeps_first_origin_select_scroll_capture_when_the_same_select_changes_after_focus|FullyQualifiedName~DialogHost_keeps_origin_advanced_story_controls_open_across_sequential_live_origin_select_changes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_after_switching_another_combo_value|FullyQualifiedName~DialogHost_does_not_replay_origin_scroll_restore_after_same_dialog_instance_rerenders" --output Detailed`
  - result: `6/6` passed

## Handoff refresh (2026-07-05T16:30:23+02:00)

- Closed another real browser-host Origin Dossier jitter path on same-instance rerenders:
  - `chummer6-ui/Chummer.Blazor/Components/Shell/DialogHost.razor` and the mirrored `chummer-presentation/Chummer.Blazor/Components/Shell/DialogHost.razor` now clear the component-local pending dialog-scroll restore before awaiting the JS restore call, so overlapping rerenders cannot replay an older combo anchor after a successful restore.
  - `chummer6-ui/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` now lock that with `DialogHost_does_not_replay_origin_scroll_restore_after_same_dialog_instance_rerenders`, which mutates the same Origin Dossier dialog instance in place and proves a later rerender does not fire another `restoreDialogScroll`.
- Verified clean on this host with:
  - `dotnet build chummer6-ui/Chummer.Tests/Chummer.Tests.csproj -f net10.0 --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet exec chummer6-ui/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~DialogHost_does_not_replay_origin_scroll_restore_after_same_dialog_instance_rerenders|FullyQualifiedName~DialogHost_keeps_origin_advanced_story_controls_open_across_sequential_live_origin_select_changes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_after_switching_another_combo_value|FullyQualifiedName~App_restoreDialogScroll_restores_raw_offset_before_origin_anchor_fallback" --output Detailed`
  - result: `4/4` passed

## Handoff refresh (2026-07-05T14:07:39+02:00)

- Tightened the remaining browser-host Origin Dossier combo jitter path so changing any story-control select keeps the advanced collapsable open without re-anchoring the viewport to a different combo:
  - `chummer6-ui/Chummer.Blazor/Components/App.razor` and the mirrored `chummer-presentation/Chummer.Blazor/Components/App.razor` now restore the raw dialog scroll offset first on Origin Dossier select refreshes and only fall back to the field/advanced anchors when the browser refuses that raw offset.
  - `chummer6-ui/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/BlazorShellComponentTests.cs` now lock that contract with `App_restoreDialogScroll_restores_raw_offset_before_origin_anchor_fallback`.
- Verified clean on this host with:
  - `dotnet build chummer6-ui/Chummer.Tests/Chummer.Tests.csproj -f net10.0 --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet exec chummer6-ui/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~App_restoreDialogScroll_restores_raw_offset_before_origin_anchor_fallback|FullyQualifiedName~DialogHost_keeps_origin_advanced_story_controls_open_across_sequential_live_origin_select_changes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_after_switching_another_combo_value" --output Detailed`
  - result: `3/3` passed

## Handoff refresh (2026-07-05T11:10:13Z)

- Origin Dossier advanced-story combo preservation was extended again so switching one combo and then another no longer drops the advanced collapsable or lets a late settle pass re-anchor the dialog:
  - `chummer6-ui/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` and the mirrored `chummer-presentation/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` now keep a short combo-restore preservation window alive through the late delayed-settle lane, ignore stale `Collapsed` events during that window, and add a `384ms` delayed restore pass on top of the existing `48/96/192ms` passes.
  - `chummer6-ui/Chummer.Blazor/Components/App.razor` and the mirrored `chummer-presentation/Chummer.Blazor/Components/App.razor` now also run a `384ms` follow-up dialog-scroll restore pass for the browser host so the web/DesktopShell lane matches the Avalonia settle behavior.
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` now hold the delayed-settle assertions open to `440ms` for both the sequential live-combo path and the full rendered Origin Dossier combo matrix.
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopShellOriginDialogTests.cs` and the mirrored `chummer-presentation/Chummer.Tests/Presentation/DesktopShellOriginDialogTests.cs` now add a real shell-level regression for changing one Origin Dossier combo and then another across the transient-null refresh path while keeping the advanced controls open.
- Verified clean on this host with:
  - `dotnet build chummer6-ui/Chummer.Tests/Chummer.Tests.csproj -f net10.0 --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet exec chummer6-ui/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~Origin_dossier_advanced_story_controls_do_not_jump_or_collapse_across_sequential_live_combo_selections|FullyQualifiedName~Origin_dossier_advanced_story_controls_stay_stable_between_immediate_and_delayed_combo_restore_passes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_across_transient_null_select_refreshes|FullyQualifiedName~DesktopShell_keeps_origin_advanced_story_controls_open_after_switching_another_combo_value|FullyQualifiedName~Main_window_keeps_origin_dossier_dialog_window_and_advanced_controls_stable_across_transient_null_combo_refresh" --output Detailed`
  - result: `5/5` passed

## Handoff refresh (2026-07-05T10:36:00Z)

- Origin Dossier advanced-story combo stability was tightened again in the Avalonia shell for the remaining delayed-settle path:
  - `chummer6-ui/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` now keeps the delayed Origin Wizard combo restore lane alive through an additional `192ms` settle pass instead of stopping at `48ms` and `96ms`.
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` now widens `Origin_dossier_advanced_story_controls_stay_stable_between_immediate_and_delayed_combo_restore_passes` from two fields to the full rendered Origin Dossier select matrix:
    - `newCharacterOriginMetatypePreference`
    - `newCharacterOriginArchetypeIntent`
    - `newCharacterRulesetId`
    - `newCharacterOriginBuildPreference`
    - `newCharacterOriginBackground`
    - `newCharacterOriginTurningPoint`
    - `newCharacterOriginTrainingPath`
    - `newCharacterOriginUpgradeExposure`
    - `newCharacterOriginPressureCost`
    - `newCharacterOriginMotivation`
    - `newCharacterOriginTone`
    - `newCharacterOriginGmConstraintPreset`
  - the delayed settle assertion now waits `240ms`, so the proof catches late scroll drift instead of only the first two restore ticks.
- Verified clean on this host with the direct MSTest host after rebuilding the narrow prerequisite set:
  - `dotnet build chummer6-ui/Chummer.Avalonia/Chummer.Avalonia.csproj -f net10.0 --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet build chummer6-ui/Chummer.Portal/Chummer.Portal.csproj -f net10.0 --nologo -v minimal -p:UseSharedCompilation=false`
  - `dotnet build chummer6-ui/Chummer.Tests/Chummer.Tests.csproj -f net10.0 --nologo -v minimal -p:UseSharedCompilation=false --no-dependencies`
  - `dotnet exec chummer6-ui/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~Origin_dossier_advanced_story_controls_do_not_jump_or_collapse_after_any_live_combo_selection|FullyQualifiedName~Origin_dossier_advanced_story_controls_stay_stable_between_immediate_and_delayed_combo_restore_passes|FullyQualifiedName~Main_window_keeps_origin_dossier_dialog_window_and_advanced_controls_stable_across_transient_null_combo_refresh" --output Detailed`
  - result: `3/3` passed

## Handoff refresh (2026-07-05T09:05:00Z)

- Origin Dossier advanced-story combo refreshes were tightened in the Avalonia dialog shell so changing any combo value no longer re-anchors the advanced-story expander or lets delayed settle passes drift the scroll position:
  - `chummer6-ui/Chummer.Avalonia/DesktopDialogWindow.axaml.cs` now prefers the preserved raw scroll offset on Origin Dossier combo-triggered rebinds and clears expander/interaction anchors for that path instead of trying to re-anchor the collapsible group.
  - `chummer6-ui/Chummer.Tests/Presentation/DesktopWindowContrastTests.cs` now also proves the popup-like combo interaction case stays expanded and stable after delayed settle passes.
  - verification on this host must use the direct MSTest host right now because `.NET 10` `dotnet test` is still landing on the legacy VSTest path here:
    - build prereqs: `dotnet build chummer6-ui/Chummer.Avalonia/Chummer.Avalonia.csproj --nologo -v minimal`
    - build prereqs: `dotnet build chummer6-ui/Chummer.Portal/Chummer.Portal.csproj --nologo -v minimal`
    - build prereqs: `dotnet build chummer6-ui/Chummer.Tests/Chummer.Tests.csproj -f net10.0 --nologo -v minimal`
    - focused proof: `dotnet exec chummer6-ui/Chummer.Tests/bin/Debug/net10.0/Chummer.Tests.dll --filter "FullyQualifiedName~Origin_dossier_advanced_story_controls_restore_pre_combo_scroll_anchor_after_popup_like_combo_shift|FullyQualifiedName~Origin_dossier_advanced_story_controls_do_not_jump_or_collapse_after_any_live_combo_selection|FullyQualifiedName~Main_window_keeps_origin_dossier_dialog_window_and_advanced_controls_stable_across_transient_null_combo_refresh" --output Detailed`
- Restored the current run-services verification lane to green by syncing the stale mirrored weekly pulse file back to canonical:
  - refreshed `/docker/chummercomplete/chummer.run-services/.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json`
    from `/docker/chummercomplete/chummer-design/products/chummer/WEEKLY_PRODUCT_PULSE.generated.json`
  - `CHUMMER_SKIP_CLEANROOM_BUILD=1 bash ./scripts/ai/run_services_verification.sh` now passes again on this host
  - `HubExtractionReadinessVerification.VerifyCanonicalProductMirror("WEEKLY_PRODUCT_PULSE.generated.json")` was the concrete blocker; the other mirrored product files already matched canonical
- Rechecked the current flagship launch blockers after the verifier cleared:
  - `RELEASE_BLOCKERS.generated.md` and `.codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json` still fail only on launch-channel posture plus external proof lanes:
    - release channel is still `preview` / `preview_supported` / `promoted_preview`
    - Google OAuth operator evidence is still missing: `.codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json`
    - Windows native visual gold proof is still missing for promoted installer digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
- Revalidated the external-artifact intake lanes rather than trusting stale blocker text:
  - `python3 scripts/verify_google_oauth_linking_operator_evidence_request.py` passes structurally and still reports `operator_action_required`
  - `python3 scripts/verify_windows_installer_visual_audit_intake_request.py` passes structurally and still reports `external_artifact_required`
  - bounded artifact discovery found no current operator bundles in the expected local intake roots:
    - no `*google-oauth-linking-operator-evidence*.zip`
    - no `*windows-installer-gold-proof*.zip`
- Important Windows truth:
  - `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json`
    already matches the promoted installer digest `80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91a`
  - the remaining Windows blocker is therefore a real stale/missing native visual proof lane, not a stale startup-smoke receipt:
    - current visual source file is still `/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json`
    - that source still records old digest `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
    - no newer `WINDOWS_INSTALLER_VISUAL_AUDIT.source.json` for the promoted digest exists anywhere in the current workspace, so do not “fix” this by editing the digest; a fresh native Windows capture bundle is still required

## Handoff refresh (2026-04-03T00:00:00Z)

- Event-control carry-forward now fail-closes relationship-only return cues unless explicit GM ops context is present:
  - `Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs` now requires event/opposition context before relationship split-token carry-forward cues can activate `event_control_packet`.
  - relationship-only carry-forward cues remain governed on `campaign_return_packet` instead of leaking into GM event controls.
- Added focused regression coverage in `Chummer.Tests/CampaignWorkspaceServerPlaneServiceTests.cs`:
  - `EventControlPacketDoesNotActivateFromCarryForwardRelationshipSignalsWithoutEventContext`
  - asserts `event_control_packet` is absent while `campaign_return_packet` remains present under relationship-only carry-forward inputs.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~EventControlPacketDoesNotActivateFromCarryForwardRelationshipSignalsWithoutEventContext" --nologo -v minimal`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~CampaignWorkspaceServerPlaneServiceTests" --nologo -v minimal`

## Handoff refresh (2026-04-03T00:00:00Z)

- Campaign prep-library synthesis now treats roster movement and aftermath/downtime as first-class governed prep lanes:
  - `Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs` now emits a reusable `roster_movement_packet` from governed `RosterTransfers` and a reusable `aftermath_packet` from governed `AftermathPackages`, then includes both in `BuildPrepPackets(...)`.
  - packet search posture now explicitly covers roster/campaign/crew movement terms and aftermath/downtime/run/artifact continuity terms instead of relying on incidental text from scene/opposition packets.
- Added focused regression coverage in `Chummer.Tests/CampaignWorkspaceServerPlaneServiceTests.cs`:
  - `PrepLibraryIncludesRosterMovementPacketWhenRosterTransfersExist`
  - `PrepLibraryIncludesAftermathPacketWhenAftermathPackagesExist`
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~CampaignWorkspaceServerPlaneServiceTests" --nologo`

## Handoff refresh (2026-04-02T17:40:42+02:00)

- Public release-truth and desktop platform honesty were tightened around the real shelf instead of internal artifact existence:
  - `Chummer.Run.Api/Services/ReleaseSelectionService.cs` now builds an explicit platform-availability matrix, marks the requested device platform as unavailable when it is off-shelf, and blocks macOS from public visibility until canonical release proof explicitly names the promoted mac artifact route.
  - `Chummer.Run.Api/ViewModels/SiteViewModels.cs`, `Views/PublicLanding/Downloads.cshtml`, and `Views/PublicLanding/Status.cshtml` now expose that matrix to users so `/downloads` and `/status` say which desktop platforms are actually public right now instead of quietly falling through to another platform.
  - `Chummer.Run.Api/Services/HubPageChromeService.cs` now keeps the landing-page header CTA aligned with the landing canon, while `Controllers/PublicLandingController.cs` and `Services/SignedInTrustStatusService.cs` now phrase guest-readable shelves and signed-in follow-through consistently (`Guest-readable handoff` plus `Signed-in handoff` continuity).
- The customer-facing proof rails were repaired rather than weakened:
  - `tests/RunServicesSmoke/Program.cs` now supplies the current `PublicLandingController` constructor dependencies (`ReleaseUploadTicketService`, `IWebHostEnvironment`) and locks the guest-readable shelf expectations plus the off-shelf macOS behavior.
  - `Chummer.Tests/ReleaseSelectionServiceTests.cs` now proves unsupported requested platforms stay unavailable without pretending another platform is recommended, and it proves macOS stays withheld until explicit promoted-proof routes exist.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "FullyQualifiedName~ReleaseSelectionServiceTests|FullyQualifiedName~PublicReleaseManifestServiceTests" --nologo`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 ../chummer-hub-registry/scripts/verify_public_release_channel.py /docker/chummercomplete/chummer-presentation/Chummer.Portal/downloads`

## Handoff refresh (2026-03-30T11:00:07+02:00)

- Guest `/help` is now part of the browser-proof lane instead of only the raw-route audit:
  - `scripts/e2e-hub-playwright.cjs` now visits `/help` in the guest browser flow, requires the stable help hero/fallback/privacy-boundary copy, and locks the live next-step links to `/downloads`, `/faq`, `/contact#support-intake`, and `/now`.
- Re-verified clean with:
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`

## Handoff refresh (2026-03-30T10:53:25+02:00)

- Public trust/legal surfaces now have browser-proof coverage instead of only raw-route checks:
  - `scripts/hub-live-audit.py` now treats `/faq`, `/privacy`, and `/terms` as richer release surfaces. The public audit now requires the FAQ search/next-step rails plus the privacy/terms policy-delta and action-link rails instead of stopping at route headings.
  - `scripts/e2e-hub-playwright.cjs` now visits `/faq`, `/privacy`, and `/terms` in the guest browser lane, verifies their customer-facing copy, and locks the critical action links (`/downloads`, `/help`, `/contact#support-intake`, `/now`) so those trust/legal surfaces can’t drift back to shallow or broken navigation.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T10:50:58+02:00)

- Guest participation routing is now canon-correct and release-blocking:
  - `Chummer.Run.Api/Controllers/PublicLandingController.cs` now resolves the signed-in participation lane on `/participate` through the actual current auth state instead of always forcing the authenticated route set. Guests now get the intended `/login?next=/participate/codex` and `/signup?next=/account/settings` handoffs, while signed-in users still keep the direct `/participate/codex` and `/account/settings` routes.
  - `scripts/hub-live-audit.py` and `scripts/e2e-hub-playwright.cjs` now treat `/what-is-chummer` and `/participate` as richer public release surfaces. The browser/live proof now requires the public story explainer rails plus the guest participation lane copy and guest-safe action hrefs.
  - `tests/RunServicesSmoke/Program.cs` now locks both participate states: guest routes must use login/signup-first handoffs, and authenticated routes must keep the direct participation/account paths.
- Integrated concurrent recap-shelf publication-trust view changes and repaired the broken contract so the repo stays green:
  - `Chummer.Run.Api/Views/Accounts/Account.cshtml` and `Chummer.Run.Api/Views/PublicLanding/Home.cshtml` were already carrying richer publication trust/discoverability rows on recap-shelf entries.
  - `Chummer.Campaign.Contracts/CampaignContracts.cs` now extends `PublicationSafeProjection` with the optional publication-trust fields those views already consume (`Audience`, `OwnershipSummary`, `PublicationState`, `TrustBand`, `Discoverable`, `PublicationSummary`, `CreatorPublicationId`, `NextSafeAction`), which clears the compile break that was failing `scripts/ai/run_services_smoke.sh` and `bash scripts/audit-compliance.sh`.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke|PublicTrustPulseServiceTests|WeeklyProductPulseArtifactServiceTests"`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T10:43:28+02:00)

- The public front door now has release-blocking proof coverage for the full weekly trust pulse instead of only the hero/proof teaser:
  - `scripts/hub-live-audit.py` now fails `/` unless the rebuilt `chummer.run` landing route renders the full weekly pulse label set (`Who can get it now`, `Release proof`, `Launch readiness`, `Adoption health`, `Closure health`, `Progress trend`, `Journey pulse`, `Provider-route stewardship`, `Current caution`), the measured trend rail (`trust-pulse-trend__point`), and the `/now` plus `/progress` trust-pulse actions.
  - `scripts/e2e-hub-playwright.cjs` now enforces the same front-door pulse rows in the browser lane and requires at least two rendered `.trust-pulse-trend__point` elements on `/` so the landing trust pulse cannot silently collapse back to a thin summary block.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke|PublicTrustPulseServiceTests|WeeklyProductPulseArtifactServiceTests"`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T10:11:48+02:00)

- Public roadmap and artifact detail pages are now part of the stronger public release-proof lane instead of only grazing their headings:
  - `scripts/hub-live-audit.py` now treats `/artifacts/current-preview-build` and `/roadmap/nexus-pan` as richer public proof surfaces and requires their real guidance rails (`Use and verify this proof`, `What this live artifact shows, who it helps, and what to check next`, `Start from the live surface`, `Open current release`, `Open support`, `Current pain, expected unlock, and the live proof you should compare first`, `Need a decision instead?`, `Compare with current proof`).
  - `scripts/e2e-hub-playwright.cjs` now enforces those same public detail-route rails in the browser lane and proves the honest next-step links back into `/now` and `/contact#support-intake` on both the live artifact page and the roadmap detail page.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T10:09:44+02:00)

- Signed-in participation is now part of the release-proof lane instead of only checking that `/participate/codex` exists:
  - `scripts/hub-live-audit.py` now treats the signed-in participation surface as release-blocking and requires the stable hero/journey/wizard contract (`Help Chummer show its work.`, `I want to participate`, `One decision, one code, one clean handoff`, `Generate fresh code`, `Open a fresh contribution lane`, `Technical details and controls`).
  - `scripts/e2e-hub-playwright.cjs` now opens the participation wizard and proves the real runtime state the local execution lane returns. It accepts the honest unavailable/complete branches, and on the actionable authorize-or-queued path it now requires the technical details rail, the one-time-code or queued-slot copy, and a clean stop path back to the `stopped` state.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T10:06:34+02:00)

- Signed-in profile and publication follow-through are now materially deeper and the publication deep-link instability is fixed:
  - `scripts/hub-live-audit.py` now treats `/account` as a release-blocking signed-in surface (`Display name`, `Handle`, `Timezone`, `Save profile`, `Primary sign-in`, `Recovery email`, `Start verification`) and it now requires creator-publication detail routes reached from both `home/work` and `account/work` to render the richer `Trust ranking` and `Discoverable now` rows.
  - `scripts/e2e-hub-playwright.cjs` now saves the signed-in profile with new values and proves they survive reload, opens the recovery-email drawer, completes the local preview verification round trip, and then requires `/account/advanced` to reflect the additional linked identity. The browser lane also now treats the creator-publication detail routes as release-blocking on the new trust/discoverability rows.
  - `Chummer.Campaign.Contracts/CampaignContracts.cs`, `Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs`, and `tests/RunServicesSmoke/Program.cs` now carry/lock `TrustBand` and `Discoverable` on recap-shelf entries so the shared home/work creator shelf can project the same trust posture into smoke and runtime proof.
  - `Chummer.Run.Api/Services/Community/CampaignSpineService.cs` no longer truncates creator-publication projections to the first three workspaces. That fixes the real runtime bug where workspace recap-shelf deep links could point at a publication that disappeared on the next request, which was why the selected publication detail route kept falling back out of the richer detail card.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `bash scripts/run_smoke.sh`
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke"` (build/test discovery completed cleanly; the filter matched no individual test cases in `Chummer.Tests`)
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T09:54:53+02:00)

- Signed-in account settings and advanced proof are now materially deeper instead of only checking route headings:
  - `scripts/hub-live-audit.py` now treats `/account/settings` and `/account/advanced` as release-blocking signed-in surfaces. It requires the stable privacy/help-policy/account-metadata rows (`Visibility`, `Recovery posture`, `Provider-backed help`, `Open help`, `Read privacy`, `Read terms`, `Contact Chummer`, `Hub account id`, `Primary auth`, `Linked identities`, `Linked channels`, `Follow horizons`) before the broader work-journey audit is allowed to pass.
  - `scripts/e2e-hub-playwright.cjs` now makes the `/home/setup` wizard materially real by selecting a starter lane, saving the onboarding flow, and only then using `/account/settings` to prove that `Follow upcoming updates` and `Invite me when the right beta opens` can be saved and survive a reload. The browser lane also now verifies the signed-in help/privacy/terms/contact link cluster and the deeper `/account/advanced` metadata rail instead of stopping at surface headings.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T09:03:40+02:00)

- Integrated the concurrent first-playable-session proof expansion and brought the mirror/proof lane back to green:
  - `Chummer.Campaign.Contracts/CampaignContracts.cs`, `Chummer.Run.Api/Services/Community/CampaignSpineService.cs`, `Chummer.Run.Api/Views/PublicLanding/Home.cshtml`, `Chummer.Run.Api/Views/Accounts/Account.cshtml`, and `tests/RunServicesSmoke/Program.cs` now carry explicit first-session `RuleReadySummary`, `ReturnLaneSummary`, and `CampaignReadySummary` fields with customer-facing labels (`Legal runner`, `Understandable return`, `Campaign-ready lane`) on both the signed-in home and account work surfaces.
  - `scripts/hub-live-audit.py` and `scripts/e2e-hub-playwright.cjs` now require those new rows on the anchored first-playable-session route, so the shared first-session proof cannot drift out of the live/browser verification lane.
  - The mirrored [.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json](/docker/chummercomplete/chummer.run-services/.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json) was refreshed to restore `closure_health`, `adoption_health`, and `progress_trend` so the design mirror matches the live weekly pulse again.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "RunServicesSmoke|DesignMirrorExecutionPlanTests|PublicTrustPulseServiceTests|WeeklyProductPulseArtifactServiceTests"`
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:59:57+02:00)

- Signed-in home proof now treats the front-door overview and setup wizard as release-blocking instead of only grazing `/home/access` and `/home/work`:
  - `scripts/hub-live-audit.py` now requires `/home` to render the stable overview cards (`Welcome back`, `Use the current preview`, `Keep this copy connected`, `Open current release`) and `/home/setup` to carry the onboarding shell plus the three setup-step headings.
  - `scripts/e2e-hub-playwright.cjs` now opens `/home`, expands the `Build, explain, and next step` drawer, verifies the signed-in overview copy, then opens `/home/setup`, launches the onboarding dialog, walks through the three setup steps, and confirms the dialog can close cleanly without client-side errors.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:57:15+02:00)

- Signed-in support proof now covers every grounded assistant handoff the drawer is supposed to surface on the customer-visible route:
  - `scripts/hub-live-audit.py` now sends a signed-in rule-environment assistant query and fails unless the reply carries a `rules_truth` citation plus an `open_home` action, alongside the already-landed `build_truth`, `support_case`, `open_work`, and `open_account_support` checks.
  - `scripts/e2e-hub-playwright.cjs` now asks the same rule-environment question inside the `Need routing help first?` drawer, follows `Open home` into `/home`, and verifies the signed-in home overview renders `Welcome back`, `Build, explain, and next step`, and `What changed for me` before returning to the support route.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:55:46+02:00)

- Signed-in support proof now closes the assistant’s tracked-case loop instead of stopping at generic help/work routing:
  - `scripts/hub-live-audit.py` now creates a support case and immediately re-queries `/api/v1/support/cases/assistant` with that exact `caseId`, failing unless the response cites a `support_case` and offers the `open_account_support` timeline action.
  - `scripts/e2e-hub-playwright.cjs` now returns to `/account/support` after filing the uniquely titled case, reopens the assistant drawer, asks for that exact tracked case by title, requires the grounded answer and citation row, then verifies the signed-in history link still reopens the same detail route.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:54:20+02:00)

- Signed-in support proof now enforces the assistant’s grounded bridge back into the campaign/build work surface instead of only checking install/update help:
  - `scripts/hub-live-audit.py` now sends a signed-in support-assistant build-handoff query before case submission and fails unless the response carries at least one `build_truth` citation plus an `open_work` action.
  - `scripts/e2e-hub-playwright.cjs` now asks the same build-handoff question inside the `Need routing help first?` drawer, requires the grounded answer/citations, follows `Open work` into `/account/work`, verifies the work surface renders `Grounded rule answers` and `Build follow-through`, then returns to `/account/support` before filing the tracked case.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:52:33+02:00)

- Signed-in support proof now covers the calmer assistant rail and the rendered history loop instead of stopping at raw API assertions and the initial form redirect:
  - `scripts/hub-live-audit.py` now requires `/account/support` to render the assistant/form shell before case submission, then proves the tracked case title and detail link stay visible in the signed-in support history after notification and after reporter verification.
  - `scripts/e2e-hub-playwright.cjs` now opens the `Need routing help first?` drawer, submits a grounded install/update assistant query, follows the returned `Open downloads` action into the signed-in downloads surface, files a uniquely titled support case, returns to `/account/support`, and reopens the exact tracked case through the rendered history link.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:45:50+02:00)

- Signed-in access proof is now materially deeper instead of only checking route headings:
  - `scripts/hub-live-audit.py` now requires real account-access recovery/install evidence (`Recent install handoffs`, `Advanced device recovery`, `Offline-ready return`, the live linked-install host/version, and no leaked installation access token), plus a post-verification `home/access` pass that proves the support-closure card carries the actual audit case title, fixed version, affected install, and `Open downloads` next action.
  - `scripts/e2e-hub-playwright.cjs` now expands the `Release and device state` drawer on `/home/access`, verifies its release/device links, and expands the `Finish on another device`, `Advanced device recovery`, optional `Offline-ready return`, and `What stays on this device` drawers on `/account/access`.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:22:24+02:00)

- The anchored `home/work` operator rail now carries the rest of the modeled guided links as verified navigation instead of unproven CTA copy:
  - `scripts/hub-live-audit.py` now resolves and verifies the home-surface links for first playable session proof when present, plus the league rail, season board, invite rail, and sponsor rail. The new checks remain tolerant of the optional first-playable card while still enforcing the operator-anchor sections when they are rendered.
  - `scripts/e2e-hub-playwright.cjs` now navigates those same anchored routes in the browser lane, verifies the URL hash survives, and asserts the expected bounded section content on each destination surface.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:19:55+02:00)

- Signed-in `home/work` proof now follows the anchored return-lane and operator-guidance links instead of only asserting the CTA copy:
  - `scripts/hub-live-audit.py` now resolves the rendered anchor targets for next-session carry-forward, aftermath return, downtime brief, campaign memory, governed roster moves, and member guidance; it fetches the base route, verifies the target id exists, and requires the anchored section content to render. The live audit fetcher now retries transient request timeouts so the heavier signed-in route walk stays stable on the local edge.
  - `scripts/e2e-hub-playwright.cjs` now captures those same anchored `home/work` links, navigates to each one, verifies the URL hash is preserved, and asserts the expected bounded section content on the target signed-in route.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:15:57+02:00)

- Signed-in `home/work` proof now follows the advertised deep links instead of only asserting that the cards mention them:
  - `scripts/hub-live-audit.py` now extracts the rendered home-surface links for workspace detail, build follow-through, grounded rule answer, and publication status, then opens each route and requires the bounded detail cards to render.
  - `scripts/e2e-hub-playwright.cjs` now captures those same `home/work` links in the browser lane and asserts they land on the expected signed-in detail surfaces before continuing through the rest of the journey.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:13:34+02:00)

- Signed-in workspace-detail proof now exercises the governed prep-library search route instead of only checking the base workspace detail page:
  - `scripts/hub-live-audit.py` now opens `/account/work/workspaces/{workspaceId}?prepQuery=opposition`, requires non-empty search results, and confirms the prep-launch, travel-prefetch, aftermath, and carry-forward evidence remain visible after the query is applied.
  - `scripts/e2e-hub-playwright.cjs` now submits the `Search governed prep packets` form on the workspace detail page, verifies the normalized query stays in the route, and asserts the same evidence survives in the browser lane.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:12:02+02:00)

- Signed-in work proof now walks the modeled account-work detail routes for run context and grounded rule answers instead of leaving them covered only by in-process smoke:
  - `scripts/hub-live-audit.py` now extracts the first `/account/work/runs/{runId}` and `/account/work/rules/{entryId}` links from `/account/work`, opens both routes, and requires the run-context and grounded-rule detail cards to render their bounded evidence blocks.
  - `scripts/e2e-hub-playwright.cjs` now captures those same rendered links from `/account/work` and asserts both detail routes in the browser lane before continuing through the rest of the signed-in journey.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:06:16+02:00)

- Signed-in trust proof now treats the install-specific `Adoption health` row as release-blocking on `/downloads`, `/now`, and `/help`:
  - `scripts/hub-live-audit.py` now fails if those signed-in routes do not render `Adoption health` in both the install-specific trust panel and the weekly trust pulse.
  - `scripts/e2e-hub-playwright.cjs` now enforces the same minimum-count check in the browser lane.
- Creator-publication follow-through is now proven all the way into build-handoff detail instead of stopping at the publication page:
  - `scripts/hub-live-audit.py` now opens the first `/account/work/build-handoffs/{handoffId}` link from the publication-detail route and requires the rendered build follow-through posture.
  - `scripts/e2e-hub-playwright.cjs` now clicks through the same build-handoff link and asserts the destination route renders the expected follow-through card.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T08:00:33+02:00)

- The workspace artifact-shelf proof now follows the creator-publication deep link instead of only checking that the link exists:
  - `scripts/hub-live-audit.py` now extracts the first `/account/work/publications/{publicationId}` link from the signed-in workspace-detail shelf, opens it, and requires the rendered publication status, trust, discovery, and build-path follow-through.
  - `scripts/e2e-hub-playwright.cjs` now clicks the same publication-status link in the browser lane and asserts the destination route renders the publication-status card rather than leaving the deep link unproven.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T07:58:45+02:00)

- Signed-in hub proof now treats workspace artifact-shelf posture as release-blocking instead of only trusting the view source:
  - `scripts/hub-live-audit.py` now verifies the workspace-detail route reached from the signed-in journey renders artifact-shelf audience, ownership, publication posture, and publication-status deep links.
  - `scripts/e2e-hub-playwright.cjs` now expands the same workspace-detail artifact-shelf drawer in the browser lane and asserts the rendered ownership/publication posture there.
  - `tests/RunServicesSmoke/Program.cs` now locks the richer workspace-detail server-plane recap-shelf contract so in-process smoke fails if ownership/publication/next-safe-action posture disappears from the bound model.
- During this pass I explicitly confirmed that `/account/work` without a selected workspace does not hydrate `SelectedWorkspaceServerPlane`; the stable release-proof seam is `/account/work/workspaces/{workspaceId}`, and the hardened checks now target that route instead of the summary page.
- Re-verified clean with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `bash scripts/run_smoke.sh`
  - `bash scripts/ai/run_services_smoke.sh`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T07:25:00+02:00)

- The live audit now fails if `/api/public/weekly-pulse` stops reflecting Fleet-backed ready-state journey proof. It asserts:
  - `journey_gate_health.state == ready`
  - `journey_gate_health.blocked_count == 0`
  - presence of `supporting_signals.closure_health`, `adoption_health`, `progress_trend`, `provider_route_stewardship`, and `launch_readiness`
- The local public-edge compose lane now keeps a higher local write budget plus a small limiter queue (`CHUMMER_API_WRITE_RATE_LIMIT_PER_MINUTE=120`, `CHUMMER_API_RATE_LIMIT_QUEUE=16`) so signed-in audit and E2E traffic stops tripping avoidable local 429 backoff.
- `scripts/e2e-hub.sh` now uses explicit compose project names for both the edge stack and the Playwright runner, which removes the symlink-derived compose naming drift and isolates the browser lane from the edge project.
- The signed-in home aftermath card now surfaces recap-shelf ownership and publication state directly on `/home/work`, and smoke coverage now locks the new ownership/state shelf posture into both the home projection and registry preview/search checks.
- Re-verified clean with:
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T07:18:59+02:00)

- The public-edge compose lane now mounts Fleet’s published artifact canon directly into the live portal container at `/fleet-artifacts` and sets `CHUMMER_PUBLIC_FLEET_ARTIFACT_ROOT=/fleet-artifacts`, so `/api/public/weekly-pulse` on `chummer.run` reflects current Fleet readiness instead of stale baked-in mirror data.
- `tests/RunServicesSmoke/Program.cs` now accepts the governed launch-readiness variants that can legitimately appear once journey proof is ready, rather than hard-coding only the older `route-canary validation` wording.
- Re-verified clean with:
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`
- Live proof after the mount fix: `/api/public/weekly-pulse` now reports `journey proof is ready` on the rebuilt local `chummer.run` edge.

## Handoff refresh (2026-03-30T06:49:05+02:00)

- Commit `e3a34688` (`Refine provider route weekly pulse decisions`) is on `main` and matches `origin/main`.
- `WeeklyProductPulseArtifactService` now derives provider-route `review_due` from generated evidence timestamps instead of only mirroring the seed date, and it makes the provider-route `next_decision` evidence-aware when live proof and support-closure posture are available.
- The mirrored [WEEKLY_PRODUCT_PULSE.generated.json](/docker/chummercomplete/chummer6-hub/.codex-design/product/WEEKLY_PRODUCT_PULSE.generated.json) was refreshed so the design mirror again carries `closure_health`, `adoption_health`, and `progress_trend` blocks alongside provider-route stewardship.
- Added/updated weekly-pulse artifact tests covering the derived provider-route review date and the hold-on-proof-failure decision path.
- Re-verified clean with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T06:39:23+02:00)

- Commit `4dacd824` (`test: harden live trust surface verification`) is on `main` and matches `origin/main`.
- `scripts/hub-live-audit.py` now requires the rendered trust-trend rail on `/`, `/downloads`, `/help`, and `/now`, and it also verifies that signed-in `/downloads`, `/now`, and `/help` expose `Recommended for this install`, `Install posture`, and the fix-ready trust state after the linked install is refreshed.
- `scripts/e2e-hub-playwright.cjs` now asserts the same signed-in trust rows and the rendered `.trust-pulse-trend__point` rail on `/downloads`, `/now`, and `/help`, so the browser proof catches missing trust-surface rendering rather than only route availability.
- Re-verified clean on the current local edge with:
  - `python3 -m py_compile scripts/hub-live-audit.py`
  - `node --check scripts/e2e-hub-playwright.cjs`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`

## Handoff refresh (2026-03-30T06:34:49+02:00)

- Commit `b6366275` (`Visualize trust trends and route verify-ready fixes`) is already on `main` and matches `origin/main`.
- The shared weekly trust pulse panel now renders measured progress points directly from `ProgressTrendSamples` instead of leaving the trend only in prose.
- `PublicTrustPulsePanelViewModel` now carries explicit trend samples, `_PublicTrustPulsePanel.cshtml` renders them, and `site.css` adds the compact trend rail styling used by `/`, `/help`, `/downloads`, and `/now`.
- Verification coverage now asserts the new trend-sample rail is part of the public trust pulse model, and the shared verification entry-point test locks the new panel/view-model seam in place.
- Re-verified clean on the rebuilt local edge with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "PublicTrustPulseServiceTests|VerificationEntryPointTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-30T06:27:17+02:00)

- Commit `eb2ab8eb` (`Deepen install-specific trust and pulse fallback`) is already on `main` and matches `origin/main`.
- Signed-in downloads trust status now includes install-aware `Recommended for this install` and `Install posture` rows so a linked install can be compared against both the promoted public shelf and any support-directed fix lane.
- `PublicTrustPulseService` now prefers the synthesized weekly-pulse `supporting_signals.adoption_health` and `supporting_signals.progress_trend` blocks when present, while still backfilling raw progress/local-proof metadata when those artifacts exist.
- Trust-pulse fixture coverage is now pinned to temp-local optional artifact paths so test results do not bleed in from repo-local generated canon files.
- Smoke coverage now locks the new signed-in downloads rows in both update-needed and verification-ready states.
- Re-verified clean on the rebuilt local edge with:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`
 
## Handoff refresh (2026-03-29T21:45:00+02:00)

- Local execution status is clean and green from the required full verification loop:
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build` completes successfully.
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work` passes.
  - `bash scripts/ai/run_services_smoke.sh` passes.
  - `bash scripts/run_smoke.sh` passes.
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh` passes.
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh` passes.
- Cross-repo build blocker from prior runs was the duplicated-attribute failure in `chummer-core-engine/Chummer.Contracts` during docker rebuild; resolved by pruning generated local artifacts in that adjacent repo before build (`../chummer-core-engine/Chummer.Contracts/obj_tmp` and stale `obj`) and not committing those external repo changes.
- Working tree for this repo is currently clean after cleanup; no untracked artifacts remain.

## Handoff refresh (2026-03-29T22:05:00+02:00)

- Product pulse v2 moved from mostly mirrored-static trust fields to a synthesized evidence path:
  - Added `WeeklyProductPulseArtifactService` to compose `/api/public/weekly-pulse` from the mirrored pulse plus live evidence overlays from:
    - `.codex-design/product/PROGRESS_REPORT.generated.json`
    - `.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json`
    - `/docker/fleet/.codex-studio/published/JOURNEY_GATES.generated.json`
    - `/docker/fleet/.codex-studio/published/SUPPORT_CASE_PACKETS.generated.json`
    - `/docker/fleet/.codex-studio/published/STATUS_PLANE.generated.yaml`
- Public trust surfaces now expose a first-class `Closure health` row backed by the synthesized weekly pulse instead of leaving support follow-through trapped in packet artifacts.
- `PublicTrustPulseService` now reads the synthesized weekly pulse JSON rather than loading the mirrored pulse file directly.
- Mirrored `WEEKLY_PRODUCT_PULSE.generated.json` was refreshed to include the new `closure_health` block and the updated summary language.
- Verification added:
  - new unit tests for `WeeklyProductPulseArtifactService`
  - extended trust-pulse service tests for closure-health derivation
  - entry-point/design-mirror assertions updated for the synthesized pulse path
  - run-services smoke now asserts `Closure health` on landing and current-release trust panels
- Full post-change verification passed:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Handoff refresh (2026-03-29T22:10:00+02:00)

- Extended the synthesized weekly pulse artifact further so `/api/public/weekly-pulse` now includes machine-readable:
  - `supporting_signals.adoption_health`
  - `supporting_signals.progress_trend`
  - alongside the already-added `supporting_signals.closure_health`
- Adoption health now derives from the local release proof plus progress-report history depth.
- Progress trend now derives directly from `PROGRESS_HISTORY.generated.json` and publishes direction, delta, range, summary, and bounded sample points.
- The mirrored `WEEKLY_PRODUCT_PULSE.generated.json` was refreshed to include the new adoption/trend blocks so static canon and synthesized runtime stay aligned.
- Smoke coverage now asserts that `/api/public/weekly-pulse` exposes closure-health, adoption-health, and measured progress-trend samples.
- Full post-change verification passed again:
  - `dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "WeeklyProductPulseArtifactServiceTests|PublicTrustPulseServiceTests|VerificationEntryPointTests|DesignMirrorExecutionPlanTests"`
  - `bash scripts/ai/run_services_smoke.sh`
  - `bash scripts/run_smoke.sh`
  - `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build`
  - `python3 scripts/hub-live-audit.py --base-url http://127.0.0.1:8091 --public-host chummer.run --forwarded-proto https --verify-http-redirects --verify-signed-in-work`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 bash scripts/e2e-hub.sh`
  - `CHUMMER_HUB_E2E_SKIP_EDGE_REBUILD=1 CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh`
  - `bash scripts/audit-compliance.sh`

## Current state (2026-03-29T21:33:00+02:00)

- Implemented trust-pulse trend surfacing from `PROGRESS_HISTORY.generated.json` into public trust rows.
- Added a new `Progress trend` row on `/now`, `/downloads`, and `/help` trust pulse panel through `PublicLandingController`.
- Extended `PublicTrustPulseService` and snapshot model with trend direction/delta and history source metadata.
- Added service tests for history loading and trend calculation, plus verification test coverage for the new `Progress trend` row.
- Hardened `scripts/hub-live-audit.py` fetch path with bounded 429 retry/backoff and expanded trust-row required snippets to include `Progress trend`.
- Re-ran full verification sequence: build/tests, `run_smoke.sh`, live audit, non-playwright e2e, and Playwright e2e (all passing after local rate-limit retries).

Remaining immediate gap
- Long-form trend chart/sparkline visuals are still absent from trust panels; currently shows summary delta only.
- Follow-up could include multi-point trend bullets in panel micro-proof if desired.

## Current state

- Local docker public edge is the active proof lane for `chummer.run`
- Public and signed-in live audits are green on a clean `docker compose -p chummer6-hub -f docker-compose.public-edge.yml up -d --build` cycle
- Wave 1 campaign workspace work now includes:
  - governed roster transfer operator flow
  - governed prep-library search
  - governed prep launch receipts on the shared workspace
  - governed travel-prefetch receipts on the shared workspace
  - governed aftermath recap packages on the shared workspace
  - governed next-session carry-forward packets on the shared workspace and server plane
  - governed downtime brief packets on the shared workspace and server plane
  - richer operator operations pulse and campaign-return pulse on the shared account/control backbone
  - explicit season/event operator rail on the shared account/control backbone
  - explicit sponsor-session operator rail on the shared account/control backbone
  - explicit league/season operations rail on the shared account/control backbone
  - support assistant verification-ready action on install-current reporter cases
  - live-edge proof for the signed-in support assistant verification loop on a claimed install
  - multi-campaign preview season bootstrap on one operator group
  - signed-in home/work aftermath recap visibility on the calmer home cockpit
  - signed-in home/work downtime brief visibility on the calmer home cockpit
  - signed-in home/work next-session carry-forward visibility on the calmer home cockpit
  - signed-in home/work governed consequence follow-through visibility on the calmer home cockpit
  - signed-in home/work governed roster-move visibility on the calmer home cockpit
  - signed-in home/work latest prep-launch and travel-prefetch receipt visibility on the calmer home cockpit
  - signed-in home/work operator-posture visibility on the calmer home cockpit
  - route-readiness gating so `/home/access` and `/home/work` unlock once real device/return truth exists even if onboarding was not explicitly marked complete yet
  - safehouse / travel mode visibility, staged offline inventory, and recap follow-through
  - signed-in and public trust pulse now exposes install-aware `Who can get it now` and `Adoption health`
  - signed-in and public trust pulse now also exposes `Launch readiness` plus `Provider-route stewardship` from the weekly pulse instead of leaving those milestone-20 signals trapped in canon JSON
  - campaign memory projection now appears on signed-in home/work and workspace detail where available
  - home starter lane now nudges linked users without existing campaign work into `/home/work` as a first-playable-session onboarding step
  - `/account/work` empty state now offers the same `Start first playable session` starter action instead of a dead-end generic message
  - shared workspace, workspace digest, and workspace server-plane projections now carry a bounded `First playable session` proof while the campaign is still in its kickoff state
- signed-in `/home/work` and `/account/work/workspaces/{workspaceId}` now surface first-session campaign-start proof, bounded evidence, and a direct route back into the same shared workspace detail
- /auth/email/start now reliably returns a preview callback link on local edge, allowing signed-in workflow assertions to execute full callback/restore verification.

## What just landed

- Added a first-class `First playable session` projection to the shared workspace, calmer workspace digest, and bounded workspace server plane so starter-lane onboarding becomes real campaign-start proof instead of only a seeding button
- Surfaced that first-session proof on both `/home/work` and `/account/work/workspaces/{workspaceId}` with campaign-start summary, bounded evidence, and the same next-step truth already used by the shared workspace
- Retired the first-session proof automatically once governed prep launch, travel prefetch, or recap follow-through lands, so the starter lane does not linger after the campaign moves into durable continuity
- Extended `PublicTrustPulseService` and signed-in/public trust-pulse rows so landing, downloads, help, and current-release surfaces now carry `Launch readiness` plus `Provider-route stewardship` straight from the weekly pulse
- Added unit and smoke assertions that lock those launch/provider pulse rows into the public and signed-in surfaces instead of leaving them as unguarded controller copy
- Refreshed the local mirrored weekly pulse artifact with launch/provider fields and made stack smoke tolerate alternate compose entry files, missing `haproxy.cfg`, and healthy `307` redirect posture on the public edge
- Added a `Start first playable session` action on `/account/work` empty-state copy so signed-in work follows the same starter-lane onboarding route as `/home/work`
- Reused `/api/v1/campaign-spine/me/workspaces/starter` from the account route and added starter-lane feedback/redirect handling instead of inventing a second onboarding API
- Added a dedicated `Aftermath recap` card on `/home/work` with bounded summary, evidence, return-shelf context, and a deep link back to the shared workspace return lane
- Added a dedicated `Downtime brief` card on `/home/work` and matching `/account/work/workspaces/{workspaceId}` detail so downtime obligations and next-session follow-through stop hiding inside the generic aftermath list
- Added a first-class `Next-session carry-forward` projection to the shared workspace and server plane, then surfaced it on both `/account/work/workspaces/{workspaceId}` and `/home/work` with return-lane truth, next-step truth, and bounded evidence
- Deepened `Teams & permissions` with an explicit operator `Operations pulse`, campaign-return pulse, and bounded watchouts instead of leaving organizer posture at raw counts and one roster-move drawer
- Added a first-class `Season / event pulse` and `Season & event rail` to `Teams & permissions`, backed by governed run, carry-forward, change-packet, and recap receipts from the shared campaign/operator projection
- Extended the signed-in `/home/work` operator card so it now carries the operator operations pulse, campaign-return pulse, and a bounded watchout from the same shared projection
- Extended the signed-in `/home/work` operator card so it now also carries the operator season/event pulse and one bounded recent-event receipt from the same shared projection
- Deep-linked the signed-in `/home/work` operator card directly into the exact `Season & event rail` drawer on `/account/work` instead of dropping users at the generic operator shell
- Fixed the campaign spine so one operator group can safely carry more than one governed campaign by resolving crew ids per campaign, keeping campaign-bound dossiers scoped by owner plus campaign instead of collapsing back to one member dossier, and narrowing roster-transfer overwrite checks to the selected target campaign
- Seeded a second governed `preview season` campaign on the default personal operator group and extended smoke coverage so organizer summaries now prove a real multi-campaign season rail instead of a single-campaign placeholder
- Added a first-class multi-campaign `Season board` to `Teams & permissions`, backed by governed workspace projections so each campaign lane shows its lead run, latest event receipt, next safe action, watchout, and direct shared-workspace route
- Added a first-class `League / season operations` rail to `Teams & permissions`, backed by governed league summaries and bounded audit lines so multi-campaign organizer work stops living across disconnected drawers
- Extended the signed-in `/home/work` operator card so it now shows one lead `Season board` lane and deep-links directly into the exact board drawer on `/account/work`
- Extended the signed-in `/home/work` operator card so it now also carries a bounded league-and-season operations summary and a direct route into the new league rail on `/account/work`
- Extended the signed-in live audit so `/account/work` now has to render the season-board entries and their direct shared-workspace routes on the rebuilt edge
- Extended the signed-in live audit so `/account/work` and `/home/work` also have to render the new league-and-season operations rail after the signed-in transfer flow resolves
- Extended public trust pulses on `/now`, `/downloads`, and `/help` so both anonymous and signed-in paths expose install-aware `Who can get it now` and `Adoption health` evidence from proof artifacts
- Exposed campaign memory in signed-in `/home/work`, `/account/work/workspaces/{workspaceId}`, and `/account/work` home surfaces so recall and transition state remains visible across campaign memory boundaries
- Tightened the grounded support assistant so reporter-facing fix questions now escalate from “read the timeline” to an explicit `Verify fix now` action once the linked install is already on the reporter-ready build
- Extended smoke coverage so verification-ready assistant answers must explicitly point back to the tracked case detail and tell the reporter to use the live verification buttons
- Extended `scripts/hub-live-audit.py` so the rebuilt local `chummer.run` edge now submits a real signed-in support case, moves it through internal release and reporter notification, refreshes the claimed install onto the fix build, asks the assistant before and after the update, and proves the `Verify fix now` action plus reporter confirmation on `/account/support/{caseId}`
- Extended `scripts/cleanup_synthetic_support_cases.py` so synthetic support cases created by the live signed-in audit are cleaned up if a later run exits before reporter confirmation
- Fixed bounded receipt retention for governed prep launches, travel-prefetch receipts, and aftermath recap packages so the newest receipts survive once the local proof store crosses its 64-item cap
- Biased signed-in home lead-workspace ordering toward the richer live lane when two workspaces share the same latest transfer timestamp, so `/home/work` keeps the active prep/aftermath lane instead of drifting to a thinner transfer-only lane
- Extended smoke coverage with an aftermath-retention overflow regression so the newest generated recap package must remain visible on `/home/work` after the cap is exceeded
- Added a first-class `Member guidance rail` to `Teams & permissions` so organizers can point people to the real current-release, download, help/trust, and support-closure surfaces from the same operator backbone
- Extended the signed-in `/home/work` operator card so it now carries bounded organizer guidance copy plus a direct route to the member-guidance rail on `/account/work`
- Extended the signed-in live audit so both `/account/work` and `/home/work` have to surface the new organizer guidance rail on the rebuilt edge
- Added a first-class `Invite & sponsorship rail` to `Teams & permissions` so operators can issue governed join codes and boost codes without leaving the shared
