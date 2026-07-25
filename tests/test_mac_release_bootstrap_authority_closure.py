from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


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
        'log "capturing candidate-bound staged UI-frame proof before deleting the private probe grant"',
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


def test_registry_authority_tools_bind_the_exact_approved_release_scope() -> None:
    source = load_bootstrap()
    materialize_start = source.index(
        'command "$RELEASE_PYTHON_BIN" "$release_authority_materializer"'
    )
    verify_start = source.index(
        'command "$RELEASE_PYTHON_BIN" "$release_authority_verifier"',
        materialize_start,
    )
    copy_start = source.index(
        "  for release_authority_file in CURRENT.json SNAPSHOT.json RELEASE_DECISION.json;",
        verify_start,
    )
    materialize = source[materialize_start:verify_start]
    verify = source[verify_start:copy_start]
    required = (
        '--release-scope-decision "$release_evidence_dir/RELEASE_SCOPE_DECISION.approved.json"',
        '--expected-release-scope-decision-sha256 "$release_scope_expected_sha256"',
    )

    for invocation in (materialize, verify):
        for argument in required:
            assert argument in invocation
        assert "--support-owner" not in invocation


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
    capture = main.index(
        'log "capturing candidate-bound staged UI-frame proof before deleting the private probe grant"'
    )
    delete = main.index('rm -f "$staged_probe_token_path"')
    handoff = main.index('materialize_staged_release_finalizer_handoff.py')
    assert capture < delete < handoff
    assert 'CHUMMER_UI_FRAME_VERIFICATION_MODE="staged_private"' in main
    assert 'CHUMMER_UI_FRAME_AUTHORITY_ROUTE="/api/v1/public/release-truth/g/$release_generation_id"' in main
    assert '--ui-frame-receipt "$staged_ui_frame_receipt"' in main
    assert (
        '--desktop-visual-receipt "$staged_desktop_visual_receipt"' in main
    )
    assert (
        '--desktop-workflow-receipt "$staged_desktop_workflow_receipt"' in main
    )
    assert (
        '--desktop-executable-receipt "$staged_desktop_executable_receipt"' in main
    )
    presentation_request = main.index(
        'log "materializing the exact candidate-bound Presentation receipt request before any upload"'
    )
    presentation_wait = main.index(
        "wait_for_presentation_candidate_receipts",
        presentation_request,
    )
    presentation_pin = main.index(
        'log "validating and pinning exact Presentation receipts before any upload"'
    )
    upload = main.index('upload_release_bundle_http \\\n', presentation_pin)
    assert presentation_request < presentation_wait < presentation_pin < upload < capture
    assert capture < delete < handoff
    pin_start = source.index("pin_presentation_candidate_receipts() {")
    pin_end = source.index("\nmain() {", pin_start)
    pin = source[pin_start:pin_end]
    assert 'getattr(os, "O_NOFOLLOW", 0)' in pin
    assert 'os.O_EXCL' in pin
    assert 'before.st_uid != os.geteuid()' in pin
    assert 'before.st_nlink != 1' in pin
    assert 'before.st_mode & 0o022' in pin
    assert "campaign_operability_candidate_binding" in pin
    assert '--stage-response "$ui_repo/$durable_stage_response"' in main
    assert 'STAGED_RELEASE_FINALIZER_HANDOFF.generated.json' in main


