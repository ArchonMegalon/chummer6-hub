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


def test_authority_closure_is_ordered_and_finishes_only_after_current_convergence() -> None:
    source = load_bootstrap()
    ordered_markers = (
        'log "publishing the exact review seed to Registry with CURRENT compare-and-swap"',
        'log "verifying all CURRENT release-facing routes converge after Registry accepted the review seed"',
        'log "accepting the digest-pinned campaign-operability scorecard only after the published review seed converged"',
        'log "publishing the exact preview-ready successor to Registry with predecessor compare-and-swap"',
        'log "advancing the sealed Hub generation to the exact Registry-published preview authority"',
        'log "verifying all CURRENT release-facing routes converge on preview-ready authority"',
        'log "done"',
    )

    positions = [source.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)
    assert source.count('log "done"') == 1

    review_current_segment = source[positions[1] : positions[2]]
    assert "--generation-id" not in review_current_segment
    assert '> "$review_seed_live_convergence_receipt"' in review_current_segment

    final_current_segment = source[positions[5] : positions[6]]
    assert "--generation-id" not in final_current_segment
    assert '> "$preview_live_convergence_receipt"' in final_current_segment


def test_preview_successor_is_bound_to_post_registry_current_convergence() -> None:
    source = load_bootstrap()
    successor_start = source.index(
        'log "materializing the scorecard-v2-backed preview-ready Registry authority successor"'
    )
    final_convergence_start = source.index(
        'log "verifying immutable generation $release_generation_id converges on preview-ready authority"'
    )
    successor_segment = source[successor_start:final_convergence_start]

    assert successor_segment.count(
        '--convergence "$review_seed_live_convergence_receipt"'
    ) == 7
    assert '--convergence "$generation_convergence_receipt"' not in successor_segment
    assert '--convergence "$live_convergence_receipt"' not in successor_segment


def test_scorecard_handoff_is_resolved_only_after_review_seed_current_convergence() -> None:
    source = load_bootstrap()
    convergence_passed = source.index(
        'log "post-Registry review-seed CURRENT convergence passed: $review_seed_live_convergence_receipt"'
    )
    wait_for_handoff = source.index(
        'log "waiting up to ${scorecard_handoff_wait_seconds}s for the caller-owned post-convergence scorecard handoff'
    )
    accept_scorecard = source.index(
        'log "accepting the digest-pinned campaign-operability scorecard only after the published review seed converged"'
    )

    assert convergence_passed < wait_for_handoff < accept_scorecard
    assert 'local scorecard_source_path="${CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_PATH' not in source
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_PATH" in source
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_EXPECTED_SHA256" in source
    assert '$retired_scorecard_setting is retired because a launch-time scorecard digest' in source
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF_PATH" in source
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF_WAIT_SECONDS" in source
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF_POLL_SECONDS" in source
    assert "resolve_release_scorecard_handoff.py" in source

    stage_settings_start = source.index('for registry_publish_setting in \\\n')
    stage_settings_end = source.index("\n  fi\n\n  local publish_mode", stage_settings_start)
    stage_settings = source[stage_settings_start:stage_settings_end]
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF_PATH" in stage_settings
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF_WAIT_SECONDS" in stage_settings
    assert "CHUMMER_CAMPAIGN_OPERABILITY_SCORECARD_HANDOFF_POLL_SECONDS" in stage_settings


def test_registry_control_secret_is_streamed_and_authority_urls_are_exact() -> None:
    source = load_bootstrap()

    assert 'unset CHUMMER_REGISTRY_CONTROL_API_KEY REGISTRY_CONTROL_API_KEY' in source
    assert '| curl -q --config - -sS \\\n' in source
    assert '--header "X-Chummer-Registry-Key:' not in source
    assert '"/api/v1/registry/release-authority/current"' in source
    assert '"/api/v1/registry/release-authority/publish"' in source
    assert (
        "Registry release-authority current and publish endpoints must share one origin"
        in source
    )


