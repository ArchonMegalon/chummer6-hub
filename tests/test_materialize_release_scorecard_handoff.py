from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_release_scorecard_handoff.py"


def write_json(path: Path, payload: object) -> bytes:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return raw


def fixture(tmp_path: Path, *, scorecard_before: bool = False):
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    converged_at = now - dt.timedelta(minutes=2)
    scorecard_at = converged_at - dt.timedelta(seconds=1) if scorecard_before else now - dt.timedelta(minutes=1)
    release_version = "run-20260721-000001"
    release_scope = tmp_path / "RELEASE_SCOPE_DECISION.approved.json"
    release_scope_raw = write_json(
        release_scope,
        {
            "contractName": "chummer.release-scope-decision/v1",
            "contractVersion": 1,
            "decisionId": "scope-run-20260721-000001",
            "status": "approved",
            "approvedAtUtc": "2026-07-21T00:00:00Z",
            "approvedBy": "Release authority",
            "releaseVersion": release_version,
            "channel": "preview",
            "releaseTarget": "preview",
            "supportOwner": "release-operations",
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
    release_scope_sha256 = hashlib.sha256(release_scope_raw).hexdigest()
    manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
    manifest_raw = write_json(manifest, {"version": release_version})
    decision = tmp_path / "RELEASE_DECISION.json"
    decision_raw = write_json(
        decision,
        {
            "releaseVersion": release_version,
            "releaseDecisionStatus": "review_required",
            "status": "review_required",
        },
    )
    snapshot = tmp_path / "SNAPSHOT.json"
    snapshot_raw = write_json(
        snapshot,
        {
            "releaseVersion": release_version,
            "releaseDecisionStatus": "review_required",
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "supportOwner": "release-operations",
            "nextActions": ["Verify live route convergence."],
            "registryCommit": "b" * 40,
        },
    )
    convergence = tmp_path / "convergence.json"
    convergence_raw = write_json(
        convergence,
        {
            "contractName": "chummer.live-release-convergence/v1",
            "contractVersion": 1,
            "generatedAtUtc": converged_at.isoformat().replace("+00:00", "Z"),
            "status": "pass",
            "mismatchCount": 0,
            "failureCount": 0,
            "mismatches": [],
            "failures": [],
            "releaseDecisionStatus": "review_required",
            "releaseVersion": release_version,
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "authoritySnapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "releaseTruth": {
                "releaseVersion": release_version,
                "releaseDecisionStatus": "review_required",
                "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
                "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            },
        },
    )
    ui_frame = tmp_path / "UI_FRAME_INTEGRITY.generated.json"
    ui_candidate_binding = {
        "release_version": release_version,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "release_decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
        "release_scope_decision_sha256": release_scope_sha256,
        "authority_route": "/api/v1/public/release-truth/g/gen-test",
        "verification_mode": "staged_private",
    }
    ui_frame_raw = write_json(
        ui_frame,
        {
            "contract_name": "chummer.ui-frame-integrity/v2",
            "contract_version": 2,
            "status": "pass",
            "verdict": "READY",
            "request_methods": ["GET"],
            "failures": [],
            "release_version": release_version,
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "release_decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
            "release_scope_decision_sha256": release_scope_sha256,
            "candidate_binding": ui_candidate_binding,
        },
    )
    presentation_binding = {
        "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
        "contract_version": 1,
        "release_version": release_version,
        "release_scope_decision_sha256": release_scope_sha256,
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
        receipt_path = tmp_path / f"{evidence_id.upper()}.generated.json"
        presentation_receipts[evidence_id] = receipt_path
        presentation_raws[evidence_id] = write_json(
            receipt_path,
            {
                "status": "pass",
                "releaseVersion": release_version,
                "receipt_kind": evidence_id,
                "campaign_operability_candidate_binding": presentation_binding,
            },
        )
    scorecard = tmp_path / "handoffs" / "scorecard.json"
    scorecard.parent.mkdir()
    nested_source_sha256 = hashlib.sha256(b"nested evidence").hexdigest()
    nested_preview_evidence = {
        "provenance_kind": "nested_declaration",
        "source_receipt_sha256": nested_source_sha256,
        "proof": {
            "release_version": release_version,
            "release_scope_decision_sha256": release_scope_sha256,
        },
    }
    registry_source_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    registry_preview_evidence = {
        "provenance_kind": "registry_review_seed",
        "source_receipt_sha256": registry_source_sha256,
        "proof": {
            "release_version": release_version,
            "release_scope_decision_sha256": release_scope_sha256,
            "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "bounded_owner": "release-operations",
            "next_actions": ["Verify live route convergence."],
        },
    }
    ui_frame_source_sha256 = hashlib.sha256(ui_frame_raw).hexdigest()
    ui_frame_candidate_evidence = {
        "contract_name": "chummer.campaign-operability-candidate-evidence/v1",
        "contract_version": 1,
        "release_version": release_version,
        "release_scope_decision_sha256": release_scope_sha256,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "authority_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "release_decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
        "registry_commit": "b" * 40,
        "source_receipt_sha256": ui_frame_source_sha256,
    }
    generic_source_sha256 = hashlib.sha256(b"generic score-three journey").hexdigest()
    generic_candidate_evidence = {
        **ui_frame_candidate_evidence,
        "source_receipt_sha256": generic_source_sha256,
    }
    presentation_rows = []
    for evidence_id in (
        "desktop_visual",
        "desktop_workflow",
        "desktop_executable",
    ):
        source_sha256 = hashlib.sha256(presentation_raws[evidence_id]).hexdigest()
        presentation_rows.append(
            {
                "id": evidence_id,
                "score": 3,
                "source_status": "pass",
                "source_verdict": "PASS",
                "source_sha256": source_sha256,
                "source_release_version": release_version,
                "candidate_evidence": {
                    **ui_frame_candidate_evidence,
                    "source_receipt_sha256": source_sha256,
                },
            }
        )
    scorecard_raw = write_json(
        scorecard,
        {
            "contract_name": "chummer.campaign_operability_scorecard",
            "contract_version": 2,
            "release_version": release_version,
            "release_scope_decision_sha256": release_scope_sha256,
            "releaseVersion": release_version,
            "releaseScopeDecisionSha256": release_scope_sha256,
            "snapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "generated_at_utc": scorecard_at.isoformat().replace("+00:00", "Z"),
            "preview_status": "pass",
            "preview_verdict": "CAMPAIGN_OPERABILITY_PREVIEW_READY",
            "preview_failures": [],
            "summary": {
                "cell_count": 36,
                "at_least_2_count": 36,
                "below_2_count": 0,
                "minimum_score": 2,
            },
            "cells": [
                {
                    "score": 3 if index == 35 else 2,
                    "evidence": (
                        [
                            {
                                "id": "journey_candidate_bound",
                                "score": 3,
                                "source_status": "ready",
                                "source_sha256": generic_source_sha256,
                                "source_release_version": release_version,
                                "candidate_evidence": generic_candidate_evidence,
                            },
                            {
                                "id": "ui_frame",
                                "score": 3,
                                "source_status": "pass",
                                "source_verdict": "PASS",
                                "source_sha256": ui_frame_source_sha256,
                                "source_release_version": release_version,
                                "candidate_evidence": ui_frame_candidate_evidence,
                            },
                            *presentation_rows,
                        ]
                        if index == 35
                        else [
                            {
                                "id": "release_channel" if index == 0 else f"evidence_{index:02d}",
                                "score": 2,
                                "source_status": "published" if index == 0 else "pass",
                                "source_verdict": "REVIEW_REQUIRED" if index == 0 else "PASS",
                                "source_sha256": (
                                    registry_source_sha256
                                    if index == 0
                                    else nested_source_sha256
                                ),
                                "bounded_owner": "release-operations",
                                "next_actions": ["Verify live route convergence."],
                                "preview_evidence": (
                                    registry_preview_evidence
                                    if index == 0
                                    else nested_preview_evidence
                                ),
                            }
                        ]
                    ),
                }
                for index in range(36)
            ],
        },
    )
    return {
        "release_version": release_version,
        "release_scope": release_scope,
        "release_scope_raw": release_scope_raw,
        "release_scope_sha256": release_scope_sha256,
        "manifest": manifest,
        "manifest_raw": manifest_raw,
        "snapshot": snapshot,
        "snapshot_raw": snapshot_raw,
        "decision": decision,
        "decision_raw": decision_raw,
        "convergence": convergence,
        "convergence_raw": convergence_raw,
        "scorecard": scorecard,
        "scorecard_raw": scorecard_raw,
        "ui_frame": ui_frame,
        "ui_frame_raw": ui_frame_raw,
        "presentation_receipts": presentation_receipts,
        "presentation_raws": presentation_raws,
    }


def command(tmp_path: Path, *, scorecard_before: bool = False):
    data = fixture(tmp_path, scorecard_before=scorecard_before)
    output = tmp_path / "release-evidence" / "scorecard.json"
    receipt = tmp_path / "release-evidence" / "handoff.json"
    return (
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(data["scorecard"]),
            "--expected-sha256",
            hashlib.sha256(data["scorecard_raw"]).hexdigest(),
            "--allowed-root",
            str(tmp_path),
            "--manifest",
            str(data["manifest"]),
            "--predecessor-snapshot",
            str(data["snapshot"]),
            "--predecessor-decision",
            str(data["decision"]),
            "--convergence",
            str(data["convergence"]),
            "--release-scope-decision",
            str(data["release_scope"]),
            "--expected-release-scope-sha256",
            str(data["release_scope_sha256"]),
            "--ui-frame-receipt",
            str(data["ui_frame"]),
            "--desktop-visual-receipt",
            str(data["presentation_receipts"]["desktop_visual"]),
            "--desktop-workflow-receipt",
            str(data["presentation_receipts"]["desktop_workflow"]),
            "--desktop-executable-receipt",
            str(data["presentation_receipts"]["desktop_executable"]),
            "--expected-release-version",
            str(data["release_version"]),
            "--output",
            str(output),
            "--receipt",
            str(receipt),
        ],
        data,
        output,
        receipt,
    )


def test_materializes_exact_postconvergence_scorecard_handoff(tmp_path: Path) -> None:
    invocation, data, output, receipt = command(tmp_path)
    completed = subprocess.run(invocation, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes() == data["scorecard_raw"]
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["contractName"] == "chummer.release-scorecard-handoff/v3"
    assert payload["status"] == "pass"
    assert payload["scorecardSha256"] == hashlib.sha256(data["scorecard_raw"]).hexdigest()
    assert payload["manifestSha256"] == hashlib.sha256(data["manifest_raw"]).hexdigest()
    assert payload["predecessorSnapshotSha256"] == hashlib.sha256(data["snapshot_raw"]).hexdigest()
    assert payload["predecessorDecisionSha256"] == hashlib.sha256(data["decision_raw"]).hexdigest()
    assert payload["stagedConvergenceSha256"] == hashlib.sha256(data["convergence_raw"]).hexdigest()
    assert payload["releaseScopeDecisionSha256"] == data["release_scope_sha256"]
    assert payload["registryCommit"] == "b" * 40
    assert payload["uiFrameReceiptSha256"] == hashlib.sha256(
        data["ui_frame_raw"]
    ).hexdigest()
    assert payload["desktopVisualReceiptSha256"] == hashlib.sha256(
        data["presentation_raws"]["desktop_visual"]
    ).hexdigest()
    assert payload["desktopWorkflowReceiptSha256"] == hashlib.sha256(
        data["presentation_raws"]["desktop_workflow"]
    ).hexdigest()
    assert payload["desktopExecutableReceiptSha256"] == hashlib.sha256(
        data["presentation_raws"]["desktop_executable"]
    ).hexdigest()


def test_rejects_digest_mismatch_and_preconvergence_scorecard(tmp_path: Path) -> None:
    invocation, _, output, _ = command(tmp_path)
    digest_index = invocation.index("--expected-sha256") + 1
    invocation[digest_index] = "f" * 64
    mismatch = subprocess.run(invocation, text=True, capture_output=True)
    assert mismatch.returncode == 1
    assert "does not match" in mismatch.stderr
    assert not output.exists()

    second_root = tmp_path / "second"
    second_root.mkdir()
    invocation, _, output, _ = command(second_root, scorecard_before=True)
    stale = subprocess.run(invocation, text=True, capture_output=True)
    assert stale.returncode == 1
    assert "after review-candidate convergence" in stale.stderr
    assert not output.exists()


def test_rejects_scorecard_outside_caller_owned_root(tmp_path: Path) -> None:
    invocation, _, output, _ = command(tmp_path)
    allowed_index = invocation.index("--allowed-root") + 1
    confined = tmp_path / "confined"
    confined.mkdir()
    invocation[allowed_index] = str(confined)
    completed = subprocess.run(invocation, text=True, capture_output=True)
    assert completed.returncode == 1
    assert "caller-owned run workspace" in completed.stderr
    assert not output.exists()


def test_rejects_convergence_or_predecessor_binding_drift(tmp_path: Path) -> None:
    for argument, label in (
        ("--manifest", "canonical release manifest"),
        ("--predecessor-snapshot", "predecessor authority"),
        ("--predecessor-decision", "predecessor authority"),
    ):
        root = tmp_path / argument.removeprefix("--")
        root.mkdir()
        invocation, _, output, _ = command(root)
        target = Path(invocation[invocation.index(argument) + 1])
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["releaseVersion"] = "run-different"
        if argument == "--manifest":
            payload["version"] = "run-different"
        write_json(target, payload)
        completed = subprocess.run(invocation, text=True, capture_output=True)
        assert completed.returncode == 1, argument
        assert label in completed.stderr
        assert not output.exists()


def test_rejects_release_scope_or_scorecard_candidate_binding_drift(tmp_path: Path) -> None:
    for mutation, expected in (
        ("scope_digest", "release-scope decision SHA-256"),
        ("scorecard_version", "preview-ready artifact"),
        ("scorecard_scope", "preview-ready artifact"),
        ("proof_scope", "score-2 proof"),
        ("registry_snapshot", "Registry proof"),
        ("generic_candidate_missing", "score-3 evidence"),
        ("generic_candidate_registry", "score-3 evidence"),
    ):
        root = tmp_path / mutation
        root.mkdir()
        invocation, _, output, _ = command(root)
        if mutation == "scope_digest":
            index = invocation.index("--expected-release-scope-sha256") + 1
            invocation[index] = "f" * 64
        else:
            scorecard = Path(invocation[invocation.index("--source") + 1])
            payload = json.loads(scorecard.read_text(encoding="utf-8"))
            if mutation == "scorecard_version":
                payload["release_version"] = "run-stale"
            elif mutation == "scorecard_scope":
                payload["release_scope_decision_sha256"] = "e" * 64
            elif mutation == "proof_scope":
                payload["cells"][1]["evidence"][0]["preview_evidence"]["proof"][
                    "release_scope_decision_sha256"
                ] = "e" * 64
            elif mutation == "registry_snapshot":
                payload["cells"][0]["evidence"][0]["preview_evidence"]["proof"][
                    "authority_snapshot_sha256"
                ] = "e" * 64
            elif mutation == "generic_candidate_missing":
                del payload["cells"][35]["evidence"][0]["candidate_evidence"]
            else:
                payload["cells"][35]["evidence"][0]["candidate_evidence"][
                    "registry_commit"
                ] = "e" * 40
            raw = write_json(scorecard, payload)
            invocation[invocation.index("--expected-sha256") + 1] = hashlib.sha256(
                raw
            ).hexdigest()
        completed = subprocess.run(invocation, text=True, capture_output=True)
        assert completed.returncode == 1, mutation
        assert expected in completed.stderr
        assert not output.exists()
