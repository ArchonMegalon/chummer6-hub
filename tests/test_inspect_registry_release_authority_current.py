from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_registry_release_authority_current.py"


def raw(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def response_payload() -> dict[str, object]:
    version = "run-20260721-000001"
    manifest_raw = raw({"releaseVersion": version})
    decision_raw = raw(
        {
            "releaseVersion": version,
            "status": "review_required",
            "releaseDecisionStatus": "review_required",
        }
    )
    snapshot = {
        "releaseVersion": version,
        "releaseDecisionStatus": "review_required",
        "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
    }
    snapshot_raw = raw(snapshot)
    current = {
        "releaseVersion": version,
        "snapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "decisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        "status": "review_required",
    }
    return {
        "current": current,
        "snapshot": snapshot,
        "snapshotBytes": base64.b64encode(snapshot_raw).decode(),
        "manifestBytes": base64.b64encode(manifest_raw).decode(),
        "releaseDecisionBytes": base64.b64encode(decision_raw).decode(),
    }


def test_inspects_exact_registry_current_envelope(tmp_path: Path) -> None:
    response = tmp_path / "response.json"
    response.write_bytes(raw(response_payload()))
    output = tmp_path / "receipt.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--response", str(response), "--output", str(output)],
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["authorityState"] == "present"
    assert receipt["releaseDecisionStatus"] == "review_required"


def test_rejects_registry_current_digest_or_field_tamper(tmp_path: Path) -> None:
    payload = response_payload()
    payload["current"]["snapshotSha256"] = "f" * 64
    payload["unexpected"] = True
    response = tmp_path / "response.json"
    response.write_bytes(raw(payload))
    output = tmp_path / "receipt.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--response", str(response), "--output", str(output)],
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 1
    assert "unexpected field set" in completed.stderr
    assert not output.exists()


def test_materializes_explicit_absent_cas_state(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--absent", "--output", str(output)],
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["authorityState"] == "absent"
    assert receipt["snapshotSha256"] == "none"
