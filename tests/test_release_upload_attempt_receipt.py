from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "release" / "release_upload_attempt_receipt.py"


def run_helper(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HELPER), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def make_candidate(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    bundle = tmp_path / "bundle"
    files = bundle / "files"
    files.mkdir(parents=True)
    canonical = bundle / "RELEASE_CHANNEL.generated.json"
    canonical.write_text(json.dumps({"version": "run-proof", "artifacts": []}) + "\n", encoding="utf-8")
    artifact = files / "proof.bin"
    artifact.write_bytes(b"proof-bytes")
    summary = tmp_path / "candidate.json"
    receipt = tmp_path / "release-upload-handoff.json"
    result = run_helper(
        "summarize",
        "--bundle-root",
        str(bundle),
        "--canonical-manifest",
        str(canonical),
        "--output",
        str(summary),
        "--file",
        str(canonical),
        "--file",
        str(artifact),
    )
    assert result.returncode == 0, result.stderr
    return bundle, canonical, summary, receipt


def transition(summary: Path, receipt: Path, state: str) -> subprocess.CompletedProcess[str]:
    return run_helper(
        "transition",
        "--receipt",
        str(receipt),
        "--summary",
        str(summary),
        "--sessions-url",
        "https://chummer.run/api/internal/releases/upload-sessions",
        "--session-id",
        "0123456789abcdef0123456789abcdef",
        "--expires-at",
        "2026-07-16T00:00:00Z",
        "--state",
        state,
    )


def test_attempt_receipt_is_owner_only_exact_and_monotonic(tmp_path: Path) -> None:
    _bundle, _canonical, summary, receipt = make_candidate(tmp_path)

    for state in ("created", "uploaded", "request_started", "completed"):
        result = transition(summary, receipt, state)
        assert result.returncode == 0, result.stderr

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert payload["schemaVersion"] == "chummer.release-upload-handoff/v1"
    assert payload["apiOrigin"] == "https://chummer.run"
    assert payload["sessionId"] == "0123456789abcdef0123456789abcdef"
    assert payload["candidate"]["version"] == "run-proof"
    assert payload["candidate"]["fileCount"] == 2
    assert all(len(payload["candidate"][field]) == 64 for field in (
        "canonicalManifestSha256",
        "inventorySha256",
        "bundleIdentitySha256",
    ))
    assert payload["completion"]["state"] == "completed"
    assert [row["state"] for row in payload["stateHistory"]] == [
        "created",
        "uploaded",
        "request_started",
        "completed",
    ]

    blocked = run_helper("preflight", "--receipt", str(receipt))
    assert blocked.returncode != 0
    assert "reconcile or archive it" in blocked.stderr


def test_attempt_receipt_rejects_invalid_transition_and_candidate_tamper(tmp_path: Path) -> None:
    _bundle, _canonical, summary, receipt = make_candidate(tmp_path)
    assert transition(summary, receipt, "created").returncode == 0

    skipped = transition(summary, receipt, "request_started")
    assert skipped.returncode != 0
    assert "invalid durable upload receipt transition" in skipped.stderr

    candidate = json.loads(summary.read_text(encoding="utf-8"))
    candidate["version"] = "run-tampered"
    summary.write_text(json.dumps(candidate), encoding="utf-8")
    tampered = transition(summary, receipt, "uploaded")
    assert tampered.returncode != 0
    assert "bundleIdentitySha256 does not bind" in tampered.stderr


def test_candidate_summary_rejects_symlinks_and_files_outside_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    canonical = bundle / "RELEASE_CHANNEL.generated.json"
    canonical.write_text('{"version":"run-proof"}\n', encoding="utf-8")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    link = bundle / "linked.bin"
    os.symlink(outside, link)

    for candidate, expected in (
        (outside, "inside the bundle root"),
        (link, "symbolic link"),
    ):
        result = run_helper(
            "summarize",
            "--bundle-root",
            str(bundle),
            "--canonical-manifest",
            str(canonical),
            "--output",
            str(tmp_path / f"{candidate.name}.json"),
            "--file",
            str(canonical),
            "--file",
            str(candidate),
        )
        assert result.returncode != 0
        assert expected in result.stderr
