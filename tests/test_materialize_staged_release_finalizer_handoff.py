from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_staged_release_finalizer_handoff.py"
VERSION = "run-20260721-stage"
GENERATION = "gen-run-20260721-stage"
STAGE_RECEIPT = "stage-" + "a" * 48


def write_json(path: Path, payload: object, mode: int = 0o600) -> bytes:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return raw


def fixture(tmp_path: Path) -> dict[str, Path | bytes | str]:
    tmp_path.chmod(0o700)
    manifest = tmp_path / "evidence" / "RELEASE_CHANNEL.generated.json"
    manifest_raw = write_json(manifest, {"version": VERSION})
    scope_decision = tmp_path / "evidence" / "RELEASE_SCOPE_DECISION.approved.json"
    scope_decision_raw = write_json(
        scope_decision,
        {
            "contractName": "chummer.release-scope-decision/v1",
            "contractVersion": 1,
            "decisionId": "scope-run-20260721-stage",
            "status": "approved",
            "approvedAtUtc": "2026-07-21T00:00:00Z",
            "approvedBy": "Release authority",
            "releaseVersion": VERSION,
            "channel": "preview",
            "releaseTarget": "preview",
            "supportOwner": "chummer-release-operations",
            "platforms": [
                {
                    "platform": "macos",
                    "rid": "osx-arm64",
                    "primaryHead": "avalonia",
                    "fallbackHeads": [],
                    "artifactAccessClass": "open_public",
                    "signingRequirement": "preview_unsigned_allowed",
                }
            ],
        },
    )
    scope_authority = (
        "design://release-scope/scope-run-20260721-stage/sha256/"
        + hashlib.sha256(scope_decision_raw).hexdigest()
    )
    promotion = tmp_path / "evidence" / "public-promotion.json"
    promotion_raw = write_json(
        promotion,
        {
            "contractName": "chummer.run.desktop_release_publication",
            "artifacts": [{"artifactId": "avalonia-osx-arm64-installer"}],
        },
    )
    scope_verification = tmp_path / "evidence" / "RELEASE_SCOPE_VERIFICATION.generated.json"
    scope_verification_raw = write_json(
        scope_verification,
        {
            "contractName": "chummer.release-scope-verification/v1",
            "contractVersion": 1,
            "status": "pass",
            "verificationPhase": "candidate_inventory",
            "decisionSha256": hashlib.sha256(scope_decision_raw).hexdigest(),
            "decisionAuthority": scope_authority,
            "releaseVersion": VERSION,
            "channel": "preview",
            "supportOwner": "chummer-release-operations",
            "platforms": [
                {
                    "platform": "macos",
                    "rid": "osx-arm64",
                    "primaryHead": "avalonia",
                    "fallbackHeads": [],
                    "artifactAccessClass": "open_public",
                    "signingRequirement": "preview_unsigned_allowed",
                }
            ],
            "exactIncomingDesktopScope": "avalonia:macos:osx-arm64",
            "artifactIds": ["avalonia-osx-arm64-installer"],
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "promotionEvidenceSha256": hashlib.sha256(promotion_raw).hexdigest(),
        },
    )
    decision = tmp_path / "evidence" / "RELEASE_DECISION.json"
    decision_raw = write_json(
        decision,
        {
            "releaseVersion": VERSION,
            "releaseDecisionStatus": "review_required",
            "status": "review_required",
        },
    )
    snapshot = tmp_path / "evidence" / "SNAPSHOT.json"
    snapshot_raw = write_json(
        snapshot,
        {
            "releaseVersion": VERSION,
            "releaseDecisionStatus": "review_required",
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "registryCommit": "b" * 40,
            "primaryHeadByPlatform": {"macos": "avalonia"},
            "artifacts": [
                {
                    "platform": "macos",
                    "head": "avalonia",
                }
            ],
        },
    )
    current = tmp_path / "evidence" / "CURRENT.json"
    write_json(
        current,
        {
            "releaseVersion": VERSION,
            "status": "review_required",
            "snapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "decisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        },
    )
    stage_response = tmp_path / "evidence" / "stage-response.json"
    write_json(
        stage_response,
        {
            "responseSanitized": True,
            "version": VERSION,
            "channel": "preview",
            "generationId": GENERATION,
            "stageReceiptId": STAGE_RECEIPT,
            "inventoryDigest": "sha256:" + "b" * 64,
            "canonicalManifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "compatibilityManifestSha256": "c" * 64,
            "targetPointerSha256": "d" * 64,
            "probeTokenExpiresAtUtc": "2026-07-21T02:00:00Z",
            "candidateArtifactIds": ["avalonia-osx-arm64-installer"],
            "exactIncomingDesktopScope": "avalonia:macos:osx-arm64",
        },
    )
    convergence = tmp_path / "evidence" / "staged-convergence.json"
    convergence_raw = write_json(
        convergence,
        {
            "contractName": "chummer.live-release-convergence/v1",
            "contractVersion": 1,
            "verificationMode": "staged_private",
            "status": "pass",
            "mismatchCount": 0,
            "failureCount": 0,
            "releaseVersion": VERSION,
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "authoritySnapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "releaseTruth": {
                "releaseVersion": VERSION,
                "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
                "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            },
        },
    )
    ui_frame = tmp_path / "evidence" / "UI_FRAME_INTEGRITY.generated.json"
    ui_frame_raw = write_json(
        ui_frame,
        {
            "contract_name": "chummer.ui-frame-integrity/v2",
            "contract_version": 2,
            "status": "pass",
            "verdict": "READY",
            "request_methods": ["GET"],
            "failures": [],
            "release_version": VERSION,
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "release_decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
            "release_scope_decision_sha256": hashlib.sha256(
                scope_decision_raw
            ).hexdigest(),
            "candidate_binding": {
                "release_version": VERSION,
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
                "release_decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
                "release_scope_decision_sha256": hashlib.sha256(
                    scope_decision_raw
                ).hexdigest(),
                "authority_route": f"/api/v1/public/release-truth/g/{GENERATION}",
                "verification_mode": "staged_private",
            },
        },
    )
    presentation_binding = {
        "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
        "contract_version": 1,
        "release_version": VERSION,
        "release_scope_decision_sha256": hashlib.sha256(
            scope_decision_raw
        ).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "release_decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
        "registry_commit": "b" * 40,
        "platform": "macos",
        "rid": "osx-arm64",
        "primary_head": "avalonia",
        "required_heads": ["avalonia"],
    }
    presentation_receipts: dict[str, Path] = {}
    presentation_raws: dict[str, bytes] = {}
    for evidence_id in (
        "desktop_visual",
        "desktop_workflow",
        "desktop_executable",
    ):
        receipt_path = tmp_path / "evidence" / f"{evidence_id.upper()}.generated.json"
        presentation_receipts[evidence_id] = receipt_path
        presentation_raws[evidence_id] = write_json(
            receipt_path,
            {
                "status": "pass",
                "releaseVersion": VERSION,
                "receipt_kind": evidence_id,
                "campaign_operability_candidate_binding": presentation_binding,
            },
        )
    bootstrap = tmp_path / "bootstrap.sh"
    bootstrap.write_bytes(b"#!/usr/bin/env bash\nexit 0\n")
    bootstrap.chmod(0o700)
    finalizer = tmp_path / "scripts" / "finalize_staged_release.py"
    finalizer.parent.mkdir()
    finalizer.write_bytes(b"#!/usr/bin/env python3\n")
    finalizer.chmod(0o700)
    tool_paths: dict[str, Path] = {}
    for name in (
        "scorecard-materializer",
        "authority-advance-materializer",
        "authority-advance-verifier",
        "registry-current-inspector",
        "live-convergence-verifier",
        "registry-authority-materializer",
        "registry-authority-verifier",
        "registry-publish-materializer",
        "registry-publish-verifier",
        "registry-authority-library",
        "release-scope-verifier",
    ):
        path = tmp_path / "scripts" / f"{name}.py"
        path.write_bytes(f"# {name}\n".encode())
        path.chmod(0o700)
        tool_paths[name] = path
    return {
        "manifest": manifest,
        "manifest_raw": manifest_raw,
        "scope_decision": scope_decision,
        "scope_decision_raw": scope_decision_raw,
        "scope_verification": scope_verification,
        "scope_verification_raw": scope_verification_raw,
        "scope_authority": scope_authority,
        "promotion": promotion,
        "decision": decision,
        "decision_raw": decision_raw,
        "snapshot": snapshot,
        "snapshot_raw": snapshot_raw,
        "current": current,
        "stage_response": stage_response,
        "convergence": convergence,
        "convergence_raw": convergence_raw,
        "ui_frame": ui_frame,
        "ui_frame_raw": ui_frame_raw,
        "presentation_receipts": presentation_receipts,
        "presentation_raws": presentation_raws,
        "bootstrap": bootstrap,
        "finalizer": finalizer,
        "tool_paths": tool_paths,
    }


