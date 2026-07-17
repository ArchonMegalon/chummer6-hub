from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from scripts.validate_install_linking_cutover_overlay_binding import (
    BUILD_INFO_RELATIVE_PATH,
    OverlayBindingError,
    _json_object,
    validate_binding,
)
from scripts.publish_public_edge_portal_overlay import (
    ensure_required_compose_mountpoints,
    full_deployment_digest,
    normalize_payload_modes,
    staged_payload_fingerprint,
    validate_payload_modes,
)


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
SHA = "a" * 64


def source_fingerprint_envelope(aggregate_sha256: str = SHA) -> dict[str, object]:
    return {
        "aggregateSha256": aggregate_sha256,
        "files": {},
        "buildInputs": {
            "algorithm": "sha256-canonical-path-content-size-v1",
            "aggregateSha256": "b" * 64,
            "fileCount": 1,
        },
        "overlayPayloadInputs": {
            "algorithm": "sha256-canonical-path-content-size-v1",
            "aggregateSha256": "c" * 64,
            "fileCount": 2,
        },
    }


def fixture_payloads(source_root: Path, active_root: Path):
    source_fingerprint = source_fingerprint_envelope()
    (active_root / "Chummer.Run.Api.dll").write_bytes(b"portal payload\n")
    (active_root / "state").mkdir()
    ensure_required_compose_mountpoints(active_root)
    normalize_payload_modes(active_root)
    staged_payload = staged_payload_fingerprint(active_root)
    deployment_digest = full_deployment_digest(
        source_fingerprint,
        staged_payload,
    )
    build_info = {
        "contractName": "chummer.public_edge_portal_overlay_publish.v1",
        "status": "pass",
        "activationStatus": "activated",
        "sourceRoot": str(source_root.resolve()),
        "sourceFingerprint": source_fingerprint,
        "stagedPayloadFingerprint": staged_payload,
        "payloadModeReceipt": validate_payload_modes(active_root),
        "fullDeploymentDigest": deployment_digest,
    }
    preflight = {
        "contractName": "chummer.public_edge_deploy_preflight.v1",
        "status": "pass",
        "generatedAtUtc": NOW.isoformat(),
        "sourceRoot": str(source_root.resolve()),
        "overlayRoot": str(active_root.resolve()),
        "overlayBuildInfoSourceFingerprint": {
            "path": str((active_root / BUILD_INFO_RELATIVE_PATH).resolve()),
            "recordedAggregateSha256": SHA,
            "expectedAggregateSha256": SHA,
            "recordedFullDeploymentDigestSha256": deployment_digest["sha256"],
            "expectedFullDeploymentDigestSha256": deployment_digest["sha256"],
            "fullDeploymentDigestMatchesRecordedInputs": True,
            "fullDeploymentDigestMatchesCurrentDeployment": True,
            "payloadModeBinding": {"status": "pass"},
            "aggregateMatchesCurrentSource": True,
            "sourceRootMatches": True,
            "missingKeys": [],
            "mismatchedKeys": [],
            "semanticMismatches": [],
        },
    }
    return preflight, build_info


def validate_fixture(
    tmp_path: Path,
    *,
    mutate_preflight=None,
    mutate_build_info=None,
    mutate_active=None,
    container_bytes: bytes | None = None,
    current_sha: str = SHA,
) -> None:
    source_root = tmp_path / "source"
    active_root = tmp_path / "active" / "app"
    source_root.mkdir(parents=True)
    active_root.mkdir(parents=True)
    preflight, build_info = fixture_payloads(source_root, active_root)
    if mutate_preflight is not None:
        mutate_preflight(preflight)
    if mutate_build_info is not None:
        mutate_build_info(build_info)
    if mutate_active is not None:
        mutate_active(active_root)
    build_info_bytes = json.dumps(build_info, sort_keys=True).encode()
    validate_binding(
        preflight=preflight,
        active_build_info_bytes=build_info_bytes,
        container_build_info_bytes=(
            build_info_bytes if container_bytes is None else container_bytes
        ),
        source_root=source_root,
        active_root=active_root,
        not_before_utc=NOW - timedelta(seconds=1),
        fingerprint_provider=lambda _: source_fingerprint_envelope(current_sha),
    )


def test_accepts_exact_source_overlay_and_container_binding(tmp_path: Path) -> None:
    validate_fixture(tmp_path)


@pytest.mark.parametrize(
    "payload",
    (
        b'{"status":"fail","status":"pass"}',
        b'{"status":"pass","unrelated":NaN}',
    ),
)
def test_rejects_ambiguous_binding_json(payload: bytes) -> None:
    with pytest.raises(OverlayBindingError):
        _json_object(payload, "binding fixture")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda preflight: preflight.update(status="fail"),
        lambda preflight: preflight.update(overlayRoot="/different/overlay"),
        lambda preflight: preflight["overlayBuildInfoSourceFingerprint"].update(
            aggregateMatchesCurrentSource=False
        ),
        lambda preflight: preflight["overlayBuildInfoSourceFingerprint"].update(
            fullDeploymentDigestMatchesCurrentDeployment=False
        ),
        lambda preflight: preflight.update(generatedAtUtc="2000-01-01T00:00:00+00:00"),
    ],
)
def test_rejects_unbound_or_stale_preflight(tmp_path: Path, mutation) -> None:
    with pytest.raises(OverlayBindingError):
        validate_fixture(tmp_path, mutate_preflight=mutation)


def test_rejects_container_build_info_mismatch(tmp_path: Path) -> None:
    with pytest.raises(OverlayBindingError, match="container build-info"):
        validate_fixture(tmp_path, container_bytes=b"{}")


def test_rejects_source_mutation_after_preflight(tmp_path: Path) -> None:
    with pytest.raises(OverlayBindingError, match="current source"):
        validate_fixture(tmp_path, current_sha="b" * 64)


def test_rejects_active_payload_mutation_after_preflight(tmp_path: Path) -> None:
    with pytest.raises(OverlayBindingError, match="current source"):
        validate_fixture(
            tmp_path,
            mutate_active=lambda active_root: (
                active_root / "unrecorded-after-preflight.dll"
            ).write_bytes(b"tampered payload\n"),
        )


def test_rejects_active_payload_mode_escalation_after_preflight(tmp_path: Path) -> None:
    with pytest.raises(OverlayBindingError, match="payload shape, and modes"):
        validate_fixture(
            tmp_path,
            mutate_active=lambda active_root: (
                active_root / "Chummer.Run.Api.dll"
            ).chmod(0o4755),
        )


def test_rejects_same_byte_external_symlink_substitution(tmp_path: Path) -> None:
    external = tmp_path / "external.dll"
    external.write_bytes(b"portal payload\n")

    def substitute(active_root: Path) -> None:
        payload = active_root / "Chummer.Run.Api.dll"
        payload.unlink()
        payload.symlink_to(external)

    with pytest.raises(OverlayBindingError, match="payload shape, and modes"):
        validate_fixture(tmp_path, mutate_active=substitute)


def test_rejects_self_asserted_full_deployment_digest(tmp_path: Path) -> None:
    with pytest.raises(OverlayBindingError, match="current source"):
        validate_fixture(
            tmp_path,
            mutate_build_info=lambda build_info: build_info[
                "fullDeploymentDigest"
            ].update(sha256="e" * 64),
        )
