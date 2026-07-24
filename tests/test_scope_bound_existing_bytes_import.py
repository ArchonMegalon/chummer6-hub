from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = (
    REPO_ROOT
    / "scripts"
    / "release"
    / "materialize_scope_bound_existing_bytes_import.py"
)
PROJECTION = (
    REPO_ROOT / "scripts" / "release" / "verify_public_projection.py"
)
CUTOVER = REPO_ROOT / "scripts" / "deploy_public_download_only_cutover.py"
GENERATION_ID = "g-20260724-scope-bound-test"
VERSION = "run-20260724-scope-bound-test"
HUB_COMMIT = "a" * 40
REGISTRY_COMMIT = "b" * 40
UI_COMMIT = "c" * 40


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def pretty_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def publish_review_snapshot(module, root: Path) -> None:
    payloads = {
        name: (
            b'{"status":"review_required"}\n'
            if name not in module.SNAPSHOT_OUTPUT_NAMES[:2]
            else b'{"status":"review-required-hub-proof"}\n'
        )
        for name in module.SNAPSHOT_OUTPUT_NAMES
    }
    payloads[module.SNAPSHOT_OUTPUT_NAMES[1]] = payloads[
        module.SNAPSHOT_OUTPUT_NAMES[0]
    ]
    digests = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in payloads.items()
    }
    snapshot_sha = module._snapshot_digest(digests)
    snapshot_id = f"public-projection-{snapshot_sha}"
    directory = root / snapshot_id
    directory.mkdir()
    for name, payload in payloads.items():
        (directory / name).write_bytes(payload)
    findings = [
        {
            "gate": "live public Windows installer",
            "status": "postdeploy_required",
            "reason": (
                "live Windows installer proof must pass after code deployment"
            ),
        }
    ]
    common = {
        "contractName": module.SNAPSHOT_CONTRACT,
        "status": module.PROJECTION_STATUS_REVIEW_REQUIRED,
        "projectionStage": (
            module.PROJECTION_STAGE_CODE_DEPLOY_REVIEW_REQUIRED
        ),
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": False,
        "candidateImportAuthority": False,
        "releaseGateFindings": findings,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha,
        "authorityInputs": {},
        "outputs": {
            name: {
                "relativePath": name,
                "sha256": digests[name],
                "sizeBytes": len(payloads[name]),
            }
            for name in module.SNAPSHOT_OUTPUT_NAMES
        },
    }
    manifest = module._canonical_json_bytes(common)
    (directory / module.SNAPSHOT_MANIFEST_NAME).write_bytes(manifest)
    pointer = {
        key: value
        for key, value in common.items()
        if key not in {"authorityInputs", "outputs", "contractName"}
    }
    pointer.update(
        {
            "contractName": module.CURRENT_CONTRACT,
            "manifestRelativePath": (
                f"{snapshot_id}/{module.SNAPSHOT_MANIFEST_NAME}"
            ),
            "manifestSha256": hashlib.sha256(manifest).hexdigest(),
            "outputs": {
                name: f"{snapshot_id}/{name}"
                for name in module.SNAPSHOT_OUTPUT_NAMES
            },
        }
    )
    (root / module.CURRENT_POINTER_NAME).write_bytes(
        module._canonical_json_bytes(pointer)
    )