def command(tmp_path: Path, data: dict[str, Path | bytes | str], output: Path) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--workspace",
        str(tmp_path),
        "--session-id",
        "1" * 32,
        "--stage-response",
        str(data["stage_response"]),
        "--manifest",
        str(data["manifest"]),
        "--release-scope-decision",
        str(data["scope_decision"]),
        "--release-scope-verification",
        str(data["scope_verification"]),
        "--promotion-evidence",
        str(data["promotion"]),
        "--release-scope-authority",
        str(data["scope_authority"]),
        "--predecessor-current",
        str(data["current"]),
        "--predecessor-snapshot",
        str(data["snapshot"]),
        "--predecessor-decision",
        str(data["decision"]),
        "--staged-convergence",
        str(data["convergence"]),
        "--ui-frame-receipt",
        str(data["ui_frame"]),
        "--desktop-visual-receipt",
        str(dict(data["presentation_receipts"])["desktop_visual"]),
        "--desktop-workflow-receipt",
        str(dict(data["presentation_receipts"])["desktop_workflow"]),
        "--desktop-executable-receipt",
        str(dict(data["presentation_receipts"])["desktop_executable"]),
        "--executed-bootstrap",
        str(data["bootstrap"]),
        "--owner-finalizer",
        str(data["finalizer"]),
        *[
            item
            for name, path in dict(data["tool_paths"]).items()
            for item in (f"--{name}", str(path))
        ],
        "--sessions-url",
        "https://chummer.run/api/internal/releases/upload-sessions",
        "--live-base-url",
        "https://chummer.run",
        "--output",
        str(output),
    ]


