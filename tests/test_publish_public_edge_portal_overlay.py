from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "publish_public_edge_portal_overlay.py"


def load_module():
    spec = importlib.util.spec_from_file_location("publish_public_edge_portal_overlay", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.real_probe_overlay_readiness = module.probe_overlay_readiness
    module.probe_overlay_readiness = lambda base_url, timeout_seconds: passing_overlay_readiness()
    return module


def make_completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def make_source_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root.parent / ".dockerignore").write_text(
        "**/bin/**\n**/obj/**\n",
        encoding="utf-8",
    )
    (root / ".dockerignore").write_text("**/bin/**\n**/obj/**\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps(
            {
                "private": True,
                "devDependencies": {"playwright": "^1.53.0"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "fixture",
                "lockfileVersion": 3,
                "packages": {
                    "": {"devDependencies": {"playwright": "^1.53.0"}},
                    "node_modules/playwright": {"version": "1.60.0"},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "playwright.config.ts").write_text(
        "export default { testDir: './tests/public' };\n",
        encoding="utf-8",
    )
    (root / "tests" / "public").mkdir(parents=True, exist_ok=True)
    for proof_name in (
        "ux-artifacts.ts",
        "frontdoor-mobile-launch.spec.ts",
        "black-ledger-frontdoor.spec.ts",
    ):
        (root / "tests" / "public" / proof_name).write_text(
            f"// sealed fixture: {proof_name}\n",
            encoding="utf-8",
        )
    (root / "docker-compose.public-edge.yml").write_text(
        "services:\n  chummer-portal:\n    image: chummer-run-api:local\n",
        encoding="utf-8",
    )
    (root / "Chummer.InstallLinking.Postgres.Tool").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.InstallLinking.Postgres.Tool" / "Chummer.InstallLinking.Postgres.Tool.csproj").write_text(
        "<Project />\n",
        encoding="utf-8",
    )
    (root / "Chummer.InstallLinking.Postgres.Tool" / "Program.cs").write_text(
        "operator tool\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "generate_public_play_worker_projection.py",
        "public_edge_payload_modes.py",
        "strict_json_contract.py",
        "validate_public_pwa_proof_authority.py",
        "verify_public_pwa_static_assets.py",
        "verify_public_edge_postdeploy_gate.py",
    ):
        (root / "scripts" / script_name).write_text(
            f"# {script_name}\n",
            encoding="utf-8",
        )
    (root / "Chummer.Run.Api").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj").write_text("<Project />\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Controllers").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "Controllers" / "AuthController.cs").write_text("auth controller\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Controllers" / "BrilliantDirectoriesBillingController.cs").write_text(
        "billing auth controller\n",
        encoding="utf-8",
    )
    (root / "Chummer.Run.Api" / "Views" / "Auth").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "Views" / "Auth" / "Entry.cshtml").write_text("auth entry\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Views" / "Billing").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "Views" / "Billing" / "Membership.cshtml").write_text(
        "billing membership\n",
        encoding="utf-8",
    )
    (root / "Chummer.Run.Api" / "Views" / "PublicLanding").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml").write_text("landing\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Downloads.cshtml").write_text("downloads\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml").write_text("status\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Services").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "Services" / "HubEmailSignInPolicy.cs").write_text("auth policy\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Services" / "ReadyForTonightService.cs").write_text("ready\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "Program.cs").write_text("program\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "ViewModels").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "ViewModels" / "SiteViewModels.cs").write_text("site view models\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "wwwroot").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "wwwroot" / "pwa-icon.svg").write_text("<svg />\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "wwwroot" / "site.webmanifest").write_text("{}\n", encoding="utf-8")
    (root / "Chummer.Run.Api" / "wwwroot" / "media" / "product").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api" / "wwwroot" / "media" / "product" / "proof-builder-trail.png").write_text(
        "png\n",
        encoding="utf-8",
    )
    (root / ".codex-design").mkdir(parents=True, exist_ok=True)
    (root / ".codex-design" / "marker.txt").write_text("design\n", encoding="utf-8")


def write_staged_build_info(
    module,
    staging_root: Path,
    source_root: Path,
    *,
    source_fingerprint: dict[str, object] | None = None,
) -> Path:
    (staging_root / "state").mkdir(exist_ok=True)
    module.ensure_required_compose_mountpoints(staging_root)
    build_info_path = staging_root / module.OVERLAY_BUILD_INFO_RELATIVE_PATH
    build_info_path.parent.mkdir(parents=True, exist_ok=True)
    build_info_path.write_text("{}\n", encoding="utf-8")
    built_source_fingerprint = (
        source_fingerprint
        if source_fingerprint is not None
        else module.source_fingerprint(source_root)
    )
    frontdoor_playwright_proof_closure = (
        module.materialize_frontdoor_playwright_proof_closure(
            source_root,
            staging_root,
        )
    )
    module.normalize_payload_modes(staging_root)
    built_staged_payload_fingerprint = module.staged_payload_fingerprint(staging_root)
    payload_mode_receipt = module.validate_payload_modes(staging_root)
    build_info_path.write_text(
        json.dumps(
            {
                "sourceFingerprint": built_source_fingerprint,
                "frontdoorPlaywrightProofClosure": (
                    frontdoor_playwright_proof_closure
                ),
                "stagedPayloadFingerprint": built_staged_payload_fingerprint,
                "payloadModeReceipt": payload_mode_receipt,
                "fullDeploymentDigest": module.full_deployment_digest(
                    built_source_fingerprint,
                    built_staged_payload_fingerprint,
                ),
            }
        ),
        encoding="utf-8",
    )
    return build_info_path


def test_full_deployment_digest_binds_source_closure_and_staged_payload() -> None:
    module = load_module()
    source_fingerprint = {
        "aggregateSha256": "a" * 64,
        "files": {},
        "buildInputs": {
            "algorithm": module.SOURCE_FINGERPRINT_ALGORITHM,
            "aggregateSha256": "b" * 64,
            "fileCount": 1,
        },
        "overlayPayloadInputs": {
            "algorithm": module.SOURCE_FINGERPRINT_ALGORITHM,
            "aggregateSha256": "c" * 64,
            "fileCount": 2,
        },
    }
    staged_payload = {
        "algorithm": module.SOURCE_FINGERPRINT_ALGORITHM,
        "aggregateSha256": "d" * 64,
        "fileCount": 3,
    }
    baseline = module.full_deployment_digest(source_fingerprint, staged_payload)
    reordered = module.full_deployment_digest(
        dict(reversed(list(source_fingerprint.items()))),
        dict(reversed(list(staged_payload.items()))),
    )
    source_drift = json.loads(json.dumps(source_fingerprint))
    source_drift["buildInputs"]["aggregateSha256"] = "e" * 64
    payload_drift = dict(staged_payload)
    payload_drift["aggregateSha256"] = "f" * 64

    assert baseline == reordered
    assert baseline["contractName"] == module.FULL_DEPLOYMENT_DIGEST_CONTRACT_NAME
    assert baseline["algorithm"] == module.FULL_DEPLOYMENT_DIGEST_ALGORITHM
    assert baseline["sha256"] != module.full_deployment_digest(
        source_drift,
        staged_payload,
    )["sha256"]
    assert baseline["sha256"] != module.full_deployment_digest(
        source_fingerprint,
        payload_drift,
    )["sha256"]


def test_full_deployment_digest_matches_runtime_unicode_and_astral_vector() -> None:
    module = load_module()
    source_fingerprint = {
        "aggregateSha256": "0123456789abcdef" * 4,
        "files": {
            "é\n": {"value": "snowman ☃ and / < > & \x7f"},
            "\U00010000": "astral",
            "\uE000": "bmp",
        },
        "buildInputs": {
            "algorithm": module.SOURCE_FINGERPRINT_ALGORITHM,
            "aggregateSha256": "1" * 64,
            "fileCount": 1,
        },
        "overlayPayloadInputs": {
            "algorithm": module.SOURCE_FINGERPRINT_ALGORITHM,
            "aggregateSha256": "2" * 64,
            "fileCount": 2,
        },
    }
    staged_payload = {
        "algorithm": module.STAGED_PAYLOAD_FINGERPRINT_ALGORITHM,
        "aggregateSha256": (
            "a2bded2b38854bb46591aa4a17210de8ecf91180f73fe3f21d7fa1a5f08159cd"
        ),
        "fileCount": 1,
        "excludedRelativePaths": [
            "wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        ],
    }

    assert module.full_deployment_digest(source_fingerprint, staged_payload)["sha256"] == (
        "81393cbb2442ef5f5bf8711f687b01035aded29376a210790e28a405a1b854ec"
    )


def test_staged_payload_fingerprint_prunes_private_state_contents(tmp_path: Path) -> None:
    module = load_module()
    root = tmp_path / "overlay"
    state = root / "state"
    state.mkdir(parents=True)
    payload = root / "Chummer.Run.Api.dll"
    payload.write_bytes(b"assembly")
    mounted_proof = root / module.REQUIRED_COMPOSE_MOUNTPOINTS[0]
    mounted_proof.parent.mkdir(parents=True)
    mounted_proof.write_bytes(b"runtime proof version one")
    private_target = state / "private-target"
    private_target.write_bytes(b"secret")
    (state / "private-link").symlink_to(private_target)
    module.normalize_payload_modes(root)

    rows = module.staged_payload_rows(root)
    fingerprint = module.staged_payload_fingerprint(root)
    mounted_proof.write_bytes(b"runtime proof version two")
    module.normalize_payload_modes(root)
    after_runtime_proof_refresh = module.staged_payload_fingerprint(root)

    assert [row["path"] for row in rows] == ["Chummer.Run.Api.dll"]
    assert fingerprint["algorithm"] == module.STAGED_PAYLOAD_FINGERPRINT_ALGORITHM
    assert fingerprint["fileCount"] == 1
    assert fingerprint["excludedRelativePaths"] == (
        module.staged_payload_runtime_mount_exclusions()
    )
    assert after_runtime_proof_refresh == fingerprint


def test_staged_payload_fingerprint_requires_declared_runtime_mountpoint_files(
    tmp_path: Path,
) -> None:
    module = load_module()
    root = tmp_path / "overlay"
    root.mkdir()
    (root / "state").mkdir()
    (root / "Chummer.Run.Api.dll").write_bytes(b"assembly")
    module.normalize_payload_modes(root)

    with pytest.raises(
        module.PayloadModePolicyError,
        match="must contain every declared runtime-mounted file exclusion",
    ):
        module.staged_payload_fingerprint(root)


def test_v3_runtime_mount_exclusions_exactly_match_nested_read_only_app_binds() -> None:
    module = load_module()
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")
    )
    volumes = compose["services"]["chummer-portal"]["volumes"]

    parsed_mounts: list[tuple[str, str, str]] = []
    for volume in volumes:
        assert isinstance(volume, str), "portal volume contracts must use auditable short syntax"
        parts = volume.rsplit(":", 2)
        if len(parts) == 3 and parts[-1] in {"ro", "rw"}:
            source, target, access = parts
        else:
            source, target = volume.rsplit(":", 1)
            access = "rw"
        parsed_mounts.append((source, target, access))

    root_overlay_mounts = [mount for mount in parsed_mounts if mount[1] == "/app"]
    state_mounts = [mount for mount in parsed_mounts if mount[1] == "/app/state"]
    nested_read_only_app_paths = {
        target.removeprefix("/app/")
        for _source, target, access in parsed_mounts
        if target.startswith("/app/") and access == "ro"
    }
    exclusions = module.staged_payload_runtime_mount_exclusions()

    assert len(root_overlay_mounts) == 1
    assert root_overlay_mounts[0][2] == "ro"
    assert len(state_mounts) == 1
    assert state_mounts[0][2] == "rw"
    assert set(exclusions) == nested_read_only_app_paths
    assert exclusions == sorted(exclusions)
    assert "." not in exclusions
    assert "state" not in exclusions


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink"])
def test_staged_payload_fingerprint_rejects_aliasing_files(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    module = load_module()
    root = tmp_path / "overlay"
    root.mkdir()
    external = tmp_path / "external.dll"
    external.write_bytes(b"same bytes")
    candidate = root / "Chummer.Run.Api.dll"
    if unsafe_kind == "symlink":
        candidate.symlink_to(external)
    else:
        candidate.hardlink_to(external)

    with pytest.raises(RuntimeError, match="symlink|hardlink"):
        module.staged_payload_fingerprint(root)


def test_staged_payload_rows_bind_modes_and_policy_rejects_mode_drift(
    tmp_path: Path,
) -> None:
    module = load_module()
    root = tmp_path / "overlay"
    root.mkdir()
    (root / "state").mkdir()
    payload = root / "Chummer.Run.Api.dll"
    payload.write_bytes(b"assembly")
    module.normalize_payload_modes(root)
    baseline_rows = module.staged_payload_rows(root)

    payload.chmod(0o755)
    drifted_rows = module.staged_payload_rows(root)

    assert baseline_rows[0]["mode"] == "0644"
    assert drifted_rows[0]["mode"] == "0755"
    with pytest.raises(module.PayloadModePolicyError):
        module.staged_payload_fingerprint(root)


def test_stable_fingerprint_reader_rejects_path_replacement_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    candidate = tmp_path / "payload.bin"
    candidate.write_bytes(b"recorded bytes")
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"recorded bytes")
    retired = tmp_path / "retired.bin"
    real_read = module.os.read
    swapped = False

    def swapping_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        chunk = real_read(descriptor, count)
        if chunk and not swapped:
            candidate.rename(retired)
            replacement.rename(candidate)
            swapped = True
        return chunk

    monkeypatch.setattr(module.os, "read", swapping_read)

    with pytest.raises(
        RuntimeError,
        match="changed while it was read|pathname no longer identifies",
    ):
        module._read_stable_fingerprint_file(candidate)


def passing_browser_redirect() -> dict[str, object]:
    return {
        "status": "pass",
        "reason": "",
        "entryUrl": (
            "http://127.0.0.1:5000/"
            "?sessionId=synthetic-probe&grant=synthetic-probe"
            "&tracking=synthetic-probe#turn-runsite-card?grant=synthetic-fragment"
        ),
        "finalUrl": "http://127.0.0.1:5000/mobile/player#turn-runsite-card",
        "expectedPath": "/mobile/player",
        "expectedHash": "#turn-runsite-card",
        "expectedQuery": "",
        "finalQuery": "",
        "pathMatches": True,
        "hashMatches": True,
        "queryDropped": True,
        "error": "",
        "title": "Player entry · Chummer",
        "heading": "Player entry",
    }


def passing_landing_body(module) -> str:  # noqa: ANN001
    return "\n".join(module.REQUIRED_LANDING_MARKERS.values())


def passing_live_surface_parity(
    program_binding: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "pass",
        "receiptPath": "/tmp/LIVE_SURFACE_PARITY.local-overlay.generated.json",
        "failureCount": 0,
        "failures": [],
        "verdict": "LIVE_SURFACE_PARITY_READY",
    }
    if program_binding is not None:
        payload.update(
            {
                "programBinding": program_binding,
                "programBindingMatches": True,
                "programSnapshotImported": str(program_binding["snapshotPath"]),
            }
        )
    return payload


def passing_overlay_readiness() -> dict[str, object]:
    return {
        "status": "pass",
        "httpStatus": 200,
        "bodyReady": True,
        "bodyStatus": "ready",
        "checks": {
            "http200": True,
            "bodyReady": True,
            "bodyStatus": True,
            "hubObject": True,
            "hubReady": True,
            "hubStatus": True,
            "projectionObject": True,
            "projectionDisabled": True,
            "projectionReady": True,
            "projectionStatus": True,
            "combinedConsistent": True,
            "jsonObject": True,
            "transport": True,
        },
        "hub": {"ready": True, "status": "pass"},
        "playProjection": {"enabled": False, "ready": True, "status": "disabled"},
        "transportError": "",
        "jsonError": "",
    }


def passing_overlay_verification(receipt_path: Path) -> dict[str, object]:
    receipt_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
    return {
        "status": "pass",
        "reason": "",
        "baseUrl": "http://127.0.0.1:5002",
        "receiptPath": str(receipt_path),
        "exitCode": 0,
        "receiptStatus": "pass",
        "probeError": "",
        "landingMarkerStatus": "pass",
        "landingMarkerChecks": {
            "playDisabledTarget": True,
            "playSignInRoute": True,
            "turnAnchor": True,
            "turnAnchorNormalizedHash": True,
            "turnAnchorRedirect": True,
        },
        "landingMissingMarkers": [],
        "landingBrowserRedirect": passing_browser_redirect(),
    }


