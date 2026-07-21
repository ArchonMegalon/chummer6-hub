from __future__ import annotations

import base64
import hashlib
import json
import stat
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_release_authority_advance_request.py"
SHA = "a" * 64


def write_json(path: Path, payload: object) -> bytes:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return raw


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def envelope(root: Path, name: str, status: str, predecessor: dict[str, str] | None = None):
    decision = {
        "releaseVersion": "run-20260720-220000",
        "releaseDecisionStatus": status,
        "status": status,
    }
    if predecessor is not None:
        decision.update(predecessor)
    decision_path = root / f"{name}-decision.json"
    decision_raw = write_json(decision_path, decision)
    snapshot = {
        "releaseVersion": "run-20260720-220000",
        "releaseDecisionStatus": status,
        "releaseDecisionSha256": digest(decision_raw),
    }
    snapshot_path = root / f"{name}-snapshot.json"
    snapshot_raw = write_json(snapshot_path, snapshot)
    current_path = root / f"{name}-current.json"
    current_raw = write_json(
        current_path,
        {
            "releaseVersion": "run-20260720-220000",
            "snapshotSha256": digest(snapshot_raw),
            "decisionSha256": digest(decision_raw),
            "status": status,
        },
    )
    return {
        "current": current_path,
        "current_raw": current_raw,
        "snapshot": snapshot_path,
        "snapshot_raw": snapshot_raw,
        "decision": decision_path,
        "decision_raw": decision_raw,
    }


def fixture(tmp_path: Path):
    predecessor = envelope(tmp_path, "predecessor", "review_required")
    scorecard = tmp_path / "scorecard.json"
    scorecard_raw = write_json(scorecard, {"status": "pass", "cells": []})
    convergence = tmp_path / "convergence.json"
    convergence_raw = write_json(convergence, {"status": "pass", "mismatchCount": 0})
    bindings = {
        "authoritySnapshotSha256": digest(predecessor["snapshot_raw"]),
        "candidateDecisionStatus": "review_required",
        "candidateDecisionSha256": digest(predecessor["decision_raw"]),
        "scorecardSha256": digest(scorecard_raw),
        "convergenceSha256": digest(convergence_raw),
    }
    successor = envelope(tmp_path, "successor", "preview_ready", bindings)
    shelf = tmp_path / "shelf-current.json"
    shelf_raw = write_json(
        shelf,
        {
            "schemaVersion": "chummer.release-shelf-current/v1",
            "generationId": "run-20260720-220000",
            "inventoryDigest": "sha256:" + SHA,
        },
    )
    return predecessor, successor, scorecard, convergence, shelf, shelf_raw


def command(tmp_path: Path, output: Path) -> list[str]:
    predecessor, successor, scorecard, convergence, shelf, _ = fixture(tmp_path)
    return [
        sys.executable,
        str(SCRIPT),
        "--generation-id",
        "run-20260720-220000",
        "--shelf-current",
        str(shelf),
        "--predecessor-current",
        str(predecessor["current"]),
        "--predecessor-snapshot",
        str(predecessor["snapshot"]),
        "--predecessor-decision",
        str(predecessor["decision"]),
        "--successor-current",
        str(successor["current"]),
        "--successor-snapshot",
        str(successor["snapshot"]),
        "--successor-decision",
        str(successor["decision"]),
        "--scorecard",
        str(scorecard),
        "--convergence",
        str(convergence),
        "--output",
        str(output),
    ]


