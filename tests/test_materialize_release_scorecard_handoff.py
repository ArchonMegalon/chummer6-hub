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
            "releaseDecisionSha256": "a" * 64,
            "releaseTruth": {
                "releaseVersion": release_version,
                "releaseDecisionStatus": "review_required",
                "releaseDecisionSha256": "a" * 64,
            },
        },
    )
    scorecard = tmp_path / "handoffs" / "scorecard.json"
    scorecard.parent.mkdir()
    scorecard_raw = write_json(
        scorecard,
        {
            "contract_name": "chummer.campaign_operability_scorecard",
            "contract_version": 2,
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
            "cells": [{"score": 2} for _ in range(36)],
        },
    )
    return release_version, convergence, convergence_raw, scorecard, scorecard_raw


def command(tmp_path: Path, *, scorecard_before: bool = False):
    release_version, convergence, _, scorecard, scorecard_raw = fixture(
        tmp_path, scorecard_before=scorecard_before
    )
    output = tmp_path / "release-evidence" / "scorecard.json"
    receipt = tmp_path / "release-evidence" / "handoff.json"
    return (
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(scorecard),
            "--expected-sha256",
            hashlib.sha256(scorecard_raw).hexdigest(),
            "--allowed-root",
            str(tmp_path),
            "--convergence",
            str(convergence),
            "--expected-release-version",
            release_version,
            "--output",
            str(output),
            "--receipt",
            str(receipt),
        ],
        scorecard_raw,
        output,
        receipt,
    )


def test_materializes_exact_postconvergence_scorecard_handoff(tmp_path: Path) -> None:
    invocation, scorecard_raw, output, receipt = command(tmp_path)
    completed = subprocess.run(invocation, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes() == scorecard_raw
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["scorecardSha256"] == hashlib.sha256(scorecard_raw).hexdigest()


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
