from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = REPO_ROOT / "scripts" / "release" / "release_upload_attempt_receipt.py"
MATERIALIZER = REPO_ROOT / "scripts" / "release" / "materialize_candidate_import_authority.py"
PROJECTION = REPO_ROOT / "scripts" / "release" / "verify_public_projection.py"
DEFAULT_HEADS = ("avalonia",)


def write_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return payload


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_embedded_document(
    authority: dict[str, object],
    path: str,
    mutate,
) -> None:
    native = authority["custody"]["nativeWindowsFinalizedEvidence"]
    entry = next(item for item in native["files"] if item["path"] == path)
    document = json.loads(base64.b64decode(entry["base64"]))
    replacement = mutate(document)
    payload = (json.dumps(replacement, sort_keys=True, separators=(",", ":")) + "\n").encode()
    entry["base64"] = base64.b64encode(payload).decode()
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    entry["sizeBytes"] = len(payload)


def write_rehashed_authority(path: Path, authority: dict[str, object]) -> None:
    path.write_bytes(
        (json.dumps(authority, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )


def refresh_rehashed_evidence_bindings(authority: dict[str, object]) -> None:
    native = authority["custody"]["nativeWindowsFinalizedEvidence"]
    entries = {entry["path"]: entry for entry in native["files"]}

    capture = json.loads(
        base64.b64decode(entries["WINDOWS_NATIVE_CAPTURE.generated.json"]["base64"])
    )
    candidate = capture.get("candidate")
    if isinstance(candidate, dict):
        for name, path in (
            (
                "contentInventory",
                "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
            ),
            (
                "exportReceipt",
                "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
            ),
        ):
            entry = entries[path]
            candidate[name] = {
                "path": path,
                "sha256": entry["sha256"],
                "sizeBytes": entry["sizeBytes"],
            }
            candidate[f"{name}Sha256"] = entry["sha256"]
    for head in capture.get("heads", []):
        for reference_name in ("receipt", "progressLog"):
            reference = head.get(reference_name)
            if isinstance(reference, dict) and reference.get("path") in entries:
                reference["sha256"] = entries[reference["path"]]["sha256"]
        for screenshot in head.get("screenshots", []):
            if isinstance(screenshot, dict) and screenshot.get("path") in entries:
                screenshot["sha256"] = entries[screenshot["path"]]["sha256"]
    rewrite_embedded_document(
        authority,
        "WINDOWS_NATIVE_CAPTURE.generated.json",
        lambda _: capture,
    )

    capture_inventory = json.loads(
        base64.b64decode(entries["WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"]["base64"])
    )
    capture_inventory["captureManifestSha256"] = entries[
        "WINDOWS_NATIVE_CAPTURE.generated.json"
    ]["sha256"]
    rewrite_embedded_document(
        authority,
        "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
        lambda _: capture_inventory,
    )

    finalization = json.loads(
        base64.b64decode(entries["WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"]["base64"])
    )
    finalization["captureInventorySha256"] = entries[
        "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
    ]["sha256"]
    for proof in finalization["proofs"]:
        proof["sha256"] = entries[proof["path"]]["sha256"]
    rewrite_embedded_document(
        authority,
        "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
        lambda _: finalization,
    )

    finalized_inventory = json.loads(
        base64.b64decode(entries["WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"]["base64"])
    )
    for row in finalized_inventory["files"]:
        entry = entries.get(row["path"])
        if entry is not None:
            row["sha256"] = entry["sha256"]
            row["sizeBytes"] = entry["sizeBytes"]
    rewrite_embedded_document(
        authority,
        "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json",
        lambda _: finalized_inventory,
    )


def source(workflow: str, actor: str, artifact: str) -> dict[str, str]:
    return {
        "repository": "ArchonMegalon/chummer6-ui",
        "workflow": workflow,
        "runId": "12345",
        "runAttempt": "1",
        "ref": "refs/heads/main",
        "sha": "a" * 40,
        "actor": actor,
        "artifactName": artifact,
    }


def refresh_finalized_inventory(root: Path) -> None:
    target = root / "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != target
    ]
    write_json(
        target,
        {
            "contractName": "chummer6-ui.preview-nightly-native-windows-finalized-inventory",
            "contractVersion": 1,
            "files": rows,
        },
    )


def refresh_directory_evidence_bindings(root: Path) -> None:
    capture_path = root / "WINDOWS_NATIVE_CAPTURE.generated.json"
    capture = json.loads(capture_path.read_text())
    for name, relative in (
        (
            "contentInventory",
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
        ),
        (
            "exportReceipt",
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
        ),
    ):
        document = root / relative
        capture["candidate"][name] = {
            "path": relative,
            "sha256": sha(document),
            "sizeBytes": document.stat().st_size,
        }
        capture["candidate"][f"{name}Sha256"] = sha(document)
    for head in capture.get("heads", []):
        for reference_name in ("receipt", "progressLog"):
            reference = head.get(reference_name)
            if isinstance(reference, dict):
                reference["sha256"] = sha(root / reference["path"])
        for screenshot in head.get("screenshots", []):
            if isinstance(screenshot, dict):
                screenshot["sha256"] = sha(root / screenshot["path"])
    write_json(capture_path, capture)

    capture_inventory_path = root / "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
    capture_inventory = json.loads(capture_inventory_path.read_text())
    capture_inventory["captureManifestSha256"] = sha(capture_path)
    write_json(capture_inventory_path, capture_inventory)

    finalization_path = root / "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
    finalization = json.loads(finalization_path.read_text())
    finalization["captureInventorySha256"] = sha(capture_inventory_path)
    for proof in finalization["proofs"]:
        proof["sha256"] = sha(root / proof["path"])
    write_json(finalization_path, finalization)
    refresh_finalized_inventory(root)


def candidate_fixture(
    tmp_path: Path,
    *,
    generated_at: datetime | None = None,
    runner: str = "powershell.exe",
    required_heads: tuple[str, ...] = DEFAULT_HEADS,
    artifact_heads: tuple[str, ...] | None = None,
    evidence_heads: tuple[str, ...] | None = None,
    extra_scope_drift: str | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    artifact_heads = artifact_heads or required_heads
    evidence_heads = evidence_heads or required_heads
    now = generated_at or datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")
    bundle = tmp_path / "bundle"
    files = bundle / "files"
    files.mkdir(parents=True)
    canonical = bundle / "RELEASE_CHANNEL.generated.json"
    all_byte_heads = tuple(dict.fromkeys((*artifact_heads, *evidence_heads)))
    for index, head in enumerate(all_byte_heads, start=1):
        (files / f"chummer-{head}-win-x64-installer.exe").write_bytes(
            b"MZ" + bytes([index]) * 16
        )
        (files / f"chummer-{head}-win-x64-payload.zip").write_bytes(
            b"PK" + bytes([index + 10]) * 24
        )
    artifacts = []
    for head in artifact_heads:
        installer = files / f"chummer-{head}-win-x64-installer.exe"
        payload = files / f"chummer-{head}-win-x64-payload.zip"
        artifacts.append(
            {
                "artifactId": f"{head}-win-x64-installer",
                "head": head,
                "platform": "windows",
                "rid": "win-x64",
                "arch": "x64",
                "kind": "installer",
                "installerMode": "bootstrap",
                "payloadAcquisitionMode": "download",
                "fileName": installer.name,
                "sha256": sha(installer),
                "sizeBytes": installer.stat().st_size,
                "payloadFileName": payload.name,
                "payloadSha256": sha(payload),
                "payloadSizeBytes": payload.stat().st_size,
            }
        )
    if extra_scope_drift == "rid":
        head = required_heads[0]
        extra_installer = files / f"chummer-{head}-win-arm64-installer.exe"
        extra_payload = files / f"chummer-{head}-win-arm64-payload.zip"
        extra_installer.write_bytes(b"MZ-extra-rid")
        extra_payload.write_bytes(b"PK-extra-rid")
        artifacts.append(
            {
                "artifactId": f"{head}-win-arm64-installer",
                "head": head,
                "platform": "windows",
                "rid": "win-arm64",
                "arch": "arm64",
                "kind": "installer",
                "installerMode": "bootstrap",
                "payloadAcquisitionMode": "download",
                "fileName": extra_installer.name,
                "sha256": sha(extra_installer),
                "sizeBytes": extra_installer.stat().st_size,
                "payloadFileName": extra_payload.name,
                "payloadSha256": sha(extra_payload),
                "payloadSizeBytes": extra_payload.stat().st_size,
            }
        )
    elif extra_scope_drift == "kind":
        head = required_heads[0]
        extra = files / f"chummer-{head}-win-x64-symbols.zip"
        extra.write_bytes(b"PK-extra-kind")
        artifacts.append(
            {
                "artifactId": f"{head}-win-x64-symbols",
                "head": head,
                "platform": "windows",
                "rid": "win-x64",
                "arch": "x64",
                "kind": "archive",
                "fileName": extra.name,
                "sha256": sha(extra),
                "sizeBytes": extra.stat().st_size,
            }
        )
    elif extra_scope_drift == "file":
        (files / f"chummer-{required_heads[0]}-win-x64-debug.zip").write_bytes(
            b"PK-extra-file"
        )
    elif extra_scope_drift is not None:
        raise AssertionError(f"unknown extra scope drift: {extra_scope_drift}")
    write_json(
        canonical,
        {
            "contractName": "Chummer.Hub.Registry.Contracts",
            "version": "run-candidate",
            "releaseVersion": "run-candidate",
            "channel": "preview",
            "channelId": "preview",
            "artifacts": artifacts,
            "desktopTupleCoverage": {
                "requiredDesktopHeads": list(required_heads),
            },
        },
    )

    summary = tmp_path / "candidate-summary.json"
    inventory = tmp_path / "candidate-inventory.json"
    command = [
        sys.executable,
        str(SUMMARY),
        "summarize",
        "--bundle-root",
        str(bundle),
        "--canonical-manifest",
        str(canonical),
        "--output",
        str(summary),
        "--inventory-output",
        str(inventory),
    ]
    for path in sorted(path for path in bundle.rglob("*") if path.is_file()):
        command.extend(("--file", str(path)))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr

    finalized = tmp_path / "finalized"
    finalized.mkdir()
    provenance_rows = [
        {
            "path": path.relative_to(bundle).as_posix(),
            "sha256": sha(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in sorted(path for path in bundle.rglob("*") if path.is_file())
    ]
    provenance = finalized / "candidate-provenance" / "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
    write_json(
        provenance,
        {
            "contractName": "chummer6-ui.preview-nightly-candidate-content-inventory",
            "contractVersion": 1,
            "release": {"channel": "preview", "version": "run-candidate"},
            "manifest": {
                "path": canonical.name,
                "sha256": sha(canonical),
            },
            "files": provenance_rows,
        },
    )
    producer_source = source(
        ".github/workflows/preview-nightly-candidate-export.yml",
        "candidate-producer",
        "preview-nightly-candidate-12345-1",
    )
    export_heads = []
    for head in evidence_heads:
        installer = files / f"chummer-{head}-win-x64-installer.exe"
        payload = files / f"chummer-{head}-win-x64-payload.zip"
        export_heads.append(
            {
                "headId": head,
                "rid": "win-x64",
                "installer": {
                    "relativePath": f"files/{installer.name}",
                    "fileName": installer.name,
                    "sha256": sha(installer),
                    "sizeBytes": installer.stat().st_size,
                },
                "payload": {
                    "relativePath": f"files/{payload.name}",
                    "fileName": payload.name,
                    "sha256": sha(payload),
                    "sizeBytes": payload.stat().st_size,
                },
            }
        )
    export_receipt = (
        finalized
        / "candidate-provenance"
        / "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
    )
    write_json(
        export_receipt,
        {
            "contractName": "chummer6-ui.preview-nightly-candidate-export",
            "contractVersion": 1,
            "status": "exported",
            "release": {"channel": "preview", "version": "run-candidate"},
            "candidateManifest": {
                "path": canonical.name,
                "sha256": sha(canonical),
            },
            "contentInventory": {
                "path": provenance.name,
                "sha256": sha(provenance),
            },
            "source": {
                **producer_source,
                "runnerLabel": "chummer-preview-nightly-export-abcdefghijkl",
            },
            "heads": export_heads,
        },
    )

    capture_source = source(
        ".github/workflows/windows-native-evidence-capture.yml",
        "github-actions[bot]",
        "windows-native-evidence-12345-1",
    )
    final_source = source(
        ".github/workflows/windows-native-evidence-finalize.yml",
        "accountable-reviewer",
        "windows-native-evidence-finalized-12345-1",
    )
    proof_bindings = []
    capture_heads = []
    for index, head in enumerate(evidence_heads, start=1):
        installer = files / f"chummer-{head}-win-x64-installer.exe"
        payload = files / f"chummer-{head}-win-x64-payload.zip"
        startup_relative = f"startup-smoke/startup-smoke-{head}-win-x64.receipt.json"
        write_json(
            finalized / startup_relative,
            {
                "status": "pass",
                "readyCheckpoint": "pre_ui_event_loop",
                "headId": head,
                "platform": "windows",
                "rid": "win-x64",
                "channelId": "preview",
                "releaseVersion": "run-candidate",
                "artifactFileName": installer.name,
                "artifactDigest": f"sha256:{sha(installer)}",
                "bootstrapPayloadAcquisitionMode": "download",
                "bootstrapPayloadFileName": payload.name,
                "bootstrapPayloadSha256": sha(payload),
                "bootstrapPayloadSizeBytes": payload.stat().st_size,
                "executionEnvironment": "native_windows",
                "nativeHostEvidence": {
                    "contractName": "chummer6-ui.native_windows_host_evidence",
                    "status": "verified",
                    "isNativeWindows": True,
                    "hostPlatform": "windows",
                    "hostKernel": "Windows_NT",
                    "runner": runner,
                    "evidenceSource": "GitHub-hosted windows-latest",
                },
            },
        )
        screenshots = []
        for role in ("progress", "completion"):
            relative = f"screenshots/windows-installer-{head}-win-x64-{role}.png"
            shot = finalized / relative
            shot.parent.mkdir(parents=True, exist_ok=True)
            shot.write_bytes(b"png" + bytes([index, 1 if role == "progress" else 2]))
            screenshots.append({"role": role, "path": relative, "sha256": sha(shot)})
        progress_relative = f"startup-smoke/windows-installer-progress-{head}-win-x64.log"
        progress = finalized / progress_relative
        progress.write_text("Install complete\n", encoding="utf-8")
        proof_relative = f"WINDOWS_INSTALLER_VISUAL_PROOF-{head}-win-x64.generated.json"
        proof = finalized / proof_relative
        write_json(
            proof,
            {
                "contractName": "chummer6-ui.windows_installer_visual_proof",
                "contractVersion": 1,
                "status": "passed",
                "generatedAt": timestamp,
                "version": "run-candidate",
                "releaseVersion": "run-candidate",
                "channel": "preview",
                "channelId": "preview",
                "platform": "windows",
                "head": head,
                "headId": head,
                "rid": "win-x64",
                "artifactFileName": installer.name,
                "artifactDigest": f"sha256:{sha(installer)}",
                "screenshots": screenshots,
                "checks": {
                    "capture_mode": "interactive",
                    "human_review_confirmed": True,
                },
                "readabilityReview": {
                    "status": "passed",
                    "reviewer": "accountable-reviewer",
                },
                "contrastReview": {
                    "status": "passed",
                    "reviewer": "accountable-reviewer",
                },
                "clippingReview": {
                    "status": "passed",
                    "reviewer": "accountable-reviewer",
                },
                "finalizationBinding": final_source,
            },
        )
        proof_bindings.append(
            {"headId": head, "path": proof_relative, "sha256": sha(proof)}
        )
        export_head = next(row for row in export_heads if row["headId"] == head)
        capture_heads.append(
            {
                **export_head,
                "receipt": {
                    "path": startup_relative,
                    "sha256": sha(finalized / startup_relative),
                },
                "progressLog": {
                    "path": progress_relative,
                    "sha256": sha(progress),
                },
                "screenshots": [
                    {**screenshot, "width": 1280, "height": 720}
                    for screenshot in screenshots
                ],
            }
        )

    candidate_binding = {
        **producer_source,
        "artifactId": "503",
        "artifactSha256": "d" * 64,
        "artifactCreatedAt": (now - timedelta(minutes=1))
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifactExpiresAt": (now + timedelta(days=14))
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifestPath": canonical.name,
        "manifestSha256": sha(canonical),
        "contentInventorySha256": sha(provenance),
        "exportReceiptSha256": sha(export_receipt),
        "handoffSha256": "b" * 64,
        "authenticatedApiSha256": "c" * 64,
        "contentInventory": {
            "path": provenance.relative_to(finalized).as_posix(),
            "sha256": sha(provenance),
            "sizeBytes": provenance.stat().st_size,
        },
        "exportReceipt": {
            "path": export_receipt.relative_to(finalized).as_posix(),
            "sha256": sha(export_receipt),
            "sizeBytes": export_receipt.stat().st_size,
        },
    }
    capture = finalized / "WINDOWS_NATIVE_CAPTURE.generated.json"
    write_json(
        capture,
        {
            "contractName": "chummer6-ui.preview-nightly-native-windows-capture",
            "contractVersion": 1,
            "status": "captured",
            "captureMode": "interactive",
            "generatedAt": timestamp,
            "version": "run-candidate",
            "channelId": "preview",
            "source": capture_source,
            "candidate": candidate_binding,
            "heads": capture_heads,
        },
    )
    capture_inventory = finalized / "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
    write_json(
        capture_inventory,
        {
            "contractName": "chummer6-ui.preview-nightly-native-windows-capture-inventory",
            "contractVersion": 1,
            "captureManifestSha256": sha(capture),
            "files": [],
        },
    )

    write_json(
        finalized / "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
        {
            "contractName": "chummer6-ui.preview-nightly-native-windows-finalization",
            "contractVersion": 1,
            "status": "passed",
            "generatedAt": timestamp,
            "captureInventorySha256": sha(capture_inventory),
            "captureSource": capture_source,
            "finalizationSource": final_source,
            "reviewer": "accountable-reviewer",
            "reviewerWasCaptureActor": False,
            "humanReviewConfirmed": True,
            "proofs": proof_bindings,
        },
    )
    refresh_finalized_inventory(finalized)
    return bundle, canonical, summary, inventory, finalized


def run_materializer(
    tmp_path: Path,
    *,
    generated_at: datetime | None = None,
    runner: str = "powershell.exe",
    required_heads: tuple[str, ...] = DEFAULT_HEADS,
    artifact_heads: tuple[str, ...] | None = None,
    evidence_heads: tuple[str, ...] | None = None,
    extra_scope_drift: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, tuple[Path, Path, Path, Path, Path]]:
    fixture = candidate_fixture(
        tmp_path,
        generated_at=generated_at,
        runner=runner,
        required_heads=required_heads,
        artifact_heads=artifact_heads,
        evidence_heads=evidence_heads,
        extra_scope_drift=extra_scope_drift,
    )
    return invoke_materializer(fixture, tmp_path / "candidate-authority.json")


def invoke_materializer(
    fixture: tuple[Path, Path, Path, Path, Path],
    output: Path,
) -> tuple[subprocess.CompletedProcess[str], Path, tuple[Path, Path, Path, Path, Path]]:
    bundle, canonical, summary, inventory, finalized = fixture
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--bundle-root",
            str(bundle),
            "--canonical-manifest",
            str(canonical),
            "--candidate-summary",
            str(summary),
            "--candidate-inventory",
            str(inventory),
            "--windows-finalized-root",
            str(finalized),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, output, fixture


def load_projection():
    spec = importlib.util.spec_from_file_location("candidate_projection_test", PROJECTION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def publish_review_snapshot(module, root: Path) -> None:
    payloads = {
        name: (
            b'{"status":"review_required"}\n'
            if name not in module.SNAPSHOT_OUTPUT_NAMES[:2]
            else b'{"status":"review-required-hub-proof"}\n'
        )
        for name in module.SNAPSHOT_OUTPUT_NAMES
    }
    payloads[module.SNAPSHOT_OUTPUT_NAMES[1]] = payloads[module.SNAPSHOT_OUTPUT_NAMES[0]]
    digests = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    snapshot_sha = module._snapshot_digest(digests)
    snapshot_id = f"public-projection-{snapshot_sha}"
    directory = root / snapshot_id
    directory.mkdir()
    for name, payload in payloads.items():
        (directory / name).write_bytes(payload)
    findings = [
        {
            "gate": "live public Windows installer",
            "status": "postdeploy_required",
            "reason": "live Windows installer proof must pass after code deployment",
        }
    ]
    common = {
        "contractName": module.SNAPSHOT_CONTRACT,
        "status": module.PROJECTION_STATUS_REVIEW_REQUIRED,
        "projectionStage": module.PROJECTION_STAGE_CODE_DEPLOY_REVIEW_REQUIRED,
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": False,
        "candidateImportAuthority": False,
        "releaseGateFindings": findings,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha,
        "authorityInputs": {},
        "outputs": {
            name: {
                "relativePath": name,
                "sha256": digests[name],
                "sizeBytes": len(payloads[name]),
            }
            for name in module.SNAPSHOT_OUTPUT_NAMES
        },
    }
    manifest = module._canonical_json_bytes(common)
    (directory / module.SNAPSHOT_MANIFEST_NAME).write_bytes(manifest)
    pointer = {
        key: value
        for key, value in common.items()
        if key not in {"authorityInputs", "outputs", "contractName"}
    }
    pointer.update(
        {
            "contractName": module.CURRENT_CONTRACT,
            "manifestRelativePath": f"{snapshot_id}/{module.SNAPSHOT_MANIFEST_NAME}",
            "manifestSha256": hashlib.sha256(manifest).hexdigest(),
            "outputs": {
                name: f"{snapshot_id}/{name}" for name in module.SNAPSHOT_OUTPUT_NAMES
            },
        }
    )
    (root / module.CURRENT_POINTER_NAME).write_bytes(module._canonical_json_bytes(pointer))


def test_fresh_native_finalization_materializes_exact_custody(tmp_path: Path) -> None:
    completed, output, fixture = run_materializer(tmp_path)
    assert completed.returncode == 0, completed.stderr
    authority = json.loads(output.read_text())
    assert authority["status"] == "candidate_import_ready"
    assert authority["candidate"]["fileCount"] == 3
    assert authority["custody"]["canonicalManifest"]["base64"]
    evidence = authority["custody"]["nativeWindowsFinalizedEvidence"]
    assert evidence["reviewer"] == "accountable-reviewer"
    assert len(evidence["files"]) >= 8
    capture_entry = next(
        row
        for row in evidence["files"]
        if row["path"] == "WINDOWS_NATIVE_CAPTURE.generated.json"
    )
    capture = json.loads(base64.b64decode(capture_entry["base64"]))
    assert capture["candidate"]["workflow"] == (
        ".github/workflows/preview-nightly-candidate-export.yml"
    )
    assert capture["candidate"]["exportReceipt"]["path"].startswith(
        "candidate-provenance/"
    )
    assert output.stat().st_mode & 0o777 == 0o600
    assert authority["candidate"]["canonicalManifestSha256"] == sha(fixture[1])


@pytest.mark.parametrize(
    ("generated_at", "runner", "expected"),
    [
        (datetime.now(timezone.utc) - timedelta(days=2), "powershell.exe", "stale"),
        (None, "wine64", "not exact native-Windows evidence"),
    ],
)
def test_stale_or_wine_windows_evidence_cannot_authorize_candidate_import(
    tmp_path: Path,
    generated_at: datetime | None,
    runner: str,
    expected: str,
) -> None:
    completed, output, _ = run_materializer(
        tmp_path, generated_at=generated_at, runner=runner
    )
    assert completed.returncode != 0
    assert expected in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("required_heads", "artifact_heads", "evidence_heads"),
    [
        (("avalonia",), ("avalonia",), ("avalonia", "blazor-desktop")),
        (
            ("avalonia", "blazor-desktop"),
            ("avalonia", "blazor-desktop"),
            ("avalonia",),
        ),
    ],
)
def test_manifest_and_native_evidence_head_scope_cannot_widen_or_narrow(
    tmp_path: Path,
    required_heads: tuple[str, ...],
    artifact_heads: tuple[str, ...],
    evidence_heads: tuple[str, ...],
) -> None:
    completed, output, _ = run_materializer(
        tmp_path,
        required_heads=required_heads,
        artifact_heads=artifact_heads,
        evidence_heads=evidence_heads,
    )

    assert completed.returncode != 0
    assert (
        "required-head" in completed.stderr
        or "required desktop tuples" in completed.stderr
    )
    assert not output.exists()


def test_materializer_rejects_windows_artifact_head_outside_required_scope(
    tmp_path: Path,
) -> None:
    completed, output, _ = run_materializer(
        tmp_path,
        required_heads=("avalonia",),
        artifact_heads=("avalonia", "blazor-desktop"),
        evidence_heads=("avalonia",),
    )

    assert completed.returncode != 0
    assert "outside requiredDesktopHeads" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize("drift", ["rid", "kind", "file"])
def test_allowed_head_windows_scope_cannot_widen_by_rid_kind_or_file(
    tmp_path: Path,
    drift: str,
) -> None:
    fixture = candidate_fixture(tmp_path, extra_scope_drift=drift)
    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert "required desktop tuple" in completed.stderr
    assert not output.exists()

    _, canonical_path, summary_path, inventory_path, _ = fixture
    module = load_projection()
    with pytest.raises(module.ProjectionBlocked, match="required desktop tuple"):
        module._candidate_windows_scope(
            json.loads(canonical_path.read_text()),
            json.loads(inventory_path.read_text())["files"],
            json.loads(summary_path.read_text()),
        )


def test_materializer_rejects_fully_rehashed_exporter_source_tamper(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    finalized = fixture[-1]
    export_path = (
        finalized
        / "candidate-provenance"
        / "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
    )
    export = json.loads(export_path.read_text())
    export["source"]["actor"] = "different-producer"
    write_json(export_path, export)
    refresh_directory_evidence_bindings(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert "source differs from capture authority" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "ready_checkpoint",
        "visual_contract_version",
        "visual_contract_type",
        "empty_runner",
        "blank_runner",
    ],
)
def test_materializer_rejects_fully_rehashed_native_evidence_contract_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    fixture = candidate_fixture(tmp_path)
    finalized = fixture[-1]
    startup_path = (
        finalized
        / "startup-smoke"
        / "startup-smoke-avalonia-win-x64.receipt.json"
    )
    visual_path = (
        finalized
        / "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json"
    )

    if tamper == "ready_checkpoint":
        startup = json.loads(startup_path.read_text())
        startup["readyCheckpoint"] = "post_ui_event_loop"
        write_json(startup_path, startup)
    elif tamper == "visual_contract_version":
        visual = json.loads(visual_path.read_text())
        visual["contractVersion"] = 2
        write_json(visual_path, visual)
    elif tamper == "visual_contract_type":
        visual = json.loads(visual_path.read_text())
        visual["contractVersion"] = True
        write_json(visual_path, visual)
    else:
        startup = json.loads(startup_path.read_text())
        startup["nativeHostEvidence"]["runner"] = (
            "" if tamper == "empty_runner" else "   "
        )
        write_json(startup_path, startup)
    refresh_directory_evidence_bindings(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_projection_scope_parser_rejects_windows_artifact_head_widening(
    tmp_path: Path,
) -> None:
    bundle, canonical_path, summary_path, inventory_path, _ = candidate_fixture(
        tmp_path,
        required_heads=("avalonia",),
        artifact_heads=("avalonia", "blazor-desktop"),
        evidence_heads=("avalonia",),
    )
    del bundle
    module = load_projection()

    with pytest.raises(module.ProjectionBlocked, match="outside requiredDesktopHeads"):
        module._candidate_windows_scope(
            json.loads(canonical_path.read_text()),
            json.loads(inventory_path.read_text())["files"],
            json.loads(summary_path.read_text()),
        )


def test_candidate_snapshot_is_mutually_bounded_and_cannot_be_reissued(
    tmp_path: Path,
) -> None:
    completed, authority_path, _ = run_materializer(tmp_path / "candidate")
    assert completed.returncode == 0, completed.stderr
    module = load_projection()
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(mode=0o700)
    publish_review_snapshot(module, snapshot_root)
    authority_sha = sha(authority_path)

    result = module.publish_candidate_import_snapshot(
        snapshot_root,
        authority_path=authority_path,
        expected_authority_sha256=authority_sha,
    )

    assert result.candidate_import_authority is True
    assert result.release_upload_authority is False
    assert result.code_deployment_authority is False
    assert set(result.outputs) == set(module.CANDIDATE_SNAPSHOT_OUTPUT_NAMES)
    resolved = module.resolve_current_snapshot(
        snapshot_root, purpose=module.PROJECTION_PURPOSE_CANDIDATE_IMPORT
    )
    assert resolved.snapshot_sha256 == result.snapshot_sha256
    with pytest.raises(module.ProjectionBlocked, match="not authorized for release upload"):
        module.resolve_current_snapshot(snapshot_root)
    with pytest.raises(module.ProjectionBlocked, match="not authorized for code deployment"):
        module.resolve_current_snapshot(
            snapshot_root, purpose=module.PROJECTION_PURPOSE_CODE_DEPLOY
        )
    with pytest.raises(module.ProjectionBlocked, match="not authorized for code deployment"):
        module.publish_candidate_import_snapshot(
            snapshot_root,
            authority_path=authority_path,
            expected_authority_sha256=authority_sha,
        )


@pytest.mark.parametrize(
    "tamper",
    [
        "empty_capture",
        "capture_actor",
        "capture_workflow",
        "stale_capture",
        "not_native",
        "wine_runner",
        "ready_checkpoint",
        "visual_contract_version",
        "visual_contract_type",
        "empty_runner",
        "blank_runner",
        "artifact_digest",
        "candidate_artifact_name",
        "export_source",
        "export_heads",
    ],
)
def test_projection_rejects_freshly_rehashed_semantic_evidence_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    completed, authority_path, _ = run_materializer(tmp_path / "candidate")
    assert completed.returncode == 0, completed.stderr
    authority = json.loads(authority_path.read_text())
    native = authority["custody"]["nativeWindowsFinalizedEvidence"]
    startup_path = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"
    proof_path = "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json"
    export_path = (
        "candidate-provenance/"
        "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
    )

    if tamper == "empty_capture":
        rewrite_embedded_document(authority, "WINDOWS_NATIVE_CAPTURE.generated.json", lambda _: {})
    elif tamper == "capture_actor":
        native["captureSource"]["actor"] = "untrusted-capture-actor"
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            lambda value: {**value, "source": native["captureSource"]},
        )
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
            lambda value: {**value, "captureSource": native["captureSource"]},
        )
    elif tamper == "capture_workflow":
        native["captureSource"]["workflow"] = ".github/workflows/untrusted.yml"
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            lambda value: {**value, "source": native["captureSource"]},
        )
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
            lambda value: {**value, "captureSource": native["captureSource"]},
        )
    elif tamper == "stale_capture":
        stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        native["captureGeneratedAtUtc"] = stale
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            lambda value: {**value, "generatedAt": stale},
        )
    elif tamper == "not_native":
        rewrite_embedded_document(
            authority,
            startup_path,
            lambda value: {
                **value,
                "executionEnvironment": "compatibility_layer",
                "nativeHostEvidence": {**value["nativeHostEvidence"], "isNativeWindows": False},
            },
        )
    elif tamper == "wine_runner":
        rewrite_embedded_document(
            authority,
            startup_path,
            lambda value: {
                **value,
                "nativeHostEvidence": {**value["nativeHostEvidence"], "runner": "wine64"},
            },
        )
    elif tamper == "ready_checkpoint":
        rewrite_embedded_document(
            authority,
            startup_path,
            lambda value: {**value, "readyCheckpoint": "post_ui_event_loop"},
        )
    elif tamper == "visual_contract_version":
        rewrite_embedded_document(
            authority,
            proof_path,
            lambda value: {**value, "contractVersion": 2},
        )
    elif tamper == "visual_contract_type":
        rewrite_embedded_document(
            authority,
            proof_path,
            lambda value: {**value, "contractVersion": True},
        )
    elif tamper in {"empty_runner", "blank_runner"}:
        rewrite_embedded_document(
            authority,
            startup_path,
            lambda value: {
                **value,
                "nativeHostEvidence": {
                    **value["nativeHostEvidence"],
                    "runner": "" if tamper == "empty_runner" else "   ",
                },
            },
        )
    elif tamper == "artifact_digest":
        rewrite_embedded_document(
            authority,
            proof_path,
            lambda value: {**value, "artifactDigest": "sha256:" + "f" * 64},
        )
    elif tamper == "candidate_artifact_name":
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            lambda value: {
                **value,
                "candidate": {
                    **value["candidate"],
                    "artifactName": "preview-nightly-candidate-99999-1",
                },
            },
        )
    elif tamper == "export_source":
        rewrite_embedded_document(
            authority,
            export_path,
            lambda value: {
                **value,
                "source": {**value["source"], "actor": "different-producer"},
            },
        )
    else:
        rewrite_embedded_document(
            authority,
            export_path,
            lambda value: {
                **value,
                "heads": [
                    {
                        **value["heads"][0],
                        "installer": {
                            **value["heads"][0]["installer"],
                            "sha256": "f" * 64,
                        },
                    }
                ],
            },
        )

    refresh_rehashed_evidence_bindings(authority)
    tampered = tmp_path / "tampered-authority.json"
    write_rehashed_authority(tampered, authority)
    module = load_projection()
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(mode=0o700)
    publish_review_snapshot(module, snapshot_root)

    with pytest.raises(module.ProjectionBlocked):
        module.publish_candidate_import_snapshot(
            snapshot_root,
            authority_path=tampered,
            expected_authority_sha256=sha(tampered),
        )