def test_http_bootstrap_materializes_presentation_request_after_candidate_before_upload() -> None:
    source = load_bootstrap()
    main = staging_main_segment(source)
    for variable in (
        "CHUMMER_PRESENTATION_DESKTOP_VISUAL_RECEIPT_PATH",
        "CHUMMER_PRESENTATION_DESKTOP_WORKFLOW_RECEIPT_PATH",
        "CHUMMER_PRESENTATION_DESKTOP_EXECUTABLE_RECEIPT_PATH",
    ):
        assert f'local {variable.lower()}=' not in main
        assert variable in main
        assert f"{variable} must name an absolute caller-owned" not in main

    authority = main.index(
        'log "materializing review-required Registry authority for the exact generation-projected nightly"'
    )
    request = main.index(
        'log "materializing the exact candidate-bound Presentation receipt request before any upload"'
    )
    wait = main.index("wait_for_presentation_candidate_receipts", request)
    pin = main.index(
        'log "validating and pinning exact Presentation receipts before any upload"',
        wait,
    )
    upload = main.index('upload_release_bundle_http \\\n', pin)
    assert authority < request < wait < pin < upload
    assert (
        'local presentation_receipt_intake_dir="$work_root/.c/presentation-candidate-receipts"'
        in main
    )
    assert 'CHUMMER_PRESENTATION_RECEIPT_WAIT_SECONDS:-1800' in main
    assert 'CHUMMER_PRESENTATION_RECEIPT_POLL_SECONDS:-5' in main
    assert "PRESENTATION_CANDIDATE_RECEIPT_REQUEST.generated.json" in main


