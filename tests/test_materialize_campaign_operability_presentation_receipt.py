from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_campaign_operability_presentation_receipt.py"


def write_json(path: Path, payload: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def fixture(tmp_path: Path, evidence_id: str) -> dict[str, object]:
    release_version = "run-20260728-120000"
    artifact_sha256 = "a" * 64
    artifact_size = 1234
    artifact_id = "chummer-avalonia-win-x64-installer"
    source_sha = "d" * 40

    scope_path = tmp_path / "RELEASE_SCOPE_DECISION.approved.json"
    scope_raw = write_json(
        scope_path,
        {
            "contractName": "chummer.release-scope-decision/v1",
            "contractVersion": 1,
            "decisionId": "scope-run-20260728-120000",
            "status": "approved",
            "approvedAtUtc": "2026-07-28T12:00:00Z",
            "approvedBy": "Release authority",
            "releaseVersion": release_version,
            "channel": "preview",
            "releaseTarget": "preview",
            "supportOwner": "release-operations",
            "platforms": [
                {
                    "platform": "windows",
                    "rid": "win-x64",
                    "primaryHead": "avalonia",
                    "fallbackHeads": [],
                    "artifactAccessClass": "open_public",
                    "signingRequirement": "preview_unsigned_allowed",
                }
            ],
        },
    )
    scope_sha256 = hashlib.sha256(scope_raw).hexdigest()

    handoff = {
        "arch": "x64",
        "artifactAccessClass": "open_public",
        "artifactId": artifact_id,
        "channel": "preview",
        "contractName": "chummer.public-preview-byte-handoff/v1",
        "downloadUrl": f"/downloads/{artifact_id}.exe",
        "head": "avalonia",
        "platform": "windows",
        "publicInstallRoute": "/install",
        "releaseScopeDecisionSha256": scope_sha256,
        "releaseVersion": release_version,
        "rid": "win-x64",
        "sha256": artifact_sha256,
        "signingRequirement": "preview_unsigned_allowed",
        "sizeBytes": artifact_size,
        "sourcePublicationState": "preview",
        "status": "approved_public_preview_bytes",
    }

    manifest_raw = (
        json.dumps(
            {"releaseVersion": release_version},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    decision_payload = {
        "contractName": "chummer.preview-release-decision/v2",
        "releaseVersion": release_version,
        "releaseDecisionStatus": "review_required",
        "status": "review_required",
        "manifestSha256": manifest_sha256,
        "releaseScopeDecisionSha256": scope_sha256,
        "artifactHandoff": handoff,
    }
    decision_raw = (
        json.dumps(decision_payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    decision_sha256 = hashlib.sha256(decision_raw).hexdigest()
    snapshot_payload = {
        "authorityContract": "chummer.release-authority-snapshot/v2",
        "releaseVersion": release_version,
        "releaseDecisionStatus": "review_required",
        "releaseDecisionSha256": decision_sha256,
        "manifestSha256": manifest_sha256,
        "registryCommit": "c" * 40,
        "artifacts": [
            {
                "artifactId": artifact_id,
                "head": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "arch": "x64",
                "downloadUrl": handoff["downloadUrl"],
                "sha256": artifact_sha256,
                "sizeBytes": artifact_size,
                "publicInstallRoute": "/install",
                "installAccessClass": "open_public",
            }
        ],
    }
    snapshot_raw = (
        json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    authority = (
        tmp_path
        / "authority"
        / "snapshots"
        / release_version
        / snapshot_sha256
    )
    authority.mkdir(parents=True)
    manifest_path = authority / "RELEASE_CHANNEL.json"
    decision_path = authority / "RELEASE_DECISION.json"
    snapshot_path = authority / "SNAPSHOT.json"
    manifest_path.write_bytes(manifest_raw)
    decision_path.write_bytes(decision_raw)
    snapshot_path.write_bytes(snapshot_raw)

    source_path = tmp_path / "source" / f"{evidence_id}.json"
    common = {
        "releaseVersion": release_version,
        "platform": "windows",
        "rid": "win-x64",
    }
    if evidence_id == "desktop_visual":
        source_payload = {
            **common,
            "contractName": (
                "chummer6-ui.unsigned-preview-windows-installer-visual-proof"
            ),
            "contractVersion": 1,
            "status": "passed",
            "head": "avalonia",
            "artifactDigest": f"sha256:{artifact_sha256}",
            "checks": {
                "accountable_review_confirmed": True,
                "capture_mode": "hosted_native_windows",
            },
        }
    elif evidence_id == "desktop_executable":
        source_payload = {
            **common,
            "status": "pass",
            "headId": "avalonia",
            "artifactDigest": f"sha256:{artifact_sha256}",
            "artifactSha256": artifact_sha256,
            "artifactId": artifact_id,
            "executionEnvironment": "native_windows",
            "nativeHostEvidence": {
                "status": "verified",
                "isNativeWindows": True,
            },
        }
    else:
        source_payload = {
            "status": "passed",
            "reviewer": "release-authority",
            "candidateContentInventory": {
                "contractName": (
                    "chummer6-ui.preview-nightly-unsigned-candidate-content-inventory"
                ),
                "contractVersion": 1,
                "platformScope": "windows_only",
                "sourceSha": source_sha,
                "release": {
                    "version": release_version,
                    "channel": "preview",
                },
                "files": [
                    {
                        "path": f"publication/files/{artifact_id}.exe",
                        "sha256": artifact_sha256,
                        "sizeBytes": artifact_size,
                    }
                ],
            },
            "captureSource": {"sha": source_sha},
            "finalizationSource": {"sha": source_sha},
        }
    source_raw = write_json(source_path, source_payload)

    return {
        "release_version": release_version,
        "artifact_sha256": artifact_sha256,
        "scope_path": scope_path,
        "scope_sha256": scope_sha256,
        "manifest_path": manifest_path,
        "decision_path": decision_path,
        "snapshot_path": snapshot_path,
        "snapshot_sha256": snapshot_sha256,
        "decision_sha256": decision_sha256,
        "manifest_sha256": manifest_sha256,
        "source_path": source_path,
        "source_raw": source_raw,
        "source_sha256": hashlib.sha256(source_raw).hexdigest(),
        "source_payload": source_payload,
    }


def command(
    tmp_path: Path,
    evidence_id: str,
    *,
    output: Path | None = None,
    expected_source_sha256: str | None = None,
    snapshot_path: Path | None = None,
) -> tuple[list[str], dict[str, object], Path]:
    data = fixture(tmp_path, evidence_id)
    receipt = output or tmp_path / "receipts" / f"{evidence_id}.json"
    return (
        [
            sys.executable,
            str(SCRIPT),
            "--evidence-id",
            evidence_id,
            "--source",
            str(data["source_path"]),
            "--expected-source-sha256",
            expected_source_sha256 or str(data["source_sha256"]),
            "--allowed-source-root",
            str(tmp_path / "source"),
            "--release-scope-decision",
            str(data["scope_path"]),
            "--expected-release-scope-sha256",
            str(data["scope_sha256"]),
            "--manifest",
            str(data["manifest_path"]),
            "--snapshot",
            str(snapshot_path or data["snapshot_path"]),
            "--decision",
            str(data["decision_path"]),
            "--generated-at-utc",
            "2026-07-28T12:30:00Z",
            "--output",
            str(receipt),
        ],
        data,
        receipt,
    )


@pytest.mark.parametrize(
    "evidence_id",
    ["desktop_visual", "desktop_workflow", "desktop_executable"],
)
def test_materializes_exact_candidate_bound_receipt(
    tmp_path: Path,
    evidence_id: str,
) -> None:
    argv, data, receipt = command(tmp_path, evidence_id)
    source_before = Path(data["source_path"]).read_bytes()

    result = subprocess.run(argv, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    payload = json.loads(receipt.read_text())
    assert payload["status"] == "pass"
    assert payload["evidenceId"] == evidence_id
    assert payload["releaseVersion"] == data["release_version"]
    assert payload["sourceReceiptSha256"] == data["source_sha256"]
    assert payload["sourceArtifact"]["sha256"] == data["artifact_sha256"]
    binding = payload["campaign_operability_candidate_binding"]
    assert binding == {
        "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
        "contract_version": 1,
        "release_version": data["release_version"],
        "release_scope_decision_sha256": data["scope_sha256"],
        "manifest_sha256": data["manifest_sha256"],
        "authority_snapshot_sha256": data["snapshot_sha256"],
        "release_decision_sha256": data["decision_sha256"],
        "registry_commit": "c" * 40,
        "platform": "windows",
        "rid": "win-x64",
        "primary_head": "avalonia",
        "required_heads": ["avalonia"],
    }
    assert Path(data["source_path"]).read_bytes() == source_before
    assert os.stat(receipt).st_mode & 0o777 == 0o600


def test_rejects_source_digest_drift_without_output(tmp_path: Path) -> None:
    argv, _, receipt = command(
        tmp_path,
        "desktop_visual",
        expected_source_sha256="f" * 64,
    )

    result = subprocess.run(argv, capture_output=True, text=True)

    assert result.returncode == 1
    assert "source receipt SHA-256 does not match expected bytes" in result.stderr
    assert not receipt.exists()


def test_rejects_candidate_artifact_drift_without_output(tmp_path: Path) -> None:
    argv, data, receipt = command(tmp_path, "desktop_executable")
    source_path = Path(data["source_path"])
    payload = dict(data["source_payload"])
    payload["artifactSha256"] = "b" * 64
    drifted_raw = write_json(source_path, payload)
    source_index = argv.index("--expected-source-sha256") + 1
    argv[source_index] = hashlib.sha256(drifted_raw).hexdigest()

    result = subprocess.run(argv, capture_output=True, text=True)

    assert result.returncode == 1
    assert "does not prove the exact native candidate artifact" in result.stderr
    assert not receipt.exists()


def test_rejects_snapshot_outside_digest_bound_path(tmp_path: Path) -> None:
    argv, data, receipt = command(tmp_path, "desktop_visual")
    unbound = tmp_path / "unbound" / "SNAPSHOT.json"
    unbound.parent.mkdir()
    unbound.write_bytes(Path(data["snapshot_path"]).read_bytes())
    snapshot_index = argv.index("--snapshot") + 1
    argv[snapshot_index] = str(unbound)

    result = subprocess.run(argv, capture_output=True, text=True)

    assert result.returncode == 1
    assert "snapshot path does not bind its exact digest" in result.stderr
    assert not receipt.exists()


def test_fails_closed_when_output_already_exists(tmp_path: Path) -> None:
    argv, _, receipt = command(tmp_path, "desktop_workflow")
    first = subprocess.run(argv, capture_output=True, text=True)
    before = receipt.read_bytes()

    second = subprocess.run(argv, capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 1
    assert receipt.read_bytes() == before
