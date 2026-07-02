# NOT_GOLD

Generated: 2026-07-02T07:06:36Z
Scope: full_estate_v20
Accepted boundaries: yes

## Gate Summary
- PASS `account_handoff_runtime_config`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json`
- PASS `black_ledger_live_media_proof`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json`
- PASS `blazor_execution_horizon_bridge`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json`
- PASS `design_quality_gate`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/DESIGN_QUALITY_GATE.generated.json`
- PASS `desktop_native_model_depth`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/DESKTOP_NATIVE_MODEL_DEPTH.generated.json`
- PASS `external_distribution_mirror_proof`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json`
  - mirrors: local_registry=pass, onedrive=fail, pcloud=fail, public_edge=pass; external_required=False
- PASS `icanpreneur_discovery_lane`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/ICANPRENEUR_DISCOVERY_LANE.generated.json`
- PASS `live_public_web_recrawl`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/LIVE_PUBLIC_WEB_RECRAWL.generated.json`
- PASS `live_public_windows_installer`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json`
- PASS `live_surface_parity`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/LIVE_SURFACE_PARITY.generated.json`
- PASS `ltd_optimization_stack`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/LTD_OPTIMIZATION_STACK.generated.json`
- PASS `operator_release_dashboard`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
  - release: run-20260701-124648 on preview
- PASS `participate_billing_honesty`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/PARTICIPATE_BILLING_HONESTY.generated.json`
- PASS `premium_ui_design_exit_gate`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/PREMIUM_UI_DESIGN_EXIT_GATE.generated.json`
- PASS `provider_proof_discoverability`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/PROVIDER_PROOF_DISCOVERABILITY.generated.json`
- PASS `public_copy_leak_gate`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/PUBLIC_COPY_LEAK_GATE.generated.json`
- PASS `public_edge_postdeploy_gate`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json`
  - public edge: Version run-20260701-124648 with browser proof `pass` and horizons `full`
  - mobile ledger: opt_in_required
- PASS `public_route_proof`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - routes 188/188, failed 0, negative-path failures 0
- FAIL `release_ready`: `fail` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/RELEASE_READY.generated.json`
  - release failures: FAIL verify_public_edge_deploy_source, FAIL verify_windows_installer_visual_audit, verify_public_edge_deploy_source, verify_windows_installer_visual_audit
- PASS `rule_authority_minimum_coverage`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json`
- PASS `ruleset_readiness`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/RULESET_READINESS.generated.json`
  - authority approved: sr4, sr6
- PASS `table_pulse_scenario_replay`: `pass` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/TABLE_PULSE_SCENARIO_REPLAY.generated.json`
- PASS `ui_layout_exit_gate`: `pass` at `/docker/chummercomplete/_completion/chummer_run_redesign_closure/UI_LAYOUT_EXIT_GATE.generated.json`
- FAIL `windows_installer_visual_audit`: `fail` at `/tmp/chummer-run-services-nightly.VsudjQ/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
  - visual audit failures: Windows installer visual audit source digest does not match promoted installer
  - next actions:
    - Run the promoted Windows installer on a native Windows host and capture native startup plus installer progress/completion surfaces.
    - Preferred remote path: run the native Windows proof runner from a controlled Windows host; it captures native Windows evidence only and does not publish downloads.
    - Use PowerShell: scripts/capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5
    - Use PowerShell: scripts/capture_windows_installer_visual_audit.ps1 -LaunchInstaller -CaptureRequiredSet -ScaledDpiScale 1.5 -ClippingStatus pass -ReadabilityStatus pass
    - If you need manual capture, run scripts/capture_windows_installer_visual_audit.ps1 once per surface/DPI for install-progress and completion at default plus scaled DPI.
    - If progress and completion screenshots are byte-identical, rerun manual capture with the progress dialog visible before accepting the completion dialog.
    - If proof came from a remote Windows runner, import it with: python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify
    - Commit the generated source receipt and screenshots under /docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/visual-audit/windows-installer.
    - Replace the incompatible-host Windows startup-smoke receipt with a native Windows pass for the same promoted installer digest.

## Accepted Boundaries
- `optional_external_mirrors_degraded`: Local registry and public edge are release-blocking and passing, but optional external mirrors are degraded.

## Failures
- windows_installer_visual_audit failed
- release_ready failed