def test_materializes_secret_redacted_exact_staged_handoff(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    output = tmp_path / "evidence" / "STAGED_RELEASE_FINALIZER_HANDOFF.json"
    result = subprocess.run(command(tmp_path, data, output), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["status"] == "review_required"
    assert payload["publicCurrentMutated"] is False
    assert payload["secretRedacted"] is True
    assert payload["generationId"] == GENERATION
    assert payload["manifestSha256"] == hashlib.sha256(data["manifest_raw"]).hexdigest()
    assert payload["releaseScopeDecisionSha256"] == hashlib.sha256(
        data["scope_decision_raw"]
    ).hexdigest()
    assert payload["exactIncomingDesktopScope"] == "avalonia:macos:osx-arm64"
    assert payload["releaseScopePlatforms"][0]["primaryHead"] == "avalonia"
    assert payload["stagedConvergenceSha256"] == hashlib.sha256(data["convergence_raw"]).hexdigest()
    assert payload["uiFrameReceiptSha256"] == hashlib.sha256(
        data["ui_frame_raw"]
    ).hexdigest()
    assert payload["desktopVisualReceiptSha256"] == hashlib.sha256(
        dict(data["presentation_raws"])["desktop_visual"]
    ).hexdigest()
    assert payload["desktopWorkflowReceiptSha256"] == hashlib.sha256(
        dict(data["presentation_raws"])["desktop_workflow"]
    ).hexdigest()
    assert payload["desktopExecutableReceiptSha256"] == hashlib.sha256(
        dict(data["presentation_raws"])["desktop_executable"]
    ).hexdigest()
    assert "probeToken" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600


def test_rejects_public_or_drifted_convergence(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    convergence = Path(data["convergence"])
    payload = json.loads(convergence.read_text())
    payload["verificationMode"] = "committed_public"
    write_json(convergence, payload)
    output = tmp_path / "evidence" / "handoff.json"
    result = subprocess.run(command(tmp_path, data, output), capture_output=True, text=True)
    assert result.returncode == 1
    assert "staged convergence" in result.stderr
    assert not output.exists()


def test_rejects_probe_secret_in_sanitized_stage_response(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    response = Path(data["stage_response"])
    payload = json.loads(response.read_text())
    payload["probeToken"] = "x" * 43
    write_json(response, payload)
    output = tmp_path / "evidence" / "handoff.json"
    result = subprocess.run(command(tmp_path, data, output), capture_output=True, text=True)
    assert result.returncode == 1
    assert "secret-redacted" in result.stderr
    assert not output.exists()


def test_rejects_stage_inventory_outside_approved_scope(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    response = Path(data["stage_response"])
    payload = json.loads(response.read_text())
    payload["candidateArtifactIds"] = ["rogue-osx-arm64-installer"]
    write_json(response, payload)
    output = tmp_path / "evidence" / "handoff.json"
    result = subprocess.run(command(tmp_path, data, output), capture_output=True, text=True)
    assert result.returncode == 1
    assert "approved release scope and inventory" in result.stderr
    assert not output.exists()


def test_rejects_symlinked_pinned_scope_input(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    scope = Path(data["scope_decision"])
    target = scope.with_name("scope-target.json")
    scope.rename(target)
    scope.symlink_to(target)
    output = tmp_path / "evidence" / "handoff.json"
    result = subprocess.run(command(tmp_path, data, output), capture_output=True, text=True)
    assert result.returncode == 1
    assert "without following symlinks" in result.stderr
    assert not output.exists()
