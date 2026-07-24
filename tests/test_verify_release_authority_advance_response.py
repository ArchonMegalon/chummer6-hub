from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_authority_advance_response.py"
GENERATION = "gen-run-20260721-000001"
VERSION = "run-20260721-000001"


def write_json(path: Path, payload: object) -> bytes:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return raw


def append_part(digest, label: str, raw: bytes) -> None:
    label_raw = label.encode()
    digest.update(struct.pack(">II", len(label_raw), len(raw)))
    digest.update(label_raw)
    digest.update(raw)


def fixture(tmp_path: Path):
    values = {
        "releaseScopeDecisionBytes": {
            "contractName": "chummer.release-scope-decision/v1",
            "releaseVersion": VERSION,
            "status": "approved",
        },
        "predecessorCurrentBytes": {"releaseVersion": VERSION, "status": "review_required"},
        "predecessorSnapshotBytes": {"releaseVersion": VERSION, "releaseDecisionStatus": "review_required"},
        "predecessorDecisionBytes": {
            "releaseVersion": VERSION,
            "status": "review_required",
            "releaseDecisionStatus": "review_required",
        },
        "successorCurrentBytes": {"releaseVersion": VERSION, "status": "preview_ready"},
        "successorSnapshotBytes": {"releaseVersion": VERSION, "releaseDecisionStatus": "preview_ready"},
        "successorDecisionBytes": {
            "releaseVersion": VERSION,
            "status": "preview_ready",
            "releaseDecisionStatus": "preview_ready",
        },
        "scorecardBytes": {"contract_name": "chummer.campaign_operability_scorecard"},
        "convergenceBytes": {"contractName": "chummer.live-release-convergence/v1"},
    }
    paths = {}
    raws = {}
    for name, payload in values.items():
        path = tmp_path / f"{name}.json"
        paths[name] = path
        raws[name] = write_json(path, payload)

    pointer = "a" * 64
    inventory = "b" * 64
    scope_sha256 = hashlib.sha256(raws["releaseScopeDecisionBytes"]).hexdigest()
    request = {
        "generationId": GENERATION,
        "expectedShelfPointerSha256": pointer,
        "expectedShelfInventoryDigest": "sha256:" + inventory,
        "expectedReleaseScopeDecisionSha256": scope_sha256,
        **{name: base64.b64encode(raw).decode() for name, raw in raws.items()},
    }
    request_path = tmp_path / "request.json"
    write_json(request_path, request)

    digest = hashlib.sha256()
    append_part(digest, "generation", GENERATION.encode())
    append_part(digest, "shelf-pointer", pointer.encode())
    append_part(digest, "shelf-inventory", inventory.encode())
    append_part(digest, "release-scope-digest", scope_sha256.encode())
    append_part(digest, "release-scope", raws["releaseScopeDecisionBytes"])
    for label, name in (
        ("predecessor-current", "predecessorCurrentBytes"),
        ("predecessor-snapshot", "predecessorSnapshotBytes"),
        ("predecessor-decision", "predecessorDecisionBytes"),
        ("successor-current", "successorCurrentBytes"),
        ("successor-snapshot", "successorSnapshotBytes"),
        ("successor-decision", "successorDecisionBytes"),
        ("scorecard", "scorecardBytes"),
        ("convergence", "convergenceBytes"),
    ):
        append_part(digest, label, raws[name])
    response = {
        "generationId": GENERATION,
        "releaseVersion": VERSION,
        "revisionId": "auth-" + digest.hexdigest(),
        "previousDecisionStatus": "review_required",
        "decisionStatus": "preview_ready",
        "snapshotSha256": hashlib.sha256(raws["successorSnapshotBytes"]).hexdigest(),
        "decisionSha256": hashlib.sha256(raws["successorDecisionBytes"]).hexdigest(),
        "scorecardSha256": hashlib.sha256(raws["scorecardBytes"]).hexdigest(),
        "convergenceSha256": hashlib.sha256(raws["convergenceBytes"]).hexdigest(),
        "journalReceiptId": "authority-" + "c" * 32,
        "committedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "recovered": False,
    }
    response_path = tmp_path / "response.json"
    write_json(response_path, response)
    return paths, request_path, response_path


