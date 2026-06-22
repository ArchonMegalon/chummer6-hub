# NOT_GOLD

Generated: 2026-06-22T12:57:32Z
Scope: full_estate_v20
Accepted boundaries: yes

## Gate Summary
- FAIL `black_ledger_live_media_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json`
- PASS `design_quality_gate`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/DESIGN_QUALITY_GATE.generated.json`
- FAIL `desktop_native_model_depth`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/DESKTOP_NATIVE_MODEL_DEPTH.generated.json`
- FAIL `external_distribution_mirror_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json`
  - mirrors: local_registry=pass, onedrive=fail, pcloud=fail, public_edge=pass; external_required=False
- PASS `icanpreneur_discovery_lane`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/ICANPRENEUR_DISCOVERY_LANE.generated.json`
- FAIL `live_public_web_recrawl`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LIVE_PUBLIC_WEB_RECRAWL.generated.json`
- FAIL `live_surface_parity`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LIVE_SURFACE_PARITY.generated.json`
- PASS `ltd_optimization_stack`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LTD_OPTIMIZATION_STACK.generated.json`
- FAIL `operator_release_dashboard`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
  - release: run-258 on preview
- PASS `provider_proof_discoverability`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PROVIDER_PROOF_DISCOVERABILITY.generated.json`
- PASS `public_copy_leak_gate`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_COPY_LEAK_GATE.generated.json`
- PASS `public_route_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - routes 165/165, failed 0, negative-path failures 0
- FAIL `release_ready`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RELEASE_READY.generated.json`
- FAIL `rule_authority_minimum_coverage`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json`
- FAIL `ruleset_readiness`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RULESET_READINESS.generated.json`
  - authority approved: sr4, sr6
- FAIL `table_pulse_scenario_replay`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/TABLE_PULSE_SCENARIO_REPLAY.generated.json`
- PASS `ui_layout_exit_gate`: `pass` at `/docker/chummercomplete/_completion/chummer_run_redesign_closure/UI_LAYOUT_EXIT_GATE.generated.json`
- PASS `windows_installer_visual_audit`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json`

## Accepted Boundaries
- `optional_external_mirrors_degraded`: Local registry and public edge are release-blocking and passing, but optional external mirrors are degraded.

## Failures
- live_public_web_recrawl stale
- rule_authority_minimum_coverage stale
- ruleset_readiness stale
- desktop_native_model_depth stale
- black_ledger_live_media_proof stale
- table_pulse_scenario_replay stale
- live_surface_parity stale
- external_distribution_mirror_proof stale
- operator_release_dashboard stale
- release_ready stale
