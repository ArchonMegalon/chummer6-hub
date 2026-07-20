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
        },
    )
    scorecard = tmp_path / "scorecard.json"
    scorecard_raw = write_json(scorecard, {"status": "pass"})
    handoff = tmp_path / "scorecard-handoff.json"
    handoff_raw = write_json(
        handoff,
        {
            "contractName": "chummer.release-scorecard-handoff-request/v1",
            "releaseVersion": RELEASE_VERSION,
            "convergenceSha256": hashlib.sha256(convergence_raw).hexdigest(),
            "scorecardPath": str(scorecard),
            "scorecardSha256": hashlib.sha256(scorecard_raw).hexdigest(),
        },
        mode=handoff_mode,
    )
    return convergence, convergence_raw, scorecard, scorecard_raw, handoff, handoff_raw


def command(tmp_path: Path, handoff: Path, convergence: Path, output: Path) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--handoff",
        str(handoff),
        "--allowed-root",
        str(tmp_path),
        "--convergence",
        str(convergence),
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
    convergence, convergence_raw, scorecard, scorecard_raw, handoff, handoff_raw = fixture(
        tmp_path
    )
    output = tmp_path / "resolution.json"
    completed = subprocess.run(
        command(tmp_path, handoff, convergence, output), text=True, capture_output=True
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scorecardPath"] == str(scorecard)
    assert payload["scorecardSha256"] == hashlib.sha256(scorecard_raw).hexdigest()
    assert payload["convergenceSha256"] == hashlib.sha256(convergence_raw).hexdigest()
    assert payload["handoffSha256"] == hashlib.sha256(handoff_raw).hexdigest()
    assert output.stat().st_mode & 0o777 == 0o600


def test_rejects_non_private_or_wrong_convergence_handoff(tmp_path: Path) -> None:
    convergence, _, _, _, handoff, _ = fixture(tmp_path, handoff_mode=0o644)
    output = tmp_path / "resolution.json"
    non_private = subprocess.run(
        command(tmp_path, handoff, convergence, output), text=True, capture_output=True
    )
    assert non_private.returncode == 1
    assert "mode 0600" in non_private.stderr
    assert not output.exists()

    handoff.unlink()
    convergence, _, _, _, handoff, _ = fixture(tmp_path)
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    payload["convergenceSha256"] = "f" * 64
    write_json(handoff, payload, mode=0o600)
    wrong_convergence = subprocess.run(
        command(tmp_path, handoff, convergence, output), text=True, capture_output=True
    )
    assert wrong_convergence.returncode == 1
    assert "exact review-seed convergence" in wrong_convergence.stderr
    assert not output.exists()


def test_missing_handoff_times_out_without_waiting(tmp_path: Path) -> None:
    convergence, _, _, _, handoff, _ = fixture(tmp_path)
    handoff.unlink()
    output = tmp_path / "resolution.json"
    completed = subprocess.run(
        command(tmp_path, handoff, convergence, output), text=True, capture_output=True
    )

    assert completed.returncode == 1
    assert "timed out waiting" in completed.stderr
    assert not output.exists()


def test_rejects_scorecard_outside_caller_owned_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    convergence, convergence_raw, _, scorecard_raw, handoff, _ = fixture(allowed)
    outside = tmp_path / "outside-scorecard.json"
    outside.write_bytes(scorecard_raw)
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    payload["scorecardPath"] = str(outside)
    payload["convergenceSha256"] = hashlib.sha256(convergence_raw).hexdigest()
    write_json(handoff, payload, mode=0o600)
    output = allowed / "resolution.json"

    completed = subprocess.run(
        command(allowed, handoff, convergence, output), text=True, capture_output=True
    )
    assert completed.returncode == 1
    assert "caller-owned run workspace" in completed.stderr
    assert not output.exists()
