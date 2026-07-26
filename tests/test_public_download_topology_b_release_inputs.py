from __future__ import annotations

from decimal import Decimal
import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = ROOT / "scripts" / "deploy_public_download_only_cutover.py"
WRAPPER_PATH = ROOT / "scripts" / "deploy_public_edge_portal.sh"


def load_controller() -> Any:
    spec = importlib.util.spec_from_file_location(
        "topology_b_release_input_contract",
        CONTROLLER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_controller()
candidate_scanner = controller.load_module(
    ROOT / "scripts" / "release" / "materialize_candidate_import_authority.py",
    "topology_b_release_input_candidate_scanner",
)


def projection_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "projection"
    root.mkdir()
    (root / "PUBLIC_PROJECTION_MANIFEST.generated.json").write_text(
        '{"schema":"fixture","snapshotId":"public-projection-semantic"}\n',
        encoding="utf-8",
    )
    (root / "projection.bin").write_bytes(b"projection source bytes\n")
    semantic_sha256 = "fa691b" + "0" * 58
    source_tree_sha256 = controller.tree_sha256_file_stream(
        root,
        label="authentic projection source fixture",
    )
    assert semantic_sha256 != source_tree_sha256
    return root, semantic_sha256, source_tree_sha256


def test_projection_semantic_identity_is_distinct_from_source_tree_digest(
    tmp_path: Path,
) -> None:
    projection_root, semantic_sha256, source_tree_sha256 = projection_fixture(
        tmp_path
    )
    annotations = controller.SidecarConfig.__annotations__
    assert "projection_authority_root" in annotations
    assert "projection_current_sha256" in annotations
    assert "projection_snapshot_sha256" in annotations
    assert "projection_source_tree_sha256" in annotations

    operation_root = tmp_path / "operation"
    operation_root.mkdir()
    volume_names = {
        logical: f"fixture-{logical}"
        for logical in controller.SIDECAR_LOGICAL_VOLUMES
    }
    config = SimpleNamespace(
        sidecar_certificate=operation_root / "sidecar.pfx",
        sidecar_certificate_password=operation_root / "sidecar.password",
        overlay_staging_root=operation_root / "app",
        fleet_source=operation_root / "fleet",
        fleet_sha256="1" * 64,
        shelf_source=operation_root / "shelf",
        projection_authority_root=projection_root.parent,
        projection_current_sha256="8" * 64,
        projection_snapshot_root=projection_root,
        projection_snapshot_id=f"public-projection-{semantic_sha256}",
        projection_snapshot_sha256=semantic_sha256,
        projection_source_tree_sha256=source_tree_sha256,
        runtime_proof_source=operation_root / "runtime-proof.json",
        runtime_proof_sha256="2" * 64,
        final_gold_source=operation_root / "final-gold.json",
        final_gold_sha256="3" * 64,
        volume_names=volume_names,
    )

    environment = controller._sidecar_compose_environment(
        config,
        dp={
            "certificateSha256": "4" * 64,
            "passwordSha256": "5" * 64,
        },
        app_overlay_sha256="6" * 64,
        shelf={"shelfTreeSha256": "7" * 64},
    )

    assert config.projection_snapshot_id == (
        f"public-projection-{semantic_sha256}"
    )
    assert environment[
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256"
    ] == source_tree_sha256
    assert environment[
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"
    ] == str(projection_root.parent)
    assert environment[
        "CHUMMER_PUBLIC_EDGE_PROJECTION_CURRENT_SHA256"
    ] == "8" * 64
    assert environment[
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ID"
    ] == config.projection_snapshot_id
    assert source_tree_sha256 != semantic_sha256


def candidate_current_payload(
    snapshot_id: str,
    snapshot_sha256: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    names = (
        "HUB_LOCAL_RELEASE_PROOF.generated.json",
        "HUB_SERVED_RELEASE_PROOF.generated.json",
        "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
        "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
        "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
        "RELEASE_CHANNEL.generated.json",
        "FLAGSHIP_PRODUCT_READINESS.generated.json",
        "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json",
    )
    return {
        "contractName": "chummer.public_projection_current/v1",
        "status": "candidate_import_ready",
        "projectionStage": "candidate_import_ready",
        "codeDeploymentAuthority": False,
        "releaseUploadAuthority": False,
        "candidateImportAuthority": True,
        "releaseGateFindings": [],
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "manifestRelativePath": (
            f"{snapshot_id}/PUBLIC_PROJECTION_SNAPSHOT.generated.json"
        ),
        "manifestSha256": manifest_sha256,
        "outputs": {name: f"{snapshot_id}/{name}" for name in names},
    }


def projection_current_binding_fixture(
    tmp_path: Path,
) -> tuple[SimpleNamespace, Path]:
    snapshot_sha256 = "1" * 64
    snapshot_id = f"public-projection-{snapshot_sha256}"
    manifest_sha256 = "2" * 64
    authority_root = tmp_path / "published"
    snapshot_root = authority_root / snapshot_id
    snapshot_root.mkdir(parents=True)
    current = authority_root / "CURRENT.json"
    current.write_text(
        json.dumps(
            candidate_current_payload(
                snapshot_id,
                snapshot_sha256,
                manifest_sha256,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    current.chmod(0o644)
    config = SimpleNamespace(
        projection_authority_root=authority_root,
        projection_current_sha256=hashlib.sha256(
            current.read_bytes()
        ).hexdigest(),
        projection_snapshot_root=snapshot_root,
        projection_snapshot_id=snapshot_id,
        projection_snapshot_sha256=snapshot_sha256,
        projection_manifest_sha256=manifest_sha256,
    )
    return config, current


def test_candidate_projection_current_binds_the_nested_runtime_authority(
    tmp_path: Path,
) -> None:
    config, _current = projection_current_binding_fixture(tmp_path)

    controller._validate_projection_current_binding(config)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("flattened", "outside the authenticated authority root"),
        ("status", "does not bind the selected candidate-import snapshot"),
        ("digest", "CURRENT digest drifted"),
        ("output-extra", "does not bind the selected candidate-import snapshot"),
    ],
)
def test_candidate_projection_current_rejects_flattening_or_drift(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    config, current = projection_current_binding_fixture(tmp_path)
    if mutation == "flattened":
        config.projection_snapshot_root = config.projection_authority_root
    elif mutation == "digest":
        config.projection_current_sha256 = "f" * 64
    else:
        payload = json.loads(current.read_text(encoding="utf-8"))
        if mutation == "status":
            payload["status"] = "review_required"
        elif mutation == "output-extra":
            payload["outputs"]["unexpected.json"] = (
                f"{config.projection_snapshot_id}/unexpected.json"
            )
        else:
            raise AssertionError(mutation)
        current.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        current.chmod(0o644)
        config.projection_current_sha256 = hashlib.sha256(
            current.read_bytes()
        ).hexdigest()

    with pytest.raises(controller.CutoverError, match=expected):
        controller._validate_projection_current_binding(config)


def test_wrapper_uses_a_sidecar_only_active_runtime_authority() -> None:
    lines = WRAPPER_PATH.read_text(encoding="utf-8").splitlines()
    authority_argument = next(
        line
        for line in lines
        if "--active-runtime-authority" in line
    )

    assert "CANONICAL_ACTIVE_RUNTIME_AUTHORITY" not in authority_argument
    assert "PUBLIC_DOWNLOAD" in authority_argument
    assert any(
        "PUBLIC_DOWNLOAD" in line
        and "ACTIVE_RUNTIME_AUTHORITY" in line
        and "CANONICAL_ACTIVE_RUNTIME_AUTHORITY" not in line
        for line in lines
    )


def test_wrapper_operation_identity_is_not_source_head_only() -> None:
    script = WRAPPER_PATH.read_text(encoding="utf-8")
    operation_root_lines = [
        line.strip()
        for line in script.splitlines()
        if line.startswith("PUBLIC_DOWNLOAD_OPERATION_ROOT=")
    ]

    assert len(operation_root_lines) == 1
    assert "PUBLIC_DOWNLOAD_OPERATION_ID" in script
    assert "PUBLIC_DOWNLOAD_OPERATION_ID" in operation_root_lines[0]
    assert "${EXPECTED_HEAD,,}" not in operation_root_lines[0]


@pytest.mark.parametrize(
    "api_base",
    (
        "https://attacker.example/client/v4",
        "http://api.cloudflare.com/client/v4",
        "https://api.cloudflare.com/client/v4/",
        "https://api.cloudflare.com/client/v4/extra",
        "https://api.cloudflare.com/client/v4?redirect=attacker.example",
    ),
)
def test_cloudflare_api_base_is_exact_before_any_credential_read(
    api_base: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_touched = False

    def reject_credential_read(*_args: Any, **_kwargs: Any) -> bytes:
        nonlocal credential_touched
        credential_touched = True
        raise AssertionError("credential material was touched")

    monkeypatch.setattr(
        controller,
        "stable_regular_bytes",
        reject_credential_read,
    )
    config = SimpleNamespace(
        operation=controller.CUTOVER_OPERATION,
        source_head="a" * 40,
        shared_lock_token="b" * 64,
        project_name="chummer-public-download-api-test",
        base_url="https://chummer.run",
        cloudflare_account_id="c" * 32,
        cloudflare_tunnel_id="d" * 8 + "-dddd-dddd-dddd-" + "d" * 12,
        cloudflare_api_base=api_base,
        ready_timeout_seconds=0,
    )

    with pytest.raises(controller.CutoverError, match="Cloudflare API base"):
        controller._validate_sidecar_config(config)

    assert credential_touched is False


def test_exact_official_cloudflare_api_base_passes_the_api_boundary() -> None:
    config = SimpleNamespace(
        operation=controller.CUTOVER_OPERATION,
        source_head="a" * 40,
        shared_lock_token="b" * 64,
        project_name="chummer-public-download-api-test",
        base_url="https://chummer.run",
        cloudflare_account_id="c" * 32,
        cloudflare_tunnel_id="d" * 8 + "-dddd-dddd-dddd-" + "d" * 12,
        cloudflare_api_base="https://api.cloudflare.com/client/v4",
        ready_timeout_seconds=0,
    )

    with pytest.raises(controller.CutoverError, match="readiness timeout"):
        controller._validate_sidecar_config(config)


FRESH_WINDOWS_PATHS = (
    "files/chummer-avalonia-win-x64-installer.exe",
    "files/chummer-avalonia-win-x64-payload.zip",
    "files/chummer-avalonia-win-x64-payload.zip.json",
)
REAL_V6_INSTALLER_SHA256 = (
    "8b2f2c4a37f72f202ff7af1b3eed5af0cc32138496f25ad9ae5512a2048d0f4a"
)
REAL_V6_INSTALLER_SIZE_BYTES = 2_734_880
REAL_V6_PAYLOAD_SHA256 = (
    "22464a462bf72e0b24efd686ddb2a66114bccde0f98b82273e15f7335a35582e"
)
REAL_V6_PAYLOAD_SIZE_BYTES = 51_231_862


def write_review_bound_candidate(
    tmp_path: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    candidate_root = tmp_path / "candidate"
    files_root = candidate_root / "files"
    evidence_root = candidate_root / "release-evidence"
    smoke_root = candidate_root / "startup-smoke"
    for path in (candidate_root, files_root, evidence_root, smoke_root):
        path.mkdir(exist_ok=True, mode=0o700)
        path.chmod(0o700)

    generation_id = "g-20260724T152516Z-6907464d-c779a59"
    release_version = "run-20260723-230227"
    scope_sha256 = (
        "d24e0033b9e6aadb82c754202be8fd514303ed0a7bdb83a1ee7c22d6978718ee"
    )
    registry_commit = "c779a59afca81858e62d727499e2daeab89b4f0d"
    installer = b"fixture installer bytes\n"
    payload = b"fixture payload bytes\n"
    sidecar = b'{"fixture":"payload-sidecar"}\n'
    installer_sha256 = REAL_V6_INSTALLER_SHA256
    payload_sha256 = REAL_V6_PAYLOAD_SHA256
    installer_name = "chummer-avalonia-win-x64-installer.exe"
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    artifact_id = "avalonia-win-x64-installer"
    download_url = (
        f"/downloads/g/{generation_id}/files/{installer_name}"
    )
    install_route = f"/downloads/install/{artifact_id}"
    known_issue = "Fixture review-required release remains bounded."
    artifact = {
        "artifactId": artifact_id,
        "id": artifact_id,
        "fileName": installer_name,
        "downloadUrl": download_url,
        "sha256": installer_sha256,
        "sizeBytes": REAL_V6_INSTALLER_SIZE_BYTES,
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "arch": "x64",
        "kind": "installer",
        "compatibilityState": "compatible",
        "installAccessClass": "open_public",
        "payloadFileName": payload_name,
        "payloadSha256": payload_sha256,
        "payloadSizeBytes": REAL_V6_PAYLOAD_SIZE_BYTES,
    }
    canonical = {
        "version": release_version,
        "releaseVersion": release_version,
        "generationId": generation_id,
        "channel": "preview",
        "channelId": "preview",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "knownIssueSummary": known_issue,
        "publishedAt": "2026-07-24T12:40:00Z",
        "generatedAt": "2026-07-24T12:40:00Z",
        "artifacts": [artifact],
    }
    compatibility = {
        "version": release_version,
        "generationId": generation_id,
        "channel": "preview",
        "status": "published",
        "downloads": [
            {
                **artifact,
                "url": download_url,
            }
        ],
    }
    canonical_raw = (
        json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    compatibility_raw = (
        json.dumps(
            compatibility,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    base_payloads = {
        "RELEASE_CHANNEL.generated.json": canonical_raw,
        "releases.json": compatibility_raw,
        f"files/{installer_name}": installer,
        f"files/{payload_name}": payload,
        f"files/{payload_name}.json": sidecar,
    }
    for relative, raw in base_payloads.items():
        path = candidate_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o600)

    handoff = {
        "contractName": "chummer.public-preview-byte-handoff/v1",
        "status": "approved_public_preview_bytes",
        "sourcePublicationState": "preview",
        "releaseScopeDecisionSha256": scope_sha256,
        "releaseVersion": release_version,
        "channel": "preview",
        "artifactId": artifact_id,
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "arch": "x64",
        "sha256": installer_sha256,
        "sizeBytes": REAL_V6_INSTALLER_SIZE_BYTES,
        "artifactAccessClass": "open_public",
        "signingRequirement": "preview_unsigned_allowed",
        "downloadUrl": download_url,
        "publicInstallRoute": install_route,
    }
    next_actions = ["Keep the fixture under review."]
    decision = {
        "contractName": "chummer.preview-release-decision/v2",
        "generatedAt": "2026-07-24T15:25:16Z",
        "status": "review_required",
        "releaseDecisionStatus": "review_required",
        "verdict": "PREVIEW_RELEASE_REVIEW_REQUIRED",
        "releaseVersion": release_version,
        "releaseScopeDecisionSha256": scope_sha256,
        "channel": "preview",
        "platforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "fallbackHeadsByPlatform": {"windows": []},
        "artifactAccessClass": "open_public",
        "supportOwner": "chummer-release-operations",
        "nextActions": next_actions,
        "registryCommit": registry_commit,
        "manifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "authoritySnapshotSha256": "",
        "candidateDecisionStatus": "",
        "candidateDecisionSha256": "",
        "manifestGeneratedAt": "2026-07-24T12:40:00Z",
        "scorecardSha256": "",
        "convergenceSha256": "",
        "blockingFindings": [
            {
                "id": "preview_1",
                "severity": "release_truth",
                "summary": "Fixture remains review-required.",
            }
        ],
        "artifactHandoff": handoff,
    }

    def encoded(value: dict[str, Any]) -> bytes:
        return (
            json.dumps(value, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()

    decision_raw = encoded(decision)
    snapshot = {
        "artifactCount": 1,
        "artifacts": [
            {
                "artifactId": artifact_id,
                "head": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "arch": "x64",
                "kind": "installer",
                "downloadUrl": download_url,
                "sha256": installer_sha256,
                "sizeBytes": REAL_V6_INSTALLER_SIZE_BYTES,
                "compatibilityState": "compatible",
                "promotionState": "promoted",
                "publicationScope": "signed-in-and-public",
                "revokeState": "not_revoked",
                "publicInstallRoute": install_route,
                "installAccessClass": "open_public",
            }
        ],
        "authorityContract": "chummer.release-authority-snapshot/v2",
        "availablePlatforms": ["windows"],
        "channel": "preview",
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": known_issue,
        "manifestPath": "RELEASE_CHANNEL.json",
        "manifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "nextActions": next_actions,
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "registryCommit": registry_commit,
        "registryRepository": "ArchonMegalon/chummer6-hub-registry",
        "releaseDecisionPath": "RELEASE_DECISION.json",
        "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        "releaseDecisionStatus": "review_required",
        "releaseVersion": release_version,
        "rolloutState": "public_release_review_required",
        "status": "published",
        "supportOwner": "chummer-release-operations",
        "supportabilityState": "review_required",
    }
    snapshot_raw = encoded(snapshot)
    current = {
        "decisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        "releaseVersion": release_version,
        "snapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "status": "review_required",
    }
    evidence_payloads = {
        "release-evidence/CURRENT.json": encoded(current),
        "release-evidence/RELEASE_DECISION.json": decision_raw,
        "release-evidence/SNAPSHOT.json": snapshot_raw,
    }
    smoke = {
        "status": "pass",
        "headId": "avalonia",
        "version": release_version,
        "releaseVersion": release_version,
        "channelId": "preview",
        "platform": "windows",
        "arch": "x64",
        "rid": "win-x64",
        "artifactDigest": f"sha256:{installer_sha256}",
        "artifactSha256": installer_sha256,
        "artifactId": artifact_id,
        "artifactFileName": installer_name,
        "fileName": installer_name,
        "artifactRelativePath": f"files/{installer_name}",
        "bootstrapPayloadSha256": payload_sha256,
        "bootstrapPayloadSizeBytes": REAL_V6_PAYLOAD_SIZE_BYTES,
        "bootstrapPayloadFileName": payload_name,
    }
    evidence_payloads[
        controller.SCOPE_BOUND_STARTUP_SMOKE_PATH
    ] = encoded(smoke)
    for relative, raw in evidence_payloads.items():
        path = candidate_root / relative
        path.write_bytes(raw)
        path.chmod(0o400)

    base_rows = sorted(
        (
            {
                "path": path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "sizeBytes": len(raw),
            }
            for path, raw in base_payloads.items()
        ),
        key=lambda row: row["path"],
    )
    inventory = {
        "contractName": "chummer.release-upload.candidate-inventory/v1",
        "contractVersion": 1,
        "files": base_rows,
    }
    candidate = {
        "version": release_version,
        "canonicalManifestSha256": hashlib.sha256(
            canonical_raw
        ).hexdigest(),
        "inventorySha256": controller._candidate_inventory_sha256(
            base_rows
        ),
        "fileCount": len(base_rows),
        "totalBytes": sum(row["sizeBytes"] for row in base_rows),
        "bundleIdentitySha256": "0" * 64,
    }
    authority = {
        "generationId": generation_id,
        "releaseScopeDecisionSha256": scope_sha256,
    }
    return (
        candidate_root,
        inventory,
        candidate,
        canonical_raw,
        authority,
    )


def capture_review_candidate(
    candidate_root: Path,
    inventory: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    rows, _modes, _directories, captured = (
        controller._scope_bound_full_candidate_inventory(
            SimpleNamespace(release_candidate_root=candidate_root),
            candidate_materializer=candidate_scanner,
            inventory=inventory,
            candidate=candidate,
        )
    )
    return rows, captured


def rewrite_review_authority(
    candidate_root: Path,
    *,
    mutate_decision: Any = None,
    mutate_snapshot: Any = None,
) -> None:
    evidence_root = candidate_root / "release-evidence"
    decision_path = evidence_root / "RELEASE_DECISION.json"
    snapshot_path = evidence_root / "SNAPSHOT.json"
    current_path = evidence_root / "CURRENT.json"
    decision = json.loads(decision_path.read_bytes())
    snapshot = json.loads(snapshot_path.read_bytes())
    if mutate_decision is not None:
        mutate_decision(decision)
    decision_raw = (
        json.dumps(decision, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    decision_path.chmod(0o600)
    decision_path.write_bytes(decision_raw)
    decision_path.chmod(0o400)
    snapshot["releaseDecisionSha256"] = hashlib.sha256(
        decision_raw
    ).hexdigest()
    if mutate_snapshot is not None:
        mutate_snapshot(snapshot)
    snapshot_raw = (
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    snapshot_path.chmod(0o600)
    snapshot_path.write_bytes(snapshot_raw)
    snapshot_path.chmod(0o400)
    current = json.loads(current_path.read_bytes())
    current["decisionSha256"] = hashlib.sha256(decision_raw).hexdigest()
    current["snapshotSha256"] = hashlib.sha256(
        snapshot_raw
    ).hexdigest()
    current_raw = (
        json.dumps(current, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    current_path.chmod(0o600)
    current_path.write_bytes(current_raw)
    current_path.chmod(0o400)


def rewrite_startup_smoke(
    candidate_root: Path,
    *,
    mutate: Any,
) -> None:
    smoke_path = (
        candidate_root
        / controller.SCOPE_BOUND_STARTUP_SMOKE_PATH
    )
    receipt = json.loads(smoke_path.read_bytes())
    mutate(receipt)
    raw = (
        json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    smoke_path.chmod(0o600)
    smoke_path.write_bytes(raw)
    smoke_path.chmod(0o400)


def test_scope_bound_full_candidate_accepts_only_authenticated_adjuncts(
    tmp_path: Path,
) -> None:
    root, inventory, candidate, canonical_raw, authority = (
        write_review_bound_candidate(tmp_path)
    )
    rows, captured = capture_review_candidate(
        root,
        inventory,
        candidate,
    )

    review = controller._validate_scope_bound_review_authority(
        canonical_raw=canonical_raw,
        canonical=json.loads(canonical_raw),
        evidence_bytes=captured,
        generation_id=authority["generationId"],
        release_scope_decision_sha256=authority[
            "releaseScopeDecisionSha256"
        ],
        candidate_version=candidate["version"],
    )
    smoke = controller._validate_scope_bound_startup_smoke(
        captured[controller.SCOPE_BOUND_STARTUP_SMOKE_PATH],
        artifact=json.loads(canonical_raw)["artifacts"][0],
        release_version=candidate["version"],
    )

    assert len(rows) == 5
    assert set(captured).issuperset(
        controller.SCOPE_BOUND_CANDIDATE_ADJUNCT_PATHS
    )
    assert len(review["releaseTruth"]) == 17
    assert review["generationId"] == authority["generationId"]
    assert review["releaseTruth"]["artifactHandoff"][
        "downloadUrl"
    ].startswith(f"/downloads/g/{authority['generationId']}/")
    assert smoke["status"] == "pass"


@pytest.mark.parametrize(
    ("drift", "expected_error"),
    (
        ("artifact_count_bool", "snapshot contradicts"),
        ("snapshot_size_decimal", "artifact binding drifted"),
        ("handoff_size_decimal", "artifact handoff drifted"),
    ),
)
def test_scope_bound_review_authority_rejects_real_v6_numeric_type_drift(
    tmp_path: Path,
    drift: str,
    expected_error: str,
) -> None:
    root, inventory, candidate, canonical_raw, authority = (
        write_review_bound_candidate(tmp_path)
    )
    if drift == "artifact_count_bool":
        rewrite_review_authority(
            root,
            mutate_snapshot=lambda value: value.__setitem__(
                "artifactCount",
                True,
            ),
        )
    elif drift == "snapshot_size_decimal":
        rewrite_review_authority(
            root,
            mutate_snapshot=lambda value: value["artifacts"][0].__setitem__(
                "sizeBytes",
                float(REAL_V6_INSTALLER_SIZE_BYTES),
            ),
        )
    else:
        rewrite_review_authority(
            root,
            mutate_decision=lambda value: value[
                "artifactHandoff"
            ].__setitem__(
                "sizeBytes",
                float(REAL_V6_INSTALLER_SIZE_BYTES),
            ),
        )

    _rows, captured = capture_review_candidate(
        root,
        inventory,
        candidate,
    )
    with pytest.raises(controller.CutoverError, match=expected_error):
        controller._validate_scope_bound_review_authority(
            canonical_raw=canonical_raw,
            canonical=json.loads(canonical_raw),
            evidence_bytes=captured,
            generation_id=authority["generationId"],
            release_scope_decision_sha256=authority[
                "releaseScopeDecisionSha256"
            ],
            candidate_version=candidate["version"],
        )


def test_scope_bound_startup_smoke_rejects_real_v6_decimal_payload_size(
    tmp_path: Path,
) -> None:
    root, inventory, candidate, canonical_raw, _authority = (
        write_review_bound_candidate(tmp_path)
    )
    rewrite_startup_smoke(
        root,
        mutate=lambda value: value.__setitem__(
            "bootstrapPayloadSizeBytes",
            float(REAL_V6_PAYLOAD_SIZE_BYTES),
        ),
    )
    _rows, captured = capture_review_candidate(
        root,
        inventory,
        candidate,
    )

    with pytest.raises(controller.CutoverError, match="startup-smoke"):
        controller._validate_scope_bound_startup_smoke(
            captured[controller.SCOPE_BOUND_STARTUP_SMOKE_PATH],
            artifact=json.loads(canonical_raw)["artifacts"][0],
            release_version=candidate["version"],
        )


@pytest.mark.parametrize("field", ("fileCount", "totalBytes"))
def test_scope_bound_candidate_summary_requires_exact_integer_type(
    tmp_path: Path,
    field: str,
) -> None:
    root, inventory, candidate, _canonical_raw, _authority = (
        write_review_bound_candidate(tmp_path)
    )
    candidate[field] = Decimal(candidate[field])

    with pytest.raises(controller.CutoverError, match="summary drifted"):
        capture_review_candidate(root, inventory, candidate)


def test_type_aware_json_equality_preserves_decimal_without_integer_coercion(
) -> None:
    assert controller._json_semantically_equal(
        {"finite": [Decimal("1.5")]},
        {"finite": [Decimal("1.5")]},
    )
    assert not controller._json_semantically_equal(
        {"sizeBytes": Decimal(REAL_V6_INSTALLER_SIZE_BYTES)},
        {"sizeBytes": REAL_V6_INSTALLER_SIZE_BYTES},
    )
    assert not controller._json_semantically_equal(
        {"artifactCount": True},
        {"artifactCount": 1},
    )


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_scope_bound_full_candidate_rejects_adjunct_path_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    root, inventory, candidate, _canonical_raw, _authority = (
        write_review_bound_candidate(tmp_path)
    )
    if mutation == "missing":
        (
            root
            / "release-evidence"
            / "CURRENT.json"
        ).unlink()
    else:
        extra = root / "release-evidence" / "EXTRA.json"
        extra.write_text("{}\n", encoding="utf-8")
        extra.chmod(0o400)

    with pytest.raises(
        controller.CutoverError,
        match="adjunct path closure",
    ):
        capture_review_candidate(root, inventory, candidate)


@pytest.mark.parametrize(
    "drift",
    ("generation", "handoff_url", "scope", "manifest_sha256"),
)
def test_scope_bound_review_authority_rejects_binding_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    root, inventory, candidate, canonical_raw, authority = (
        write_review_bound_candidate(tmp_path)
    )
    generation_id = authority["generationId"]
    scope_sha256 = authority["releaseScopeDecisionSha256"]
    if drift == "handoff_url":
        rewrite_review_authority(
            root,
            mutate_decision=lambda value: value[
                "artifactHandoff"
            ].__setitem__(
                "downloadUrl",
                "/downloads/g/wrong/files/"
                "chummer-avalonia-win-x64-installer.exe",
            ),
        )
    elif drift == "scope":
        rewrite_review_authority(
            root,
            mutate_decision=lambda value: value.__setitem__(
                "releaseScopeDecisionSha256",
                "f" * 64,
            ),
        )
    elif drift == "manifest_sha256":
        rewrite_review_authority(
            root,
            mutate_snapshot=lambda value: value.__setitem__(
                "manifestSha256",
                "e" * 64,
            ),
        )
    else:
        generation_id = "g-wrong-generation"

    _rows, captured = capture_review_candidate(
        root,
        inventory,
        candidate,
    )
    with pytest.raises(controller.CutoverError):
        controller._validate_scope_bound_review_authority(
            canonical_raw=canonical_raw,
            canonical=json.loads(canonical_raw),
            evidence_bytes=captured,
            generation_id=generation_id,
            release_scope_decision_sha256=scope_sha256,
            candidate_version=candidate["version"],
        )


def test_scope_bound_review_authority_rejects_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    root, inventory, candidate, canonical_raw, authority = (
        write_review_bound_candidate(tmp_path)
    )
    current_path = root / "release-evidence" / "CURRENT.json"
    current_path.chmod(0o600)
    current_path.write_bytes(
        b'{"releaseVersion":"one","releaseVersion":"two"}\n'
    )
    current_path.chmod(0o400)
    _rows, captured = capture_review_candidate(
        root,
        inventory,
        candidate,
    )

    with pytest.raises(controller.CutoverError, match="strict JSON"):
        controller._validate_scope_bound_review_authority(
            canonical_raw=canonical_raw,
            canonical=json.loads(canonical_raw),
            evidence_bytes=captured,
            generation_id=authority["generationId"],
            release_scope_decision_sha256=authority[
                "releaseScopeDecisionSha256"
            ],
            candidate_version=candidate["version"],
        )


def test_strict_json_accepts_exact_finite_decimal_and_exponent_numbers() -> None:
    parsed = controller._strict_json_object_bytes(
        (
            b'{"decimal":1.5,"exponent":1e3,"negative":-2.5E-3,'
            b'"zero":0.0,"integer":1,"boolean":true}\n'
        ),
        label="finite-number fixture",
    )

    assert parsed == {
        "decimal": Decimal("1.5"),
        "exponent": Decimal("1e3"),
        "negative": Decimal("-2.5E-3"),
        "zero": Decimal("0.0"),
        "integer": 1,
        "boolean": True,
    }
    assert type(parsed["decimal"]) is Decimal
    assert type(parsed["integer"]) is int
    assert type(parsed["boolean"]) is bool


@pytest.mark.parametrize(
    "number",
    (
        "NaN",
        "Infinity",
        "-Infinity",
        "1e309",
        "-1e309",
    ),
)
def test_strict_json_rejects_nonfinite_and_overflow_numbers(
    number: str,
) -> None:
    with pytest.raises(controller.CutoverError, match="strict JSON"):
        controller._strict_json_object_bytes(
            f'{{"value":{number}}}\n'.encode(),
            label="nonfinite-number fixture",
        )


def test_windows_preview_sidecar_preserves_authenticated_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_root = tmp_path / "operation"
    operation_root.mkdir(mode=0o700)
    shelf_source = operation_root / "release-shelf"
    sealed_generation = "g-sealed-review-authority"
    observed: dict[str, str] = {}
    migration_authority = tmp_path / "migration-authority.json"
    migration_authority.write_bytes(b"fixture migration authority\n")
    config = SimpleNamespace(
        delivery_phase="windows-preview",
        source_root=ROOT,
        source_head="a" * 40,
        shelf_root=tmp_path / "canonical-shelf",
        migration_candidate_root=tmp_path / "migration-candidate",
        migration_authority=migration_authority,
        migration_authority_sha256=hashlib.sha256(
            migration_authority.read_bytes()
        ).hexdigest(),
        release_candidate_root=tmp_path / "release-candidate",
        operation_root=operation_root,
        shelf_source=shelf_source,
    )

    monkeypatch.setattr(
        controller,
        "_load_restoration_spec",
        lambda _config: [],
    )
    monkeypatch.setattr(
        controller,
        "materialize_incumbent_candidate",
        lambda **_kwargs: {
            "candidateInventoryDigest": "sha256:" + "c" * 64
        },
    )
    monkeypatch.setattr(
        controller,
        "validate_release_candidate_authority",
        lambda *_args, **_kwargs: {
            "generationId": sealed_generation,
            "reviewRequiredReleaseTruth": {"contractName": "fixture"},
        },
    )
    monkeypatch.setattr(
        controller,
        "tree_sha256_file_stream",
        lambda *_args, **_kwargs: "d" * 64,
    )

    class Generation:
        GENERATIONS_DIRECTORY = "generations"
        CANONICAL_MANIFEST = "RELEASE_CHANNEL.generated.json"
        COMPATIBILITY_MANIFEST = "releases.json"

        @staticmethod
        def validate_generation_id(value: str) -> str:
            observed["validatedGenerationId"] = value
            return value

        @staticmethod
        def new_generation_id() -> str:
            raise AssertionError(
                "a new generation must not replace sealed authority"
            )

        @staticmethod
        def new_activation_receipt_id() -> str:
            return "activation-fixture"

        @staticmethod
        def prepare_sidecar_active_layout(
            _candidate_root: Path,
            output_root: Path,
            *,
            generation_id: str,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            observed["materializedGenerationId"] = generation_id
            generation_root = (
                output_root / "generations" / generation_id
            )
            generation_root.mkdir(parents=True)
            (
                generation_root
                / "RELEASE_CHANNEL.generated.json"
            ).write_bytes(b"canonical\n")
            (generation_root / "releases.json").write_bytes(
                b"compatibility\n"
            )
            return {
                "pointer": {"inventoryDigest": "sha256:" + "e" * 64},
                "pointerSha256": "f" * 64,
                "activationCandidateSha256": "1" * 64,
                "canonicalMirrorSha256": "2" * 64,
                "compatibilityMirrorSha256": "3" * 64,
                "writerPolicy": "sidecar-readonly-v1",
            }

        @staticmethod
        def sha256_file(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

    class Attestor:
        @staticmethod
        def prepare_public_download_migration(
            _shelf_root: Path,
            _validation_root: Path,
            _candidate_root: Path,
            _authority: Path,
            _authority_sha256: str,
            _source_head: str,
            generation_id: str,
            _activation_receipt_id: str,
        ) -> dict[str, Any]:
            observed["attestedGenerationId"] = generation_id
            return {"generationId": generation_id}

    receipt = controller.prepare_sidecar_release_shelf(
        config,
        generation=Generation,
        attestor=Attestor,
        projection_verifier=object(),
        candidate_materializer=object(),
    )

    assert receipt["generationId"] == sealed_generation
    assert observed == {
        "validatedGenerationId": sealed_generation,
        "attestedGenerationId": sealed_generation,
        "materializedGenerationId": sealed_generation,
    }
    assert receipt["releaseCandidateAuthority"][
        "reviewRequiredReleaseTruth"
    ] == {"contractName": "fixture"}


def release_candidate_authority_fixture(
    tmp_path: Path,
    *,
    fresh_digest_override: str | None = None,
    retained_digest_override: str | None = None,
) -> tuple[Any, Any, Any, dict[str, dict[str, Any]]]:
    release_root = tmp_path / "sealed-bundle"
    incumbent_root = tmp_path / "incumbent-candidate"
    projection_root = tmp_path / "projection"
    for root in (release_root, incumbent_root, projection_root):
        (root / "files").mkdir(parents=True)

    canonical = b'{"version":"fresh-windows"}\n'
    compatibility = b'{"version":"fresh-windows","downloads":[]}\n'
    (release_root / "RELEASE_CHANNEL.generated.json").write_bytes(canonical)
    (release_root / "releases.json").write_bytes(compatibility)
    retained_path = "files/retained-linux.tar.zst"
    retained_bytes = b"retained incumbent bytes\n"
    (release_root / retained_path).write_bytes(retained_bytes)
    (incumbent_root / retained_path).write_bytes(retained_bytes)

    release_bytes = {
        FRESH_WINDOWS_PATHS[0]: b"fresh installer bytes\n",
        FRESH_WINDOWS_PATHS[1]: b"fresh payload bytes\n",
        FRESH_WINDOWS_PATHS[2]: b'{"fresh":"payload-sidecar"}\n',
    }
    incumbent_bytes = {
        FRESH_WINDOWS_PATHS[0]: b"old installer bytes\n",
        FRESH_WINDOWS_PATHS[1]: b"old payload bytes\n",
        FRESH_WINDOWS_PATHS[2]: b'{"old":"payload-sidecar"}\n',
    }
    for path, payload in release_bytes.items():
        (release_root / path).write_bytes(payload)
    for path, payload in incumbent_bytes.items():
        (incumbent_root / path).write_bytes(payload)

    def row(path: str, payload: bytes) -> dict[str, Any]:
        return {
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "sizeBytes": len(payload),
        }

    release_rows = [
        row("RELEASE_CHANNEL.generated.json", canonical),
        row("releases.json", compatibility),
        *(row(path, release_bytes[path]) for path in FRESH_WINDOWS_PATHS),
        row(retained_path, retained_bytes),
    ]
    incumbent_rows = [
        row("RELEASE_CHANNEL.generated.json", b"old canonical\n"),
        row("releases.json", b"old compatibility\n"),
        *(row(path, incumbent_bytes[path]) for path in FRESH_WINDOWS_PATHS),
        row(retained_path, retained_bytes),
    ]
    release_modes = {item["path"]: 0o644 for item in release_rows}
    incumbent_modes = {item["path"]: 0o644 for item in incumbent_rows}
    release_with_modes = [
        {**item, "mode": release_modes[item["path"]]}
        for item in release_rows
    ]
    incumbent_with_modes = [
        {**item, "mode": incumbent_modes[item["path"]]}
        for item in incumbent_rows
    ]
    release_by_path = {item["path"]: item for item in release_rows}
    fresh_delta = [
        {
            **release_by_path[path],
            "mode": release_modes[path],
        }
        for path in FRESH_WINDOWS_PATHS
    ]
    if fresh_digest_override is not None:
        fresh_delta[0]["sha256"] = fresh_digest_override
    retained = [
        {
            **release_by_path[retained_path],
            "mode": release_modes[retained_path],
        }
    ]
    if retained_digest_override is not None:
        retained[0]["sha256"] = retained_digest_override

    scope = {
        "fullShelfInventory": release_with_modes,
        "freshDelta": fresh_delta,
        "retainedFromIncumbent": retained,
        "sourceSha": "e" * 40,
    }
    registry = {
        "registryCommit": "d" * 40,
        "compositionInputDocument": {
            "incumbentSnapshot": {
                "fullShelfInventory": incumbent_with_modes,
                "directoryModes": {"files": 0o755},
            }
        }
    }
    inventory = {"contractName": "fixture"}
    custody = {
        "inventory": {"token": "inventory"},
        "unsignedPublicationEvidence": {
            "files": [{"path": "scope.json", "token": "scope"}],
            "retainedInventorySha256": "8" * 64,
            "incumbentInventorySha256": "9" * 64,
        },
        "registryPrepareCandidateReceipt": {"token": "registry"},
        "registryFinalizeAuthority": {"token": "registry-authority"},
        "registryFinalizeReceipt": {"token": "registry-finalize"},
        "canonicalManifest": {"token": "canonical"},
        "compatibilityManifest": {"token": "compatibility"},
    }
    authority = {
        "contractName": (
            "chummer.release-upload.candidate-import-authority/v3"
        ),
        "contractVersion": 3,
        "candidate": {
            "version": "fresh-windows",
            "bundleIdentitySha256": "a" * 64,
            "inventorySha256": "b" * 64,
            "fileCount": len(release_rows),
            "totalBytes": sum(item["sizeBytes"] for item in release_rows),
            "canonicalManifestSha256": hashlib.sha256(canonical).hexdigest(),
        },
        "custody": custody,
    }
    authority_path = projection_root / (
        "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    )
    authority_path.write_bytes(b"fixture candidate authority\n")
    release_receipt = projection_root / "RELEASE_CHANNEL.generated.json"
    release_receipt.write_bytes(canonical)
    composition_raw = (
        json.dumps(
            registry["compositionInputDocument"],
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    direct_import = {
        "compositionRequest": {
            "path": "composition.json",
            "sha256": hashlib.sha256(composition_raw).hexdigest(),
            "sizeBytes": len(composition_raw),
        },
        "contractName": "chummer6-ui.preview-nightly-unsigned-direct-import",
        "contractVersion": 1,
        "crossRunBitReproducible": False,
        "deployAuthorized": False,
        "hubCandidateImportAuthority": {
            "path": "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json",
            "sha256": hashlib.sha256(authority_path.read_bytes()).hexdigest(),
            "sizeBytes": len(authority_path.read_bytes()),
        },
        "platformScope": "windows_only",
        "publicationAuthorized": False,
        "registryCandidateReceipt": {
            "path": "registry.json",
            "sha256": hashlib.sha256(b"registry").hexdigest(),
            "sizeBytes": len(b"registry"),
        },
        "registryFinalizeAuthority": {
            "path": "registry-authority.json",
            "sha256": hashlib.sha256(b"registry-authority").hexdigest(),
            "sizeBytes": len(b"registry-authority"),
        },
        "registryFinalizeReceipt": {
            "path": "registry-finalize.json",
            "sha256": hashlib.sha256(b"registry-finalize").hexdigest(),
            "sizeBytes": len(b"registry-finalize"),
        },
        "release": {"channel": "preview", "version": "fresh-windows"},
        "signature": {
            "policy": "preview_policy",
            "required": False,
            "status": "unsigned",
        },
        "sourceCommits": {
            "hub": "c" * 40,
            "registry": "d" * 40,
            "ui": "e" * 40,
        },
        "status": "sealed_review_required",
        "transport": {},
        "uiScope": {
            "path": "scope.json",
            "sha256": hashlib.sha256(b"scope").hexdigest(),
            "sizeBytes": len(b"scope"),
        },
        "uploadAuthorized": False,
    }
    direct_import_receipt = (
        release_root.parent
        / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    )
    direct_import_receipt.write_text(
        json.dumps(direct_import, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config = SimpleNamespace(
        source_root=ROOT,
        source_head="c" * 40,
        candidate_import_authority=authority_path,
        candidate_import_authority_sha256=hashlib.sha256(
            authority_path.read_bytes()
        ).hexdigest(),
        release_candidate_root=release_root,
        migration_candidate_root=incumbent_root,
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=hashlib.sha256(canonical).hexdigest(),
        direct_import_receipt=direct_import_receipt,
        direct_import_receipt_sha256=hashlib.sha256(
            direct_import_receipt.read_bytes()
        ).hexdigest(),
    )

    class ProjectionVerifier:
        CANDIDATE_UNSIGNED_SCOPE_FILE = "scope.json"
        CANDIDATE_REGISTRY_RECEIPT_FILE = "registry.json"
        CANDIDATE_REGISTRY_AUTHORITY_FILE = "registry-authority.json"
        CANDIDATE_REGISTRY_FINALIZE_FILE = "registry-finalize.json"
        CANDIDATE_UNSIGNED_COMPOSITION_FILE = "composition.json"

        @staticmethod
        def _validate_candidate_import_authority(_raw: bytes) -> dict[str, Any]:
            return authority

        @staticmethod
        def _candidate_embedded_bytes(
            item: dict[str, Any] | None,
            *,
            label: str,
            expected_path: str,
        ) -> bytes:
            assert item is not None, label
            token = item.get("token")
            return {
                "inventory": b"inventory",
                "scope": b"scope",
                "registry": b"registry",
                "registry-authority": b"registry-authority",
                "registry-finalize": b"registry-finalize",
                "canonical": canonical,
                "compatibility": compatibility,
            }[token]

        @staticmethod
        def _strict_json_object(
            raw: bytes, *, label: str
        ) -> dict[str, Any]:
            if raw.startswith(b"{"):
                return json.loads(raw)
            return {
                b"inventory": inventory,
                b"scope": scope,
                b"registry": registry,
            }[raw]

    class CandidateMaterializer:
        observed_release_root: Path | None = None

        @classmethod
        def _validate_bundle_inventory(
            cls,
            root: Path,
            *_args: Any,
            **_kwargs: Any,
        ) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], list[Any]]:
            cls.observed_release_root = root
            return release_rows, release_modes, {"files": 0o755}, []

        @staticmethod
        def _scan_bundle_tree(
            root: Path,
        ) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], list[Any]]:
            assert root == incumbent_root
            return incumbent_rows, incumbent_modes, {"files": 0o755}, []

    return (
        config,
        ProjectionVerifier,
        CandidateMaterializer,
        release_by_path,
    )


def test_v3_authority_binds_exact_candidate_tree_retained_and_fresh_delta(
    tmp_path: Path,
) -> None:
    (
        config,
        projection_verifier,
        candidate_materializer,
        release_by_path,
    ) = release_candidate_authority_fixture(tmp_path)

    receipt = controller.validate_release_candidate_authority(
        config,
        projection_verifier=projection_verifier,
        candidate_materializer=candidate_materializer,
    )

    assert (
        candidate_materializer.observed_release_root
        == config.release_candidate_root
    )
    assert receipt["servingAuthority"] is True
    assert receipt["retainedInventorySha256"] == "8" * 64
    assert receipt["incumbentInventorySha256"] == "9" * 64
    assert {
        item["path"]: (item["sha256"], item["sizeBytes"])
        for item in receipt["freshDelta"]
    } == {
        path: (
            release_by_path[path]["sha256"],
            release_by_path[path]["sizeBytes"],
        )
        for path in FRESH_WINDOWS_PATHS
    }


def test_v3_authority_rejects_fresh_windows_hash_not_in_exact_bundle(
    tmp_path: Path,
) -> None:
    config, projection_verifier, candidate_materializer, _release = (
        release_candidate_authority_fixture(
            tmp_path,
            fresh_digest_override="f" * 64,
        )
    )

    with pytest.raises(controller.CutoverError, match="freshDelta|fresh"):
        controller.validate_release_candidate_authority(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
        )


def test_v3_authority_rejects_retained_hash_not_in_incumbent(
    tmp_path: Path,
) -> None:
    config, projection_verifier, candidate_materializer, _release = (
        release_candidate_authority_fixture(
            tmp_path,
            retained_digest_override="e" * 64,
        )
    )

    with pytest.raises(controller.CutoverError, match="retained"):
        controller.validate_release_candidate_authority(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
        )