def write_release_channel_receipt(root: Path) -> tuple[Path, str]:
    path = root / "selected-release-channel.json"
    payload = {
        "contractName": "Chummer.Hub.Registry.Contracts",
        "status": "published",
        "version": "run-20260713-123603",
        "publishedAt": "2026-07-13T12:38:14Z",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
        "publicTrustMetrics": {
            "releaseChannel": {
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            },
            "proofFreshness": {"status": "stale"},
        },
        "registryBoundaryCoverage": {
            "releaseChannel": {
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            },
        },
    }
    raw_bytes = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw_bytes)
    return path, hashlib.sha256(raw_bytes).hexdigest()


def child_binding_fields(receipt_path: Path, sha256: str) -> dict[str, object]:
    return {
        "release_channel_receipt": str(receipt_path),
        "release_channel_receipt_sha256_expected": sha256,
        "release_channel_receipt_sha256_actual": sha256,
        "release_channel_receipt_sha256_matches": True,
        "release_channel_receipt_binding_status": "pass",
        "release_channel_version": "run-20260713-123603",
        "release_channel_published_at": "2026-07-13T12:38:14Z",
    }


def write_child_verification_receipt(
    path: Path,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    invocation_id: str,
    **overrides: object,
) -> None:
    payload: dict[str, object] = {
        "status": "pass",
        "contractName": "chummer.downloads_version_marker.bound.v1",
        "invocation_id": invocation_id,
        "downloads_has_marker": True,
        "status_redirect_has_marker": True,
        "downloads_version_marker_matches_release_channel": True,
        "status_redirect_version_marker_matches_release_channel": True,
        "status_redirect_heading_matches_release_channel": True,
        "status_redirect_heading_recognized": True,
        "status_redirect_heading_uses_generic_updated_copy": False,
        "visible_version_matches_release_channel": True,
        "public_release_manifest_exists": True,
        "public_release_channel_matches_release_channel": True,
        "public_release_status_matches_release_channel": True,
        "public_release_version_matches_release_channel": True,
        "public_release_published_at_matches_release_channel": True,
        "public_release_proof_freshness_matches_release_channel": True,
        "public_release_supportability_matches_release_channel": True,
        "public_release_rollout_matches_release_channel": True,
        "public_release_copy_safe": True,
        "release_manifest_channel_matches_release_channel": True,
        "release_manifest_status_matches_release_channel": True,
        "release_manifest_version_matches_release_channel": True,
        "release_manifest_published_at_matches_release_channel": True,
        "release_manifest_proof_freshness_matches_release_channel": True,
        "release_manifest_supportability_compatible_with_release_channel": True,
        "release_manifest_rollout_compatible_with_release_channel": True,
        "release_manifest_internal_supportability_consistent": True,
        "release_manifest_copy_safe": True,
        "downloads_status": 200,
        "status_status": 200,
        "release_manifest_http_status": 200,
        **child_binding_fields(release_channel_receipt, release_channel_receipt_sha256),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def materialize_with_binding(module, output: Path, *, binding_root: Path, **kwargs):
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(
        binding_root
    )
    original_verify = kwargs.get("verify_overlay_fn")
    if original_verify is not None:
        def bound_verify(
            staging,
            *,
            source_root,
            verify_timeout_seconds,
            verification_deadline_seconds,
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            verification_programs,
        ):
            result = original_verify(
                staging,
                source_root=source_root,
                verify_timeout_seconds=verify_timeout_seconds,
                verification_receipt_path=verification_receipt_path,
            )
            result.update(
                {
                    "receiptBindingMatchesSelectedInput": True,
                    "receiptInvocationMatchesCurrent": True,
                    "receiptProcessResultConsistent": True,
                    "releaseChannelReceiptPath": str(release_channel_receipt),
                    "releaseChannelReceiptSnapshotPath": str(release_channel_receipt),
                    "releaseChannelReceiptSha256Expected": release_channel_receipt_sha256,
                    "releaseChannelReceiptSha256Actual": release_channel_receipt_sha256,
                    "releaseChannelReceiptSha256Matches": True,
                    "releaseChannelVersion": "run-20260713-123603",
                    "releaseChannelPublishedAt": "2026-07-13T12:38:14Z",
                    "releaseManifestConservativeReviewFloorApplied": True,
                    "releaseManifestSupportabilityExact": False,
                    "releaseManifestSupportabilityCompatible": True,
                    "releaseManifestRolloutExact": False,
                    "releaseManifestRolloutCompatible": True,
                    "verificationPrograms": verification_programs,
                    "verificationProgramsMatch": True,
                    "receiptProgramBindingsMatch": True,
                }
            )
            return result

        kwargs["verify_overlay_fn"] = bound_verify
    return module.materialize(
        output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        **kwargs,
    )


def test_overlay_publish_lock_rejects_competing_publisher(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import importlib.util, sys, time\n"
                "from pathlib import Path\n"
                f"script = Path({str(SCRIPT)!r})\n"
                "spec = importlib.util.spec_from_file_location('publish_public_edge_portal_overlay_holder', script)\n"
                "module = importlib.util.module_from_spec(spec)\n"
                "sys.modules[spec.name] = module\n"
                "spec.loader.exec_module(module)\n"
                "source_root = Path(sys.argv[1])\n"
                "with module.overlay_publish_lock(source_root):\n"
                "    print('locked', flush=True)\n"
                "    time.sleep(10)\n"
            ),
            str(source_root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(RuntimeError, match="another public-edge overlay publisher already owns"):
            with module.overlay_publish_lock(source_root):
                pass
    finally:
        holder.terminate()
        holder.communicate(timeout=10)


def test_direct_activation_owns_shared_mutation_lock_and_cleans_it(tmp_path: Path) -> None:
    module = load_module()
    lock_path = tmp_path / ".state" / "public-edge-mutation.lock"
    module.PUBLIC_EDGE_MUTATION_LOCK = lock_path

    with module.public_edge_mutation_lock(activate=True) as acquired:
        assert acquired == lock_path
        token_path = lock_path / module.PUBLIC_EDGE_MUTATION_LOCK_TOKEN_FILE
        assert token_path.is_file()
        assert token_path.stat().st_mode & 0o777 == 0o600
        assert lock_path.stat().st_mode & 0o777 == 0o700
        with pytest.raises(
            module.PublicEdgeMutationLockUnavailable,
            match="another public-edge mutation",
        ):
            with module.public_edge_mutation_lock(activate=True):
                pass

    assert not lock_path.exists()


def test_inherited_shared_mutation_lock_requires_exact_safe_owner_token(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock_path = tmp_path / ".state" / "public-edge-mutation.lock"
    lock_path.parent.mkdir(mode=0o700)
    lock_path.mkdir(mode=0o700)
    token_path = lock_path / module.PUBLIC_EDGE_MUTATION_LOCK_TOKEN_FILE
    token = "a" * 64
    token_path.write_text(token + "\n", encoding="ascii")
    token_path.chmod(0o600)
    module.PUBLIC_EDGE_MUTATION_LOCK = lock_path

    with module.public_edge_mutation_lock(activate=True, inherited_token=token) as acquired:
        assert acquired == lock_path
    assert lock_path.is_dir()
    assert token_path.is_file()

    with pytest.raises(module.PublicEdgeMutationLockUnavailable, match="does not own"):
        with module.public_edge_mutation_lock(
            activate=True,
            inherited_token="b" * 64,
        ):
            pass
    token_path.chmod(0o644)
    with pytest.raises(module.PublicEdgeMutationLockUnavailable, match="unsafe identity"):
        with module.public_edge_mutation_lock(activate=True, inherited_token=token):
            pass


def test_shared_mutation_lock_rejects_unsafe_root_without_repairing_it(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock_root = tmp_path / ".state"
    lock_root.mkdir(mode=0o755)
    lock_root.chmod(0o755)
    module.PUBLIC_EDGE_MUTATION_LOCK = lock_root / "public-edge-mutation.lock"

    with pytest.raises(
        module.PublicEdgeMutationLockUnavailable,
        match="mode-0700",
    ):
        with module.public_edge_mutation_lock(activate=True):
            pass

    assert lock_root.stat().st_mode & 0o777 == 0o755
    assert not module.PUBLIC_EDGE_MUTATION_LOCK.exists()


def test_shared_mutation_lock_cleanup_never_unlinks_replaced_token_target(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock_path = tmp_path / ".state" / "public-edge-mutation.lock"
    module.PUBLIC_EDGE_MUTATION_LOCK = lock_path
    victim = tmp_path / "victim"
    victim.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(
        module.PublicEdgeMutationLockUnavailable,
        match="owner token changed identity",
    ):
        with module.public_edge_mutation_lock(activate=True):
            token_path = lock_path / module.PUBLIC_EDGE_MUTATION_LOCK_TOKEN_FILE
            token_path.unlink()
            token_path.symlink_to(victim)

    assert victim.read_text(encoding="utf-8") == "preserve\n"
    assert (lock_path / module.PUBLIC_EDGE_MUTATION_LOCK_TOKEN_FILE).is_symlink()


def test_main_persists_shared_mutation_lock_receipt_while_both_locks_are_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    output = tmp_path / "receipt.json"
    release_channel_receipt = tmp_path / "release.json"
    release_channel_receipt.write_text("{}\n", encoding="utf-8")
    args = publisher_args(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256="0" * 64,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=tmp_path / "active" / "app",
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
    )
    args.activate = True
    module.PUBLIC_EDGE_MUTATION_LOCK = tmp_path / ".state" / "public-edge-mutation.lock"
    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(
        module,
        "require_disk_capacity",
        lambda **_kwargs: {"status": "pass"},
    )
    monkeypatch.setattr(module, "invalidate_prior_publisher_outputs", lambda _plan: [])

    def fake_materialize(path: Path, **_kwargs):
        payload = {"contractName": module.CONTRACT_NAME, "status": "pass"}
        module.atomic_write_json(path, payload)
        return payload

    monkeypatch.setattr(module, "materialize", fake_materialize)

    assert module.main() == 0
    capsys.readouterr()

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["sharedMutationLock"] == {
        "required": True,
        "status": "held",
        "path": str(module.PUBLIC_EDGE_MUTATION_LOCK),
        "inherited": False,
        "acquiredBeforeOverlayPublishLock": True,
    }
    assert not module.PUBLIC_EDGE_MUTATION_LOCK.exists()


def publisher_args(
    *,
    output: Path,
    release_channel_receipt: Path,
    release_channel_receipt_sha256: str,
    source_root: Path,
    staging_root: Path,
    active_root: Path,
    backup_root: Path,
    build_root: Path,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        configuration="Release",
        verify_timeout_seconds=5.0,
        publish_timeout_seconds=30.0,
        activate=False,
        reuse_staging=False,
        skip_backup_on_activate=False,
        activation_mode="copy",
    )


def test_run_command_terminates_publish_process_group_at_timeout(tmp_path: Path) -> None:
    module = load_module()
    started_at = time.monotonic()

    result = module.run_command(
        ["/bin/sh", "-c", "printf 'started\\n'; sleep 30 & exit 0"],
        cwd=tmp_path,
        timeout_seconds=0.1,
    )

    assert time.monotonic() - started_at < 5.0
    assert result.returncode == module.PUBLISH_TIMEOUT_EXIT_CODE
    assert result.stdout == "started\n"
    assert "timed out after 0.1 seconds" in result.stderr
    assert "process group was terminated" in result.stderr


def test_run_command_preserves_normal_process_result(tmp_path: Path) -> None:
    module = load_module()

    result = module.run_command(
        [sys.executable, "-c", "import sys; print('ok'); print('note', file=sys.stderr)"],
        cwd=tmp_path,
        timeout_seconds=5.0,
    )

    assert result.returncode == 0
    assert result.stdout == "ok\n"
    assert result.stderr == "note\n"


def test_verify_published_overlay_enforces_global_deadline_and_writes_finite_timeout_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "staging" / "app"
    staging_root.mkdir(parents=True)
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(
        tmp_path
    )

    def blocking_verifier(*args, **kwargs):
        time.sleep(5.0)
        raise AssertionError("the hard verification deadline did not interrupt the verifier")

    monkeypatch.setattr(
        module,
        "_verify_published_overlay_with_budget",
        blocking_verifier,
    )
    started_at = time.monotonic()

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=1.0,
        verification_deadline_seconds=0.05,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert time.monotonic() - started_at < 2.0
    assert receipt["status"] == "fail"
    assert receipt["reason"] == "verification_deadline_exceeded"
    assert receipt["timedOut"] is True
    assert receipt["receiptPersisted"] is True
    assert receipt["verificationDeadline"]["deadlineSeconds"] == 0.05
    assert receipt["verificationDeadline"]["elapsedSeconds"] >= 0.05
    assert receipt["verificationDeadline"]["remainingSeconds"] == 0.0
    json.dumps(receipt, allow_nan=False)
    persisted = json.loads(verification_receipt_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "fail"
    assert persisted["reason"] == "verification_deadline_exceeded"
    assert persisted["goalCompletionClaimAllowed"] is False
    json.dumps(persisted, allow_nan=False)


@pytest.mark.parametrize(
    ("timeout_field", "timeout_value", "expected_label"),
    [
        ("publish_timeout_seconds", 0, "publish timeout"),
        ("publish_timeout_seconds", float("nan"), "publish timeout"),
        ("publish_timeout_seconds", float("inf"), "publish timeout"),
        (
            "publish_timeout_seconds",
            2.0 * 60.0 * 60.0 + 1.0,
            "publish timeout",
        ),
        ("verify_timeout_seconds", 0, "verification timeout"),
        ("verify_timeout_seconds", float("nan"), "verification timeout"),
        (
            "verify_timeout_seconds",
            10.0 * 60.0 + 1.0,
            "verification timeout",
        ),
        (
            "verification_deadline_seconds",
            float("nan"),
            "global verification deadline",
        ),
        (
            "verification_deadline_seconds",
            60.0 * 60.0 + 1.0,
            "global verification deadline",
        ),
        ("minimum_free_disk_bytes", -1, "minimum free disk bytes"),
        ("minimum_free_disk_bytes", float("inf"), "minimum free disk bytes"),
    ],
)
def test_materialize_rejects_unbounded_timeouts_before_mutation(
    tmp_path: Path,
    timeout_field: str,
    timeout_value: float,
    expected_label: str,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(
        tmp_path
    )
    staging_root = tmp_path / "staging" / "app"
    build_root = tmp_path / "build"
    staging_root.mkdir(parents=True)
    build_root.mkdir()
    (staging_root / "sentinel.txt").write_text("staging\n", encoding="utf-8")
    (build_root / "sentinel.txt").write_text("build\n", encoding="utf-8")
    output = tmp_path / "receipt.json"

    with pytest.raises(RuntimeError, match=expected_label):
        module.materialize(
            output,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=staging_root,
            active_root=tmp_path / "active" / "app",
            backup_root=tmp_path / "backups",
            build_root=build_root,
            **{timeout_field: timeout_value},
        )

    assert (staging_root / "sentinel.txt").read_text(encoding="utf-8") == "staging\n"
    assert (build_root / "sentinel.txt").read_text(encoding="utf-8") == "build\n"
    assert not output.exists()
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_materialize_rejects_low_disk_before_authority_or_staging_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(
        tmp_path
    )
    staging_root = tmp_path / "staging" / "app"
    build_root = tmp_path / "build"
    staging_root.mkdir(parents=True)
    build_root.mkdir()
    staging_sentinel = staging_root / "sentinel.txt"
    build_sentinel = build_root / "sentinel.txt"
    staging_sentinel.write_text("staging\n", encoding="utf-8")
    build_sentinel.write_text("build\n", encoding="utf-8")
    output = tmp_path / "receipt.json"
    output.write_text("prior receipt\n", encoding="utf-8")
    before_output = output.stat()
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: types.SimpleNamespace(total=4096, used=3584, free=512),
    )

    with pytest.raises(module.OverlayDiskCapacityError) as raised:
        module.materialize(
            output,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=staging_root,
            active_root=tmp_path / "active" / "app",
            backup_root=tmp_path / "backups",
            build_root=build_root,
            minimum_free_disk_bytes=1024,
        )

    assert raised.value.check["status"] == "fail"
    assert raised.value.check["minimumFreeBytes"] == 1024
    assert raised.value.check["filesystems"][0]["freeBytes"] == 512
    assert output.read_text(encoding="utf-8") == "prior receipt\n"
    after_output = output.stat()
    assert (
        after_output.st_dev,
        after_output.st_ino,
        after_output.st_size,
        after_output.st_mtime_ns,
    ) == (
        before_output.st_dev,
        before_output.st_ino,
        before_output.st_size,
        before_output.st_mtime_ns,
    )
    assert staging_sentinel.read_text(encoding="utf-8") == "staging\n"
    assert build_sentinel.read_text(encoding="utf-8") == "build\n"
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_materialize_records_explicit_low_disk_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: types.SimpleNamespace(total=4096, used=3584, free=512),
    )

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=tmp_path / "active" / "app",
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
        minimum_free_disk_bytes=1024,
        allow_low_disk_capacity=True,
        run_command_fn=lambda command, *, cwd: make_completed(
            stderr="publish intentionally skipped\n",
            returncode=1,
        ),
    )

    assert payload["status"] == "fail"
    assert payload["diskCapacityCheck"]["status"] == "overridden"
    assert payload["diskCapacityCheck"]["overrideRequested"] is True
    assert payload["diskCapacityCheck"]["failures"]
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["diskCapacityCheck"] == payload["diskCapacityCheck"]


def test_materialize_records_publish_timeout_as_fail_receipt(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    output = tmp_path / "receipt.json"

    def timed_out_publish(command, *, cwd):
        return subprocess.CompletedProcess(
            args=command,
            returncode=module.PUBLISH_TIMEOUT_EXIT_CODE,
            stdout="partial publish output\n",
            stderr="public-edge overlay publish timed out\n",
        )

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=tmp_path / "active" / "app",
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
        publish_timeout_seconds=17.0,
        run_command_fn=timed_out_publish,
    )

    assert payload["status"] == "fail"
    assert payload["publishTimeoutSeconds"] == 17.0
    assert payload["publish"]["exitCode"] == module.PUBLISH_TIMEOUT_EXIT_CODE
    assert payload["publish"]["timedOut"] is True
    assert payload["publish"]["timeoutSeconds"] == 17.0
    assert payload["verification"]["status"] == "skipped"
    assert payload["verification"]["reason"] == "publish_failed"
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["status"] == "fail"
    assert persisted["publish"]["timedOut"] is True


def test_main_lock_loser_does_not_clobber_shared_output_or_derived_receipts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    output = tmp_path / "receipt.json"
    output.write_text("operator-owned receipt\n", encoding="utf-8")
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    active_root = tmp_path / "active" / "app"
    args = publisher_args(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
    )
    monkeypatch.setattr(module, "parse_args", lambda: args)

    with module.overlay_publish_lock(source_root, active_root):
        before = output.stat()
        assert module.main() == 1
        after = output.stat()

    capsys.readouterr()
    assert output.read_text(encoding="utf-8") == "operator-owned receipt\n"
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    assert not (tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json").exists()
    assert not (tmp_path / "LIVE_SURFACE_PARITY.local-overlay.generated.json").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()
    assert not (tmp_path / ".release-channel-authority").exists()


def test_main_rejects_output_inside_active_without_writing_failure_receipt(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    active_root = tmp_path / "active" / "app"
    active_root.mkdir(parents=True)
    output = active_root / "receipt.json"
    output.write_text("active sentinel\n", encoding="utf-8")
    before = output.stat()
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    args = publisher_args(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
    )
    monkeypatch.setattr(module, "parse_args", lambda: args)

    assert module.main() == 1
    capsys.readouterr()
    after = output.stat()
    assert output.read_text(encoding="utf-8") == "active sentinel\n"
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    assert not module.publish_lock_path(source_root, active_root).exists()
    assert not (active_root / ".release-channel-authority").exists()


def test_main_owned_failure_invalidates_prior_pass_output_while_lock_is_held(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    output = tmp_path / "receipt.json"
    output.write_text('{"status":"pass","stale":true}\n', encoding="utf-8")
    stale_derived = [
        tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json",
        tmp_path / "LIVE_SURFACE_PARITY.local-overlay.generated.json",
        tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.startup.log",
    ]
    for path in stale_derived:
        path.write_text("stale pass evidence\n", encoding="utf-8")
    release_channel_receipt, _ = write_release_channel_receipt(tmp_path)
    args = publisher_args(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256="0" * 64,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=tmp_path / "active" / "app",
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
    )
    monkeypatch.setattr(module, "parse_args", lambda: args)

    assert module.main() == 1
    capsys.readouterr()

    assert not output.exists()
    assert all(not path.exists() for path in stale_derived)
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


@pytest.mark.parametrize(
    ("timeout_field", "timeout_value", "invalid_receipt_field", "valid_receipt_field", "valid_value"),
    [
        (
            "publish_timeout_seconds",
            float("nan"),
            "publishTimeoutSeconds",
            "verifyTimeoutSeconds",
            5.0,
        ),
        (
            "verify_timeout_seconds",
            float("inf"),
            "verifyTimeoutSeconds",
            "publishTimeoutSeconds",
            30.0,
        ),
    ],
)
def test_main_invalid_cli_timeout_does_not_clobber_prior_receipts(
    tmp_path: Path,
    monkeypatch,
    capsys,
    timeout_field: str,
    timeout_value: float,
    invalid_receipt_field: str,
    valid_receipt_field: str,
    valid_value: float,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    output = tmp_path / "receipt.json"
    protected_paths = [
        output,
        tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json",
        tmp_path / "LIVE_SURFACE_PARITY.local-overlay.generated.json",
        tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.startup.log",
    ]
    for index, path in enumerate(protected_paths):
        path.write_text(f"prior receipt {index}\n", encoding="utf-8")
    before = {
        path: (
            path.read_bytes(),
            path.stat().st_dev,
            path.stat().st_ino,
            path.stat().st_mtime_ns,
        )
        for path in protected_paths
    }
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(
        tmp_path
    )
    active_root = tmp_path / "active" / "app"
    args = publisher_args(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=tmp_path / "staging" / "app",
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
    )
    setattr(args, timeout_field, timeout_value)
    monkeypatch.setattr(module, "parse_args", lambda: args)

    assert module.main() == 1

    failure_receipt = json.loads(capsys.readouterr().out)
    assert failure_receipt["status"] == "fail"
    assert failure_receipt["timeoutValidation"]["status"] == "fail"
    assert failure_receipt["timeoutValidation"]["errors"]
    assert failure_receipt[invalid_receipt_field] is None
    assert failure_receipt[valid_receipt_field] == valid_value
    assert failure_receipt["failureReceiptWritten"] is False
    for path, expected in before.items():
        assert (
            path.read_bytes(),
            path.stat().st_dev,
            path.stat().st_ino,
            path.stat().st_mtime_ns,
        ) == expected
    assert not module.publish_lock_path(source_root, active_root).exists()
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_main_checks_disk_before_invalidating_receipts_or_staging(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    output = tmp_path / "receipt.json"
    protected_paths = [
        output,
        tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json",
        tmp_path / "LIVE_SURFACE_PARITY.local-overlay.generated.json",
        tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.startup.log",
    ]
    for index, path in enumerate(protected_paths):
        path.write_text(f"prior receipt {index}\n", encoding="utf-8")
    before = {
        path: (
            path.read_bytes(),
            path.stat().st_dev,
            path.stat().st_ino,
            path.stat().st_mtime_ns,
        )
        for path in protected_paths
    }
    staging_root = tmp_path / "staging" / "app"
    build_root = tmp_path / "build"
    staging_root.mkdir(parents=True)
    build_root.mkdir()
    (staging_root / "sentinel.txt").write_text("staging\n", encoding="utf-8")
    (build_root / "sentinel.txt").write_text("build\n", encoding="utf-8")
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(
        tmp_path
    )
    args = publisher_args(
        output=output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=staging_root,
        active_root=tmp_path / "active" / "app",
        backup_root=tmp_path / "backups",
        build_root=build_root,
    )
    args.minimum_free_disk_bytes = 1024
    args.allow_low_disk_capacity = False
    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: types.SimpleNamespace(total=4096, used=3584, free=512),
    )

    assert module.main() == 1

    failure_receipt = json.loads(capsys.readouterr().out)
    assert failure_receipt["status"] == "fail"
    assert failure_receipt["diskCapacityCheck"]["status"] == "fail"
    assert failure_receipt["diskCapacityCheck"]["minimumFreeBytes"] == 1024
    assert failure_receipt["failureReceiptWritten"] is False
    for path, expected in before.items():
        assert (
            path.read_bytes(),
            path.stat().st_dev,
            path.stat().st_ino,
            path.stat().st_mtime_ns,
        ) == expected
    assert (staging_root / "sentinel.txt").read_text(encoding="utf-8") == "staging\n"
    assert (build_root / "sentinel.txt").read_text(encoding="utf-8") == "build\n"
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_path_plan_rejects_reserved_authority_collision_before_any_write(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    staging_root = tmp_path / "staging" / "app"
    build_root = tmp_path / "build"
    staging_root.mkdir(parents=True)
    build_root.mkdir()
    (staging_root / "keep.txt").write_text("staging\n", encoding="utf-8")
    (build_root / "keep.txt").write_text("build\n", encoding="utf-8")
    colliding_output = tmp_path / ".release-channel-authority"

    with pytest.raises(RuntimeError, match="file/authority-root collision"):
        module.materialize(
            colliding_output,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=staging_root,
            active_root=tmp_path / "active" / "app",
            backup_root=tmp_path / "backups",
            build_root=build_root,
        )

    assert (staging_root / "keep.txt").read_text(encoding="utf-8") == "staging\n"
    assert (build_root / "keep.txt").read_text(encoding="utf-8") == "build\n"
    assert not colliding_output.exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


@pytest.mark.parametrize(
    "derived_name",
    [
        "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.startup.log",
        "LIVE_SURFACE_PARITY.local-overlay.generated.json",
    ],
)
def test_path_plan_rejects_hardlinked_planned_file_without_mutating_alias(
    tmp_path: Path,
    derived_name: str,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    sentinel = tmp_path / "outside-sentinel.txt"
    sentinel.write_text("do not truncate\n", encoding="utf-8")
    derived_path = tmp_path / derived_name
    derived_path.hardlink_to(sentinel)

    with pytest.raises(RuntimeError, match="hardlink aliases"):
        module.validate_publisher_path_plan(
            output=tmp_path / "receipt.json",
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=tmp_path / "staging" / "app",
            active_root=tmp_path / "active" / "app",
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
            activation_mode="copy",
        )

    assert sentinel.read_text(encoding="utf-8") == "do not truncate\n"
    assert derived_path.read_text(encoding="utf-8") == "do not truncate\n"


def test_path_plan_rejects_hardlinked_publish_lock_without_truncating_alias(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    active_root = tmp_path / "active" / "app"
    lock_path = module.publish_lock_path(source_root, active_root)
    lock_path.parent.mkdir(parents=True)
    sentinel = tmp_path / "lock-sentinel.txt"
    sentinel.write_text("lock sentinel\n", encoding="utf-8")
    lock_path.hardlink_to(sentinel)
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    with pytest.raises(RuntimeError, match="publish lock has hardlink aliases"):
        module.validate_publisher_path_plan(
            output=tmp_path / "receipt.json",
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=tmp_path / "staging" / "app",
            active_root=active_root,
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
            activation_mode="copy",
        )

    assert sentinel.read_text(encoding="utf-8") == "lock sentinel\n"
    assert lock_path.read_text(encoding="utf-8") == "lock sentinel\n"


@pytest.mark.parametrize("collision", ["verification_receipt", "selected_receipt", "mutable_ancestor"])
def test_path_plan_rejects_output_collision_matrix_before_writes(
    tmp_path: Path,
    collision: str,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    staging_root = tmp_path / "staging" / "app"
    if collision == "verification_receipt":
        output = tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json"
    elif collision == "selected_receipt":
        output = release_channel_receipt
    else:
        output = tmp_path / "staging"
    selected_bytes = release_channel_receipt.read_bytes()

    with pytest.raises(RuntimeError, match="unsafe public-edge overlay"):
        module.validate_publisher_path_plan(
            output=output,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=staging_root,
            active_root=tmp_path / "active" / "app",
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
            activation_mode="copy",
        )

    assert release_channel_receipt.read_bytes() == selected_bytes
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_path_plan_confines_source_writes_to_published_receipt_subtree(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    program_path = source_root / "Program.cs"
    program_path.write_text("source sentinel\n", encoding="utf-8")
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    common = {
        "release_channel_receipt": release_channel_receipt,
        "release_channel_receipt_sha256": release_channel_receipt_sha256,
        "source_root": source_root,
        "staging_root": tmp_path / "staging" / "app",
        "active_root": tmp_path / "active" / "app",
        "backup_root": tmp_path / "backups",
        "build_root": tmp_path / "build",
        "activation_mode": "copy",
    }

    with pytest.raises(RuntimeError, match="outside the confined receipt root"):
        module.validate_publisher_path_plan(output=program_path, **common)

    allowed_output = source_root / ".codex-studio" / "published" / "receipt.json"
    plan = module.validate_publisher_path_plan(output=allowed_output, **common)
    assert plan["output"] == allowed_output
    assert program_path.read_text(encoding="utf-8") == "source sentinel\n"


def test_materialize_rejects_output_in_dynamic_active_transaction_namespace(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    active_root = tmp_path / "active" / "app"
    active_root.mkdir(parents=True)
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    colliding_output = active_root.parent / ".app.retired-20990101T000000Z"

    with pytest.raises(RuntimeError, match="reserved active transaction namespace"):
        module.materialize(
            colliding_output,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=tmp_path / "staging" / "app",
            active_root=active_root,
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
            activate=True,
            skip_backup_on_activate=True,
        )

    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert not colliding_output.exists()
    assert not module.activation_transaction_journal_path(active_root).exists()


def test_verification_program_snapshot_is_read_only_independent_and_drift_detecting(
    tmp_path: Path,
) -> None:
    module = load_module()
    source = tmp_path / "verifier.py"
    source.write_text("VALUE = 'safe'\n", encoding="utf-8")
    binding = module.snapshot_verification_program(
        "testVerifier",
        source,
        tmp_path / "authority",
    )
    snapshot = Path(binding["snapshotPath"])
    source_stat = source.stat()
    snapshot_stat = snapshot.stat()

    assert binding["status"] == "pass"
    assert snapshot.read_text(encoding="utf-8") == "VALUE = 'safe'\n"
    assert snapshot_stat.st_nlink == 1
    assert snapshot_stat.st_mode & 0o222 == 0
    assert (source_stat.st_dev, source_stat.st_ino) != (
        snapshot_stat.st_dev,
        snapshot_stat.st_ino,
    )

    source.write_text("VALUE = 'changed source'\n", encoding="utf-8")
    assert snapshot.read_text(encoding="utf-8") == "VALUE = 'safe'\n"
    assert module.refresh_verification_program_binding(binding)["status"] == "fail"

    source.write_text("VALUE = 'safe'\n", encoding="utf-8")
    snapshot.chmod(0o644)
    snapshot.write_text("VALUE = 'changed snapshot'\n", encoding="utf-8")
    assert source.read_text(encoding="utf-8") == "VALUE = 'safe'\n"
    assert module.refresh_verification_program_binding(binding)["status"] == "fail"


def test_verification_program_snapshot_rejects_corrupt_or_hardlinked_digest_target(
    tmp_path: Path,
) -> None:
    module = load_module()
    source = tmp_path / "verifier.py"
    source_bytes = b"VALUE = 'safe'\n"
    source.write_bytes(source_bytes)
    digest = hashlib.sha256(source_bytes).hexdigest()

    corrupt_root = tmp_path / "corrupt-authority"
    corrupt_root.mkdir()
    corrupt_target = corrupt_root / f"verifier.{digest}.py"
    corrupt_target.write_text("corrupt\n", encoding="utf-8")
    corrupt_target.chmod(0o444)
    with pytest.raises(RuntimeError, match="snapshot is corrupt"):
        module.snapshot_verification_program("testVerifier", source, corrupt_root)

    hardlink_root = tmp_path / "hardlink-authority"
    hardlink_root.mkdir()
    hardlink_target = hardlink_root / f"verifier.{digest}.py"
    hardlink_target.write_bytes(source_bytes)
    hardlink_target.chmod(0o444)
    outside_alias = tmp_path / "snapshot-alias.py"
    outside_alias.hardlink_to(hardlink_target)
    with pytest.raises(RuntimeError, match="unsafe hardlinks"):
        module.snapshot_verification_program("testVerifier", source, hardlink_root)

    assert outside_alias.read_bytes() == source_bytes


def test_sealed_program_execution_uses_bound_bytes_despite_snapshot_path_swap(
    tmp_path: Path,
) -> None:
    module = load_module()
    source = tmp_path / "verifier.py"
    source.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text(__file__ + '|SAFE', encoding='utf-8')\n",
        encoding="utf-8",
    )
    binding = module.snapshot_verification_program(
        "testVerifier",
        source,
        tmp_path / "authority",
    )
    snapshot = Path(binding["snapshotPath"])
    result_path = tmp_path / "result.txt"
    descriptor = -1

    with module.sealed_verification_program_execution(binding) as execution:
        descriptor = int(execution["descriptor"])
        required_seals = (
            module.fcntl.F_SEAL_SEAL
            | module.fcntl.F_SEAL_SHRINK
            | module.fcntl.F_SEAL_GROW
            | module.fcntl.F_SEAL_WRITE
        )
        assert execution["sha256Expected"] == execution["sha256Actual"]
        assert execution["sha256Matches"] is True
        assert int(execution["seals"]) & required_seals == required_seals

        snapshot.rename(snapshot.with_suffix(".saved"))
        snapshot.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "Path(sys.argv[1]).write_text('MALICIOUS', encoding='utf-8')\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                module.SEALED_PYTHON_PROGRAM_WRAPPER,
                str(descriptor),
                str(execution["sha256Expected"]),
                str(binding["sourcePath"]),
                str(result_path),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(descriptor,),
        )
        assert completed.returncode == 0, completed.stderr
        assert result_path.read_text(encoding="utf-8") == f"{source}|SAFE"
        assert module.refresh_verification_program_binding(binding)["status"] == "fail"
        assert module.os.fstat(descriptor).st_size > 0

    with pytest.raises(OSError):
        module.os.fstat(descriptor)


def test_real_verifier_snapshot_executes_with_original_file_semantics_and_parity_has_no_cache(
    tmp_path: Path,
) -> None:
    module = load_module()
    programs = module.snapshot_verification_programs(tmp_path / "authority")
    verifier_binding = programs["programs"]["downloadsVersionMarker"]
    parity_binding = programs["programs"]["liveSurfaceParity"]

    with module.sealed_verification_program_execution(verifier_binding) as execution:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                module.SEALED_PYTHON_PROGRAM_WRAPPER,
                str(execution["descriptor"]),
                str(execution["sha256Expected"]),
                str(verifier_binding["sourcePath"]),
                "--help",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(int(execution["descriptor"]),),
        )
    assert completed.returncode == 0, completed.stderr
    assert "usage: verify_downloads_version_marker.py" in completed.stdout

    parity_module = module.load_live_surface_parity_module(parity_binding)
    assert Path(parity_module.REPO_ROOT) == module.RUN_SERVICES_ROOT
    assert not (tmp_path / "authority" / "__pycache__").exists()


def test_materialize_isolated_build_workspace_copies_build_and_overlay_payload_closure(tmp_path: Path) -> None:
    module = load_module()
    workspace_root = tmp_path
    source_root = workspace_root / "chummer.run-services"
    make_source_tree(source_root)

    design_root = workspace_root / "chummer-design"
    (design_root / ".dockerignore").parent.mkdir(parents=True, exist_ok=True)
    (design_root / ".dockerignore").write_text("**/drafts/**\n", encoding="utf-8")
    (design_root / "products" / "chummer").mkdir(parents=True, exist_ok=True)
    (design_root / "products" / "chummer" / "marker.txt").write_text(
        "design product\n",
        encoding="utf-8",
    )

    for relative_path in (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("global.json"),
        Path("Chummer.Campaign.Contracts") / "marker.txt",
        Path("Chummer.Control.Contracts") / "marker.txt",
        Path("Chummer.Play.Contracts") / "marker.txt",
        Path("Chummer.Run.Contracts") / "marker.txt",
        Path("Chummer.World.Contracts") / "marker.txt",
        Path("Chummer.Portal") / "ignored.txt",
        Path(".vexp") / "index.db",
        Path(".pytest_cache") / "state",
        Path("Chummer.Run.Api") / "bin_tmp" / "ignored.txt",
    ):
        absolute_path = source_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(relative_path.as_posix(), encoding="utf-8")

    core_root = workspace_root / "chummer-core-engine"
    for relative_path in (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("global.json"),
        Path("Chummer.Contracts") / "marker.txt",
        Path("unrelated") / "ignored.txt",
    ):
        absolute_path = core_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(relative_path.as_posix(), encoding="utf-8")

    hub_root = workspace_root / "chummer-hub-registry"
    for relative_path in (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("Chummer.Hub.Registry.Contracts") / "marker.txt",
        Path("Chummer.Run.Registry") / "marker.txt",
        Path("black-ledger") / "ignored.txt",
    ):
        absolute_path = hub_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(relative_path.as_posix(), encoding="utf-8")

    media_root = workspace_root / "fleet" / "repos" / "chummer-media-factory"
    for relative_path in (
        Path("Directory.Build.props"),
        Path("Directory.Build.targets"),
        Path("src") / "Chummer.Media.Contracts" / "marker.txt",
        Path("docs") / "ignored.txt",
    ):
        absolute_path = media_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(relative_path.as_posix(), encoding="utf-8")

    build_root = workspace_root / "build"
    build_source_root, copied_roots = module.materialize_isolated_build_workspace(source_root, build_root)

    assert build_source_root == build_root / "workspace" / "chummer.run-services"
    copied_roots_relative = sorted(
        Path(copied_root).relative_to(build_root / "workspace").as_posix()
        for copied_root in copied_roots
    )
    assert copied_roots_relative == [
        ".",
        "chummer-core-engine",
        "chummer-design",
        "chummer-hub-registry",
        "chummer.run-services",
        "fleet/repos/chummer-media-factory",
    ]
    assert (build_source_root / "Chummer.Run.Api" / "Chummer.Run.Api.csproj").is_file()
    assert (build_source_root / "Chummer.Campaign.Contracts" / "marker.txt").is_file()
    assert (build_source_root / "Directory.Build.props").is_file()
    assert (build_root / "workspace" / ".dockerignore").is_file()
    assert (
        build_root / "workspace" / "chummer-design" / "products" / "chummer" / "marker.txt"
    ).is_file()
    assert (build_root / "workspace" / "chummer-design" / ".dockerignore").is_file()
    assert (
        build_source_root / "scripts" / "verify_public_pwa_static_assets.py"
    ).is_file()
    assert (build_source_root / "scripts" / "public_edge_payload_modes.py").is_file()
    assert (build_source_root / "scripts" / "strict_json_contract.py").is_file()
    assert not (build_source_root / "Chummer.Portal").exists()
    assert not (build_source_root / ".vexp").exists()
    assert not (build_source_root / ".pytest_cache").exists()
    assert not (build_source_root / "Chummer.Run.Api" / "bin_tmp").exists()
    assert (build_source_root / ".codex-design" / "marker.txt").is_file()
    assert (build_root / "workspace" / "chummer-core-engine" / "Chummer.Contracts" / "marker.txt").is_file()
    assert not (build_root / "workspace" / "chummer-core-engine" / "unrelated").exists()
    assert (build_root / "workspace" / "chummer-hub-registry" / "Chummer.Run.Registry" / "marker.txt").is_file()
    assert (build_root / "workspace" / "chummer-hub-registry" / "black-ledger" / "ignored.txt").is_file()
    assert (
        build_root
        / "workspace"
        / "fleet"
        / "repos"
        / "chummer-media-factory"
        / "src"
        / "Chummer.Media.Contracts"
        / "marker.txt"
    ).is_file()
    assert not (build_root / "workspace" / "fleet" / "repos" / "chummer-media-factory" / "docs").exists()


def test_frontdoor_playwright_proof_closure_is_exact_digest_bound_and_mutation_fails(
    tmp_path: Path,
) -> None:
    module = load_module()
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    receipt = module.materialize_frontdoor_playwright_proof_closure(
        REPO_ROOT,
        staging_root,
    )
    closure_root = (
        staging_root / module.FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT
    )

    assert receipt["status"] == "pass"
    assert receipt["fileCount"] == 7
    assert receipt["playwrightPackageVersion"] == "1.60.0"
    assert len(receipt["aggregateSha256"]) == 64
    assert {row["relativePath"] for row in receipt["files"]} == {
        "package.json",
        "package-lock.json",
        "playwright.config.ts",
        "tests/public/ux-artifacts.ts",
        "tests/public/frontdoor-mobile-launch.spec.ts",
        "tests/public/black-ledger-frontdoor.spec.ts",
        "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml",
    }
    assert module.validate_frontdoor_playwright_proof_closure(closure_root) == receipt

    mobile_spec = closure_root / "tests/public/frontdoor-mobile-launch.spec.ts"
    mobile_spec.write_text(
        mobile_spec.read_text(encoding="utf-8") + "\n// unbound mutation\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="file digest drifted"):
        module.validate_frontdoor_playwright_proof_closure(closure_root)


def test_staged_payload_fingerprint_binds_frontdoor_playwright_proof_closure(
    tmp_path: Path,
) -> None:
    module = load_module()
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    (staging_root / "state").mkdir()
    (staging_root / "Chummer.Run.Api.dll").write_bytes(b"assembly")
    module.ensure_required_compose_mountpoints(staging_root)
    module.materialize_frontdoor_playwright_proof_closure(REPO_ROOT, staging_root)
    module.normalize_payload_modes(staging_root)

    before = module.staged_payload_fingerprint(staging_root)
    closure_spec = (
        staging_root
        / module.FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT
        / "tests/public/frontdoor-mobile-launch.spec.ts"
    )
    closure_spec.write_bytes(closure_spec.read_bytes() + b"\n// staged mutation\n")
    module.normalize_payload_modes(staging_root)
    after = module.staged_payload_fingerprint(staging_root)

    assert before["aggregateSha256"] != after["aggregateSha256"]
    assert any(
        row["path"].endswith("tests/public/frontdoor-mobile-launch.spec.ts")
        for row in module.staged_payload_rows(staging_root)
    )


def test_frontdoor_playwright_proof_closure_rejects_unbound_file(tmp_path: Path) -> None:
    module = load_module()
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    module.materialize_frontdoor_playwright_proof_closure(REPO_ROOT, staging_root)
    closure_root = (
        staging_root / module.FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT
    )
    unbound = closure_root / "tests/public/old-frontdoor.spec.ts"
    unbound.parent.mkdir(parents=True, exist_ok=True)
    unbound.write_text("throw new Error('old proof');\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="contains unbound files"):
        module.validate_frontdoor_playwright_proof_closure(closure_root)


def test_build_input_fingerprint_binds_frontdoor_playwright_proof_and_postdeploy_runner() -> None:
    module = load_module()
    paths = {str(row["path"]) for row in module.build_input_rows(REPO_ROOT)}

    prefix = REPO_ROOT.name
    assert {
        f"{prefix}/package.json",
        f"{prefix}/package-lock.json",
        f"{prefix}/playwright.config.ts",
        f"{prefix}/tests/public/ux-artifacts.ts",
        f"{prefix}/tests/public/frontdoor-mobile-launch.spec.ts",
        f"{prefix}/tests/public/black-ledger-frontdoor.spec.ts",
        f"{prefix}/scripts/verify_public_edge_postdeploy_gate.py",
    }.issubset(paths)


def test_build_input_fingerprint_preserves_symlinked_copy_plan_root(tmp_path: Path) -> None:
    module = load_module()
    workspace_root = tmp_path / "workspace"
    source_root = workspace_root / "chummer.run-services"
    make_source_tree(source_root)

    external_fleet_root = tmp_path / "external-fleet"
    media_contract = (
        external_fleet_root
        / "repos"
        / "chummer-media-factory"
        / "src"
        / "Chummer.Media.Contracts"
        / "marker.txt"
    )
    media_contract.parent.mkdir(parents=True, exist_ok=True)
    media_contract.write_text("media contract\n", encoding="utf-8")
    (workspace_root / "fleet").symlink_to(external_fleet_root, target_is_directory=True)

    build_root = tmp_path / "build"
    before = module.build_input_fingerprint(source_root)
    build_source_root, _ = module.materialize_isolated_build_workspace(source_root, build_root)
    after = module.build_input_fingerprint(build_source_root)

    assert before == after
    assert any(
        row["path"]
        == "fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/marker.txt"
        for row in module.build_input_rows(source_root)
    )


def test_build_input_fingerprint_excludes_runtime_mounted_generated_proof(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "chummer.run-services"
    make_source_tree(source_root)
    mounted_proof = (
        source_root
        / "Chummer.Run.Api"
        / "wwwroot"
        / "proofs"
        / "mac-codex-release"
        / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )
    mounted_proof.parent.mkdir(parents=True)
    mounted_proof.write_text('{"generated_at":"first"}\n', encoding="utf-8")

    before = module.build_input_fingerprint(source_root)
    mounted_proof.write_text('{"generated_at":"second"}\n', encoding="utf-8")
    after_mounted_refresh = module.build_input_fingerprint(source_root)
    (source_root / "Chummer.Run.Api" / "Program.cs").write_text("program changed\n", encoding="utf-8")
    after_program_change = module.build_input_fingerprint(source_root)

    assert before == after_mounted_refresh
    assert after_program_change != after_mounted_refresh
    assert not any(
        row["path"].endswith(
            "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        for row in module.build_input_rows(source_root)
    )


def test_build_input_fingerprint_covers_operator_tool_and_compose_closure(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "chummer.run-services"
    make_source_tree(source_root)
    design_root = tmp_path / "chummer-design"
    (design_root / "products" / "chummer").mkdir(parents=True)
    (design_root / ".dockerignore").write_text("**/drafts/**\n", encoding="utf-8")
    (design_root / "products" / "chummer" / "product.yaml").write_text(
        "product: chummer\n",
        encoding="utf-8",
    )
    expected_paths = {
        ".dockerignore",
        "chummer.run-services/.dockerignore",
        "chummer.run-services/docker-compose.public-edge.yml",
        "chummer.run-services/scripts/generate_public_play_worker_projection.py",
        "chummer.run-services/scripts/public_edge_payload_modes.py",
        "chummer.run-services/scripts/strict_json_contract.py",
        "chummer.run-services/scripts/validate_public_pwa_proof_authority.py",
        "chummer.run-services/scripts/verify_public_pwa_static_assets.py",
        "chummer.run-services/Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj",
        "chummer.run-services/Chummer.InstallLinking.Postgres.Tool/Program.cs",
        "chummer-design/.dockerignore",
        "chummer-design/products/chummer/product.yaml",
    }

    rows = module.build_input_rows(source_root)
    assert expected_paths <= {str(row["path"]) for row in rows}
    before = module.build_input_fingerprint(source_root)

    for path in (
        tmp_path / ".dockerignore",
        source_root / ".dockerignore",
        source_root / "docker-compose.public-edge.yml",
        source_root / "scripts" / "generate_public_play_worker_projection.py",
        source_root / "scripts" / "public_edge_payload_modes.py",
        source_root / "scripts" / "strict_json_contract.py",
        source_root / "scripts" / "validate_public_pwa_proof_authority.py",
        source_root / "scripts" / "verify_public_pwa_static_assets.py",
        source_root / "Chummer.InstallLinking.Postgres.Tool" / "Chummer.InstallLinking.Postgres.Tool.csproj",
        source_root / "Chummer.InstallLinking.Postgres.Tool" / "Program.cs",
        design_root / ".dockerignore",
        design_root / "products" / "chummer" / "product.yaml",
    ):
        original = path.read_text(encoding="utf-8")
        path.write_text(f"{original}changed\n", encoding="utf-8")
        assert module.build_input_fingerprint(source_root) != before
        path.write_text(original, encoding="utf-8")


def test_isolated_build_workspace_is_a_copy_not_a_live_hardlink(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "chummer.run-services"
    make_source_tree(source_root)
    source_file = source_root / "Chummer.Run.Api" / "Program.cs"

    build_source_root, _ = module.materialize_isolated_build_workspace(
        source_root,
        tmp_path / "build",
    )
    snapshot_file = build_source_root / "Chummer.Run.Api" / "Program.cs"

    assert source_file.stat().st_ino != snapshot_file.stat().st_ino
    source_file.write_text("changed live source\n", encoding="utf-8")
    assert snapshot_file.read_text(encoding="utf-8") == "program\n"


def test_source_fingerprint_binds_copied_codex_design_and_black_ledger(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "chummer.run-services"
    make_source_tree(source_root)
    black_ledger_file = tmp_path / "chummer-hub-registry" / "black-ledger" / "entry.json"
    black_ledger_file.parent.mkdir(parents=True, exist_ok=True)
    black_ledger_file.write_text("{}\n", encoding="utf-8")

    before = module.source_fingerprint(source_root)
    (source_root / ".codex-design" / "marker.txt").write_text(
        "changed design\n",
        encoding="utf-8",
    )
    after_design_change = module.source_fingerprint(source_root)
    black_ledger_file.write_text('{"changed":true}\n', encoding="utf-8")
    after_ledger_change = module.source_fingerprint(source_root)

    assert before["buildInputs"] == after_design_change["buildInputs"]
    assert (
        before["overlayPayloadInputs"]["aggregateSha256"]
        != after_design_change["overlayPayloadInputs"]["aggregateSha256"]
    )
    assert (
        after_design_change["overlayPayloadInputs"]["aggregateSha256"]
        != after_ledger_change["overlayPayloadInputs"]["aggregateSha256"]
    )


def test_source_fingerprint_comparison_requires_algorithm_and_critical_file_details(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    expected = module.source_fingerprint(source_root)

    wrong_algorithm = json.loads(json.dumps(expected))
    wrong_algorithm["buildInputs"]["algorithm"] = "sha256-path-only-v0"
    missing_critical_file = json.loads(json.dumps(expected))
    del missing_critical_file["files"]["landing"]
    wrong_critical_path = json.loads(json.dumps(expected))
    wrong_critical_path["files"]["landing"]["relativePath"] = "wrong/Landing.cshtml"
    wrong_critical_sha = json.loads(json.dumps(expected))
    wrong_critical_sha["files"]["landing"]["sha256"] = "0" * 64

    for recorded in (
        wrong_algorithm,
        missing_critical_file,
        wrong_critical_path,
        wrong_critical_sha,
    ):
        comparison = module.source_fingerprint_comparison(recorded, expected)
        assert comparison["matchesCurrentSource"] is False

    assert module.source_fingerprint_comparison(wrong_algorithm, expected)[
        "buildInputAlgorithmMatches"
    ] is False
    assert module.source_fingerprint_comparison(missing_critical_file, expected)[
        "criticalFileDetailsMatchCurrentSource"
    ] is False


def test_materialize_stages_and_verifies_overlay_without_activation(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"

    def fake_run(command, *, cwd):
        staging_root.mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        return make_completed(stdout="publish ok\n")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        verification_receipt_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        return {
            "status": "pass",
            "reason": "",
            "baseUrl": "http://127.0.0.1:5001",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 0,
            "receiptStatus": "pass",
            "probeError": "",
            "landingMarkerStatus": "pass",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": True,
                "turnAnchorNormalizedHash": True,
                "turnAnchorRedirect": True,
            },
            "landingMissingMarkers": [],
            "landingBrowserRedirect": passing_browser_redirect(),
        }

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        run_command_fn=fake_run,
        verify_overlay_fn=fake_verify,
    )

    assert payload["status"] == "test_only"
    assert payload["testOutcomeStatus"] == "pass"
    assert payload["testOnly"] is True
    assert payload["authoritativeReceipt"] is False
    assert payload["activationStatus"] == "staged_only"
    assert payload["activateRequested"] is False
    assert payload["buildRoot"] == str(build_root.resolve())
    assert payload["buildSourceRoot"].endswith("/workspace/source")
    assert payload["buildProjectPath"].endswith("/workspace/source/Chummer.Run.Api/Chummer.Run.Api.csproj")
    assert payload["copiedCodexDesign"] is True
    assert payload["copiedSourceWwwroot"] is True
    assert "dotnet" in payload["publishCommand"][0]
    assert "publish" in payload["publishCommand"]
    assert "--artifacts-path" not in payload["publishCommand"]
    assert "-p:ChummerDesktopRuntimeIdentifiers=" in payload["publishCommand"]
    assert payload["verification"]["receiptStatus"] == "pass"
    assert payload["releaseChannelReceipt"]["sha256Matches"] is True
    assert payload["releaseChannelReceipt"]["sha256Expected"] == payload["releaseChannelReceipt"]["sha256Actual"]
    assert payload["releaseChannelReceipt"]["snapshotPath"].endswith(
        f"RELEASE_CHANNEL.{payload['releaseChannelReceipt']['sha256Actual']}.json"
    )
    snapshot_path = Path(payload["releaseChannelReceipt"]["snapshotPath"])
    assert snapshot_path.parent == output.parent / ".release-channel-authority"
    assert snapshot_path.is_file()
    assert snapshot_path.parent != build_root
    assert payload["verification"]["releaseManifestConservativeReviewFloorApplied"] is True
    assert payload["verification"]["releaseManifestSupportabilityExact"] is False
    assert payload["verification"]["releaseManifestSupportabilityCompatible"] is True
    assert payload["verification"]["releaseManifestRolloutExact"] is False
    assert payload["verification"]["releaseManifestRolloutCompatible"] is True
    assert payload["verificationProgramsMatch"] is True
    assert payload["verificationPrograms"]["contractName"] == module.VERIFICATION_PROGRAM_BINDING_CONTRACT_NAME
    assert payload["verificationPrograms"]["status"] == "pass"
    for binding in payload["verificationPrograms"]["programs"].values():
        assert binding["status"] == "pass"
        assert binding["sha256Expected"] == binding["sourceSha256Actual"]
        assert binding["sha256Expected"] == binding["snapshotSha256Actual"]
        assert binding["snapshotIndependentInode"] is True
        assert binding["snapshotLinkCount"] == 1
        assert binding["snapshotWriteBits"] == 0
    assert payload["stagingBuildInfoPath"]
    assert payload["activeBuildInfoPath"] == ""
    assert output.is_file()
    assert (staging_root / "state").is_dir()
    assert (staging_root / "wwwroot" / "pwa-icon.svg").read_text(encoding="utf-8") == "<svg />\n"
    assert (staging_root / "wwwroot" / "site.webmanifest").read_text(encoding="utf-8") == "{}\n"
    assert (
        staging_root / "wwwroot" / "media" / "product" / "proof-builder-trail.png"
    ).read_text(encoding="utf-8") == "png\n"
    assert (
        staging_root / "wwwroot" / "proofs" / "mac-codex-release" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    ).read_text(encoding="utf-8") == "{}\n"
    assert payload["composeMountpointsCreated"] == [
        "wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
    ]
    assert (staging_root / ".codex-design" / "marker.txt").read_text(encoding="utf-8") == "design\n"
    build_info = json.loads((staging_root / module.OVERLAY_BUILD_INFO_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert build_info["contractName"] == module.CONTRACT_NAME
    assert build_info["status"] == "test_only"
    assert build_info["testOnly"] is True
    assert build_info["authoritativeReceipt"] is False
    assert build_info["activationStatus"] == "staged_only"
    assert build_info["verificationStatus"] == "pass"
    assert build_info["releaseChannelReceiptSha256Matches"] is True
    assert build_info["releaseChannelReceiptSha256Expected"] == payload["releaseChannelReceipt"]["sha256Actual"]
    assert build_info["releaseChannelVersion"] == "run-20260713-123603"
    assert build_info["releaseChannelPublishedAt"] == "2026-07-13T12:38:14Z"
    assert build_info["releaseManifestConservativeReviewFloorApplied"] is True
    assert build_info["releaseManifestSupportabilityExact"] is False
    assert build_info["releaseManifestSupportabilityCompatible"] is True
    assert build_info["releaseManifestRolloutExact"] is False
    assert build_info["releaseManifestRolloutCompatible"] is True
    assert build_info["verificationProgramsMatch"] is True
    assert build_info["receiptProgramBindingsMatch"] is True
    assert build_info["verificationPrograms"] == payload["verificationPrograms"]
    assert build_info["landingMarkerStatus"] == "pass"
    assert build_info["landingHasTurnAnchor"] is True
    assert build_info["landingHasTurnAnchorRedirect"] is True
    assert build_info["landingBrowserRedirectStatus"] == "pass"
    assert build_info["landingBrowserRedirectPathMatches"] is True
    assert build_info["landingBrowserRedirectHashMatches"] is True
    assert build_info["landingMissingMarkerCount"] == 0
    assert build_info["sourceFingerprint"]["files"]["landing"]["relativePath"] == "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"
    assert build_info["sourceFingerprint"]["files"]["downloads"]["relativePath"] == "Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"
    assert build_info["sourceFingerprint"]["files"]["status"]["relativePath"] == "Chummer.Run.Api/Views/PublicLanding/Status.cshtml"
    assert build_info["sourceFingerprint"]["files"]["authController"]["relativePath"] == "Chummer.Run.Api/Controllers/AuthController.cs"
    assert build_info["sourceFingerprint"]["files"]["authEntryView"]["relativePath"] == "Chummer.Run.Api/Views/Auth/Entry.cshtml"
    assert build_info["sourceFingerprint"]["files"]["authPolicy"]["relativePath"] == "Chummer.Run.Api/Services/HubEmailSignInPolicy.cs"
    assert build_info["sourceFingerprint"]["files"]["siteViewModels"]["relativePath"] == "Chummer.Run.Api/ViewModels/SiteViewModels.cs"
    assert len(build_info["sourceFingerprint"]["aggregateSha256"]) == 64
    assert not active_root.exists()


def test_materialize_rejects_mismatched_release_channel_digest_before_cleanup_or_publish(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    build_root = tmp_path / "build"
    staging_root.mkdir(parents=True)
    build_root.mkdir(parents=True)
    (staging_root / "keep.txt").write_text("staged\n", encoding="utf-8")
    (build_root / "keep.txt").write_text("build\n", encoding="utf-8")
    release_channel_receipt, _ = write_release_channel_receipt(tmp_path)
    publish_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal publish_called
        publish_called = True
        raise AssertionError("publish must not run for a mismatched release-channel digest")

    with pytest.raises(RuntimeError, match="release-channel receipt SHA-256 mismatch"):
        module.materialize(
            tmp_path / "receipt.json",
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256="0" * 64,
            source_root=source_root,
            staging_root=staging_root,
            active_root=tmp_path / "overlay" / "app",
            backup_root=tmp_path / "backups",
            build_root=build_root,
            run_command_fn=fail_if_called,
        )

    assert publish_called is False
    assert (staging_root / "keep.txt").read_text(encoding="utf-8") == "staged\n"
    assert (build_root / "keep.txt").read_text(encoding="utf-8") == "build\n"


def test_materialize_rejects_forged_verification_program_envelope(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "staging" / "app"
    active_root = tmp_path / "active" / "app"
    build_root = tmp_path / "build"
    output = tmp_path / "receipt.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    def fake_run(command, *, cwd):
        staging_root.mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        return make_completed(stdout="publish ok\n")

    def forged_verify(
        staging,
        *,
        source_root,
        verify_timeout_seconds,
        verification_receipt_path,
        release_channel_receipt,
        release_channel_receipt_sha256,
        verification_programs,
    ):
        forged_programs = json.loads(json.dumps(verification_programs))
        forged_programs["programs"]["downloadsVersionMarker"]["snapshotSha256Actual"] = "0" * 64
        result = passing_overlay_verification(verification_receipt_path)
        result.update(
            {
                "receiptBindingMatchesSelectedInput": True,
                "receiptInvocationMatchesCurrent": True,
                "receiptProcessResultConsistent": True,
                "releaseChannelReceiptPath": str(release_channel_receipt),
                "releaseChannelReceiptSnapshotPath": str(release_channel_receipt),
                "releaseChannelReceiptSha256Expected": release_channel_receipt_sha256,
                "releaseChannelReceiptSha256Actual": release_channel_receipt_sha256,
                "releaseChannelReceiptSha256Matches": True,
                "verificationPrograms": forged_programs,
                "verificationProgramsMatch": True,
                "receiptProgramBindingsMatch": True,
            }
        )
        return result

    payload = module.materialize(
        output,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=build_root,
        run_command_fn=fake_run,
        verify_overlay_fn=forged_verify,
    )

    assert payload["status"] == "fail"
    assert payload["verification"]["status"] == "fail"
    assert payload["verification"]["reason"] == "verification_program_binding_mismatch"
    assert payload["verificationProgramsMatch"] is False
    assert not active_root.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "fail"


def test_materialize_activates_overlay_and_creates_backup_after_pass_verification(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    active_root.mkdir(parents=True, exist_ok=True)
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")
    prior_active_identity = active_root.stat()

    def fake_run(command, *, cwd):
        staging_root.mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        (staging_root / "new.txt").write_text("new\n", encoding="utf-8")
        return make_completed(stdout="publish ok\n")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        verification_receipt_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        return {
            "status": "pass",
            "reason": "",
            "baseUrl": "http://127.0.0.1:5002",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 0,
            "receiptStatus": "pass",
            "probeError": "",
            "landingMarkerStatus": "pass",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": True,
                "turnAnchorNormalizedHash": True,
                "turnAnchorRedirect": True,
            },
            "landingMissingMarkers": [],
            "landingBrowserRedirect": passing_browser_redirect(),
        }

    with pytest.raises(RuntimeError, match="non-production publisher callbacks cannot activate"):
        materialize_with_binding(
            module,
            output,
            binding_root=tmp_path,
            source_root=source_root,
            staging_root=staging_root,
            active_root=active_root,
            backup_root=backup_root,
            build_root=build_root,
            activate=True,
            run_command_fn=fake_run,
            verify_overlay_fn=fake_verify,
        )

    active_identity = active_root.stat()
    assert (active_identity.st_dev, active_identity.st_ino) == (
        prior_active_identity.st_dev,
        prior_active_identity.st_ino,
    )
    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert not staging_root.exists()
    assert not build_root.exists()
    assert not output.exists()
    assert not (tmp_path / ".release-channel-authority").exists()
    assert not (tmp_path / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_activate_overlay_tree_copy_cutover_without_backup_is_atomic(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    active_root.mkdir(parents=True, exist_ok=True)
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")

    staging_root.mkdir(parents=True)
    (staging_root / "new.txt").write_text("new\n", encoding="utf-8")
    staged_file_identity = (staging_root / "new.txt").stat()

    result = module.activate_overlay_tree(
        staging_root,
        active_root,
        mode="copy",
        backup_root=None,
    )

    assert result["atomicCutover"] is True
    assert result["backupPath"] == ""
    assert result["rollbackStatus"] == "not_required"
    assert result["transactionCleanupStatus"] == "complete"
    assert (active_root / "new.txt").read_text(encoding="utf-8") == "new\n"
    installed_identity = (active_root / "new.txt").stat()
    assert (installed_identity.st_dev, installed_identity.st_ino) == (
        staged_file_identity.st_dev,
        staged_file_identity.st_ino,
    )
    assert not staging_root.exists()
    assert not (active_root / "old.txt").exists()
    assert list(active_root.parent.glob(".app.candidate-*")) == []
    assert list(active_root.parent.glob(".app.retired-*")) == []


def test_activate_overlay_tree_copy_cutover_preserves_exact_prior_tree_as_backup(
    tmp_path: Path,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    staging_root.mkdir(parents=True)
    active_root.mkdir(parents=True)
    staged_file = staging_root / "new.txt"
    prior_file = active_root / "old.txt"
    staged_file.write_text("new\n", encoding="utf-8")
    prior_file.write_text("old\n", encoding="utf-8")
    staged_identity = staged_file.stat()
    prior_identity = prior_file.stat()

    result = module.activate_overlay_tree(
        staging_root,
        active_root,
        mode="copy",
        backup_root=backup_root,
    )

    backup_path = Path(result["backupPath"])
    installed_identity = (active_root / "new.txt").stat()
    backup_identity = (backup_path / "old.txt").stat()
    assert result["atomicCutover"] is True
    assert result["transactionCleanupStatus"] == "complete"
    assert backup_path.is_relative_to(backup_root)
    assert (active_root / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert (backup_path / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert (installed_identity.st_dev, installed_identity.st_ino) == (
        staged_identity.st_dev,
        staged_identity.st_ino,
    )
    assert (backup_identity.st_dev, backup_identity.st_ino) == (
        prior_identity.st_dev,
        prior_identity.st_ino,
    )
    assert not staging_root.exists()
    assert not module.activation_transaction_journal_path(active_root).exists()


def test_activate_overlay_tree_rejects_hardlink_mode_without_mutating_either_tree(
    tmp_path: Path,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    (staging_root / "wwwroot" / "css").mkdir(parents=True, exist_ok=True)
    (staging_root / "wwwroot" / "css" / "site.css").write_text("body {}\n", encoding="utf-8")
    active_root.mkdir(parents=True, exist_ok=True)

    (active_root / "old.txt").write_text("old\n", encoding="utf-8")
    staging_file = staging_root / "wwwroot" / "css" / "site.css"
    active_file = active_root / "old.txt"
    staging_identity = staging_file.stat()
    active_identity = active_file.stat()

    with pytest.raises(RuntimeError, match="hardlink activation is disabled"):
        module.activate_overlay_tree(staging_root, active_root, mode="hardlink")

    assert staging_file.read_text(encoding="utf-8") == "body {}\n"
    assert active_file.read_text(encoding="utf-8") == "old\n"
    assert (staging_file.stat().st_dev, staging_file.stat().st_ino) == (
        staging_identity.st_dev,
        staging_identity.st_ino,
    )
    assert (active_file.stat().st_dev, active_file.stat().st_ino) == (
        active_identity.st_dev,
        active_identity.st_ino,
    )
    assert not list(active_root.parent.glob(".app.candidate-*"))


def test_copy_activation_exchange_failure_leaves_exact_active_and_staging_trees(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    staging_root.mkdir(parents=True)
    active_root.mkdir(parents=True)
    (staging_root / "new.txt").write_text("new\n", encoding="utf-8")
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")

    def fail_exchange(_left: Path, _right: Path) -> None:
        raise OSError("injected exchange failure")

    monkeypatch.setattr(module, "atomic_exchange_overlay_roots", fail_exchange)

    with pytest.raises(module.OverlayActivationError) as raised:
        module.activate_overlay_tree(
            staging_root,
            active_root,
            mode="copy",
            backup_root=backup_root,
        )

    assert raised.value.rollback_status == "active_unchanged"
    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert not (active_root / "new.txt").exists()
    assert (staging_root / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert not module.activation_transaction_journal_path(active_root).exists()


def test_copy_activation_backup_rename_failure_atomically_restores_exact_prior_active(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    staging_root.mkdir(parents=True)
    active_root.mkdir(parents=True)
    (staging_root / "new.txt").write_text("new\n", encoding="utf-8")
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")
    original_atomic_move = module.atomic_move_overlay_root

    def fail_backup_move(source: Path, destination: Path) -> None:
        if backup_root in destination.parents:
            raise OSError("injected backup rename failure")
        original_atomic_move(source, destination)

    monkeypatch.setattr(module, "atomic_move_overlay_root", fail_backup_move)

    with pytest.raises(module.OverlayActivationError) as raised:
        module.activate_overlay_tree(
            staging_root,
            active_root,
            mode="copy",
            backup_root=backup_root,
        )

    assert raised.value.rollback_status == "exact_prior_active_restored"
    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert not (active_root / "new.txt").exists()
    assert (staging_root / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert not module.activation_transaction_journal_path(active_root).exists()
    assert not list(backup_root.rglob("app"))


def test_materialize_rejects_hardlink_mode_before_any_publish_or_receipt_write(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    active_root.mkdir(parents=True)
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")

    staging_root.mkdir(parents=True)
    build_root.mkdir(parents=True)
    (staging_root / "keep.txt").write_text("staged\n", encoding="utf-8")
    (build_root / "keep.txt").write_text("build\n", encoding="utf-8")
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    publish_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal publish_called
        publish_called = True
        raise AssertionError("publish must not run for disabled hardlink activation")

    with pytest.raises(RuntimeError, match="hardlink activation is disabled"):
        module.materialize(
            output,
            release_channel_receipt=release_channel_receipt,
            release_channel_receipt_sha256=release_channel_receipt_sha256,
            source_root=source_root,
            staging_root=staging_root,
            active_root=active_root,
            backup_root=backup_root,
            build_root=build_root,
            activate=True,
            activation_mode="hardlink",
        )

    assert publish_called is False
    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert (staging_root / "keep.txt").read_text(encoding="utf-8") == "staged\n"
    assert (build_root / "keep.txt").read_text(encoding="utf-8") == "build\n"
    assert not list(active_root.parent.glob(".app.candidate-*"))
    assert not output.exists()
    assert not (output.parent / ".release-channel-authority").exists()
    assert not (output.parent / module.VERIFICATION_PROGRAM_AUTHORITY_DIRECTORY_NAME).exists()


def test_incomplete_activation_journal_blocks_staging_cleanup(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True)
    sentinel = staging_root / "must-survive.txt"
    sentinel.write_text("staged recovery tree\n", encoding="utf-8")
    journal_path = module.activation_transaction_journal_path(active_root)
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(module.OverlayActivationError) as raised:
        materialize_with_binding(
            module,
            tmp_path / "receipt.json",
            binding_root=tmp_path,
            source_root=source_root,
            staging_root=staging_root,
            active_root=active_root,
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
        )

    assert raised.value.reason == "incomplete_activation_transaction_requires_recovery"
    assert raised.value.recovery_path == journal_path
    assert sentinel.read_text(encoding="utf-8") == "staged recovery tree\n"


def test_materialize_does_not_activate_when_verification_fails(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    active_root.mkdir(parents=True, exist_ok=True)
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")

    def fake_run(command, *, cwd):
        staging_root.mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        return make_completed(stdout="publish ok\n")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        verification_receipt_path.write_text(json.dumps({"status": "fail"}), encoding="utf-8")
        return {
            "status": "fail",
            "reason": "verification_failed",
            "baseUrl": "http://127.0.0.1:5003",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 1,
            "receiptStatus": "fail",
            "probeError": "",
            "landingMarkerStatus": "fail",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": False,
                "turnAnchorNormalizedHash": False,
                "turnAnchorRedirect": False,
            },
            "landingMissingMarkers": [
                "#turn-runsite-card",
                'const normalizedHash = window.location.hash.split("?")[0];',
                "window.location.replace(`/mobile/player${window.location.search}${normalizedHash}`);",
            ],
            "landingBrowserRedirect": {
                "status": "fail",
                "reason": "browser_redirect_failed",
                "entryUrl": "http://127.0.0.1:5003/#turn-runsite-card",
                "finalUrl": "",
                "expectedPath": "/mobile/player",
                "expectedHash": "#turn-runsite-card",
                "pathMatches": False,
                "hashMatches": False,
                "error": "timed out",
                "title": "",
                "heading": "",
            },
        }

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        run_command_fn=fake_run,
        verify_overlay_fn=fake_verify,
    )

    assert payload["status"] == "fail"
    assert payload["activationStatus"] == "staged_only"
    assert payload["stagingBuildInfoPath"]
    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert payload["backupPath"] == ""


def test_materialize_activates_when_verification_receipt_allows_overlay_activation(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    active_root.mkdir(parents=True, exist_ok=True)
    (active_root / "old.txt").write_text("old\n", encoding="utf-8")

    def fake_run(command, *, cwd):
        staging_root.mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        (staging_root / "new.txt").write_text("new\n", encoding="utf-8")
        return make_completed(stdout="publish ok\n")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        verification_receipt_path.write_text(
            json.dumps(
                {
                    "status": "fail",
                    "failures": [
                        "release channel supportabilityState is not launch-supported",
                        "release channel rolloutState is blocking: coverage_incomplete",
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {
            "status": "fail",
            "reason": "verification_failed",
            "baseUrl": "http://127.0.0.1:5003",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 1,
            "receiptStatus": "fail",
            "receiptAllowsOverlayActivation": True,
            "probeError": "",
            "landingMarkerStatus": "pass",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": True,
                "turnAnchorNormalizedHash": True,
                "turnAnchorRedirect": True,
            },
            "landingMissingMarkers": [],
            "landingBrowserRedirect": passing_browser_redirect(),
        }

    with pytest.raises(RuntimeError, match="non-production publisher callbacks cannot activate"):
        materialize_with_binding(
            module,
            output,
            binding_root=tmp_path,
            source_root=source_root,
            staging_root=staging_root,
            active_root=active_root,
            backup_root=backup_root,
            build_root=build_root,
            activate=True,
            run_command_fn=fake_run,
            verify_overlay_fn=fake_verify,
        )

    assert (active_root / "old.txt").read_text(encoding="utf-8") == "old\n"
    assert not (active_root / "new.txt").exists()
    assert not staging_root.exists()
    assert not output.exists()


def test_materialize_preserves_existing_published_wwwroot_files(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"

    def fake_run(command, *, cwd):
        (staging_root / "wwwroot" / "media" / "product").mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        (staging_root / "wwwroot" / "pwa-icon.svg").write_text("published\n", encoding="utf-8")
        (staging_root / "wwwroot" / "site.webmanifest").write_text("published manifest\n", encoding="utf-8")
        (staging_root / "wwwroot" / "media" / "product" / "proof-builder-trail.png").write_text(
            "published png\n",
            encoding="utf-8",
        )
        return make_completed(stdout="publish ok\n")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        verification_receipt_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        return {
            "status": "pass",
            "reason": "",
            "baseUrl": "http://127.0.0.1:5004",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 0,
            "receiptStatus": "pass",
            "probeError": "",
            "landingMarkerStatus": "pass",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": True,
                "turnAnchorNormalizedHash": True,
                "turnAnchorRedirect": True,
            },
            "landingMissingMarkers": [],
            "landingBrowserRedirect": passing_browser_redirect(),
        }

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        run_command_fn=fake_run,
        verify_overlay_fn=fake_verify,
    )

    assert payload["status"] == "test_only"
    assert payload["testOutcomeStatus"] == "pass"
    assert payload["testOnly"] is True
    assert payload["authoritativeReceipt"] is False
    assert payload["copiedSourceWwwroot"] is False
    assert (staging_root / "wwwroot" / "pwa-icon.svg").read_text(encoding="utf-8") == "published\n"
    assert (staging_root / "wwwroot" / "site.webmanifest").read_text(encoding="utf-8") == "published manifest\n"
    assert (
        staging_root / "wwwroot" / "media" / "product" / "proof-builder-trail.png"
    ).read_text(encoding="utf-8") == "published png\n"


def test_materialize_reuses_existing_staging_overlay_without_republish(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    build_info_path = write_staged_build_info(module, staging_root, source_root)

    def fake_run(command, *, cwd):
        raise AssertionError("publish should be skipped when reusing staging")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        verification_receipt_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        return {
            "status": "pass",
            "reason": "",
            "baseUrl": "http://127.0.0.1:5005",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 0,
            "receiptStatus": "pass",
            "probeError": "",
            "landingMarkerStatus": "pass",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": True,
                "turnAnchorNormalizedHash": True,
                "turnAnchorRedirect": True,
            },
            "landingMissingMarkers": [],
            "landingBrowserRedirect": passing_browser_redirect(),
        }

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        reuse_staging=True,
        run_command_fn=fake_run,
        verify_overlay_fn=fake_verify,
    )

    assert payload["status"] == "test_only"
    assert payload["testOutcomeStatus"] == "pass"
    assert payload["testOnly"] is True
    assert payload["authoritativeReceipt"] is False
    assert payload["reuseStaging"] is True
    assert payload["publish"]["skipped"] is True
    assert payload["publish"]["skipReason"] == "reused_existing_staging_overlay"
    assert payload["stagingSourceFingerprintCheck"]["status"] == "pass"
    assert payload["stagingSourceFingerprintCheck"]["matchesCurrentSource"] is True
    assert payload["copiedCodexDesign"] is True
    assert payload["copiedSourceWwwroot"] is True
    assert payload["verificationProgramsMatch"] is True
    assert payload["verification"]["receiptProgramBindingsMatch"] is True
    assert payload["verificationPrograms"]["status"] == "pass"
    assert (staging_root / ".codex-design" / "marker.txt").read_text(encoding="utf-8") == "design\n"


def test_staged_source_fingerprint_rejects_duplicate_build_info_fields(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    staging_root.mkdir(parents=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    build_info_path = write_staged_build_info(module, staging_root, source_root)
    original = build_info_path.read_text(encoding="utf-8")
    build_info_path.write_text(
        original.replace("{", '{"sourceFingerprint":null,', 1),
        encoding="utf-8",
    )

    check = module.staged_source_fingerprint_check(staging_root, source_root)

    assert check["status"] == "fail"
    assert check["reason"] == "staging_build_info_invalid"
    assert check["matchesCurrentSource"] is False


@pytest.mark.parametrize("contract_defect", ["wrong_algorithm", "missing_critical_file"])
def test_materialize_fails_closed_before_reusing_incomplete_fingerprint_contract(
    tmp_path: Path,
    contract_defect: str,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    recorded = module.source_fingerprint(source_root)
    if contract_defect == "wrong_algorithm":
        recorded["buildInputs"]["algorithm"] = "sha256-path-only-v0"
    else:
        del recorded["files"]["landing"]
    build_info_path = write_staged_build_info(
        module,
        staging_root,
        source_root,
        source_fingerprint=recorded,
    )

    def fail_verify(*args, **kwargs):
        raise AssertionError("invalid reuse fingerprint must fail before verification")

    payload = materialize_with_binding(
        module,
        tmp_path / "receipt.json",
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
        reuse_staging=True,
        verify_overlay_fn=fail_verify,
    )

    assert payload["status"] == "fail"
    assert payload["publish"]["skipReason"] == "staging_source_fingerprint_mismatch"
    assert payload["stagingSourceFingerprintCheck"]["matchesCurrentSource"] is False
    assert not active_root.exists()


def test_materialize_fails_closed_before_reusing_tampered_staged_payload(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    write_staged_build_info(module, staging_root, source_root)
    tamper = staging_root / "unverified-tamper.bin"
    tamper.write_text("tampered\n", encoding="utf-8")
    tamper.chmod(0o644)

    def fail_verify(*args, **kwargs):
        raise AssertionError("tampered staged bytes must fail before verification")

    payload = materialize_with_binding(
        module,
        tmp_path / "receipt.json",
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
        reuse_staging=True,
        verify_overlay_fn=fail_verify,
    )

    assert payload["status"] == "fail"
    assert payload["publish"]["skipReason"] == "staging_payload_mode_receipt_mismatch"
    assert payload["stagingSourceFingerprintCheck"][
        "stagedPayloadMatchesRecordedFingerprint"
    ] is False
    assert payload["stagingSourceFingerprintCheck"]["payloadModeBinding"]["status"] == "fail"
    assert not active_root.exists()


def test_materialize_fails_closed_when_reused_staging_fingerprint_is_stale(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    build_info_path = write_staged_build_info(module, staging_root, source_root)
    (source_root / "Chummer.Run.Api" / "Program.cs").write_text("changed program\n", encoding="utf-8")

    def fake_run(command, *, cwd):
        raise AssertionError("publish should not run when reuse-staging is explicit")

    def fake_verify(*args, **kwargs):
        raise AssertionError("stale staging must fail before verification or activation")

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        reuse_staging=True,
        run_command_fn=fake_run,
        verify_overlay_fn=fake_verify,
    )

    assert payload["status"] == "fail"
    assert payload["activationStatus"] == "not_requested"
    assert payload["publish"]["skipReason"] == "staging_source_fingerprint_mismatch"
    assert payload["stagingSourceFingerprintCheck"]["status"] == "fail"
    assert payload["stagingSourceFingerprintCheck"]["matchesCurrentSource"] is False
    assert not active_root.exists()


def test_materialize_rechecks_source_fingerprint_after_verification_before_activation(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    build_info_path = write_staged_build_info(module, staging_root, source_root)

    def fake_run(command, *, cwd):
        raise AssertionError("publish should be skipped when reusing staging")

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        (source_root / "Chummer.Run.Api" / "Program.cs").write_text(
            "changed during verification\n",
            encoding="utf-8",
        )
        verification_receipt_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        return {
            "status": "pass",
            "reason": "",
            "baseUrl": "http://127.0.0.1:5005",
            "receiptPath": str(verification_receipt_path),
            "exitCode": 0,
            "receiptStatus": "pass",
            "probeError": "",
            "landingMarkerStatus": "pass",
            "landingMarkerChecks": {
                "playDisabledTarget": True,
                "playSignInRoute": True,
                "turnAnchor": True,
                "turnAnchorNormalizedHash": True,
                "turnAnchorRedirect": True,
            },
            "landingMissingMarkers": [],
            "landingBrowserRedirect": passing_browser_redirect(),
        }

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        reuse_staging=True,
        run_command_fn=fake_run,
        verify_overlay_fn=fake_verify,
    )

    staged_build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["activationStatus"] == "staged_only"
    assert payload["stagingSourceFingerprintCheck"]["status"] == "fail"
    assert payload["stagingSourceFingerprintCheck"]["reason"] == "source_changed_during_overlay_verification"
    assert staged_build_info["status"] == "fail"
    assert not active_root.exists()


def test_materialize_reports_payload_mode_drift_without_losing_failure_receipt(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    payload_file = staging_root / "Chummer.Run.Api.dll"
    payload_file.write_text("dll\n", encoding="utf-8")
    write_staged_build_info(module, staging_root, source_root)

    def fake_verify(staging, *, source_root, verify_timeout_seconds, verification_receipt_path):
        payload_file.chmod(0o755)
        return passing_overlay_verification(verification_receipt_path)

    payload = materialize_with_binding(
        module,
        tmp_path / "receipt.json",
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
        reuse_staging=True,
        verify_overlay_fn=fake_verify,
    )

    assert payload["status"] == "fail"
    assert payload["verification"]["reason"] == (
        "staging_payload_modes_changed_during_verification"
    )
    assert payload["payloadModeIntegrityCheck"]["status"] == "fail"
    assert payload["stagedPayloadIntegrityCheck"]["status"] == "fail"
    assert payload["stagedPayloadIntegrityCheck"]["afterVerification"] == {}
    assert payload["stagedPayloadIntegrityCheck"]["inspectionError"]
    assert not active_root.exists()


def test_materialize_fails_closed_when_overlay_payload_source_changes_during_copy(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "chummer.run-services"
    make_source_tree(source_root)
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"

    def fake_run(command, *, cwd):
        staging_root.mkdir(parents=True, exist_ok=True)
        (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
        return make_completed(stdout="publish ok\n")

    original_copy_optional_tree = module.copy_optional_tree

    def copy_and_mutate_live_source(source: Path, destination: Path) -> bool:
        copied = original_copy_optional_tree(source, destination)
        if destination.name == ".codex-design":
            (source_root / ".codex-design" / "marker.txt").write_text(
                "changed during overlay copy\n",
                encoding="utf-8",
            )
        return copied

    module.copy_optional_tree = copy_and_mutate_live_source

    def fail_verify(*args, **kwargs):
        raise AssertionError("source drift after overlay copy must skip verification")

    payload = materialize_with_binding(
        module,
        tmp_path / "receipt.json",
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=tmp_path / "backups",
        build_root=tmp_path / "build",
        run_command_fn=fake_run,
        verify_overlay_fn=fail_verify,
    )

    assert payload["status"] == "fail"
    assert payload["activationStatus"] == "staged_only"
    assert payload["verification"]["reason"] == "source_fingerprint_mismatch_after_overlay_copy"
    assert payload["stagingSourceFingerprintCheck"]["reason"] == "source_changed_during_overlay_copy"
    assert payload["stagingSourceFingerprintCheck"]["overlayPayloadInputsMatchCurrentSource"] is False
    assert not active_root.exists()


def test_materialize_rejects_symlink_alias_between_staging_and_active_roots(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    active_root = tmp_path / "overlay" / "app"
    active_root.mkdir(parents=True)
    sentinel = active_root / "must-survive.txt"
    sentinel.write_text("active\n", encoding="utf-8")
    staging_alias = tmp_path / "staging-alias"
    staging_alias.symlink_to(active_root, target_is_directory=True)

    with pytest.raises(RuntimeError, match="roots overlap"):
        materialize_with_binding(
            module,
            tmp_path / "receipt.json",
            binding_root=tmp_path,
            source_root=source_root,
            staging_root=staging_alias,
            active_root=active_root,
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
        )

    assert sentinel.read_text(encoding="utf-8") == "active\n"


def test_materialize_rejects_symlinked_active_root_without_touching_target(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    external_active = tmp_path / "external-active"
    external_active.mkdir()
    sentinel = external_active / "must-survive.txt"
    sentinel.write_text("active\n", encoding="utf-8")
    active_alias = tmp_path / "overlay" / "app"
    active_alias.parent.mkdir()
    active_alias.symlink_to(external_active, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink component"):
        materialize_with_binding(
            module,
            tmp_path / "receipt.json",
            binding_root=tmp_path,
            source_root=source_root,
            staging_root=tmp_path / "overlay-next" / "app",
            active_root=active_alias,
            backup_root=tmp_path / "backups",
            build_root=tmp_path / "build",
        )

    assert sentinel.read_text(encoding="utf-8") == "active\n"


def test_materialize_fails_closed_when_reuse_staging_requested_without_app_payload(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    make_source_tree(source_root)
    build_root = tmp_path / "build"
    staging_root = tmp_path / "overlay-next" / "app"
    active_root = tmp_path / "overlay" / "app"
    backup_root = tmp_path / "backups"
    output = tmp_path / "receipt.json"
    staging_root.mkdir(parents=True, exist_ok=True)

    def fake_run(command, *, cwd):
        raise AssertionError("publish should not run when reuse-staging is explicit")

    payload = materialize_with_binding(
        module,
        output,
        binding_root=tmp_path,
        source_root=source_root,
        staging_root=staging_root,
        active_root=active_root,
        backup_root=backup_root,
        build_root=build_root,
        reuse_staging=True,
        run_command_fn=fake_run,
    )

    assert payload["status"] == "fail"
    assert payload["publish"]["skipped"] is False
    assert payload["publish"]["skipReason"] == "staging_overlay_missing_app_dll"
    assert payload["verification"]["reason"] == "publish_failed"


class _FakeProcess:
    def __init__(self) -> None:
        self._returncode = None

    def poll(self):
        return self._returncode

    def terminate(self) -> None:
        self._returncode = 0

    def wait(self, timeout=None) -> int:
        self._returncode = 0
        return 0

    def kill(self) -> None:
        self._returncode = -9


def test_probe_landing_anchor_browser_redirect_returns_pass_when_hash_canonicalizes(monkeypatch) -> None:
    module = load_module()

    class FakeLocator:
        @property
        def first(self):
            return self

        def inner_text(self, timeout=None) -> str:
            return "Player entry"

    class FakePage:
        def __init__(self) -> None:
            self.url = "http://127.0.0.1:5010/mobile/player#turn-runsite-card"

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            assert url == (
                "http://127.0.0.1:5010/"
                "?sessionId=synthetic-probe&grant=synthetic-probe"
                "&tracking=synthetic-probe#turn-runsite-card?grant=synthetic-fragment"
            )
            assert wait_until == "domcontentloaded"
            assert 0 < timeout <= 5_000

        def wait_for_function(self, script: str, timeout: int) -> None:
            assert "currentUrl.pathname === '/mobile/player'" in script
            assert "currentUrl.hash === '#turn-runsite-card'" in script
            assert "currentUrl.search === ''" in script
            assert 0 < timeout <= 5_000

        def locator(self, selector: str) -> FakeLocator:
            assert selector == "h1"
            return FakeLocator()

        def title(self) -> str:
            return "Player entry · Chummer"

        def close(self) -> None:
            pass

    class FakeBrowser:
        def new_page(self, viewport: dict[str, int]) -> FakePage:
            assert viewport == {"width": 390, "height": 844}
            return FakePage()

        def close(self) -> None:
            pass

    class FakeChromium:
        def launch(self, headless: bool, timeout: int) -> FakeBrowser:
            assert headless is True
            assert 0 < timeout <= 5_000
            return FakeBrowser()

    class FakePlaywrightContext:
        def __enter__(self):
            return types.SimpleNamespace(chromium=FakeChromium())

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(Error=Exception, sync_playwright=lambda: FakePlaywrightContext()),
    )

    receipt = module.probe_landing_anchor_browser_redirect("http://127.0.0.1:5010", 5.0)

    assert receipt["status"] == "pass"
    assert receipt["entryUrl"] == (
        "http://127.0.0.1:5010/"
        "?sessionId=synthetic-probe&grant=synthetic-probe"
        "&tracking=synthetic-probe#turn-runsite-card?grant=synthetic-fragment"
    )
    assert receipt["finalUrl"] == "http://127.0.0.1:5010/mobile/player#turn-runsite-card"
    assert receipt["pathMatches"] is True
    assert receipt["hashMatches"] is True
    assert receipt["expectedQuery"] == ""
    assert receipt["finalQuery"] == ""
    assert receipt["queryDropped"] is True
    assert receipt["title"] == "Player entry · Chummer"
    assert receipt["heading"] == "Player entry"


def test_probe_landing_anchor_browser_redirect_falls_back_to_firefox(monkeypatch) -> None:
    module = load_module()
    launches: list[str] = []

    class FakeLocator:
        @property
        def first(self):
            return self

        def inner_text(self, timeout=None) -> str:
            return "Player entry"

    class FakePage:
        url = "http://127.0.0.1:5010/mobile/player#turn-runsite-card"

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            pass

        def wait_for_function(self, script: str, timeout: int) -> None:
            pass

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

        def title(self) -> str:
            return "Player entry"

        def close(self) -> None:
            pass

    class FakeBrowser:
        def new_page(self, viewport: dict[str, int]) -> FakePage:
            return FakePage()

        def close(self) -> None:
            pass

    class FakeChromium:
        def launch(self, headless: bool, timeout: int) -> FakeBrowser:
            launches.append("chromium")
            raise RuntimeError("chromium launch failed")

    class FakeFirefox:
        def launch(self, headless: bool, timeout: int) -> FakeBrowser:
            launches.append("firefox")
            return FakeBrowser()

    class FakePlaywrightContext:
        def __enter__(self):
            return types.SimpleNamespace(chromium=FakeChromium(), firefox=FakeFirefox())

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(Error=Exception, sync_playwright=lambda: FakePlaywrightContext()),
    )

    receipt = module.probe_landing_anchor_browser_redirect("http://127.0.0.1:5010", 5.0)

    assert receipt["status"] == "pass"
    assert receipt["browserName"] == "firefox"
    assert launches == ["chromium", "firefox"]


def test_build_overlay_verification_env_keeps_play_projection_absent() -> None:
    module = load_module()

    env = module.build_overlay_verification_env(
        "http://127.0.0.1:5010",
        "http://127.0.0.1:6123/",
    )

    assert "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED" not in env
    assert "CHUMMER_PUBLIC_PLAY_PROXY_URL" not in env
    assert env["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] == "http://127.0.0.1:6123/feedback"
    assert env["CHUMMER_PRODUCTLIFT_ROADMAP_URL"] == "http://127.0.0.1:6123/roadmap"
    assert env["GOOGLE_OIDC_CLIENT_ID"] == "local-overlay-proof-client"
    assert env["GOOGLE_OIDC_CLIENT_SECRET"] == "local-overlay-proof-secret"
    assert env["GOOGLE_OIDC_REDIRECT_URI"] == "http://127.0.0.1:5010/auth/google/callback"


def test_isolated_overlay_process_env_scrubs_every_inherited_retired_play_transport_name(tmp_path: Path) -> None:
    module = load_module()
    inherited = {
        name: "https://attacker.invalid/false-green"
        for name in module.RETIRED_PUBLIC_PLAY_PROXY_ENV_NAMES
    }
    inherited["CHUMMER_PUBLIC_PLAY_PROXY_ENABLED"] = "true"
    inherited["UNRELATED_SETTING"] = "preserved"

    env = module.build_isolated_overlay_process_env(
        inherited,
        base_url="http://127.0.0.1:5010",
        temp_root=tmp_path / "tmp",
        source_root=tmp_path / "source",
    )

    assert module.RETIRED_PUBLIC_PLAY_PROXY_ENV_NAMES.isdisjoint(env)
    assert env["UNRELATED_SETTING"] == "preserved"
    assert env["ASPNETCORE_URLS"] == "http://127.0.0.1:5010"


class _ReadinessResponse:
    def __init__(self, status: int, payload: object):
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


def test_overlay_readiness_probe_requires_combined_ready_and_disabled_projection() -> None:
    module = load_module()
    payload = {
        "ready": True,
        "status": "ready",
        "hub": {"ready": True, "status": "pass"},
        "playProjection": {"enabled": False, "ready": True, "status": "disabled"},
    }

    receipt = module.real_probe_overlay_readiness(
        "http://127.0.0.1:5010",
        5.0,
        open_url=lambda request, timeout: _ReadinessResponse(200, payload),
    )

    assert receipt["status"] == "pass"
    assert receipt["httpStatus"] == 200
    assert all(receipt["checks"].values())


@pytest.mark.parametrize(
    ("http_status", "body"),
    [
        (503, {"ready": True, "status": "ready", "hub": {"ready": True, "status": "pass"}, "playProjection": {"enabled": False, "ready": True, "status": "disabled"}}),
        (200, {"ready": False, "status": "not_ready", "hub": {"ready": True, "status": "pass"}, "playProjection": {"enabled": False, "ready": True, "status": "disabled"}}),
        (200, {"ready": True, "status": "ready", "hub": {"ready": True, "status": "pass"}, "playProjection": {"enabled": True, "ready": True, "status": "disabled"}}),
        (200, {"ready": True, "status": "ready", "hub": {"ready": True, "status": "pass"}, "playProjection": {"enabled": False, "ready": False, "status": "projection_retired_local_mirror_only"}}),
        (200, {"ready": True, "status": "ready", "playProjection": {"enabled": False, "ready": True, "status": "disabled"}}),
        (200, {"ready": True, "status": "ready", "hub": {"ready": False, "status": "fail"}, "playProjection": {"enabled": False, "ready": True, "status": "disabled"}}),
        (200, {"ready": True, "status": "ready", "hub": {"ready": True}, "playProjection": {"enabled": False, "ready": True, "status": "disabled"}}),
        (200, {"ready": True, "status": "ready", "hub": "pass", "playProjection": {"enabled": False, "ready": True, "status": "disabled"}}),
        (200, {"ready": True, "status": "ready", "hub": {"ready": True, "status": "pass"}}),
        (200, {"ready": True, "status": "ready", "hub": {"ready": True, "status": "pass"}, "playProjection": "disabled"}),
    ],
)
def test_overlay_readiness_probe_cannot_false_green_http_or_projection_drift(
    http_status: int,
    body: dict[str, object],
) -> None:
    module = load_module()

    receipt = module.real_probe_overlay_readiness(
        "http://127.0.0.1:5010",
        5.0,
        open_url=lambda request, timeout: _ReadinessResponse(http_status, body),
    )

    assert receipt["status"] == "fail"
    assert not all(receipt["checks"].values())


def test_runtime_dependency_stub_cannot_supply_play_html_or_executable_assets() -> None:
    module = load_module()
    stub = module.LocalPublicRuntimeDependencyStub()

    mobile_payload, mobile_type = stub._build_payload("/mobile/player")
    script_payload, script_type = stub._build_payload("/mobile-turn-companion.js")

    assert mobile_type == "text/html; charset=utf-8"
    assert script_type == "text/html; charset=utf-8"
    assert b"data-turn-root" not in mobile_payload
    assert b"mobile-turn-companion.js" not in mobile_payload
    assert b"console.log" not in script_payload


def test_verify_published_overlay_forces_probe_urls_and_clears_port_overrides(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5015)
    monkeypatch.setenv("HTTP_PORTS", "8080")
    monkeypatch.setenv("HTTPS_PORTS", "8443")
    monkeypatch.setenv("ASPNETCORE_HTTP_PORTS", "8081")
    monkeypatch.setenv("ASPNETCORE_HTTPS_PORTS", "8444")
    monkeypatch.setenv("CHUMMER_PUBLIC_PLAY_PROXY_ENABLED", "true")
    monkeypatch.setenv("CHUMMER_PUBLIC_PLAY_PROXY_URL", "https://attacker.invalid/")
    monkeypatch.setenv("CHUMMER_PUBLIC_PLAY_PROXY_API_KEY", "must-not-survive")
    monkeypatch.setenv("CHUMMER_PUBLIC_PLAY_PROXY_ALLOWED_ORIGINS", "https://attacker.invalid/")

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return passing_landing_body(module)
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module, "probe_landing_anchor_browser_redirect", lambda base_url, timeout_seconds: passing_browser_redirect())
    monkeypatch.setattr(module, "verify_local_live_surface_parity", lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding))

    captured_env: dict[str, str] = {}

    def fake_popen(*args, **kwargs):
        nonlocal captured_env
        captured_env = dict(kwargs["env"])
        return _FakeProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    captured_command: list[str] = []
    captured_child_timeout: list[float] = []

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds, timeout):
        captured_command.extend(command)
        captured_child_timeout.append(timeout)
        assert len(pass_fds) == 1
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "pass"
    assert captured_env["ASPNETCORE_URLS"] == "http://127.0.0.1:5015"
    assert captured_env["URLS"] == "http://127.0.0.1:5015"
    assert "HTTP_PORTS" not in captured_env
    assert "HTTPS_PORTS" not in captured_env
    assert "ASPNETCORE_HTTP_PORTS" not in captured_env
    assert "ASPNETCORE_HTTPS_PORTS" not in captured_env
    assert module.RETIRED_PUBLIC_PLAY_PROXY_ENV_NAMES.isdisjoint(captured_env)
    assert receipt["combinedReadiness"]["status"] == "pass"
    receipt_arg_index = captured_command.index("--release-channel-receipt")
    digest_arg_index = captured_command.index("--release-channel-receipt-sha256")
    invocation_arg_index = captured_command.index("--invocation-id")
    assert captured_command[receipt_arg_index + 1] == str(release_channel_receipt)
    assert captured_command[digest_arg_index + 1] == release_channel_receipt_sha256
    assert len(captured_command[invocation_arg_index + 1]) == 32
    assert len(captured_child_timeout) == 1
    assert 0 < captured_child_timeout[0] <= 5.0
    assert captured_command[1] == "-c"
    assert captured_command[2] == module.SEALED_PYTHON_PROGRAM_WRAPPER
    assert captured_command[4] == receipt["verifierProgramExecutionSha256Expected"]
    assert captured_command[5] == str(module.DOWNLOADS_VERSION_MARKER_SCRIPT_PATH)
    assert receipt["receiptBindingMatchesSelectedInput"] is True
    assert receipt["receiptInvocationMatchesCurrent"] is True
    assert receipt["receiptProcessResultConsistent"] is True
    assert receipt["passReceiptContractSatisfied"] is True
    assert receipt["releaseChannelReceiptSha256Actual"] == release_channel_receipt_sha256
    assert receipt["verificationProgramsMatch"] is True
    assert receipt["receiptProgramBindingsMatch"] is True
    assert receipt["verifierProgramExecutionMode"] == "sealed_memfd_from_content_addressed_snapshot"
    assert receipt["verifierProgramExecutionSha256Expected"] == receipt[
        "verifierProgramExecutionSha256Actual"
    ]
    assert receipt["verifierProgramExecutionSha256Matches"] is True
    assert receipt["verifierProgramSnapshotExecuted"].endswith(
        f".{receipt['verifierProgramExecutionSha256Actual']}.py"
    )
    assert receipt["parityProgramSnapshotImported"] == receipt["verificationPrograms"][
        "programs"
    ]["liveSurfaceParity"]["snapshotPath"]
    child_receipt = json.loads(verification_receipt_path.read_text(encoding="utf-8"))
    assert child_receipt["publisher_verification_programs_match"] is True
    assert child_receipt["publisher_verification_programs"] == receipt["verificationPrograms"]
    assert len(child_receipt["publisher_child_receipt_sha256_before_program_binding"]) == 64
    production_evidence = module.production_verification_evidence(
        receipt,
        receipt["verificationPrograms"],
        verification_receipt_path,
    )
    assert production_evidence["status"] == "pass"
    assert all(production_evidence["checks"].values())


def test_pass_receipt_contract_rejects_binding_only_pass_shape(tmp_path: Path) -> None:
    module = load_module()
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    assert module.pass_receipt_satisfies_overlay_contract(
        {
            "status": "pass",
            **child_binding_fields(
                release_channel_receipt,
                release_channel_receipt_sha256,
            ),
        }
    ) is False


def test_verify_published_overlay_rejects_pass_receipt_without_selected_input_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5016)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return "\n".join(module.REQUIRED_LANDING_MARKERS.values())
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(
        module,
        "probe_landing_anchor_browser_redirect",
        lambda base_url, timeout_seconds: passing_browser_redirect(),
    )
    monkeypatch.setattr(
        module,
        "verify_local_live_surface_parity",
        lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding),
    )

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        verification_receipt_path.write_text(
            json.dumps({"status": "pass"}),
            encoding="utf-8",
        )
        return make_completed(stdout="unbound pass-shaped receipt\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "verification_failed"
    assert receipt["receiptStatus"] == "pass"
    assert receipt["receiptBindingMatchesSelectedInput"] is False


def test_verify_published_overlay_rejects_preexisting_pass_receipt_when_child_crashes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)
    write_child_verification_receipt(
        verification_receipt_path,
        release_channel_receipt,
        release_channel_receipt_sha256,
        "stale-prior-invocation",
    )

    monkeypatch.setattr(module, "pick_free_port", lambda: 5017)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return "\n".join(module.REQUIRED_LANDING_MARKERS.values())
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(
        module,
        "probe_landing_anchor_browser_redirect",
        lambda base_url, timeout_seconds: passing_browser_redirect(),
    )
    monkeypatch.setattr(
        module,
        "verify_local_live_surface_parity",
        lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding),
    )

    def crashing_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        assert not verification_receipt_path.exists()
        return make_completed(stderr="child verifier crashed\n", returncode=2)

    monkeypatch.setattr(module.subprocess, "run", crashing_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "verification_failed"
    assert receipt["exitCode"] == 2
    assert receipt["receiptStatus"] == ""
    assert receipt["receiptInvocationMatchesCurrent"] is False
    assert receipt["receiptProcessResultConsistent"] is False
    assert not verification_receipt_path.exists()


def test_verify_published_overlay_requires_public_install_handoffs_and_query_dropping_redirect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5011)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return passing_landing_body(module)
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(module, "probe_landing_anchor_browser_redirect", lambda base_url, timeout_seconds: passing_browser_redirect())
    monkeypatch.setattr(module, "verify_local_live_surface_parity", lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding))

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
            status_redirect_heading="Stable downloads",
            status_redirect_heading_expected="Stable downloads",
            downloads_has_marker=True,
            status_redirect_has_marker=True,
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "pass"
    assert receipt["landingMarkerStatus"] == "pass"
    assert receipt["landingMissingMarkers"] == []
    assert receipt["landingForbiddenMarkers"] == []
    assert receipt["landingMarkerChecks"]["buildPublicInstallHandoff"] is True
    assert receipt["landingMarkerChecks"]["playPublicInstallHandoff"] is True
    assert receipt["landingMarkerChecks"]["turnAnchorNormalizedHash"] is True
    assert receipt["landingMarkerChecks"]["turnAnchorRedirect"] is True
    assert all(receipt["landingForbiddenMarkerChecks"].values())
    assert receipt["landingBrowserRedirect"]["status"] == "pass"
    assert receipt["landingBrowserRedirect"]["finalQuery"] == ""
    assert receipt["landingBrowserRedirect"]["queryDropped"] is True
    assert receipt["receiptSummary"]["landingHasBuildPublicInstallHandoff"] is True
    assert receipt["receiptSummary"]["landingHasPlayPublicInstallHandoff"] is True
    assert receipt["receiptSummary"]["landingRetiredMarkersAbsent"] is True
    assert receipt["receiptSummary"]["landingHasTurnAnchorRedirect"] is True
    assert receipt["receiptSummary"]["landingBrowserRedirectStatus"] == "pass"
    assert receipt["receiptSummary"]["landingBrowserRedirectExpectedQuery"] == ""
    assert receipt["receiptSummary"]["landingBrowserRedirectFinalQuery"] == ""
    assert receipt["receiptSummary"]["landingBrowserRedirectQueryDropped"] is True
    assert receipt["localLiveSurfaceParity"]["status"] == "pass"


def test_verify_published_overlay_allows_release_posture_only_receipt_failures(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5012)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Preview downloads</h1>"
        if path == "/":
            return passing_landing_body(module)
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(module, "probe_landing_anchor_browser_redirect", lambda base_url, timeout_seconds: passing_browser_redirect())
    monkeypatch.setattr(module, "verify_local_live_surface_parity", lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding))

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        payload = {
            "status": "fail",
            "contractName": "chummer.downloads_version_marker.bound.v1",
            "invocation_id": command[command.index("--invocation-id") + 1],
            "failures": [
                "release channel supportabilityState is not launch-supported",
                "release channel rolloutState is blocking: coverage_incomplete",
            ],
            "downloads_has_marker": True,
            "status_redirect_has_marker": True,
            "downloads_version_marker_matches_release_channel": True,
            "status_redirect_version_marker_matches_release_channel": True,
            "status_redirect_heading_matches_release_channel": True,
            "status_redirect_heading_recognized": True,
            "status_redirect_heading_uses_generic_updated_copy": False,
            "visible_version_matches_release_channel": True,
            "public_release_manifest_exists": True,
            "public_release_channel_matches_release_channel": True,
            "public_release_status_matches_release_channel": True,
            "public_release_version_matches_release_channel": True,
            "public_release_published_at_matches_release_channel": True,
            "public_release_proof_freshness_matches_release_channel": True,
            "public_release_supportability_matches_release_channel": True,
            "public_release_rollout_matches_release_channel": True,
            "public_release_copy_safe": True,
            "public_release_has_preview_or_review_caveat": True,
            "release_manifest_channel_matches_release_channel": True,
            "release_manifest_status_matches_release_channel": True,
            "release_manifest_version_matches_release_channel": True,
            "release_manifest_published_at_matches_release_channel": True,
            "release_manifest_proof_freshness_matches_release_channel": True,
            "release_manifest_supportability_compatible_with_release_channel": True,
            "release_manifest_rollout_compatible_with_release_channel": True,
            "release_manifest_internal_supportability_consistent": True,
            "release_manifest_copy_safe": True,
            "release_manifest_has_preview_or_review_caveat": True,
            "downloads_status": 200,
            "status_status": 200,
            "release_manifest_http_status": 200,
            "status_redirect_heading": "Preview downloads",
            "status_redirect_heading_expected": "Preview downloads",
            **child_binding_fields(
                release_channel_receipt,
                release_channel_receipt_sha256,
            ),
        }
        verification_receipt_path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return make_completed(stdout="verify posture-only fail\n", returncode=1)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "pass"
    assert receipt["reason"] == ""
    assert receipt["receiptStatus"] == "fail"
    assert receipt["receiptAllowsOverlayActivation"] is True
    assert receipt["receiptSummary"]["receiptAllowsOverlayActivation"] is True
    assert receipt["localLiveSurfaceParity"]["status"] == "pass"


def test_verify_published_overlay_rejects_retired_play_gate_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5012)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return passing_landing_body(module) + '\ndata-disabled-target="/mobile/player"'
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(
        module,
        "probe_landing_anchor_browser_redirect",
        lambda base_url, timeout_seconds: passing_browser_redirect(),
    )
    monkeypatch.setattr(
        module,
        "verify_local_live_surface_parity",
        lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding),
    )

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "landing_forbidden_marker_present"
    assert receipt["landingMarkerStatus"] == "fail"
    assert 'data-disabled-target="/mobile/player"' in receipt["landingForbiddenMarkers"]
    assert receipt["landingForbiddenMarkerChecks"]["playDisabledTarget"] is False
    assert receipt["receiptSummary"]["landingRetiredMarkersAbsent"] is False


def test_verify_published_overlay_fails_when_landing_anchor_redirect_marker_is_missing(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5012)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return "\n".join(
                marker
                for name, marker in module.REQUIRED_LANDING_MARKERS.items()
                if name != "turnAnchorRedirect"
            )
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(module, "probe_landing_anchor_browser_redirect", lambda base_url, timeout_seconds: passing_browser_redirect())
    monkeypatch.setattr(module, "verify_local_live_surface_parity", lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding))

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "landing_marker_missing"
    assert receipt["landingMarkerStatus"] == "fail"
    assert "window.location.replace(`/mobile/player${normalizedHash}`);" in receipt[
        "landingMissingMarkers"
    ]
    assert receipt["receiptSummary"]["landingHasTurnAnchorRedirect"] is False


def test_verify_published_overlay_fails_when_browser_redirect_does_not_canonicalize_anchor(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5013)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return passing_landing_body(module)
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(
        module,
        "probe_landing_anchor_browser_redirect",
        lambda base_url, timeout_seconds: {
            "status": "fail",
            "reason": "browser_redirect_failed",
            "entryUrl": f"{base_url}/#turn-runsite-card",
            "finalUrl": f"{base_url}/#turn-runsite-card",
            "expectedPath": "/mobile/player",
            "expectedHash": "#turn-runsite-card",
            "pathMatches": False,
            "hashMatches": False,
            "error": "page.wait_for_function: Timeout 5000ms exceeded.",
            "title": "Chummer",
            "heading": "Chummer",
        },
    )
    monkeypatch.setattr(module, "verify_local_live_surface_parity", lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding))

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "landing_browser_redirect_failed"
    assert receipt["landingBrowserRedirect"]["status"] == "fail"
    assert receipt["receiptSummary"]["landingBrowserRedirectStatus"] == "fail"
    assert receipt["receiptSummary"]["landingBrowserRedirectPathMatches"] is False
    assert receipt["receiptSummary"]["landingBrowserRedirectHashMatches"] is False


def test_verify_published_overlay_fails_when_browser_redirect_leaks_synthetic_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5013)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return passing_landing_body(module)
        raise AssertionError(f"unexpected path {path}")

    leaked_query = "sessionId=synthetic-probe&grant=synthetic-probe&tracking=synthetic-probe"
    redirect_receipt = passing_browser_redirect()
    redirect_receipt.update(
        {
            "finalUrl": f"http://127.0.0.1:5000/mobile/player?{leaked_query}#turn-runsite-card",
            "finalQuery": leaked_query,
            "queryDropped": False,
        }
    )

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(
        module,
        "probe_landing_anchor_browser_redirect",
        lambda base_url, timeout_seconds: redirect_receipt,
    )
    monkeypatch.setattr(
        module,
        "verify_local_live_surface_parity",
        lambda base_url, output_path, program_binding: passing_live_surface_parity(program_binding),
    )

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "landing_browser_redirect_failed"
    assert receipt["landingBrowserRedirect"]["expectedQuery"] == ""
    assert receipt["landingBrowserRedirect"]["finalQuery"] == leaked_query
    assert receipt["landingBrowserRedirect"]["queryDropped"] is False
    assert receipt["receiptSummary"]["landingBrowserRedirectFinalQuery"] == leaked_query
    assert receipt["receiptSummary"]["landingBrowserRedirectQueryDropped"] is False


def test_verify_published_overlay_fails_when_local_live_surface_parity_fails(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    staging_root = tmp_path / "overlay" / "app"
    staging_root.mkdir(parents=True, exist_ok=True)
    (staging_root / "Chummer.Run.Api.dll").write_text("dll\n", encoding="utf-8")
    verification_receipt_path = tmp_path / "verify.json"
    release_channel_receipt, release_channel_receipt_sha256 = write_release_channel_receipt(tmp_path)

    monkeypatch.setattr(module, "pick_free_port", lambda: 5014)

    def fake_wait_for_http(base_url: str, path: str, timeout_seconds: float) -> str:
        if path.startswith("/http_api/posts"):
            return '{"data":[],"total":0}'
        if path == "/status":
            return "<h1>Status</h1>"
        if path == "/":
            return passing_landing_body(module)
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(module, "wait_for_http", fake_wait_for_http)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    monkeypatch.setattr(module, "probe_landing_anchor_browser_redirect", lambda base_url, timeout_seconds: passing_browser_redirect())
    monkeypatch.setattr(
        module,
        "verify_local_live_surface_parity",
        lambda base_url, output_path, program_binding: {
            "status": "fail",
            "receiptPath": str(output_path),
            "failureCount": 2,
            "failures": ["/mobile: missing required text: Live-session turn companion"],
            "verdict": "LIVE_SURFACE_PARITY_NOT_READY",
            "programBinding": program_binding,
            "programBindingMatches": True,
            "programSnapshotImported": str(program_binding["snapshotPath"]),
        },
    )

    def fake_run(command, *, cwd, check, text, stdout, stderr, pass_fds):
        write_child_verification_receipt(
            verification_receipt_path,
            release_channel_receipt,
            release_channel_receipt_sha256,
            command[command.index("--invocation-id") + 1],
        )
        return make_completed(stdout="verify ok\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.verify_published_overlay(
        staging_root,
        source_root=tmp_path / "source",
        verify_timeout_seconds=5.0,
        verification_receipt_path=verification_receipt_path,
        release_channel_receipt=release_channel_receipt,
        release_channel_receipt_sha256=release_channel_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["reason"] == "live_surface_parity_failed"
    assert receipt["localLiveSurfaceParity"]["status"] == "fail"
    assert receipt["receiptSummary"]["localLiveSurfaceParityFailureCount"] == 2


def test_wait_for_http_uses_the_full_verification_budget_for_each_request(monkeypatch) -> None:
    module = load_module()
    observed_timeouts: list[float] = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b"ok"

    def fake_urlopen(request, timeout):
        observed_timeouts.append(float(timeout))
        return _FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    body = module.wait_for_http("http://127.0.0.1:5010", "/status", 8.5)

    assert body == "ok"
    assert observed_timeouts
    assert observed_timeouts[0] > 8.0


def test_local_public_runtime_dependency_stub_serves_participate_snapshot_json() -> None:
    module = load_module()

    with module.LocalPublicRuntimeDependencyStub() as stub:
        request = module.Request(
            f"{stub.base_url}/http_api/posts?tab=feedback",
            headers={"User-Agent": "pytest"},
        )
        with module.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            content_type = response.headers.get("Content-Type", "")

    assert "application/json" in content_type
    assert payload == {"data": [], "total": 0}
