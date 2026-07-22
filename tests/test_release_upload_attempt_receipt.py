from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


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


def test_attempt_receipt_seals_inert_stage_handoff_monotonically(tmp_path: Path) -> None:
    _bundle, _canonical, summary, receipt = make_candidate(tmp_path)
    for state in ("created", "uploaded", "stage_request_started"):
        result = transition(summary, receipt, state)
        assert result.returncode == 0, result.stderr

    stage_response = receipt.parent / "release-stage-response.json"
    stage_response.write_text(
        json.dumps(
            {
                "candidateArtifactIds": ["avalonia-win-x64-installer"],
                "canonicalManifestSha256": "1" * 64,
                "channel": "preview",
                "compatibilityManifestSha256": "2" * 64,
                "exactIncomingDesktopScope": "avalonia:windows:win-x64",
                "generationId": "gen-proof",
                "inventoryDigest": "sha256:" + "3" * 64,
                "previousGenerationId": "gen-incumbent",
                "previousPointerSha256": "sha256:" + "5" * 64,
                "probeTokenExpiresAtUtc": "2026-07-22T00:15:00Z",
                "publishedAt": "2026-07-22T00:00:00Z",
                "responseSanitized": True,
                "stageReceiptId": "stage-proof",
                "stagedAtUtc": "2026-07-22T00:00:01Z",
                "suppressedFieldCount": 1,
                "targetPointerSha256": "4" * 64,
                "version": "run-proof",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    stage_response.chmod(0o600)
    staged = run_helper(
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
        "staged",
        "--stage-response",
        str(stage_response),
    )
    assert staged.returncode == 0, staged.stderr

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["completion"]["state"] == "staged"
    assert payload["stageResponse"] == {
        "path": "release-stage-response.json",
        "sha256": hashlib.sha256(stage_response.read_bytes()).hexdigest(),
        "generationId": "gen-proof",
        "stageReceiptId": "stage-proof",
        "exactIncomingDesktopScope": "avalonia:windows:win-x64",
    }
    assert [row["state"] for row in payload["stateHistory"]] == [
        "created",
        "uploaded",
        "stage_request_started",
        "staged",
    ]
    cannot_complete = transition(summary, receipt, "completed")
    assert cannot_complete.returncode != 0
    assert "invalid durable upload receipt transition" in cannot_complete.stderr


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("inventoryDigest", "3" * 64),
        ("previousPointerSha256", "5" * 64),
        ("canonicalManifestSha256", "sha256:" + "1" * 64),
        ("compatibilityManifestSha256", "sha256:" + "2" * 64),
        ("targetPointerSha256", "sha256:" + "4" * 64),
    ],
)
def test_stage_response_enforces_dto_specific_digest_formats(
    tmp_path: Path,
    field: str,
    invalid_value: str,
) -> None:
    payload = {
        "candidateArtifactIds": ["avalonia-win-x64-installer"],
        "canonicalManifestSha256": "1" * 64,
        "channel": "preview",
        "compatibilityManifestSha256": "2" * 64,
        "exactIncomingDesktopScope": "avalonia:windows:win-x64",
        "generationId": "gen-proof",
        "inventoryDigest": "sha256:" + "3" * 64,
        "previousGenerationId": "gen-incumbent",
        "previousPointerSha256": "sha256:" + "5" * 64,
        "probeTokenExpiresAtUtc": "2026-07-22T00:15:00Z",
        "publishedAt": "2026-07-22T00:00:00Z",
        "responseSanitized": True,
        "stageReceiptId": "stage-proof",
        "stagedAtUtc": "2026-07-22T00:00:01Z",
        "suppressedFieldCount": 1,
        "targetPointerSha256": "4" * 64,
        "version": "run-proof",
    }
    payload[field] = invalid_value
    source = tmp_path / "stage-response.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    source.chmod(0o600)

    result = run_helper(
        "persist-stage-response",
        "--source",
        str(source),
        "--output",
        str(tmp_path / "durable-stage-response.json"),
    )

    assert result.returncode != 0
    assert f"stage response {field} is invalid" in result.stderr


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