def run_sourced(command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            "bash",
            "-c",
            f'source "$1"; RELEASE_PYTHON_BIN=python3; {command}',
            "presentation-receipt-test",
            str(BOOTSTRAP),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def presentation_fixture(tmp_path: Path) -> dict[str, object]:
    release_version = "run-candidate-proof"
    registry_commit = "a" * 40
    support_owner = "chummer-release-operations"
    scope = {
        "releaseVersion": release_version,
        "supportOwner": support_owner,
        "platforms": [
            {
                "platform": "macos",
                "rid": "osx-arm64",
                "primaryHead": "avalonia",
                "fallbackHeads": ["blazor-desktop"],
            }
        ],
    }
    scope_path = tmp_path / "scope.json"
    scope_raw = (json.dumps(scope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    scope_path.write_bytes(scope_raw)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(
        (json.dumps({"version": release_version}, sort_keys=True) + "\n").encode()
    )
    decision_path = tmp_path / "decision.json"
    decision_path.write_bytes(b'{"status":"review_required"}\n')
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    decision_sha256 = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "manifestSha256": manifest_sha256,
                "releaseDecisionSha256": decision_sha256,
                "registryCommit": registry_commit,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    binding = {
        "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
        "contract_version": 1,
        "release_version": release_version,
        "release_scope_decision_sha256": hashlib.sha256(scope_raw).hexdigest(),
        "manifest_sha256": manifest_sha256,
        "authority_snapshot_sha256": hashlib.sha256(
            snapshot_path.read_bytes()
        ).hexdigest(),
        "release_decision_sha256": decision_sha256,
        "registry_commit": registry_commit,
        "platform": "macos",
        "rid": "osx-arm64",
        "primary_head": "avalonia",
        "required_heads": ["avalonia", "blazor-desktop"],
    }
    sources: list[Path] = []
    for evidence_id in ("desktop_visual", "desktop_workflow", "desktop_executable"):
        path = tmp_path / f"{evidence_id}.json"
        path.write_text(
            json.dumps(
                {
                    "contract_name": f"fixture.{evidence_id}",
                    "status": "pass",
                    "releaseVersion": release_version,
                    "campaign_operability_candidate_binding": binding,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        sources.append(path)
    return {
        "release_version": release_version,
        "registry_commit": registry_commit,
        "support_owner": support_owner,
        "scope_path": scope_path,
        "scope_sha256": hashlib.sha256(scope_raw).hexdigest(),
        "manifest_path": manifest_path,
        "snapshot_path": snapshot_path,
        "decision_path": decision_path,
        "binding": binding,
        "sources": sources,
    }


def test_presentation_request_exposes_exact_post_build_binding_without_release_mutation(
    tmp_path: Path,
) -> None:
    fixture = presentation_fixture(tmp_path)
    request = tmp_path / "request.json"
    presentation_repo = tmp_path / "presentation"
    presentation_repo.mkdir(mode=0o700)
    outputs = [tmp_path / f"output-{index}.json" for index in range(3)]
    result = run_sourced(
        'write_presentation_candidate_receipt_request "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}" "${13}" "${14}"',
        str(request),
        str(fixture["scope_path"]),
        str(fixture["scope_sha256"]),
        str(fixture["manifest_path"]),
        str(fixture["snapshot_path"]),
        str(fixture["decision_path"]),
        str(fixture["release_version"]),
        str(fixture["registry_commit"]),
        str(fixture["support_owner"]),
        str(presentation_repo),
        *(str(path) for path in outputs),
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(request.stat().st_mode) == 0o600
    payload = json.loads(request.read_text(encoding="utf-8"))
    assert payload["status"] == "action_required"
    assert payload["countsAsBuildEvidence"] is False
    assert payload["countsAsPublicationEvidence"] is False
    assert payload["candidateBinding"] == fixture["binding"]
    assert [row["outputPath"] for row in payload["producers"]] == [
        str(path) for path in outputs
    ]
    assert "ticket" not in request.read_text(encoding="utf-8").lower()


def test_presentation_wait_is_bounded_and_rejects_unsafe_paths(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")
    receipts = [tmp_path / f"receipt-{index}.json" for index in range(3)]
    command = (
        'wait_for_presentation_candidate_receipts '
        '"$2" 0 1 "$3" "$4" "$5"'
    )
    missing = run_sourced(
        command,
        str(request),
        *(str(path) for path in receipts),
    )

    assert missing.returncode != 0
    assert str(request) in missing.stderr
    assert "before timeout" in missing.stderr

    for path in receipts:
        path.write_text("{}\n", encoding="utf-8")
    accepted = run_sourced(
        command,
        str(request),
        *(str(path) for path in receipts),
    )
    assert accepted.returncode == 0, accepted.stderr

    receipts[1].unlink()
    receipts[1].symlink_to(receipts[0])
    unsafe = run_sourced(
        command,
        str(request),
        *(str(path) for path in receipts),
    )
    assert unsafe.returncode != 0
    assert "became unsafe" in unsafe.stderr


def test_presentation_receipts_are_exactly_validated_before_atomic_pin(
    tmp_path: Path,
) -> None:
    fixture = presentation_fixture(tmp_path)
    sources = list(fixture["sources"])
    target_dir = tmp_path / "pinned"
    target_dir.mkdir(mode=0o700)
    targets = [target_dir / path.name for path in sources]
    command = (
        'pin_presentation_candidate_receipts '
        '"$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" '
        '"${10}" "${11}" "${12}" "${13}" "${14}"'
    )
    arguments = [
        str(sources[0]),
        str(targets[0]),
        str(sources[1]),
        str(targets[1]),
        str(sources[2]),
        str(targets[2]),
        str(fixture["scope_path"]),
        str(fixture["scope_sha256"]),
        str(fixture["manifest_path"]),
        str(fixture["snapshot_path"]),
        str(fixture["decision_path"]),
        str(fixture["release_version"]),
        str(fixture["registry_commit"]),
    ]
    accepted = run_sourced(command, *arguments)

    assert accepted.returncode == 0, accepted.stderr
    assert [path.read_bytes() for path in targets] == [
        path.read_bytes() for path in sources
    ]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in targets)

    tampered_payload = json.loads(sources[1].read_text(encoding="utf-8"))
    tampered_payload["campaign_operability_candidate_binding"][
        "manifest_sha256"
    ] = "0" * 64
    sources[1].write_text(
        json.dumps(tampered_payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sources[1].chmod(0o600)
    rejected_dir = tmp_path / "rejected"
    rejected_dir.mkdir(mode=0o700)
    rejected_targets = [rejected_dir / path.name for path in sources]
    rejected_arguments = arguments.copy()
    rejected_arguments[1] = str(rejected_targets[0])
    rejected_arguments[3] = str(rejected_targets[1])
    rejected_arguments[5] = str(rejected_targets[2])
    rejected = run_sourced(command, *rejected_arguments)

    assert rejected.returncode != 0
    assert "does not bind the exact passing candidate" in rejected.stderr
    assert not any(path.exists() for path in rejected_targets)


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
