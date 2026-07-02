# OPERABLE_RELEASE_READY

- Generated: 2026-07-02T08:42:40Z
- Version: `run-20260701-124648`
- Channel: `preview`
- Published: `2026-07-01T14:29:35Z`
- Supportability: `preview_supported`
- Public edge: `pass` / `Version run-20260701-124648`
- Mobile PWA: `pass`, ledger `opt_in_required`
- Mirrors: local_registry=pass, onedrive=fail, pcloud=fail, public_edge=pass
- Billing mode: `unavailable`
- Release-upload mode: `default_single_operator`
- Windows visual audit: `fail`; intake `external_artifact_required`; matching promoted sources `0`

## Rulesets
- `sr4`: status `None`, workflow parity `pass`, assumption `False`
- `sr5`: status `None`, workflow parity `None`, assumption `None`
- `sr6`: status `None`, workflow parity `pass`, assumption `False`

## Checks
- PASS `account_handoff_runtime_config`: `pass`
- PASS `design_quality_gate`: `pass`
- PASS `external_distribution_mirror_proof`: `pass`
- INFO `final_gold_janitor`: `fail` (operator context, not release-blocking)
- PASS `google_oauth_linking_proof`: `pass` (operator context, not release-blocking)
- PASS `participate_billing_honesty`: `pass`
- PASS `public_copy_leak_gate`: `pass`
- PASS `public_edge_postdeploy_gate`: `pass`
- PASS `release_channel`: `published`
- INFO `release_ready`: `fail` (operator context, not release-blocking)
- PASS `ruleset_readiness`: `pass`
- PASS `ui_frame_integrity`: `pass`
- INFO `windows_installer_visual_audit`: `fail` (operator context, not release-blocking)
- PASS `windows_installer_visual_audit_intake_request`: `external_artifact_required` (operator context, not release-blocking)

## Windows Visual Audit Handoff
- Promoted installer: `chummer-avalonia-win-x64-installer.exe` / `4d14c414fcd46f4cf5d2b06ac12d02d8492431f19924bffa97390af5f1c68bf3`
- Current visual source artifact: `c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b`
- Matching promoted visual sources discovered: `0`
- Gold proof bundle discovery: `not_found`
- Operator request: Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.
- Import command: `python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify`
- Current blocker: Windows installer visual audit source digest does not match promoted installer
