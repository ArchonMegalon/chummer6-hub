from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-windows-installer-visual-proof-handoff.py"
INSTALLER_NAME = "chummer-avalonia-win-x64-installer.exe"
ARTIFACT_ID = "avalonia-win-x64-installer"
VERSION = "run-proof-only-test"
VISUAL_REASON = (
    "Windows installer visual proof is missing; capture progress and completion screenshots on a Windows host."
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _fixture(tmp_path: Path) -> dict[str, Any]:
    bundle = tmp_path / "bundle"
    files = bundle / "files"
    files.mkdir(parents=True)
    installer = files / INSTALLER_NAME
    installer.write_bytes(b"MZ-proof-only-windows-installer")
    installer_digest = _sha256(installer)

    artifact = {
        "artifactId": ARTIFACT_ID,
        "fileName": INSTALLER_NAME,
        "downloadUrl": f"https://chummer.run/downloads/files/{INSTALLER_NAME}",
        "sha256": installer_digest.removeprefix("sha256:"),
        "platform": "windows",
        "head": "avalonia",
        "rid": "win-x64",
        "channelId": "preview",
        "releaseVersion": VERSION,
        "kind": "installer",
    }
    base_manifest = {
        "version": VERSION,
        "channel": "preview",
        "supportabilityState": "review_required",
        "publicTrustMetrics": {
            "releaseChannel": {
                "channelId": "preview",
                "supportabilityState": "review_required",
            }
        },
        "registryBoundaryCoverage": {
            "channelId": "preview",
            "releaseVersion": VERSION,
            "releaseChannel": {
                "supportabilityState": "review_required",
                "publicTrustPosture": "blocked",
            },
        },
    }
    releases = {**base_manifest, "downloads": [artifact]}
    canonical = {**base_manifest, "artifacts": [artifact]}
    releases_path = bundle / "releases.json"
    canonical_path = bundle / "RELEASE_CHANNEL.generated.json"
    _write_json(releases_path, releases)
    _write_json(canonical_path, canonical)

    receipt_name = "startup-smoke-avalonia-win-x64.receipt.json"
    receipt_path = bundle / "startup-smoke" / receipt_name
    receipt = {
        "status": "pass",
        "version": VERSION,
        "releaseVersion": VERSION,
        "channelId": "preview",
        "channel": "preview",
        "platform": "windows",
        "headId": "avalonia",
        "rid": "win-x64",
        "artifactId": ARTIFACT_ID,
        "artifactFileName": INSTALLER_NAME,
        "artifactDigest": installer_digest,
        "executionEnvironment": "wine_compatibility",
        "verificationScope": "compatibility_only",
    }
    _write_json(receipt_path, receipt)

    gate_path = bundle / "UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json"
    gate = {
        "contract_name": "chummer6-ui.windows_desktop_exit_gate",
        "status": "failed",
        "channelId": "preview",
        "releaseVersion": VERSION,
        "blockingMode": "external_only",
        "blocking_mode": "external_only",
        "head": {"app_key": "avalonia", "platform": "windows", "rid": "win-x64"},
        "reasons": [VISUAL_REASON],
        "checks": {
            "release_channel_id": "preview",
            "release_channel_version": VERSION,
            "installer_exists": True,
            "installer_sha256": installer_digest,
            "expected_windows_file_name": INSTALLER_NAME,
            "expected_windows_head": "avalonia",
            "expected_windows_rid": "win-x64",
            "startup_smoke_receipt_found": True,
            "startup_smoke_status": "pass",
            "startup_smoke_digest_matches_expected": True,
            "startup_smoke_artifact_digest": installer_digest,
            "startup_smoke_version": VERSION,
            "startup_smoke_channel": "preview",
            "windows_visual_proof_external_blocker": "missing_windows_visual_proof_capture",
            "windows_installer_visual_proof_current_capture_pending": True,
        },
    }
    _write_json(gate_path, gate)

    handoff_path = bundle / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"
    handoff = {
        "contract_name": "chummer6-ui.windows_installer_visual_proof_handoff",
        "handoff_only": True,
        "handoff_scope": "staged_nightly_windows_visual_proof",
        "stable_release_unchanged": True,
        "requires_separate_publish_lane": True,
        "status": "ready_for_windows_host",
        "only_blocker_is_visual_proof": True,
        "blockers": [],
        "release_channel_manifest_path": str(canonical_path),
        "windows_gate_path": str(gate_path),
        "windows_gate_status": "failed",
        "windows_gate_reasons": [VISUAL_REASON],
        "release": {
            "channel_id": "preview",
            "version": VERSION,
            "release_version": VERSION,
        },
        "windows_installer": {
            "artifact_id": ARTIFACT_ID,
            "file_name": INSTALLER_NAME,
            "sha256": installer_digest,
        },
        "startup_smoke_path": str(receipt_path),
        "startup_smoke": {
            "status": "pass",
            "version": VERSION,
            "release_version": VERSION,
            "artifact_file_name": INSTALLER_NAME,
            "artifact_digest": installer_digest,
            "receipt_file_name": receipt_name,
            "receipt_sha256": _sha256(receipt_path),
            "matches_release_version": True,
            "matches_artifact_file_name": True,
            "matches_artifact_digest": True,
        },
    }
    _write_json(handoff_path, handoff)
    return {
        "bundle": bundle,
        "files": files,
        "releases_path": releases_path,
        "canonical_path": canonical_path,
        "receipt_path": receipt_path,
        "gate_path": gate_path,
        "handoff_path": handoff_path,
        "releases": releases,
        "canonical": canonical,
        "gate": gate,
        "handoff": handoff,
    }


def _run(paths: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(paths["files"]),
            "--manifest",
            str(paths["releases_path"]),
            "--manifest",
            str(paths["canonical_path"]),
            "--handoff",
            str(paths["handoff_path"]),
            "--windows-gate",
            str(paths["gate_path"]),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_proof_only_visual_handoff_accepts_exact_preview_candidate(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    result = _run(paths)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_visual_proof_handoff_gate:ok" in result.stdout
    assert f"version={VERSION}" in result.stdout
    assert "posture=proof_only" in result.stdout


Mutation = Callable[[dict[str, Any]], None]


def _stable_channel(paths: dict[str, Any]) -> None:
    for key in ("releases", "canonical"):
        paths[key]["channel"] = "stable"
        _write_json(paths[f"{key}_path"], paths[key])


def _optimistic_supportability(paths: dict[str, Any]) -> None:
    paths["canonical"]["supportabilityState"] = "preview_supported"
    _write_json(paths["canonical_path"], paths["canonical"])


def _optimistic_public_trust(paths: dict[str, Any]) -> None:
    paths["canonical"]["registryBoundaryCoverage"]["releaseChannel"]["publicTrustPosture"] = "preview"
    _write_json(paths["canonical_path"], paths["canonical"])


def _handoff_has_another_blocker(paths: dict[str, Any]) -> None:
    paths["handoff"]["blockers"] = ["Windows signing receipt is missing."]
    _write_json(paths["handoff_path"], paths["handoff"])


def _handoff_digest_drift(paths: dict[str, Any]) -> None:
    paths["handoff"]["windows_installer"]["sha256"] = f"sha256:{'0' * 64}"
    _write_json(paths["handoff_path"], paths["handoff"])


def _startup_receipt_digest_drift(paths: dict[str, Any]) -> None:
    paths["handoff"]["startup_smoke"]["receipt_sha256"] = f"sha256:{'1' * 64}"
    _write_json(paths["handoff_path"], paths["handoff"])


def _nonvisual_gate_blocker(paths: dict[str, Any]) -> None:
    paths["gate"]["reasons"] = ["Windows signing receipt is missing."]
    paths["handoff"]["windows_gate_reasons"] = paths["gate"]["reasons"]
    _write_json(paths["gate_path"], paths["gate"])
    _write_json(paths["handoff_path"], paths["handoff"])


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (_stable_channel, "restricted to channel='preview'"),
        (_optimistic_supportability, "must set supportabilityState='review_required'"),
        (_optimistic_public_trust, "publicTrustPosture must be 'blocked'"),
        (_handoff_has_another_blocker, "handoff.blockers must be []"),
        (_handoff_digest_drift, "windows_installer.sha256 does not match"),
        (_startup_receipt_digest_drift, "receipt_sha256 does not match current stage receipt bytes"),
        (_nonvisual_gate_blocker, "reasons must be non-empty and visual-proof-only"),
    ],
)
def test_proof_only_visual_handoff_fails_closed_on_contract_drift(
    tmp_path: Path,
    mutation: Mutation,
    expected: str,
) -> None:
    paths = _fixture(tmp_path)
    mutation(paths)

    result = _run(paths)

    assert result.returncode != 0
    assert "windows_installer_visual_proof_handoff_gate:fail" in result.stderr
    assert expected in result.stderr