def command(tmp_path: Path):
    paths, request, response = fixture(tmp_path)
    output = tmp_path / "receipt.json"
    return [
        sys.executable,
        str(SCRIPT),
        "--response",
        str(response),
        "--request",
        str(request),
        "--generation-id",
        GENERATION,
        "--release-version",
        VERSION,
        "--predecessor-current",
        str(paths["predecessorCurrentBytes"]),
        "--predecessor-snapshot",
        str(paths["predecessorSnapshotBytes"]),
        "--predecessor-decision",
        str(paths["predecessorDecisionBytes"]),
        "--successor-current",
        str(paths["successorCurrentBytes"]),
        "--successor-snapshot",
        str(paths["successorSnapshotBytes"]),
        "--successor-decision",
        str(paths["successorDecisionBytes"]),
        "--scorecard",
        str(paths["scorecardBytes"]),
        "--convergence",
        str(paths["convergenceBytes"]),
        "--release-scope-decision",
        str(paths["releaseScopeDecisionBytes"]),
        "--expected-release-scope-sha256",
        hashlib.sha256(paths["releaseScopeDecisionBytes"].read_bytes()).hexdigest(),
        "--output",
        str(output),
    ], response, output


def test_verifies_exact_authority_advance_response(tmp_path: Path) -> None:
    invocation, _, output = command(tmp_path)
    completed = subprocess.run(invocation, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["contractName"] == "chummer.release-authority-advance-response/v2"
    assert receipt["status"] == "pass"
    assert receipt["revisionId"].startswith("auth-")
    assert receipt["recovered"] is False
    assert receipt["releaseScopeDecisionSha256"] == hashlib.sha256(
        (tmp_path / "releaseScopeDecisionBytes.json").read_bytes()
    ).hexdigest()


def test_rejects_revision_or_digest_tamper(tmp_path: Path) -> None:
    invocation, response_path, output = command(tmp_path)
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    payload["decisionSha256"] = "f" * 64
    write_json(response_path, payload)
    completed = subprocess.run(invocation, text=True, capture_output=True)
    assert completed.returncode == 1
    assert "does not bind the exact successor request" in completed.stderr
    assert not output.exists()


def test_rejects_unknown_response_field_and_nonboolean_recovery(tmp_path: Path) -> None:
    invocation, response_path, output = command(tmp_path)
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    write_json(response_path, payload)
    unknown = subprocess.run(invocation, text=True, capture_output=True)
    assert unknown.returncode == 1
    assert "unexpected field set" in unknown.stderr
    assert not output.exists()

    second = tmp_path / "second"
    second.mkdir()
    invocation, response_path, output = command(second)
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    payload["recovered"] = "false"
    write_json(response_path, payload)
    recovered = subprocess.run(invocation, text=True, capture_output=True)
    assert recovered.returncode == 1
    assert "recovered must be boolean" in recovered.stderr
    assert not output.exists()


def test_rejects_release_scope_digest_or_exact_byte_drift(tmp_path: Path) -> None:
    invocation, _, output = command(tmp_path)
    scope_path = tmp_path / "releaseScopeDecisionBytes.json"
    scope_path.write_bytes(scope_path.read_bytes() + b" ")
    exact_byte_drift = subprocess.run(
        invocation, text=True, capture_output=True
    )
    assert exact_byte_drift.returncode == 1
    assert "releaseScopeDecisionBytes differs from exact input bytes" in exact_byte_drift.stderr
    assert not output.exists()

    second = tmp_path / "second"
    second.mkdir()
    invocation, _, output = command(second)
    request_path = second / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["expectedReleaseScopeDecisionSha256"] = "f" * 64
    write_json(request_path, request)
    digest_drift = subprocess.run(invocation, text=True, capture_output=True)
    assert digest_drift.returncode == 1
    assert "release-scope digest differs from exact input bytes" in digest_drift.stderr
    assert not output.exists()