def test_materializes_exact_byte_bound_authority_advance_request(tmp_path: Path) -> None:
    output = tmp_path / "request.json"
    completed = subprocess.run(command(tmp_path, output), text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert receipt["generationId"] == "run-20260720-220000"
    assert payload["expectedShelfPointerSha256"] == receipt["pointerSha256"]
    assert payload["expectedShelfInventoryDigest"] == "sha256:" + SHA
    assert base64.b64decode(payload["predecessorCurrentBytes"], validate=True) == (
        tmp_path / "predecessor-current.json"
    ).read_bytes()
    assert base64.b64decode(payload["successorDecisionBytes"], validate=True) == (
        tmp_path / "successor-decision.json"
    ).read_bytes()


def test_materializes_inert_staged_pointer_request_without_reading_public_current(
    tmp_path: Path,
) -> None:
    output = tmp_path / "staged-request.json"
    invocation = command(tmp_path, output)
    shelf_index = invocation.index("--shelf-current")
    del invocation[shelf_index : shelf_index + 2]
    staged = tmp_path / "staged-handoff.json"
    target_pointer_sha256 = "d" * 64
    write_json(
        staged,
        {
            "contractName": "chummer.staged-release-finalizer-handoff/v1",
            "contractVersion": 1,
            "status": "review_required",
            "state": "awaiting_owner_finalization",
            "secretRedacted": True,
            "publicCurrentMutated": False,
            "generationId": "run-20260720-220000",
            "releaseVersion": "run-20260720-220000",
            "targetPointerSha256": target_pointer_sha256,
            "inventoryDigest": "sha256:" + SHA,
        },
    )
    invocation[shelf_index:shelf_index] = ["--staged-handoff", str(staged)]

    completed = subprocess.run(invocation, text=True, capture_output=True)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["expectedShelfPointerSha256"] == target_pointer_sha256
    assert payload["expectedShelfInventoryDigest"] == "sha256:" + SHA


def test_rejects_staged_handoff_that_claims_current_was_mutated(tmp_path: Path) -> None:
    output = tmp_path / "staged-request.json"
    invocation = command(tmp_path, output)
    shelf_index = invocation.index("--shelf-current")
    del invocation[shelf_index : shelf_index + 2]
    staged = tmp_path / "staged-handoff.json"
    write_json(
        staged,
        {
            "contractName": "chummer.staged-release-finalizer-handoff/v1",
            "contractVersion": 1,
            "status": "review_required",
            "state": "awaiting_owner_finalization",
            "secretRedacted": True,
            "publicCurrentMutated": True,
            "generationId": "run-20260720-220000",
            "releaseVersion": "run-20260720-220000",
            "targetPointerSha256": "d" * 64,
            "inventoryDigest": "sha256:" + SHA,
        },
    )
    invocation[shelf_index:shelf_index] = ["--staged-handoff", str(staged)]

    completed = subprocess.run(invocation, text=True, capture_output=True)

    assert completed.returncode == 1
    assert "inert exact generation" in completed.stderr
    assert not output.exists()


def test_rejects_successor_proof_binding_tamper(tmp_path: Path) -> None:
    output = tmp_path / "request.json"
    invocation = command(tmp_path, output)
    decision_path = tmp_path / "successor-decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["convergenceSha256"] = "f" * 64
    decision_raw = write_json(decision_path, decision)
    snapshot_path = tmp_path / "successor-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["releaseDecisionSha256"] = digest(decision_raw)
    snapshot_raw = write_json(snapshot_path, snapshot)
    current_path = tmp_path / "successor-current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["decisionSha256"] = digest(decision_raw)
    current["snapshotSha256"] = digest(snapshot_raw)
    write_json(current_path, current)

    completed = subprocess.run(invocation, text=True, capture_output=True)
    assert completed.returncode == 1
    assert "convergenceSha256" in completed.stderr
    assert not output.exists()


def test_rejects_generation_drift_and_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "request.json"
    invocation = command(tmp_path, output)
    shelf = tmp_path / "shelf-current.json"
    payload = json.loads(shelf.read_text(encoding="utf-8"))
    payload["generationId"] = "different-generation"
    write_json(shelf, payload)
    rejected = subprocess.run(invocation, text=True, capture_output=True)
    assert rejected.returncode == 1
    assert "does not bind generationId" in rejected.stderr

    invocation = command(tmp_path, output)
    output.write_text("occupied", encoding="utf-8")
    repeated = subprocess.run(invocation, text=True, capture_output=True)
    assert repeated.returncode == 1
    assert "output already exists" in repeated.stderr


def test_generation_id_matches_release_shelf_policy(tmp_path: Path) -> None:
    for invalid_generation_id in ("run+preview", "r" * 129):
        output = tmp_path / (invalid_generation_id[:16] + ".json")
        invocation = command(tmp_path, output)
        generation_index = invocation.index("--generation-id") + 1
        invocation[generation_index] = invalid_generation_id

        completed = subprocess.run(invocation, text=True, capture_output=True)

        assert completed.returncode == 1
        assert "traversal-safe opaque token" in completed.stderr
        assert not output.exists()

    accepted_output = tmp_path / "accepted.json"
    accepted = command(tmp_path, accepted_output)
    accepted[accepted.index("--generation-id") + 1] = "run..preview"
    shelf_path = tmp_path / "shelf-current.json"
    shelf_payload = json.loads(shelf_path.read_text(encoding="utf-8"))
    shelf_payload["generationId"] = "run..preview"
    write_json(shelf_path, shelf_payload)

    completed = subprocess.run(accepted, text=True, capture_output=True)

    assert completed.returncode == 0, completed.stderr
    assert accepted_output.exists()
