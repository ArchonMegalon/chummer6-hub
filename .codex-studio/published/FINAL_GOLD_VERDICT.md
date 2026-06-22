# NOT_GOLD

Generated: 2026-06-20T20:13:30Z
Scope: full_estate_v20
Accepted boundaries: yes

## Gate Summary
- PASS `black_ledger_live_media_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json`
- PASS `design_quality_gate`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/DESIGN_QUALITY_GATE.generated.json`
- PASS `desktop_native_model_depth`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/DESKTOP_NATIVE_MODEL_DEPTH.generated.json`
- PASS `external_distribution_mirror_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json`
  - mirrors: local_registry=pass, onedrive=fail, pcloud=fail, public_edge=pass; external_required=False
- PASS `live_public_web_recrawl`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LIVE_PUBLIC_WEB_RECRAWL.generated.json`
- PASS `live_surface_parity`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LIVE_SURFACE_PARITY.generated.json`
- PASS `ltd_optimization_stack`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LTD_OPTIMIZATION_STACK.generated.json`
- PASS `operator_release_dashboard`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
  - release: run-258 on preview
- PASS `provider_proof_discoverability`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PROVIDER_PROOF_DISCOVERABILITY.generated.json`
- PASS `public_copy_leak_gate`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_COPY_LEAK_GATE.generated.json`
- PASS `public_route_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - routes 165/165, failed 0, negative-path failures 0
- PASS `release_ready`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RELEASE_READY.generated.json`
- PASS `rule_authority_minimum_coverage`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json`
- PASS `ruleset_readiness`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RULESET_READINESS.generated.json`
  - authority approved: sr4, sr6
- PASS `table_pulse_scenario_replay`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/TABLE_PULSE_SCENARIO_REPLAY.generated.json`
- PASS `ui_layout_exit_gate`: `pass` at `/docker/chummercomplete/_completion/chummer_run_redesign_closure/UI_LAYOUT_EXIT_GATE.generated.json`
- FAIL `windows_installer_visual_audit`: `fail` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`
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