def test_authority_recovery_checkpoint_precedes_registry_preview_cas_and_survives_until_convergence() -> None:
    source = load_bootstrap()
    checkpoint = source.index(
        'log "durable authority recovery checkpoint created before Registry CAS:'
    )
    registry_preview = source.index(
        'log "publishing the exact preview-ready successor to Registry with predecessor compare-and-swap"'
    )
    hub_advance = source.index(
        'log "advancing the sealed Hub generation to the exact Registry-published preview authority"'
    )
    generation_convergence = source.index(
        'log "verifying immutable generation $release_generation_id converges on preview-ready authority"'
    )
    current_convergence = source.index(
        'log "verifying all CURRENT release-facing routes converge on preview-ready authority"'
    )
    checkpoint_removal = source.index(
        'rm -f "$hub_authority_advance_request" "$hub_authority_checkpoint"'
    )

    assert checkpoint < registry_preview < hub_advance < generation_convergence
    assert generation_convergence < current_convergence < checkpoint_removal
    assert 'bootstrap_tmp_paths+=("$hub_authority_checkpoint")' not in source
    assert 'bootstrap_tmp_paths+=("$hub_authority_advance_request")' not in source


def test_resume_is_an_early_exact_replay_without_registry_publish_or_build() -> None:
    source = load_bootstrap()
    resume_function_start = source.index("resume_release_authority_transaction() {")
    main_start = source.index("\nmain() {", resume_function_start)
    resume_function = source[resume_function_start:main_start]

    assert "release_authority_transaction_checkpoint.py" in resume_function
    assert 'log "resume mode: verifying Registry CURRENT equals the checkpointed preview successor"' in resume_function
    assert 'log "resume mode: replaying the exact Hub authority request idempotently"' in resume_function
    assert "post_hub_authority_advance_request" in resume_function
    assert "post_registry_authority_request" not in resume_function
    assert "clone_or_update" not in resume_function
    assert "dotnet" not in resume_function
    assert resume_function.index("generation projection did not converge") < resume_function.index(
        'rm -f "$request_path" "$checkpoint_path"'
    )
    assert resume_function.index("CURRENT routes did not converge") < resume_function.index(
        'rm -f "$request_path" "$checkpoint_path"'
    )

    main_resume = source.index("if (( MAC_RELEASE_AUTHORITY_RESUME == 1 )); then")
    normal_pin_check = source.index("require_all_reviewed_commit_pins", main_resume)
    first_clone = source.index("clone_or_update", main_resume)
    assert main_resume < normal_pin_check < first_clone
    assert "authority resume rejects Registry publication credential" in source[main_resume:normal_pin_check]


def test_resume_arguments_are_all_or_nothing_and_unknown_flags_fail_closed() -> None:
    source = load_bootstrap()
    parser_start = source.index("parse_mac_release_stage_only_args() {")
    parser_end = source.index("\nresolve_mac_release_stage_output_path()", parser_start)
    parser = source[parser_start:parser_end]

    assert "authority resume requires --resume-authority-checkpoint, --resume-authority-checkpoint-sha256, and --resume-authority-workspace together" in parser
    assert "authority resume cannot be combined with stage-only mode" in parser
    assert "authority resume checkpoint SHA-256 must be 64 lowercase hexadecimal characters" in parser
    assert 'die "unsupported bootstrap argument: $1"' in parser


def test_stage_only_returns_before_authority_checkpoint_materialization() -> None:
    source = load_bootstrap()
    stage_only_call = source.index("stage_local_release_bundle ", source.index("\nmain() {"))
    stage_only_return = source.index("return 0", stage_only_call)
    checkpoint_materialization = source.index(
        'local hub_authority_checkpoint_tool="$hub_repo/scripts/release_authority_transaction_checkpoint.py"'
    )

    assert stage_only_call < stage_only_return < checkpoint_materialization


def test_same_release_ready_state_requires_resume_but_new_release_can_start() -> None:
    source = load_bootstrap()
    assert 'if [[ "$registry_current_release_version" == "$release_version" ]]; then' in source
    assert "use the digest-pinned authority resume path instead of regressing it to a review seed" in source
    assert "beginning the explicitly new release $release_version from a review-required seed" in source
