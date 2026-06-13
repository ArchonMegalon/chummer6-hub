# NOT_GOLD

Generated: 2026-06-13T08:00:49Z
Scope: full_estate_v20

## Gate Summary
- PASS `black_ledger_live_media_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json`
- PASS `design_quality_gate`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/DESIGN_QUALITY_GATE.generated.json`
- PASS `external_distribution_mirror_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json`
  - mirrors: local_registry=pass, onedrive=pass, pcloud=pass, public_edge=pass; external_required=False
- PASS `live_public_web_recrawl`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/LIVE_PUBLIC_WEB_RECRAWL.generated.json`
- FAIL `operator_release_dashboard`: `fail` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/OPERATOR_RELEASE_DASHBOARD.generated.json`
  - release: run-20260612-121055 on public_stable
  - dashboard failures: public_copy_leak_gate
- PASS `provider_proof_discoverability`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PROVIDER_PROOF_DISCOVERABILITY.generated.json`
- FAIL `public_copy_leak_gate`: `fail` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/PUBLIC_COPY_LEAK_GATE.generated.json`
- PASS `public_route_proof`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json`
  - routes 165/165, failed 0, negative-path failures 0
- FAIL `release_ready`: `fail` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RELEASE_READY.generated.json`
  - release failures: FAIL verify_public_copy_leak_gate, FAIL verify_operator_release_dashboard, verify_public_copy_leak_gate, verify_operator_release_dashboard
- PASS `rule_authority_minimum_coverage`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json`
- PASS `ruleset_readiness`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/RULESET_READINESS.generated.json`
- PASS `table_pulse_scenario_replay`: `pass` at `/docker/chummercomplete/chummer.run-services/.codex-studio/published/TABLE_PULSE_SCENARIO_REPLAY.generated.json`

## Failures
- public_copy_leak_gate failed
- operator_release_dashboard failed
- release_ready failed
- materializer failed: python3 scripts/verify_public_copy_leak_gate.py --base-url https://chummer.run
- materializer failed: python3 scripts/materialize_operator_release_dashboard.py
