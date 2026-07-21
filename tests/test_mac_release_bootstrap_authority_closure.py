from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (
    ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)


def load_bootstrap() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


def staging_main_segment(source: str) -> str:
    start = source.index('\nmain() {')
    handoff = source.index('log "owner finalizer handoff:', start)
    end = source.index("  return 0", handoff) + len("  return 0")
    return source[start:end]


def test_downloaded_bootstrap_stages_and_privately_probes_before_stopping() -> None:
    source = load_bootstrap()
    main = staging_main_segment(source)
    ordered = (
        'upload_release_bundle_http \\\n',
        'log "privately probing the sealed review-required generation; public CURRENT remains unchanged"',
        'materialize_staged_release_finalizer_handoff.py',
        'log "immutable nightly generation staged and privately verified; public CURRENT was not changed"',
        'log "status: review_required (awaiting separate owner-only scorecard, Registry CAS, and activation)"',
    )
    positions = [main.index(marker) for marker in ordered]
    assert positions == sorted(positions)
    assert main.rstrip().endswith("return 0")
    assert 'post_registry_authority_request' not in main
    assert 'activate-staged' not in main
    assert 'verifying all CURRENT release-facing routes' not in main


def test_http_upload_seals_stage_endpoint_and_never_calls_legacy_complete() -> None:
    source = load_bootstrap()
    start = source.index("upload_release_bundle_http() {")
    end = source.index("\nstage_local_release_bundle() {", start)
    upload = source[start:end]

    assert 'expected_stage_url="$(normalize_upload_url "${session_id}/stage"' in upload
    assert '"seal immutable staged generation"' in upload
    assert '"${session_id}/complete"' not in upload
    assert '"complete staged upload"' not in upload
    assert 'BOOTSTRAP_RELEASE_STAGE_ACCEPTED=1' in upload


def test_downloaded_bootstrap_rejects_owner_credentials_before_build_or_clone() -> None:
    source = load_bootstrap()
    main_start = source.index("\nmain() {")
    pin_check = source.index("require_all_reviewed_commit_pins", main_start)
    first_clone = source.index("clone_or_update", pin_check)
    early = source[main_start:pin_check]

    assert "rejects FLEET_INTERNAL_API_TOKEN" in early
    assert "rejects Registry control credentials" in early
    assert "authority resume moved to the non-public staged-release owner finalizer" in early
    assert main_start < pin_check < first_clone

    capture_start = source.index("capture_release_upload_auth_value() {")
    capture_end = source.index("\nprompt_for_release_upload_ticket() {", capture_start)
    capture = source[capture_start:capture_end]
    assert 'captured_value="$FLEET_INTERNAL_API_TOKEN"' not in capture
    assert 'captured_source="FLEET_INTERNAL_API_TOKEN"' not in capture
    reject = source.index("rejects FLEET_INTERNAL_API_TOKEN", main_start)
    capture_call = source.index("capture_release_upload_auth_value", main_start)
    assert reject < capture_call


def test_private_probe_token_is_separated_from_redacted_handoff() -> None:
    source = load_bootstrap()
    main = staging_main_segment(source)
    assert '--staged-probe-token-file "$staged_probe_token_path"' in main
    assert 'chmod 600 "$staged_probe_token_path"' in main
    assert 'BOOTSTRAP_RELEASE_STAGE_PROBE_TOKEN=""' in main
    assert 'rm -f "$staged_probe_token_path"' in main
    assert '--stage-response "$ui_repo/$durable_stage_response"' in main
    assert 'STAGED_RELEASE_FINALIZER_HANDOFF.generated.json' in main


def test_exact_executing_bootstrap_bytes_are_pinned_into_handoff_workspace() -> None:
    source = load_bootstrap()
    main = staging_main_segment(source)
    pin = main.index('local pinned_executed_bootstrap="$work_root/.c/mac-release-bootstrap.executed.sh"')
    stage = main.index('upload_release_bundle_http \\\n')
    handoff = main.index('--executed-bootstrap "$pinned_executed_bootstrap"')
    assert pin < stage < handoff
    assert "os.O_EXCL" in main[pin:stage]
    assert "pinned executed bootstrap bytes changed" in main[pin:stage]


def test_stage_only_still_returns_before_any_http_stage() -> None:
    source = load_bootstrap()
    main_start = source.index("\nmain() {")
    stage_only_call = source.index("stage_local_release_bundle ", main_start)
    stage_only_return = source.index("return 0", stage_only_call)
    http_stage = source.index("upload_release_bundle_http ", stage_only_return)
    assert stage_only_call < stage_only_return < http_stage


def test_resume_arguments_remain_fail_closed_but_public_resume_is_disabled() -> None:
    source = load_bootstrap()
    parser_start = source.index("parse_mac_release_stage_only_args() {")
    parser_end = source.index("\nresolve_mac_release_stage_output_path()", parser_start)
    parser = source[parser_start:parser_end]
    assert "authority resume requires --resume-authority-checkpoint" in parser
    assert "authority resume cannot be combined with stage-only mode" in parser
    assert 'die "unsupported bootstrap argument: $1"' in parser
    assert "authority resume moved to the non-public staged-release owner finalizer" in source