def write(path: Path, raw: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(mode)


def fixture(tmp_path: Path) -> dict[str, Any]:
    tmp_path.chmod(0o700)
    bundle = tmp_path / "candidate"
    files = bundle / "files"
    authority_dir = tmp_path / "authority"
    bundle.mkdir(mode=0o700)
    files.mkdir(mode=0o700)
    authority_dir.mkdir(mode=0o700)

    installer_name = "chummer-avalonia-win-x64-installer.exe"
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    sidecar_name = f"{payload_name}.json"
    installer_raw = b"MZscope-bound-existing-windows-installer"
    payload_raw = b"PK\x03\x04scope-bound-existing-windows-payload"
    installer_sha = hashlib.sha256(installer_raw).hexdigest()
    payload_sha = hashlib.sha256(payload_raw).hexdigest()
    write(files / installer_name, installer_raw)
    write(files / payload_name, payload_raw)

    artifact = {
        "arch": "x64",
        "artifactId": "avalonia-win-x64-installer",
        "channel": "preview",
        "channelId": "preview",
        "compatibilityState": "compatible",
        "downloadUrl": f"/downloads/g/{GENERATION_ID}/files/{installer_name}",
        "fileName": installer_name,
        "head": "avalonia",
        "id": "avalonia-win-x64-installer",
        "installAccessClass": "open_public",
        "installerMode": "bootstrap",
        "kind": "installer",
        "payloadAcquisitionMode": "download",
        "payloadDownloadUrl": (
            f"/downloads/g/{GENERATION_ID}/install/"
            "avalonia-win-x64-installer/payload"
        ),
        "payloadFileName": payload_name,
        "payloadSha256": payload_sha,
        "payloadSizeBytes": len(payload_raw),
        "platform": "windows",
        "releaseVersion": VERSION,
        "rid": "win-x64",
        "sha256": installer_sha,
        "sizeBytes": len(installer_raw),
        "version": VERSION,
    }
    semantic_install_route = (
        "/downloads/install/avalonia-win-x64-installer"
    )
    fallback_install_route = (
        "/downloads/install/blazor-desktop-win-x64-installer"
    )
    semantic_row = {
        "artifactId": "avalonia-win-x64-installer",
        "head": "avalonia",
        "platform": "windows",
        "publicInstallRoute": semantic_install_route,
        "rid": "win-x64",
        "tupleId": "avalonia:windows:win-x64",
    }
    coverage = {
        "complete": True,
        "desktopRouteTruth": [
            dict(semantic_row),
            {
                "artifactId": "",
                "head": "blazor-desktop",
                "platform": "windows",
                "publicInstallRoute": fallback_install_route,
                "rid": "win-x64",
                "tupleId": "blazor-desktop:windows:win-x64",
            },
        ],
        "externalProofRequests": [],
        "missingRequiredHeads": [],
        "missingRequiredPlatformHeadPairs": [],
        "missingRequiredPlatformHeadRidTuples": [],
        "missingRequiredPlatforms": [],
        "promotedInstallerTuples": [
            {
                "arch": "x64",
                "artifactId": "avalonia-win-x64-installer",
                "head": "avalonia",
                "kind": "installer",
                "platform": "windows",
                "rid": "win-x64",
                "tupleId": "avalonia:windows:win-x64",
            }
        ],
        "promotedPlatformHeadRidTuples": [
            "avalonia:win-x64:windows"
        ],
        "promotedPlatformHeads": {"windows": ["avalonia"]},
        "requiredDesktopHeads": ["avalonia"],
        "requiredDesktopPlatformHeadRidTuples": [
            "avalonia:win-x64:windows"
        ],
        "requiredDesktopPlatforms": ["windows"],
    }
    install_aware = [
        {
            "artifactId": "avalonia-win-x64-installer",
            "conciergeAssetRefs": {
                "publicTrustWrapper": semantic_install_route
            },
            "head": "avalonia",
            "platform": "windows",
            "recoveryProofRefs": [semantic_install_route],
            "rid": "win-x64",
            "tupleId": "avalonia:windows:win-x64",
        }
    ]
    canonical = {
        "artifactIdentityRegistry": [dict(semantic_row)],
        "artifactPublicationBindings": [dict(semantic_row)],
        "artifacts": [artifact],
        "channel": "preview",
        "channelId": "preview",
        "desktopSurfaceRefs": [dict(semantic_row)],
        "desktopTupleCoverage": coverage,
        "generatedAt": "2026-07-24T12:40:00Z",
        "generationId": GENERATION_ID,
        "installAwareArtifactRegistry": install_aware,
        "knownIssueSummary": (
            "Fixture review-required release remains bounded."
        ),
        "platformScope": "windows_only",
        "publishedAt": "2026-07-24T12:40:00Z",
        "registryCommit": REGISTRY_COMMIT,
        "registry_commit": REGISTRY_COMMIT,
        "releaseVersion": VERSION,
        "rolloutState": "public_release_review_required",
        "status": "published",
        "supportabilityState": "review_required",
        "version": VERSION,
    }
    compatibility_row = {
        **artifact,
        "url": artifact["downloadUrl"],
    }
    compatibility = {
        "artifactIdentityRegistry": [dict(semantic_row)],
        "artifactPublicationBindings": [dict(semantic_row)],
        "channel": "preview",
        "channelId": "preview",
        "desktopSurfaceRefs": [dict(semantic_row)],
        "desktopTupleCoverage": coverage,
        "downloads": [compatibility_row],
        "generationId": GENERATION_ID,
        "installAwareArtifactRegistry": install_aware,
        "platformScope": "windows_only",
        "registryCommit": REGISTRY_COMMIT,
        "registry_commit": REGISTRY_COMMIT,
        "releaseVersion": VERSION,
        "version": VERSION,
    }
    sidecar = {
        "contractName": "chummer6-ui.windows_bootstrap_payload",
        "downloadUrl": (
            f"https://chummer.run/downloads/files/{payload_name}"
        ),
        "fileName": payload_name,
        "installerFileName": installer_name,
        "payloadAcquisitionMode": "download",
        "releaseVersion": VERSION,
        "sha256": payload_sha,
        "sizeBytes": len(payload_raw),
    }
    canonical_path = bundle / "RELEASE_CHANNEL.generated.json"
    compatibility_path = bundle / "releases.json"
    sidecar_path = files / sidecar_name
    write(canonical_path, pretty_bytes(canonical))
    write(compatibility_path, pretty_bytes(compatibility))
    write(sidecar_path, pretty_bytes(sidecar))

    decision = {
        "approvedAtUtc": "2026-07-24T06:35:55Z",
        "approvedBy": "Workspace owner",
        "channel": "preview",
        "contractName": "chummer.release-scope-decision/v1",
        "contractVersion": 1,
        "decisionId": "scope-run-20260724-scope-bound-test",
        "platforms": [
            {
                "artifactAccessClass": "open_public",
                "fallbackHeads": [],
                "platform": "windows",
                "primaryHead": "avalonia",
                "rid": "win-x64",
                "signingRequirement": "preview_unsigned_allowed",
            }
        ],
        "releaseTarget": "preview",
        "releaseVersion": VERSION,
        "status": "approved",
        "supportOwner": "chummer-release-operations",
    }
    decision_path = tmp_path / "RELEASE_SCOPE_DECISION.approved.json"
    write(decision_path, canonical_bytes(decision))
    decision_sha = sha(decision_path)
    authority_output = (
        authority_dir / "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    )
    direct_output = (
        tmp_path / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    )
    return {
        "root": tmp_path,
        "bundle": bundle,
        "canonical": canonical_path,
        "compatibility": compatibility_path,
        "sidecar": sidecar_path,
        "decision": decision_path,
        "decisionSha": decision_sha,
        "scopeAuthority": (
            "design://release-scope/"
            f"{decision['decisionId']}/sha256/{decision_sha}"
        ),
        "authority": authority_output,
        "direct": direct_output,
    }


def invoke(
    item: dict[str, Any],
    *,
    expected_scope_sha: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--bundle-root",
            str(item["bundle"]),
            "--generation-id",
            GENERATION_ID,
            "--release-scope-decision",
            str(item["decision"]),
            "--expected-release-scope-sha256",
            expected_scope_sha or item["decisionSha"],
            "--release-scope-authority",
            item["scopeAuthority"],
            "--hub-commit",
            HUB_COMMIT,
            "--registry-commit",
            REGISTRY_COMMIT,
            "--ui-commit",
            UI_COMMIT,
            "--authority-output",
            str(item["authority"]),
            "--direct-import-output",
            str(item["direct"]),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def add_cutover_review_evidence(item: dict[str, Any]) -> None:
    canonical_raw = item["canonical"].read_bytes()
    canonical = json.loads(canonical_raw)
    artifact = canonical["artifacts"][0]
    artifact_id = artifact["artifactId"]
    install_route = f"/downloads/install/{artifact_id}"
    support_owner = "chummer-release-operations"
    next_actions = ["Keep the fixture under review."]
    handoff = {
        "contractName": "chummer.public-preview-byte-handoff/v1",
        "status": "approved_public_preview_bytes",
        "sourcePublicationState": "preview",
        "releaseScopeDecisionSha256": item["decisionSha"],
        "releaseVersion": VERSION,
        "channel": "preview",
        "artifactId": artifact_id,
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "arch": "x64",
        "sha256": artifact["sha256"],
        "sizeBytes": artifact["sizeBytes"],
        "artifactAccessClass": "open_public",
        "signingRequirement": "preview_unsigned_allowed",
        "downloadUrl": artifact["downloadUrl"],
        "publicInstallRoute": install_route,
    }
    decision = {
        "contractName": "chummer.preview-release-decision/v2",
        "generatedAt": "2026-07-24T15:25:16Z",
        "status": "review_required",
        "releaseDecisionStatus": "review_required",
        "verdict": "PREVIEW_RELEASE_REVIEW_REQUIRED",
        "releaseVersion": VERSION,
        "releaseScopeDecisionSha256": item["decisionSha"],
        "channel": "preview",
        "platforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "fallbackHeadsByPlatform": {"windows": []},
        "artifactAccessClass": "open_public",
        "supportOwner": support_owner,
        "nextActions": next_actions,
        "registryCommit": REGISTRY_COMMIT,
        "manifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "authoritySnapshotSha256": "",
        "candidateDecisionStatus": "",
        "candidateDecisionSha256": "",
        "manifestGeneratedAt": canonical["publishedAt"],
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
    decision_raw = canonical_bytes(decision)
    snapshot = {
        "authorityContract": "chummer.release-authority-snapshot/v2",
        "releaseVersion": VERSION,
        "channel": "preview",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "artifactCount": 1,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": canonical["knownIssueSummary"],
        "manifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "registryRepository": "ArchonMegalon/chummer6-hub-registry",
        "registryCommit": REGISTRY_COMMIT,
        "releaseDecisionStatus": "review_required",
        "releaseDecisionSha256": hashlib.sha256(
            decision_raw
        ).hexdigest(),
        "supportOwner": support_owner,
        "nextActions": next_actions,
        "artifacts": [
            {
                "artifactId": artifact_id,
                "head": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "arch": "x64",
                "kind": "installer",
                "downloadUrl": artifact["downloadUrl"],
                "sha256": artifact["sha256"],
                "sizeBytes": artifact["sizeBytes"],
                "compatibilityState": "compatible",
                "promotionState": "promoted",
                "publicationScope": "signed-in-and-public",
                "revokeState": "not_revoked",
                "publicInstallRoute": install_route,
                "installAccessClass": "open_public",
            }
        ],
        "manifestPath": "RELEASE_CHANNEL.json",
        "releaseDecisionPath": "RELEASE_DECISION.json",
    }
    snapshot_raw = canonical_bytes(snapshot)
    current = {
        "releaseVersion": VERSION,
        "snapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "decisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        "status": "review_required",
    }
    smoke = {
        "status": "pass",
        "headId": "avalonia",
        "version": VERSION,
        "releaseVersion": VERSION,
        "channelId": "preview",
        "platform": "windows",
        "arch": "x64",
        "rid": "win-x64",
        "artifactDigest": f"sha256:{artifact['sha256']}",
        "artifactSha256": artifact["sha256"],
        "artifactId": artifact_id,
        "artifactFileName": artifact["fileName"],
        "fileName": artifact["fileName"],
        "artifactRelativePath": f"files/{artifact['fileName']}",
        "bootstrapPayloadSha256": artifact["payloadSha256"],
        "bootstrapPayloadSizeBytes": artifact["payloadSizeBytes"],
        "bootstrapPayloadFileName": artifact["payloadFileName"],
    }
    evidence = {
        "release-evidence/CURRENT.json": canonical_bytes(current),
        "release-evidence/RELEASE_DECISION.json": decision_raw,
        "release-evidence/SNAPSHOT.json": snapshot_raw,
        (
            "startup-smoke/"
            "startup-smoke-avalonia-win-x64.receipt.json"
        ): canonical_bytes(smoke),
    }
    for relative, raw in evidence.items():
        write(item["bundle"] / relative, raw, mode=0o400)


def test_materializer_roundtrips_through_projection_and_cutover_validator(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)

    completed = invoke(item)

    assert completed.returncode == 0, completed.stderr
    assert stat.S_IMODE(item["authority"].stat().st_mode) == 0o600
    assert stat.S_IMODE(item["direct"].stat().st_mode) == 0o600
    authority_raw = item["authority"].read_bytes()
    assert b"probeToken" not in authority_raw
    assert b"Authorization" not in authority_raw
    projection = load_module(
        PROJECTION, "scope_bound_projection_roundtrip"
    )
    authority = projection._validate_candidate_import_authority(
        authority_raw
    )
    binding = authority["custody"]["scopeBoundExistingBytes"]
    assert binding["retainedFromIncumbent"] == []
    assert binding["retainedPlatforms"] == []
    assert binding["shelfPlatforms"] == ["windows"]
    assert binding["releaseScopeDecisionSha256"] == item["decisionSha"]
    assert binding["sourceCommitPosture"] == {
        "hub": "cutover_source_head_required",
        "registry": "bound_to_sealed_manifest_aliases",
        "ui": "caller_asserted_unverified_informational",
    }

    snapshot_root = tmp_path / "projection"
    snapshot_root.mkdir(mode=0o700)
    publish_review_snapshot(projection, snapshot_root)
    projected = projection.publish_candidate_import_snapshot(
        snapshot_root,
        authority_path=item["authority"],
        expected_authority_sha256=sha(item["authority"]),
    )
    projected_authority = projected.outputs[
        "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    ]
    projected_release = projected.outputs[
        "RELEASE_CHANNEL.generated.json"
    ]
    assert projected_release.read_bytes() == item["canonical"].read_bytes()
    resolved = projection.resolve_current_snapshot(
        snapshot_root,
        purpose=projection.PROJECTION_PURPOSE_CANDIDATE_IMPORT,
    )
    assert resolved.snapshot_sha256 == projected.snapshot_sha256
    add_cutover_review_evidence(item)
    cutover = load_module(CUTOVER, "scope_bound_cutover_roundtrip")
    config = SimpleNamespace(
        source_root=REPO_ROOT,
        source_head=HUB_COMMIT,
        candidate_import_authority=projected_authority,
        candidate_import_authority_sha256=sha(projected_authority),
        direct_import_receipt=item["direct"],
        direct_import_receipt_sha256=sha(item["direct"]),
        release_candidate_root=item["bundle"],
        migration_candidate_root=tmp_path / "unused-migration",
        release_channel_receipt=projected_release,
        release_channel_receipt_sha256=sha(projected_release),
    )

    receipt = cutover.validate_release_candidate_authority(config)

    assert receipt["projectionProfile"] == (
        "v3_scope_bound_existing_windows_bytes"
    )
    assert receipt["generationId"] == GENERATION_ID
    assert len(receipt["freshDelta"]) == 3
    assert receipt["sourceCommits"] == {
        "hub": HUB_COMMIT,
        "registry": REGISTRY_COMMIT,
        "ui": UI_COMMIT,
    }
    assert receipt["sourceCommitVerification"] == {
        "hub": "verified_against_cutover_source_head",
        "registry": "verified_against_manifest_aliases",
        "ui": "caller_asserted_unverified_informational",
    }


def test_materializer_rejects_release_scope_digest_drift(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)

    completed = invoke(item, expected_scope_sha="d" * 64)

    assert completed.returncode != 0
    assert "SHA-256 drifted" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_credential_shaped_manifest_field(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    manifest = json.loads(item["canonical"].read_text())
    manifest["probeToken"] = "must-never-enter-authority"
    item["canonical"].write_bytes(pretty_bytes(manifest))
    item["canonical"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "credential-shaped field" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_candidate_symlink(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    sidecar_raw = item["sidecar"].read_bytes()
    outside = tmp_path / "outside-sidecar.json"
    write(outside, sidecar_raw)
    item["sidecar"].unlink()
    item["sidecar"].symlink_to(outside)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "symbolic link" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_group_writable_candidate_mode(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    payload = (
        item["bundle"]
        / "files"
        / "chummer-avalonia-win-x64-payload.zip"
    )
    payload.chmod(0o660)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "unsafe mode" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_special_candidate_mode(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    payload = (
        item["bundle"]
        / "files"
        / "chummer-avalonia-win-x64-payload.zip"
    )
    payload.chmod(0o4600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "unsafe mode" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_manifest_pair_byte_drift(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    compatibility = json.loads(item["compatibility"].read_text())
    compatibility["downloads"][0]["payloadSha256"] = "e" * 64
    item["compatibility"].write_bytes(pretty_bytes(compatibility))
    item["compatibility"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "manifest pair Windows byte bindings disagree" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_authority_output_inside_candidate(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    item["authority"] = (
        item["bundle"]
        / "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    )

    completed = invoke(item)

    assert completed.returncode != 0
    assert "must be outside the candidate bundle" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_protocol_relative_payload_url(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    sidecar = json.loads(item["sidecar"].read_text())
    sidecar["downloadUrl"] = (
        "//example.invalid/downloads/files/"
        "chummer-avalonia-win-x64-payload.zip"
    )
    item["sidecar"].write_bytes(pretty_bytes(sidecar))
    item["sidecar"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "sidecar differs from the manifest byte graph" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_generation_route_drift(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    canonical = json.loads(item["canonical"].read_text())
    compatibility = json.loads(item["compatibility"].read_text())
    canonical["artifacts"][0]["payloadDownloadUrl"] = (
        "https://example.invalid/payload?access_token=credential-value"
    )
    compatibility["downloads"][0]["payloadDownloadUrl"] = (
        "https://example.invalid/payload?access_token=credential-value"
    )
    item["canonical"].write_bytes(pretty_bytes(canonical))
    item["canonical"].chmod(0o600)
    item["compatibility"].write_bytes(pretty_bytes(compatibility))
    item["compatibility"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert (
        "credential-shaped material" in completed.stderr
        or "generation-aware manifest routes drifted" in completed.stderr
        or "URL query or fragment" in completed.stderr
    )
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_non_windows_required_platforms(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    for key in ("canonical", "compatibility"):
        manifest = json.loads(item[key].read_text())
        manifest["desktopTupleCoverage"]["requiredDesktopPlatforms"] = [
            "linux",
            "macos",
            "windows",
        ]
        item[key].write_bytes(pretty_bytes(manifest))
        item[key].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "Windows source posture drifted" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_registry_source_commit_drift(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    for key in ("canonical", "compatibility"):
        manifest = json.loads(item[key].read_text())
        manifest["registryCommit"] = "d" * 40
        manifest["registry_commit"] = "d" * 40
        item[key].write_bytes(pretty_bytes(manifest))
        item[key].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "Windows source posture drifted" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_nested_manifest_authority_overclaim(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    for key in ("canonical", "compatibility"):
        manifest = json.loads(item[key].read_text())
        manifest["publicationAuthorized"] = True
        manifest["deployAuthority"] = True
        item[key].write_bytes(pretty_bytes(manifest))
        item[key].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert (
        "must not claim authority" in completed.stderr
        or "must be exactly false" in completed.stderr
    )
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_unknown_nested_authority_overclaim(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    canonical = json.loads(item["canonical"].read_text())
    canonical["servingAuthority"] = True
    item["canonical"].write_bytes(pretty_bytes(canonical))
    item["canonical"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "must not claim authority" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_nested_semantic_route_escape(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    canonical = json.loads(item["canonical"].read_text())
    canonical["artifactPublicationBindings"][0][
        "publicInstallRoute"
    ] = "https://example.invalid/install?access_token=credential-value"
    item["canonical"].write_bytes(pretty_bytes(canonical))
    item["canonical"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert (
        "credential-shaped material" in completed.stderr
        or "semantic route graph drifted" in completed.stderr
        or "URL query or fragment" in completed.stderr
    )
    assert not item["authority"].exists()
    assert not item["direct"].exists()


@pytest.mark.parametrize(
    "support_url",
    (
        "/support?accessToken=credential-value",
        "/support?access-token=credential-value",
        "/support?access%5Ftoken=credential-value",
        "/support?token=credential-value",
        "/support#credential-value",
    ),
)
def test_materializer_rejects_query_or_fragment_in_extension_url(
    tmp_path: Path,
    support_url: str,
) -> None:
    item = fixture(tmp_path)
    for key in ("canonical", "compatibility"):
        manifest = json.loads(item[key].read_text())
        manifest["extension"] = {"supportUrl": support_url}
        item[key].write_bytes(pretty_bytes(manifest))
        item[key].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "URL query or fragment" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_rejects_nested_non_windows_coverage(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    for key in ("canonical", "compatibility"):
        manifest = json.loads(item[key].read_text())
        coverage = manifest["desktopTupleCoverage"]
        coverage["promotedPlatformHeads"]["macos"] = ["avalonia"]
        coverage["desktopRouteTruth"].append(
            {
                "artifactId": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platform": "macos",
                "publicInstallRoute": (
                    "/downloads/install/avalonia-osx-arm64-installer"
                ),
                "rid": "osx-arm64",
                "tupleId": "avalonia:macos:osx-arm64",
            }
        )
        item[key].write_bytes(pretty_bytes(manifest))
        item[key].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "Windows source posture drifted" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_materializer_requires_both_registry_commit_aliases(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    canonical = json.loads(item["canonical"].read_text())
    del canonical["registry_commit"]
    item["canonical"].write_bytes(pretty_bytes(canonical))
    item["canonical"].chmod(0o600)

    completed = invoke(item)

    assert completed.returncode != 0
    assert "Windows source posture drifted" in completed.stderr
    assert not item["authority"].exists()
    assert not item["direct"].exists()


def test_cutover_rejects_nonadjacent_direct_import_receipt(
    tmp_path: Path,
) -> None:
    item = fixture(tmp_path)
    completed = invoke(item)
    assert completed.returncode == 0, completed.stderr
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    copied_direct = (
        outside / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    )
    write(copied_direct, item["direct"].read_bytes())
    projection = load_module(
        PROJECTION, "scope_bound_projection_nonadjacent_direct"
    )
    cutover = load_module(
        CUTOVER, "scope_bound_cutover_nonadjacent_direct"
    )
    config = SimpleNamespace(
        source_root=REPO_ROOT,
        source_head=HUB_COMMIT,
        candidate_import_authority=item["authority"],
        candidate_import_authority_sha256=sha(item["authority"]),
        direct_import_receipt=copied_direct,
        direct_import_receipt_sha256=sha(copied_direct),
        release_candidate_root=item["bundle"],
        migration_candidate_root=tmp_path / "unused-migration",
        release_channel_receipt=item["canonical"],
        release_channel_receipt_sha256=sha(item["canonical"]),
    )

    with pytest.raises(cutover.CutoverError, match="candidate-adjacent"):
        cutover.validate_release_candidate_authority(
            config,
            projection_verifier=projection,
        )
