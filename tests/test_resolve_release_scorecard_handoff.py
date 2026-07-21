from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve_release_scorecard_handoff.py"
RELEASE_VERSION = "run-20260721-010203"


def write_json(path: Path, payload: object, *, mode: int | None = None) -> bytes:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    if mode is not None:
        path.chmod(mode)
    return raw


def fixture(tmp_path: Path, *, handoff_mode: int = 0o600):
    manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
    manifest_raw = write_json(manifest, {"version": RELEASE_VERSION})
    decision = tmp_path / "RELEASE_DECISION.json"
    decision_raw = write_json(
        decision,
        {
            "releaseVersion": RELEASE_VERSION,
            "releaseDecisionStatus": "review_required",
            "status": "review_required",
        },
    )
    snapshot = tmp_path / "SNAPSHOT.json"
    snapshot_raw = write_json(
        snapshot,
        {
            "releaseVersion": RELEASE_VERSION,
            "releaseDecisionStatus": "review_required",
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
        },
    )
    convergence = tmp_path / "convergence.json"
    convergence_raw = write_json(
        convergence,
        {
            "contractName": "chummer.live-release-convergence/v1",
            "contractVersion": 1,
            "status": "pass",
            "mismatchCount": 0,
            "failureCount": 0,
            "releaseDecisionStatus": "review_required",
            "releaseVersion": RELEASE_VERSION,
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "authoritySnapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "releaseTruth": {
                "releaseVersion": RELEASE_VERSION,
                "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
                "releaseDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            },
        },
    )
    scorecard = tmp_path / "scorecard.json"
    scorecard_raw = write_json(scorecard, {"status": "pass"})
    handoff = tmp_path / "scorecard-handoff.json"
    handoff_raw = write_json(
        handoff,
        {
            "contractName": "chummer.release-scorecard-handoff-request/v2",
            "releaseVersion": RELEASE_VERSION,
            "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
            "predecessorSnapshotSha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "predecessorDecisionSha256": hashlib.sha256(decision_raw).hexdigest(),
            "stagedConvergenceSha256": hashlib.sha256(convergence_raw).hexdigest(),
            "scorecardPath": str(scorecard),
            "scorecardSha256": hashlib.sha256(scorecard_raw).hexdigest(),
        },
        mode=handoff_mode,
    )
    return {
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
        "handoff": handoff,
        "handoff_raw": handoff_raw,
    }


def command(tmp_path: Path, data: dict[str, Path | bytes], output: Path) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--handoff",
        str(data["handoff"]),
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
        "--expected-release-version",
        RELEASE_VERSION,
        "--timeout-seconds",
        "0",
        "--poll-seconds",
        "1",
        "--output",
        str(output),
    ]


def test_resolves_exact_caller_owned_postconvergence_handoff(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    output = tmp_path / "resolution.json"
    completed = subprocess.run(
        command(tmp_path, data, output), text=True, capture_output=True
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["contractName"] == "chummer.release-scorecard-handoff-resolution/v2"
    assert payload["scorecardPath"] == str(data["scorecard"])
    assert payload["scorecardSha256"] == hashlib.sha256(data["scorecard_raw"]).hexdigest()
    assert payload["manifestSha256"] == hashlib.sha256(data["manifest_raw"]).hexdigest()
    assert payload["predecessorSnapshotSha256"] == hashlib.sha256(data["snapshot_raw"]).hexdigest()
    assert payload["predecessorDecisionSha256"] == hashlib.sha256(data["decision_raw"]).hexdigest()
    assert payload["stagedConvergenceSha256"] == hashlib.sha256(data["convergence_raw"]).hexdigest()
    assert payload["handoffSha256"] == hashlib.sha256(data["handoff_raw"]).hexdigest()
    assert output.stat().st_mode & 0o777 == 0o600


def test_rejects_non_private_or_wrong_convergence_handoff(tmp_path: Path) -> None:
    data = fixture(tmp_path, handoff_mode=0o644)
    output = tmp_path / "resolution.json"
    non_private = subprocess.run(
        command(tmp_path, data, output), text=True, capture_output=True
    )
    assert non_private.returncode == 1
    assert "mode 0600" in non_private.stderr
    assert not output.exists()

    data["handoff"].unlink()
    data = fixture(tmp_path)
    payload = json.loads(data["handoff"].read_text(encoding="utf-8"))
    payload["stagedConvergenceSha256"] = "f" * 64
    write_json(data["handoff"], payload, mode=0o600)
    wrong_convergence = subprocess.run(
        command(tmp_path, data, output), text=True, capture_output=True
    )
    assert wrong_convergence.returncode == 1
    assert "exact staged release authority" in wrong_convergence.stderr
    assert not output.exists()


def test_missing_handoff_times_out_without_waiting(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    data["handoff"].unlink()
    output = tmp_path / "resolution.json"
    completed = subprocess.run(
        command(tmp_path, data, output), text=True, capture_output=True
    )

    assert completed.returncode == 1
    assert "timed out waiting" in completed.stderr
    assert not output.exists()


def test_rejects_scorecard_outside_caller_owned_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    data = fixture(allowed)
    outside = tmp_path / "outside-scorecard.json"
    outside.write_bytes(data["scorecard_raw"])
    payload = json.loads(data["handoff"].read_text(encoding="utf-8"))
    payload["scorecardPath"] = str(outside)
    write_json(data["handoff"], payload, mode=0o600)
    output = allowed / "resolution.json"

    completed = subprocess.run(
        command(allowed, data, output), text=True, capture_output=True
    )
    assert completed.returncode == 1
    assert "caller-owned run workspace" in completed.stderr
    assert not output.exists()


def test_rejects_each_unbound_release_identity(tmp_path: Path) -> None:
    for field in (
        "manifestSha256",
        "predecessorSnapshotSha256",
        "predecessorDecisionSha256",
        "stagedConvergenceSha256",
    ):
        root = tmp_path / field
        root.mkdir()
        data = fixture(root)
        payload = json.loads(data["handoff"].read_text(encoding="utf-8"))
        payload[field] = "f" * 64
        write_json(data["handoff"], payload, mode=0o600)
        output = root / "resolution.json"
        completed = subprocess.run(
            command(root, data, output), text=True, capture_output=True
        )
        assert completed.returncode == 1, field
        assert "exact staged release authority" in completed.stderr
        assert not output.exists()
