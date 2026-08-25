import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT / "ops/build-ghost-private-nonprod/deploy-first-provider-disabled-rook-lane.sh"
)
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def run_sourced(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"\n{body}', "test", str(SCRIPT_PATH)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_first_rollout_has_fail_closed_authorities_before_build() -> None:
    main = SCRIPT.split("main() {", 1)[1]
    build = main.index("build_under_limits")
    for required in (
        "validate_sources_and_authoritative_hub",
        "validate_external_secrets_without_output",
        "ensure_host_limits",
        "snapshot_runtime_authority",
        "verify_rendered_provider_disabled_compose",
        "validate_receipt_target",
        "create_rollback_refs",
    ):
        assert main.index(required) < build
    assert "git -C \"$repo_root\" ls-remote --exit-code origin refs/heads/main" in SCRIPT
    assert '"$remote_main" = "$CHUMMER_RUN_SERVICES_REVISION"' in SCRIPT
    assert "minimum_free_gib" in SCRIPT and ":-28}" in SCRIPT
    assert '"$minimum_free_gib" -ge 28' in SCRIPT
    assert "/proc/pressure/io" in SCRIPT
    assert "verify_candidate_source_labels" in SCRIPT
    for label in (
        "org.opencontainers.image.revision",
        "run.chummer.build-ghost.hub-revision",
        "run.chummer.build-ghost.core-revision",
        "run.chummer.build-ghost.hub-registry-revision",
        "run.chummer.build-ghost.ui-kit-revision",
        "run.chummer.build-ghost.media-factory-revision",
    ):
        assert label in SCRIPT


def test_first_rollout_is_provider_disabled_loopback_only() -> None:
    for gate in (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED",
    ):
        assert f'.environment.{gate} == \"false\"' in SCRIPT
    for empty in (
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_HMAC_KEY",
        "CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_HREF",
        "CHUMMER_BUILD_GHOST_MEETING_BROKER_API_TOKEN",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_API_KEY",
    ):
        assert empty in SCRIPT
    assert '.host_ip == \"127.0.0.1\"' in SCRIPT
    assert "loopback-port-must-remain-8443" in SCRIPT
    assert 'has(\"build-ghost-cloudflare-access-edge\") | not' in SCRIPT
    assert "COMPOSE_PROFILES=" in SCRIPT


def test_first_rollout_preserves_and_restores_without_deletion() -> None:
    assert "first-rollout-rollback-$nonce" in SCRIPT
    assert 'docker image tag "$presentation_rollback_ref" "$presentation_image"' in SCRIPT
    assert 'docker image tag "$ai_rollback_ref" "$ai_image"' in SCRIPT
    assert 'docker image tag "$edge_rollback_ref" "$edge_image"' in SCRIPT
    assert "--force-recreate" in SCRIPT
    assert "rollback-restored volumes=preserved" in SCRIPT
    assert "positive_canary=passed" in SCRIPT
    assert "rook=text-fallback" in SCRIPT
    for forbidden in (
        "docker compose down",
        "docker volume rm",
        "docker image rm",
        "docker system prune",
        "docker volume prune",
    ):
        assert forbidden not in SCRIPT


def test_external_store_key_validation_accepts_only_canonical_distinct_32_bytes() -> None:
    valid = run_sourced(
        """
CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHUMMER_AI_INTERNAL_API_TOKEN=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
validate_external_secrets_without_output
printf 'accepted\\n'
"""
    )
    assert valid.returncode == 0, valid.stderr
    assert valid.stdout == "accepted\n"

    invalid = run_sourced(
        """
CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
CHUMMER_AI_INTERNAL_API_TOKEN=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY=not-canonical
validate_external_secrets_without_output
"""
    )
    assert invalid.returncode != 0
    assert "live-support-session-store-key-invalid" in invalid.stderr
    assert "not-canonical" not in invalid.stdout + invalid.stderr


def test_control_values_reject_reduced_disk_safety_margin() -> None:
    result = run_sourced(
        """
minimum_free_gib=27
max_io_full_avg10=10
poll_seconds=10
build_timeout_seconds=3600
up_timeout_seconds=900
validate_control_values
"""
    )
    assert result.returncode != 0
    assert "minimum-free-space-must-be-at-least-twenty-eight-gib" in result.stderr
