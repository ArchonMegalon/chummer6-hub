from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUB_CLOSEOUT = ROOT / "scripts" / "ai" / "hub_closeout.sh"


def test_hub_closeout_declares_both_oci_subjects_before_the_authoritative_build() -> None:
    script = HUB_CLOSEOUT.read_text(encoding="utf-8")

    identity_begin = script.index(
        'begin_oci_build_provenance "$identity_provenance_invocation_id" '
        '"run-services-identity" "Chummer.Run.Identity/Chummer.Run.Identity.csproj" '
        '"run-services-identity" "chummer-run-identity:local"'
    )
    api_begin = script.index(
        'begin_oci_build_provenance "$api_provenance_invocation_id" '
        '"run-services-api" "Chummer.Run.Api/Chummer.Run.Api.csproj" '
        '"run-services-api" "chummer-run-api:local"'
    )
    build = script.index(
        '"$BUILD_PROVENANCE_DOCKER_BINARY" compose "${compose_args[@]}" up -d --build --remove-orphans '
        '"${public_edge_services[@]}"'
    )
    identity_finalize = script.index(
        'finalize_oci_build_provenance "$identity_provenance_invocation_id"'
    )
    api_finalize = script.index(
        'finalize_oci_build_provenance "$api_provenance_invocation_id"'
    )

    assert identity_begin < build
    assert api_begin < build
    assert build < identity_finalize
    assert build < api_finalize
    assert (
        'identity_provenance_invocation_id="run-services-identity-$provenance_run_id"'
        in script
    )
    assert 'api_provenance_invocation_id="run-services-api-$provenance_run_id"' in script


def test_hub_closeout_oci_provenance_is_image_bound_and_fail_closed() -> None:
    script = HUB_CLOSEOUT.read_text(encoding="utf-8")

    assert '--artifact-kind "oci_image"' in script
    assert '--artifact-image "$image_name"' in script
    assert '--docker-binary "$docker_binary"' in script
    assert '--source-repository "chummer.run-services"' in script
    assert '--source-repo-root "$ROOT_DIR"' in script
    for repository in (
        "chummer-presentation",
        "chummer-core-engine",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    ):
        assert f'--source-material "{repository}=' in script
    assert '--build-input "compose_file=$HUB_EDGE_COMPOSE_PATH"' in script
    assert '--build-input "dockerfile=$dockerfile_path"' in script
    assert 'dotnet restore Chummer.Run.Api/Chummer.Run.Api.csproj --nologo' in script
    assert 'dotnet restore Chummer.Run.Identity/Chummer.Run.Identity.csproj --nologo' in script
    assert 'BUILD_PROVENANCE_DOCKER_BINARY" != /*' in script
    assert (
        '"$BUILD_PROVENANCE_DOCKER_BINARY" compose "${compose_args[@]}" up -d --build'
        in script
    )


def test_hub_closeout_can_force_fresh_oci_subjects_without_rebuilding_on_deploy() -> None:
    script = HUB_CLOSEOUT.read_text(encoding="utf-8")

    identity_begin = script.index(
        'begin_oci_build_provenance "$identity_provenance_invocation_id"'
    )
    api_begin = script.index(
        'begin_oci_build_provenance "$api_provenance_invocation_id"'
    )
    no_cache_build = script.index(
        'compose "${compose_args[@]}" build --no-cache "${public_edge_services[@]}"'
    )
    no_build_deploy = script.index(
        'compose "${compose_args[@]}" up -d --no-build --remove-orphans '
        '"${public_edge_services[@]}"'
    )
    identity_finalize = script.index(
        'finalize_oci_build_provenance "$identity_provenance_invocation_id"'
    )
    api_finalize = script.index(
        'finalize_oci_build_provenance "$api_provenance_invocation_id"'
    )

    assert 'HUB_CLOSEOUT_NO_CACHE="${HUB_CLOSEOUT_NO_CACHE:-0}"' in script
    assert identity_begin < no_cache_build
    assert api_begin < no_cache_build
    assert no_cache_build < no_build_deploy
    assert no_build_deploy < identity_finalize
    assert no_build_deploy < api_finalize


def test_hub_closeout_provenance_only_mode_is_explicit_and_requires_a_build() -> None:
    script = HUB_CLOSEOUT.read_text(encoding="utf-8")

    api_finalize = script.index(
        'finalize_oci_build_provenance "$api_provenance_invocation_id"'
    )
    verify_switch = script.index(
        'if [[ "$HUB_CLOSEOUT_POST_BUILD_VERIFY" == "0"'
    )
    solution_build = script.index("dotnet build Chummer.Run.sln --nologo")

    assert (
        'HUB_CLOSEOUT_POST_BUILD_VERIFY="${HUB_CLOSEOUT_POST_BUILD_VERIFY:-1}"'
        in script
    )
    assert "Post-build verification can be skipped only after this invocation builds" in script
    assert (
        "hub OCI provenance build passed; post-build verification deliberately skipped"
        in script
    )
    assert api_finalize < verify_switch < solution_build
