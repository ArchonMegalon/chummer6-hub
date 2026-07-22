from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
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


def write_canonical_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
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


def rewrite_embedded_document_raw(
    authority: dict[str, object],
    path: str,
    mutate,
) -> None:
    native = authority["custody"]["nativeWindowsFinalizedEvidence"]
    entry = next(item for item in native["files"] if item["path"] == path)
    payload = mutate(base64.b64decode(entry["base64"]))
    entry["base64"] = base64.b64encode(payload).decode()
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    entry["sizeBytes"] = len(payload)


def write_rehashed_authority(path: Path, authority: dict[str, object]) -> None:
    path.write_bytes(
        (json.dumps(authority, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )


def rewrite_candidate_inventory(authority: dict[str, object], mutate) -> None:
    entry = authority["custody"]["inventory"]
    inventory = json.loads(base64.b64decode(entry["base64"]))
    replacement = mutate(inventory)
    payload = (json.dumps(replacement, sort_keys=True, separators=(",", ":")) + "\n").encode()
    entry["base64"] = base64.b64encode(payload).decode()
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    entry["sizeBytes"] = len(payload)
    rows = replacement["files"]
    digest = hashlib.sha256()
    for row in rows:
        path = row["path"].encode()
        digest.update(len(path).to_bytes(8, "big"))
        digest.update(path)
        digest.update(row["sizeBytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    candidate = authority["candidate"]
    candidate["fileCount"] = len(rows)
    candidate["totalBytes"] = sum(row["sizeBytes"] for row in rows)
    candidate["inventorySha256"] = digest.hexdigest()
    identity = {
        key: candidate[key]
        for key in (
            "version",
            "canonicalManifestSha256",
            "inventorySha256",
            "fileCount",
            "totalBytes",
        )
    }
    candidate["bundleIdentitySha256"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
    for row in capture_inventory.get("files", []):
        entry = entries.get(row.get("path"))
        if entry is not None:
            row["sha256"] = entry["sha256"]
            row["sizeBytes"] = entry["sizeBytes"]
    rewrite_embedded_document(
        authority,
        "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
        lambda _: capture_inventory,
    )

    finalization = json.loads(
        base64.b64decode(entries["WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"]["base64"])
    )
    capture_inventory_sha256 = entries[
        "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
    ]["sha256"]
    finalization["captureInventorySha256"] = capture_inventory_sha256
    capture_source = capture.get("source")
    for proof_binding in finalization["proofs"]:
        proof_path = proof_binding["path"]
        proof = json.loads(base64.b64decode(entries[proof_path]["base64"]))
        if isinstance(capture_source, dict):
            proof["review"]["captureActor"] = capture_source["actor"]
            proof["captureBinding"] = {
                key: capture_source[key]
                for key in (
                    "repository",
                    "workflow",
                    "runId",
                    "runAttempt",
                    "ref",
                    "sha",
                    "artifactName",
                )
            }
            proof["captureBinding"]["inventorySha256"] = capture_inventory_sha256
            rewrite_embedded_document(authority, proof_path, lambda _, proof=proof: proof)
        proof_binding["sha256"] = entries[proof_path]["sha256"]
    rewrite_embedded_document(
        authority,
        "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
        lambda _: finalization,
    )

    finalized_inventory = json.loads(
        base64.b64decode(entries["WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"]["base64"])
    )
    finalized_inventory["captureInventorySha256"] = capture_inventory_sha256
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
            "captureInventorySha256": sha(
                root / "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
            ),
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
    for row in capture_inventory.get("files", []):
        path = root / row["path"]
        row["sha256"] = sha(path)
        row["sizeBytes"] = path.stat().st_size
    write_json(capture_inventory_path, capture_inventory)

    finalization_path = root / "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
    finalization = json.loads(finalization_path.read_text())
    finalization["captureInventorySha256"] = sha(capture_inventory_path)
    capture_source = capture["source"]
    for proof_binding in finalization["proofs"]:
        proof_path = root / proof_binding["path"]
        proof = json.loads(proof_path.read_text())
        proof["review"]["captureActor"] = capture_source["actor"]
        proof["captureBinding"] = {
            key: capture_source[key]
            for key in (
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "artifactName",
            )
        }
        proof["captureBinding"]["inventorySha256"] = sha(capture_inventory_path)
        write_json(proof_path, proof)
        proof_binding["sha256"] = sha(proof_path)
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
    one_byte_artifacts: bool = False,
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
            b"M" if one_byte_artifacts else b"MZ" + bytes([index]) * 16
        )
        (files / f"chummer-{head}-win-x64-payload.zip").write_bytes(
            b"P" if one_byte_artifacts else b"PK" + bytes([index + 10]) * 24
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
    write_json(
        bundle / "releases.json",
        {
            "channel": "preview",
            "releaseVersion": "run-candidate",
            "artifacts": artifacts,
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
    provenance_paths = {
        canonical,
        *(
            files / f"chummer-{head}-win-x64-{role}.{suffix}"
            for head in evidence_heads
            for role, suffix in (("installer", "exe"), ("payload", "zip"))
        ),
    }
    provenance_rows = [
        {
            "path": path.relative_to(bundle).as_posix(),
            "sha256": sha(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in sorted(provenance_paths)
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
    capture_inventory_paths = sorted(
        [
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
            *[
                path
                for head in evidence_heads
                for path in (
                    f"startup-smoke/startup-smoke-{head}-win-x64.receipt.json",
                    f"startup-smoke/windows-installer-progress-{head}-win-x64.log",
                    f"screenshots/windows-installer-{head}-win-x64-progress.png",
                    f"screenshots/windows-installer-{head}-win-x64-completion.png",
                )
            ],
        ]
    )
    write_json(
        capture_inventory,
        {
            "contractName": "chummer6-ui.preview-nightly-native-windows-capture-inventory",
            "contractVersion": 1,
            "captureContract": "chummer6-ui.preview-nightly-native-windows-capture",
            "captureManifestSha256": sha(capture),
            "files": [
                {
                    "path": relative,
                    "sha256": sha(finalized / relative),
                    "sizeBytes": (finalized / relative).stat().st_size,
                }
                for relative in capture_inventory_paths
            ],
        },
    )

    for binding in proof_bindings:
        proof_path = finalized / binding["path"]
        proof = json.loads(proof_path.read_text())
        proof["review"] = {
            "authenticatedReviewer": "accountable-reviewer",
            "captureActor": capture_source["actor"],
            "allowlistSource": "repository variable plus protected environment",
            "explicitConfirmations": {
                "readability": "passed",
                "contrast": "passed",
                "clipping": "passed",
            },
        }
        proof["captureBinding"] = {
            key: capture_source[key]
            for key in (
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "artifactName",
            )
        }
        proof["captureBinding"]["inventorySha256"] = sha(capture_inventory)
        write_json(proof_path, proof)
        binding["sha256"] = sha(proof_path)

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


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def byte_reference(path: str, raw: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }


def publication_tuple(
    *,
    role: str,
    platform: str,
    rid: str,
    file_name: str,
    digest: str,
    size: int,
    evidence_only: bool = False,
) -> dict[str, object]:
    path = f"files/{file_name}"
    if evidence_only:
        path = f"release-evidence/non-published/files/{file_name}"
    return {
        "artifactRole": role,
        "consumerCommit": "a" * 40,
        "fileName": file_name,
        "head": "avalonia",
        "manifestRowSha256": hashlib.sha256(
            f"{role}:{platform}:{rid}:{file_name}".encode()
        ).hexdigest(),
        "path": path,
        "platform": platform,
        "rid": rid,
        "sha256": digest,
        "sizeBytes": size,
        "sourceReceipt": {
            "contractName": "fixture.desktop-source",
            "contractVersion": 1,
            "path": "receipts/fixture.json",
            "sha256": "e" * 64,
        },
    }


def upgrade_finalized_root_to_windows_only_v2(
    *,
    finalized: Path,
    bundle: Path,
    canonical_raw: bytes,
    compatibility_raw: bytes,
    signing_raw: bytes,
    registry_prepare_sha256: str,
    approval: dict[str, object],
    approval_raw: bytes,
    authenticode_raw: bytes,
    raw_authenticode_binding: dict[str, object],
    scope_decision_sha256: str,
    capture_supply_chain: dict[str, object] | None = None,
    export_supply_chain: dict[str, object] | None = None,
    export_numeric_lexeme: str | None = None,
) -> dict[str, object]:
    capture_path = finalized / "WINDOWS_NATIVE_CAPTURE.generated.json"
    capture = json.loads(capture_path.read_text())
    finalization_path = finalized / "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
    finalization = json.loads(finalization_path.read_text())
    capture_source = capture["source"]
    finalization_source = dict(finalization["finalizationSource"])
    if finalization_source.get("actor") == "accountable-reviewer":
        finalization_source["actor"] = "scope-approver"

    provenance_root = finalized / "candidate-provenance"
    provenance_copies = {
        "RELEASE_CHANNEL.generated.json": canonical_raw,
        "releases.json": compatibility_raw,
        "signing/signing-avalonia-win-x64.receipt.json": signing_raw,
    }
    proposal_relative = (
        "publication-scope/"
        "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json"
    )
    proposal_raw = (
        json.dumps(
            {
                "registryPrepare": {"sha256": registry_prepare_sha256},
                "registryPrepareSha256": registry_prepare_sha256,
                "scopeDecisionSha256": scope_decision_sha256,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    provenance_copies[proposal_relative] = proposal_raw
    for source_path in sorted(path for path in bundle.rglob("*") if path.is_file()):
        provenance_copies[source_path.relative_to(bundle).as_posix()] = source_path.read_bytes()
    for relative, payload in provenance_copies.items():
        target = provenance_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    inventory_path = (
        provenance_root
        / "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
    )
    inventory = json.loads(inventory_path.read_text())
    if type(inventory.get("contractVersion")) is int and inventory["contractVersion"] == 1:
        inventory["contractVersion"] = 2
    existing_rows = {
        row.get("path"): row
        for row in inventory.get("files", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    for relative, payload in provenance_copies.items():
        row = existing_rows.setdefault(relative, {"path": relative})
        row["sha256"] = hashlib.sha256(payload).hexdigest()
        row["sizeBytes"] = len(payload)
    inventory["files"] = [existing_rows[path] for path in sorted(existing_rows)]
    inventory_raw = write_json(inventory_path, inventory)

    export_path = provenance_root / "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
    export = json.loads(export_path.read_text())
    if type(export.get("contractVersion")) is int and export["contractVersion"] == 1:
        export["contractVersion"] = 2
    export["contentInventory"] = {
        "path": inventory_path.name,
        "sha256": hashlib.sha256(inventory_raw).hexdigest(),
    }
    export.setdefault(
        "publicationScope", {"registryPrepareSha256": registry_prepare_sha256}
    )
    if export_supply_chain is None:
        export.setdefault("supplyChain", {})
    else:
        export["supplyChain"] = export_supply_chain
    export.setdefault(
        "supplyChainVerification",
        {"mode": "release_authoritative", "releaseAuthoritative": True},
    )
    export_raw = write_json(export_path, export)
    if export_numeric_lexeme is not None:
        numeric_marker = b'"typedValue": 1.0'
        assert export_raw.count(numeric_marker) == 1
        export_raw = export_raw.replace(
            numeric_marker,
            f'"typedValue": {export_numeric_lexeme}'.encode(),
        )
        export_path.write_bytes(export_raw)

    candidate = capture["candidate"]
    candidate.update(
        {
            "contentInventory": byte_reference(
                inventory_path.relative_to(finalized).as_posix(), inventory_raw
            ),
            "contentInventorySha256": hashlib.sha256(inventory_raw).hexdigest(),
            "exportReceipt": byte_reference(
                export_path.relative_to(finalized).as_posix(), export_raw
            ),
            "exportReceiptSha256": hashlib.sha256(export_raw).hexdigest(),
            "fullShelfCompatibilityManifest": byte_reference(
                "candidate-provenance/releases.json", compatibility_raw
            ),
            "fullShelfCompatibilityManifestPath": "releases.json",
            "fullShelfCompatibilityManifestSha256": hashlib.sha256(
                compatibility_raw
            ).hexdigest(),
            "fullShelfManifest": byte_reference(
                "candidate-provenance/RELEASE_CHANNEL.generated.json", canonical_raw
            ),
            "fullShelfManifestPath": "RELEASE_CHANNEL.generated.json",
            "fullShelfManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
            "publicationScope": byte_reference(
                f"candidate-provenance/{proposal_relative}", proposal_raw
            ),
            "publicationScopePath": proposal_relative,
            "publicationScopeSha256": hashlib.sha256(proposal_raw).hexdigest(),
            "registryPrepareFiles": [],
            "registryPrepareSha256": registry_prepare_sha256,
            "scopeDecisionSha256": scope_decision_sha256,
            "signingReceipt": byte_reference(
                "candidate-provenance/signing/signing-avalonia-win-x64.receipt.json",
                signing_raw,
            ),
            "signingReceiptPath": "signing/signing-avalonia-win-x64.receipt.json",
            "signingReceiptSha256": hashlib.sha256(signing_raw).hexdigest(),
            "supplyChain": (
                {} if capture_supply_chain is None else capture_supply_chain
            ),
        }
    )
    auth_path = (
        finalized
        / "authenticode"
        / "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
    )
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_bytes(authenticode_raw)
    for head in capture.get("heads", []):
        if isinstance(head, dict):
            head.setdefault("authenticodeVerification", raw_authenticode_binding)
    capture["authenticodeVerification"] = raw_authenticode_binding
    if type(capture.get("contractVersion")) is int and capture["contractVersion"] == 1:
        capture["contractVersion"] = 2
    capture_raw = write_json(capture_path, capture)

    capture_inventory_path = (
        finalized / "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
    )
    capture_inventory = json.loads(capture_inventory_path.read_text())
    if (
        type(capture_inventory.get("contractVersion")) is int
        and capture_inventory["contractVersion"] == 1
    ):
        capture_inventory["contractVersion"] = 2
    existing_capture_rows = {
        row.get("path"): row
        for row in capture_inventory.get("files", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    capture_paths = {
        *existing_capture_rows,
        "WINDOWS_NATIVE_CAPTURE.generated.json",
        "authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
        *(f"candidate-provenance/{relative}" for relative in provenance_copies),
    }
    for relative in capture_paths:
        path = finalized / relative
        row = existing_capture_rows.setdefault(relative, {"path": relative})
        row["sha256"] = sha(path)
        row["sizeBytes"] = path.stat().st_size
    capture_inventory["captureManifestSha256"] = hashlib.sha256(capture_raw).hexdigest()
    capture_inventory["files"] = [
        existing_capture_rows[path] for path in sorted(capture_paths)
    ]
    capture_inventory_raw = write_json(capture_inventory_path, capture_inventory)

    proof_bindings = finalization["proofs"]
    for proof_binding in proof_bindings:
        proof_path = finalized / proof_binding["path"]
        proof = json.loads(proof_path.read_text())
        proof["authenticodeVerification"] = raw_authenticode_binding
        proof["finalizationBinding"] = finalization_source
        for name in ("readabilityReview", "contrastReview", "clippingReview"):
            if proof.get(name, {}).get("reviewer") == "accountable-reviewer":
                proof[name]["reviewer"] = "scope-approver"
        review = proof.get("review")
        if isinstance(review, dict):
            if review.get("authenticatedReviewer") == "accountable-reviewer":
                review["authenticatedReviewer"] = "scope-approver"
            review["captureActor"] = capture_source["actor"]
        proof["captureBinding"] = {
            key: capture_source[key]
            for key in (
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "artifactName",
            )
        }
        proof["captureBinding"]["inventorySha256"] = hashlib.sha256(
            capture_inventory_raw
        ).hexdigest()
        proof_raw = write_json(proof_path, proof)
        proof_binding["sha256"] = hashlib.sha256(proof_raw).hexdigest()

    approval_path = finalized / "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"
    approval_path.write_bytes(approval_raw)
    if (
        type(finalization.get("contractVersion")) is int
        and finalization["contractVersion"] == 1
    ):
        finalization["contractVersion"] = 2
    if finalization.get("reviewer") == "accountable-reviewer":
        finalization["reviewer"] = "scope-approver"
    finalization.update(
        {
            "authenticodeVerification": raw_authenticode_binding,
            "captureInventorySha256": hashlib.sha256(capture_inventory_raw).hexdigest(),
            "captureSource": capture_source,
            "finalizationSource": finalization_source,
            "scopeApproval": {
                "approver": approval["approver"],
                "path": approval_path.name,
                "scopeDecisionSha256": scope_decision_sha256,
                "sha256": hashlib.sha256(approval_raw).hexdigest(),
            },
        }
    )
    finalization_raw = write_json(finalization_path, finalization)
    refresh_finalized_inventory(finalized)
    finalized_inventory_path = (
        finalized / "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"
    )
    finalized_inventory = json.loads(finalized_inventory_path.read_text())
    return {
        "candidateProvenance": {
            "candidate": candidate,
            "contentInventory": inventory,
            "exportReceipt": export,
            "githubActionsProvenance": {},
            "localCandidateFiles": [],
            "publicationScope": export["publicationScope"],
            "registryPrepareFiles": [],
            "registryPrepareSha256": registry_prepare_sha256,
            "scopeBindings": {},
            "supplyChain": (
                {} if capture_supply_chain is None else capture_supply_chain
            ),
        },
        "captureInventorySha256": hashlib.sha256(capture_inventory_raw).hexdigest(),
        "captureSource": capture_source,
        "finalizationRaw": finalization_raw,
        "finalizationSource": finalization_source,
        "finalizedInventorySha256": sha(finalized_inventory_path),
        "fileCount": len(finalized_inventory["files"]),
    }


def write_publication_stage(
    fixture: tuple[Path, Path, Path, Path, Path],
    *,
    capture_supply_chain: dict[str, object] | None = None,
    export_supply_chain: dict[str, object] | None = None,
    export_numeric_lexeme: str | None = None,
) -> dict[str, Path]:
    bundle, canonical_path, _summary, _inventory, finalized = fixture
    stage = bundle.parent / "publication-stage"
    stage.mkdir(exist_ok=True)
    canonical = json.loads(canonical_path.read_text())
    canonical_raw = canonical_path.read_bytes()
    compatibility_path = bundle / "releases.json"
    compatibility_raw = compatibility_path.read_bytes()
    artifact = canonical["artifacts"][0]
    installer_path = bundle / "files" / artifact["fileName"]
    payload_path = bundle / "files" / artifact["payloadFileName"]
    installer = publication_tuple(
        role="installer",
        platform="windows",
        rid="win-x64",
        file_name=installer_path.name,
        digest=sha(installer_path),
        size=installer_path.stat().st_size,
    )
    payload = publication_tuple(
        role="payload",
        platform="windows",
        rid="win-x64",
        file_name=payload_path.name,
        digest=sha(payload_path),
        size=payload_path.stat().st_size,
    )
    delta = [installer, payload]
    linux_evidence = publication_tuple(
        role="installer",
        platform="linux",
        rid="linux-x64",
        file_name="chummer-avalonia-linux-x64-installer.deb",
        digest="6" * 64,
        size=17,
        evidence_only=True,
    )
    build = [linux_evidence, *delta]
    retained: list[dict[str, object]] = []
    post = list(delta)
    full_inventory = [
        {
            "mode": 0o644,
            "path": path.relative_to(bundle).as_posix(),
            "sha256": sha(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in sorted(path for path in bundle.rglob("*") if path.is_file())
    ]
    registry_inventory = [
        {**row, "mode": f"{row['mode']:04o}"} for row in full_inventory
    ]
    incumbent_raw = b'{"releaseVersion":"run-incumbent"}\n'
    incumbent_tuple = publication_tuple(
        role="installer",
        platform="windows",
        rid="win-x64",
        file_name="chummer-avalonia-win-x64-incumbent.exe",
        digest="7" * 64,
        size=19,
    )
    incumbent_inventory = [
        {
            "mode": "0644",
            "path": "RELEASE_CHANNEL.generated.json",
            "sha256": hashlib.sha256(incumbent_raw).hexdigest(),
            "sizeBytes": len(incumbent_raw),
        }
    ]
    ui_incumbent_inventory = [{**incumbent_inventory[0], "mode": 0o644}]
    ui_incumbent = {
        "canonicalManifestSha256": hashlib.sha256(incumbent_raw).hexdigest(),
        "compatibilityManifestSha256": "8" * 64,
        "desktopTupleSetSha256": canonical_sha256([incumbent_tuple]),
        "desktopTuples": [incumbent_tuple],
        "inventory": ui_incumbent_inventory,
        "inventorySha256": canonical_sha256(ui_incumbent_inventory),
        "managedPaths": [
            "RELEASE_CHANNEL.generated.json",
            "files/chummer-avalonia-win-x64-incumbent.exe",
            "releases.json",
        ],
        "platforms": ["windows"],
    }
    incumbent_snapshot_sha = canonical_sha256(ui_incumbent)
    registry_incumbent = {
        "canonicalManifest": byte_reference(
            "RELEASE_CHANNEL.generated.json", incumbent_raw
        ),
        "compatibilityManifest": {
            "path": "releases.json",
            "sha256": "8" * 64,
            "sizeBytes": 11,
        },
        "desktopTuples": [incumbent_tuple],
        "desktopTupleSetSha256": canonical_sha256([incumbent_tuple]),
        "fullInventory": incumbent_inventory,
        "fullInventorySha256": canonical_sha256(incumbent_inventory),
        "managedPaths": ui_incumbent["managedPaths"],
        "platforms": ["windows"],
        "snapshotSha256": incumbent_snapshot_sha,
    }
    projection_inputs = {
        name: {"path": path, "sha256": digest, "sizeBytes": 1}
        for name, path, digest in (
            (
                "materializer",
                "scripts/materialize_preview_publication_delta.py",
                "1" * 64,
            ),
            (
                "releaseChannelMaterializer",
                "scripts/materialize_public_release_channel.py",
                "2" * 64,
            ),
            (
                "schema",
                "contracts/preview-publication-delta-v1.schema.json",
                "3" * 64,
            ),
            (
                "verifier",
                "scripts/verify_public_release_channel.py",
                "4" * 64,
            ),
        )
    }
    composition = {
        "channel": "preview",
        "contractName": "chummer.registry.preview-publication-delta-composition",
        "contractVersion": 1,
        "incumbentSnapshot": registry_incumbent,
        "nonPublishedEvidenceTupleSetSha256": canonical_sha256([linux_evidence]),
        "nonPublishedEvidenceTuples": [linux_evidence],
        "policy": {
            "allowIncumbentRemoval": False,
            "deltaPlatforms": ["windows"],
            "evidencePlatforms": ["linux"],
            "producerDeployAuthority": False,
            "producerReleaseUploadAuthority": False,
            "retainAllIncumbent": True,
            "scope": "windows_only",
        },
        "producerCommits": {
            "desktop": "a" * 40,
            "registry": "b" * 40,
            "ui": "c" * 40,
        },
        "publicationDeltaTupleSetSha256": canonical_sha256(delta),
        "publicationDeltaTuples": delta,
        "releaseVersion": "run-candidate",
    }
    composition_raw = (
        json.dumps(composition, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    registry_candidate = {
        "canonicalManifest": byte_reference(
            "RELEASE_CHANNEL.generated.json", canonical_raw
        ),
        "channel": "preview",
        "compatibilityManifest": byte_reference("releases.json", compatibility_raw),
        "compositionInput": byte_reference("composition.json", composition_raw),
        "compositionInputDocument": composition,
        "contractName": "chummer.registry.preview-publication-delta-candidate",
        "contractVersion": 1,
        "deltaPlatforms": ["windows"],
        "deployAuthority": False,
        "evidencePlatforms": ["linux"],
        "fullShelfInventory": registry_inventory,
        "fullShelfInventorySha256": canonical_sha256(registry_inventory),
        "incumbentDesktopTupleSetSha256": canonical_sha256([incumbent_tuple]),
        "incumbentCanonicalManifestBytesBase64": base64.b64encode(
            incumbent_raw
        ).decode(),
        "incumbentSnapshotSha256": incumbent_snapshot_sha,
        "nonPublishedEvidenceTupleSetSha256": canonical_sha256([linux_evidence]),
        "postPublicationTupleSetSha256": canonical_sha256(post),
        "publicationDeltaTupleSetSha256": canonical_sha256(delta),
        "publicationEligible": False,
        "publicationStatus": "review_required",
        "registryProjectionInputs": projection_inputs,
        "releaseUploadAuthority": False,
        "routeAuthority": False,
        "releaseVersion": "run-candidate",
        "retainedPlatforms": [],
        "retainedTupleSetSha256": canonical_sha256(retained),
        "shelfPlatforms": ["windows"],
    }
    registry_prepare_dir = stage / "registry-prepare"
    registry_candidate_path = registry_prepare_dir / "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json"
    registry_candidate_raw = write_canonical_json(
        registry_candidate_path, registry_candidate
    )
    prepare_inventory = sorted(
        [
            {**byte_reference("RELEASE_CHANNEL.generated.json", canonical_raw), "mode": "0644"},
            {**byte_reference("releases.json", compatibility_raw), "mode": "0644"},
            {
                **byte_reference(
                    "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json",
                    registry_candidate_raw,
                ),
                "mode": "0644",
            },
        ],
        key=lambda row: row["path"],
    )
    registry_prepare = {
        "candidateReceiptSha256": hashlib.sha256(registry_candidate_raw).hexdigest(),
        "composition": {**byte_reference("composition.json", composition_raw), "mode": "0644"},
        "contractName": "chummer6-ui.registry-preview-prepare-binding",
        "contractVersion": 1,
        "deployAuthority": False,
        "finalizeAvailable": True,
        "finalizeReceipt": None,
        "inputRoots": {
            name: {"fileCount": 1, "inventorySha256": digest, "path": name}
            for name, digest in (
                ("incumbent", "9" * 64),
                ("delta", "a" * 64),
                ("evidence", "b" * 64),
            )
        },
        "outputInventory": prepare_inventory,
        "outputInventorySha256": canonical_sha256(prepare_inventory),
        "projectionInputs": projection_inputs,
        "publicationEligible": False,
        "registryCommit": "b" * 40,
        "releaseUploadAuthority": False,
        "routeAuthority": False,
        "status": "review_required",
        "wholeDirectoryVerified": True,
    }

    signing_path = stage / "signing" / "signing-avalonia-win-x64.receipt.json"
    signing_raw = write_json(
        signing_path,
        {
            "contractName": "chummer6-ui.desktop_artifact_signing",
            "contractVersion": 2,
            "platform": "windows",
            "app": "avalonia",
            "rid": "win-x64",
            "releaseChannel": "preview",
            "releaseVersion": "run-candidate",
            "signingStatus": "pass",
            "candidateBindings": [
                {
                    "artifactRole": row["artifactRole"],
                    "authenticodeStatus": (
                        "pass"
                        if row["artifactRole"] == "installer"
                        else "not_applicable_payload"
                    ),
                    "fileName": row["fileName"],
                    "sha256": row["sha256"],
                    "sizeBytes": row["sizeBytes"],
                }
                for row in delta
            ],
            "artifacts": [
                {
                    "fileName": installer["fileName"],
                    "sha256": installer["sha256"],
                    "signingStatus": "pass",
                }
            ],
        },
    )
    chain = {
        "trusted": True,
        "status": [],
        "revocationFlag": "entire_chain",
        "revocationMode": "online",
        "verificationFlags": "no_flag",
    }
    capture_source = json.loads(
        (finalized / "WINDOWS_NATIVE_CAPTURE.generated.json").read_text()
    )["source"]
    authenticode_path = (
        stage
        / "proof"
        / "windows-native"
        / "authenticode"
        / "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
    )
    authenticode_raw = write_json(
        authenticode_path,
        {
            "artifact": {
                "fileName": installer["fileName"],
                "sha256": installer["sha256"],
                "sizeBytes": installer["sizeBytes"],
            },
            "contractName": "chummer6-ui.windows-authenticode-verification",
            "contractVersion": 1,
            "generatedAt": "2026-07-22T00:00:00Z",
            "policy": {
                "signerCertificateSha256": "c" * 64,
                "signerSpkiSha256": "d" * 64,
            },
            "signature": {
                "codeSigningEkuOid": "1.3.6.1.5.5.7.3.3",
                "cryptographicVerification": "passed",
                "status": "valid",
                "type": "authenticode",
            },
            "signer": {
                "certificateSha256": "c" * 64,
                "spkiSha256": "d" * 64,
                "chain": chain,
            },
            "source": capture_source,
            "status": "verified",
            "timestamp": {
                "attributeOid": "1.2.840.113549.1.9.16.2.14",
                "format": "rfc3161",
                "messageImprintAlgorithmOid": "2.16.840.1.101.3.4.2.1",
                "status": "verified",
                "timestampingEkuOid": "1.3.6.1.5.5.7.3.8",
                "chain": chain,
            },
            "verifier": {"platform": "windows"},
        },
    )
    full_inventory_sha = canonical_sha256(full_inventory)
    decision = {
        "channel": "preview",
        "fullShelfCompatibilityManifestSha256": hashlib.sha256(
            compatibility_raw
        ).hexdigest(),
        "fullShelfInventorySha256": full_inventory_sha,
        "fullShelfManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "incumbentSnapshotSha256": incumbent_snapshot_sha,
        "publicationDeltaSha256": canonical_sha256(delta),
        "releaseVersion": "run-candidate",
        "scope": "windows_only",
    }
    approval_path = (
        stage
        / "proof"
        / "windows-native"
        / "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"
    )
    approval = {
        "approvedAt": "2026-07-22T00:00:00Z",
        "approver": "scope-approver",
        "authenticodeVerificationSha256": hashlib.sha256(authenticode_raw).hexdigest(),
        "contractName": "chummer6-ui.preview-nightly-windows-publication-approval",
        "contractVersion": 2,
        "fullShelfCompatibilityManifestSha256": decision[
            "fullShelfCompatibilityManifestSha256"
        ],
        "fullShelfInventorySha256": full_inventory_sha,
        "fullShelfManifestSha256": decision["fullShelfManifestSha256"],
        "incumbentSnapshotSha256": incumbent_snapshot_sha,
        "publicationDeltaSha256": canonical_sha256(delta),
        "publicationScopeProposalSha256": "5" * 64,
        "registryPrepareSha256": canonical_sha256(registry_prepare),
        "scopeDecisionSha256": canonical_sha256(decision),
        "signingReceiptSha256": hashlib.sha256(signing_raw).hexdigest(),
        "status": "approved",
    }
    approval_raw = write_json(approval_path, approval)
    registry_prepare_sha = canonical_sha256(registry_prepare)
    finalization_source = dict(
        json.loads(
            (
                finalized
                / "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
            ).read_text()
        )["finalizationSource"]
    )
    if finalization_source.get("actor") == "accountable-reviewer":
        finalization_source["actor"] = "scope-approver"
    authenticode_binding = {
        "path": "proof/windows-native/authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
        "sha256": hashlib.sha256(authenticode_raw).hexdigest(),
        "signerCertificateSha256": "c" * 64,
        "signerSpkiSha256": "d" * 64,
        "sizeBytes": len(authenticode_raw),
        "timestampUtc": "2026-07-22T00:00:00Z",
    }
    raw_scope_approval = {
        "approver": "scope-approver",
        "path": "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
        "scopeDecisionSha256": canonical_sha256(decision),
        "sha256": hashlib.sha256(approval_raw).hexdigest(),
    }
    raw_authenticode_binding = {
        **authenticode_binding,
        "path": "authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
    }
    upgraded_native = upgrade_finalized_root_to_windows_only_v2(
        finalized=finalized,
        bundle=bundle,
        canonical_raw=canonical_raw,
        compatibility_raw=compatibility_raw,
        signing_raw=signing_raw,
        registry_prepare_sha256=registry_prepare_sha,
        approval=approval,
        approval_raw=approval_raw,
        authenticode_raw=authenticode_raw,
        raw_authenticode_binding=raw_authenticode_binding,
        scope_decision_sha256=canonical_sha256(decision),
        capture_supply_chain=capture_supply_chain,
        export_supply_chain=export_supply_chain,
        export_numeric_lexeme=export_numeric_lexeme,
    )
    native_stage_root = stage / "proof" / "windows-native"
    shutil.copytree(finalized, native_stage_root, dirs_exist_ok=True)
    capture_source = upgraded_native["captureSource"]
    finalization_source = upgraded_native["finalizationSource"]
    raw_visual = json.loads(
        (
            finalized
            / "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json"
        ).read_text()
    )
    portable_visual = json.loads(json.dumps(raw_visual))
    portable_visual["authenticodeVerification"] = authenticode_binding
    for screenshot in portable_visual["screenshots"]:
        screenshot["path"] = f"proof/windows-native/{screenshot['path']}"
    visual_path = stage / "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json"
    visual_raw = write_json(visual_path, portable_visual)
    finalization_path = stage / "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
    finalization_raw = upgraded_native["finalizationRaw"]
    finalization_path.write_bytes(finalization_raw)
    native_path = stage / "NATIVE_WINDOWS_EVIDENCE.generated.json"
    native_raw = write_json(
        native_path,
        {
            "archivePath": "proof/windows-native/windows-native-evidence-finalized.zip",
            "archiveSha256": "1" * 64,
            "authenticodeVerification": authenticode_binding,
            "candidateProvenance": upgraded_native["candidateProvenance"],
            "captureInventorySha256": upgraded_native["captureInventorySha256"],
            "captureSource": capture_source,
            "contractName": "chummer6-ui.preview-nightly-native-windows-evidence",
            "contractVersion": 1,
            "fileCount": upgraded_native["fileCount"],
            "finalizationSha256": hashlib.sha256(finalization_raw).hexdigest(),
            "finalizationSource": finalization_source,
            "finalizedInventorySha256": upgraded_native[
                "finalizedInventorySha256"
            ],
            "githubActionsProvenance": {},
            "nativeFinalization": {
                "path": finalization_path.name,
                "sha256": hashlib.sha256(finalization_raw).hexdigest(),
                "sizeBytes": len(finalization_raw),
            },
            "progressLogSha256": {"avalonia": "3" * 64},
            "release": {"channel": "preview", "version": "run-candidate"},
            "scopeApproval": {
                **raw_scope_approval,
                "payload": approval,
            },
            "startupReceiptSha256": {"avalonia": "4" * 64},
            "status": "passed",
            "treeSha256": "5" * 64,
            "visualProof": {
                "path": visual_path.name,
                "sha256": hashlib.sha256(visual_raw).hexdigest(),
                "sizeBytes": len(visual_raw),
            },
            "visualProofSha256": {
                "avalonia": hashlib.sha256(visual_raw).hexdigest()
            },
            "visualReviewers": {"avalonia": "scope-approver"},
        },
    )
    empty_sha = canonical_sha256([])
    scope = {
        "approval": {
            "approver": "scope-approver",
            "path": approval_path.relative_to(stage).as_posix(),
            "sha256": hashlib.sha256(approval_raw).hexdigest(),
        },
        "approvalIndependent": True,
        "authenticodeRequired": True,
        "authenticodeVerificationSha256": hashlib.sha256(authenticode_raw).hexdigest(),
        "buildEvidenceTuples": build,
        "contractName": "chummer6-ui.preview-nightly-windows-publication-scope",
        "contractVersion": 2,
        "deployAuthorized": False,
        "fullShelfCompatibilityManifestSha256": hashlib.sha256(
            compatibility_raw
        ).hexdigest(),
        "fullShelfInventory": full_inventory,
        "fullShelfInventorySha256": full_inventory_sha,
        "fullShelfManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "incumbentSnapshot": ui_incumbent,
        "incumbentSnapshotSha256": incumbent_snapshot_sha,
        "macosSoak": {
            "byteIdentical": False,
            "incumbentTupleSetSha256": empty_sha,
            "postPublicationTupleSetSha256": empty_sha,
            "reason": "not_applicable_no_incumbent_tuple",
            "required": False,
        },
        "nativeEvidenceComposite": {
            "authenticodeVerification": {
                "contractName": "chummer6-ui.windows-authenticode-verification",
                "contractVersion": 1,
                "path": authenticode_path.relative_to(stage).as_posix(),
                "sha256": hashlib.sha256(authenticode_raw).hexdigest(),
                "sizeBytes": len(authenticode_raw),
            },
            "nativeFinalization": {
                "contractName": "chummer6-ui.preview-nightly-native-windows-finalization",
                "contractVersion": 2,
                "path": finalization_path.name,
                "sha256": hashlib.sha256(finalization_raw).hexdigest(),
                "sizeBytes": len(finalization_raw),
            },
            "visualProof": {
                "contractName": "chummer6-ui.windows_installer_visual_proof",
                "contractVersion": 1,
                "path": visual_path.name,
                "sha256": hashlib.sha256(visual_raw).hexdigest(),
                "sizeBytes": len(visual_raw),
            },
            "wrapper": {
                "contractName": "chummer6-ui.preview-nightly-native-windows-evidence",
                "contractVersion": 1,
                "path": native_path.name,
                "sha256": hashlib.sha256(native_raw).hexdigest(),
                "sizeBytes": len(native_raw),
            },
        },
        "nativeEvidenceSha256": hashlib.sha256(native_raw).hexdigest(),
        "nonPublishedEvidenceTuples": [linux_evidence],
        "postPublicationShelfTuples": post,
        "publicationDeltaTuples": delta,
        "publicationEligible": False,
        "registryPrepare": registry_prepare,
        "registryFinalizeEligible": True,
        "release": {"channel": "preview", "version": "run-candidate"},
        "retainedTuples": retained,
        "scopeDecision": decision,
        "scopeDecisionSha256": canonical_sha256(decision),
        "signingReceipt": {
            "path": signing_path.relative_to(stage).as_posix(),
            "sha256": hashlib.sha256(signing_raw).hexdigest(),
        },
        "signingReceiptSha256": hashlib.sha256(signing_raw).hexdigest(),
        "status": "validated",
        "uploadAuthorized": False,
        "visualApprovalSha256": [hashlib.sha256(visual_raw).hexdigest()],
    }
    scope_path = stage / "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json"
    scope_raw = write_json(scope_path, scope)
    disposition = {
        "artifactId": artifact["artifactId"],
        "disposition": "delta",
        "head": "avalonia",
        "platform": "windows",
        "rid": "win-x64",
        "sha256": artifact["sha256"],
        "sizeBytes": artifact["sizeBytes"],
        "sourceManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "sourceReleaseVersion": "run-candidate",
        "sourceSnapshotSha256": registry_candidate["fullShelfInventorySha256"],
    }
    registry_authority = {
        "candidateImportAuthority": True,
        "candidateReceipt": byte_reference(
            "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json", registry_candidate_raw
        ),
        "candidateReviewAuthority": True,
        "canonicalManifest": byte_reference(
            "RELEASE_CHANNEL.generated.json", canonical_raw
        ),
        "channel": "preview",
        "compatibilityManifest": byte_reference("releases.json", compatibility_raw),
        "compositionInputSha256": hashlib.sha256(composition_raw).hexdigest(),
        "contractName": "chummer.registry.preview-publication-delta-authority",
        "contractVersion": 1,
        "deltaPlatforms": ["windows"],
        "deployAuthority": False,
        "dispositions": [disposition],
        "evidence": {
            "approval": byte_reference(
                approval_path.relative_to(stage).as_posix(), approval_raw
            ),
            "nativeEvidence": byte_reference(native_path.name, native_raw),
            "signingReceipt": byte_reference(
                signing_path.relative_to(stage).as_posix(), signing_raw
            ),
            "visualEvidence": [byte_reference(visual_path.name, visual_raw)],
        },
        "evidencePlatforms": ["linux"],
        "fullShelfInventorySha256": registry_candidate["fullShelfInventorySha256"],
        "incumbentSnapshotSha256": incumbent_snapshot_sha,
        "nonPublishedEvidenceTupleSetSha256": canonical_sha256([linux_evidence]),
        "postPublicationTupleSetSha256": canonical_sha256(post),
        "publicationDeltaTupleSetSha256": canonical_sha256(delta),
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "releaseVersion": "run-candidate",
        "retainedPlatforms": [],
        "retainedTupleSetSha256": canonical_sha256(retained),
        "routeAuthority": False,
        "scope": "windows_only",
        "shelfPlatforms": ["windows"],
        "sourceScope": byte_reference(scope_path.name, scope_raw),
    }
    registry_finalize_dir = stage / "registry-finalize"
    registry_authority_path = (
        registry_finalize_dir / "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json"
    )
    registry_authority_raw = write_canonical_json(
        registry_authority_path, registry_authority
    )
    registry_finalize = {
        "authority": byte_reference(
            "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json", registry_authority_raw
        ),
        "candidateBytesMutated": False,
        "candidateImportAuthority": True,
        "candidateReceipt": byte_reference(
            "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json", registry_candidate_raw
        ),
        "candidateReviewAuthority": True,
        "canonicalManifest": byte_reference(
            "RELEASE_CHANNEL.generated.json", canonical_raw
        ),
        "channel": "preview",
        "compatibilityManifest": byte_reference("releases.json", compatibility_raw),
        "contractName": "chummer.registry.preview-publication-delta-finalize",
        "contractVersion": 1,
        "deployAuthority": False,
        "fullShelfInventorySha256": registry_candidate["fullShelfInventorySha256"],
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "releaseVersion": "run-candidate",
        "routeAuthority": False,
        "sourceScope": byte_reference(scope_path.name, scope_raw),
        "verificationStatus": "finalized",
    }
    registry_finalize_path = (
        registry_finalize_dir / "PREVIEW_PUBLICATION_DELTA_FINALIZE.json"
    )
    write_canonical_json(registry_finalize_path, registry_finalize)
    return {
        "root": stage,
        "native": native_stage_root,
        "scope": scope_path,
        "candidate": registry_candidate_path,
        "authority": registry_authority_path,
        "finalize": registry_finalize_path,
    }


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
    *,
    windows_finalized_root: Path | None = None,
    capture_supply_chain: dict[str, object] | None = None,
    export_supply_chain: dict[str, object] | None = None,
    export_numeric_lexeme: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, tuple[Path, Path, Path, Path, Path]]:
    bundle, canonical, summary, inventory, finalized = fixture
    stage = write_publication_stage(
        fixture,
        capture_supply_chain=capture_supply_chain,
        export_supply_chain=export_supply_chain,
        export_numeric_lexeme=export_numeric_lexeme,
    )
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
            str(windows_finalized_root or stage["native"]),
            "--publication-stage-root",
            str(stage["root"]),
            "--publication-scope",
            str(stage["scope"]),
            "--registry-candidate-receipt",
            str(stage["candidate"]),
            "--registry-finalize-authority",
            str(stage["authority"]),
            "--registry-finalize-receipt",
            str(stage["finalize"]),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, output, fixture


def resummarize_fixture(
    fixture: tuple[Path, Path, Path, Path, Path],
) -> None:
    bundle, canonical, summary, inventory, _ = fixture
    summary.unlink(missing_ok=True)
    inventory.unlink(missing_ok=True)
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


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_projection():
    return load_script(PROJECTION, "candidate_projection_test")


def exact_tree_fixture(tmp_path: Path):
    materializer = load_script(MATERIALIZER, "candidate_exact_tree_test")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    write_json(bundle / "RELEASE_CHANNEL.generated.json", {"status": "held"})
    write_json(bundle / "releases.json", {"status": "held"})
    rows = [
        {
            "path": path.relative_to(bundle).as_posix(),
            "sha256": sha(path),
            "sizeBytes": path.stat().st_size,
        }
        for path in sorted(bundle.iterdir())
    ]
    candidate = {
        "fileCount": len(rows),
        "totalBytes": sum(row["sizeBytes"] for row in rows),
        "inventorySha256": materializer._inventory_digest(rows),
    }
    inventory = {
        "contractName": "chummer.release-upload.candidate-inventory/v1",
        "contractVersion": 1,
        "files": rows,
    }
    return materializer, bundle, inventory, candidate


def test_candidate_inventory_rejects_unlisted_bundle_file(tmp_path: Path) -> None:
    materializer, bundle, inventory, candidate = exact_tree_fixture(tmp_path)
    (bundle / "unlisted.bin").write_bytes(b"not in the signed inventory")

    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="exact bundle bytes",
    ):
        materializer._validate_bundle_inventory(bundle, inventory, candidate)


def test_candidate_inventory_allows_bound_root_ancillary_only_for_unsigned_v3(
    tmp_path: Path,
) -> None:
    materializer, bundle, inventory, candidate = exact_tree_fixture(tmp_path)
    ancillary = bundle / "operator-note.txt"
    ancillary.write_bytes(b"retained incumbent ancillary")
    ancillary.chmod(0o644)
    row = {
        "path": ancillary.name,
        "sha256": sha(ancillary),
        "sizeBytes": ancillary.stat().st_size,
    }
    inventory["files"].append(row)
    inventory["files"].sort(key=lambda item: item["path"])
    candidate["fileCount"] += 1
    candidate["totalBytes"] += row["sizeBytes"]
    candidate["inventorySha256"] = materializer._inventory_digest(
        inventory["files"]
    )

    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="only the two finalized shelf manifests",
    ):
        materializer._validate_bundle_inventory(bundle, inventory, candidate)

    rows, modes, directory_modes, captured = materializer._validate_bundle_inventory(
        bundle,
        inventory,
        candidate,
        allow_root_ancillary_files=True,
    )
    assert rows == inventory["files"]
    assert modes[ancillary.name] == 0o644
    assert directory_modes == []
    assert set(captured) == {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
    }


def test_candidate_inventory_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    materializer, bundle, inventory, candidate = exact_tree_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    payload = outside / "payload.zip"
    payload.write_bytes(b"outside custody")
    (bundle / "files").symlink_to(outside, target_is_directory=True)
    row = {
        "path": "files/payload.zip",
        "sha256": sha(payload),
        "sizeBytes": payload.stat().st_size,
    }
    inventory["files"].append(row)
    inventory["files"].sort(key=lambda item: item["path"])
    candidate["fileCount"] += 1
    candidate["totalBytes"] += row["sizeBytes"]
    candidate["inventorySha256"] = materializer._inventory_digest(
        inventory["files"]
    )

    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="symbolic link",
    ):
        materializer._validate_bundle_inventory(bundle, inventory, candidate)


def test_candidate_tree_rejects_file_mutation_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materializer, bundle, _inventory, _candidate = exact_tree_fixture(tmp_path)
    files = bundle / "files"
    files.mkdir()
    payload = files / "payload.zip"
    payload.write_bytes(b"x" * (2 * 1024 * 1024))
    real_read = materializer.os.read
    mutated = False

    def racing_read(descriptor: int, count: int) -> bytes:
        nonlocal mutated
        chunk = real_read(descriptor, count)
        descriptor_path = Path(f"/proc/self/fd/{descriptor}")
        if (
            not mutated
            and chunk
            and descriptor_path.exists()
            and descriptor_path.resolve() == payload
        ):
            mutated = True
            payload.write_bytes(payload.read_bytes() + b"race")
        return chunk

    monkeypatch.setattr(materializer.os, "read", racing_read)
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="changed during validation",
    ):
        materializer._scan_bundle_tree(bundle)
    assert mutated is True


@pytest.mark.parametrize(
    ("path", "module_name", "helper", "exception_name"),
    [
        (
            MATERIALIZER,
            "candidate_materializer_alias_test",
            "_matching_alias",
            "CandidateAuthorityBlocked",
        ),
        (
            PROJECTION,
            "candidate_projection_alias_test",
            "_candidate_manifest_alias",
            "ProjectionBlocked",
        ),
    ],
)
def test_alias_helpers_reject_present_null(
    path: Path,
    module_name: str,
    helper: str,
    exception_name: str,
) -> None:
    module = load_script(path, module_name)

    with pytest.raises(getattr(module, exception_name), match="alias type drifted"):
        getattr(module, helper)(
            {"version": None, "releaseVersion": "run-candidate"},
            "version",
            "releaseVersion",
            label="candidate release version",
        )


def test_unsigned_candidate_scope_rejects_rehashed_non_preview_canonical_channel(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    _, canonical_path, summary_path, inventory_path, _ = fixture
    canonical = json.loads(canonical_path.read_text())
    canonical["channel"] = "stable"
    canonical["channelId"] = "stable"
    write_json(canonical_path, canonical)
    resummarize_fixture(fixture)
    candidate = json.loads(summary_path.read_text())
    rows = json.loads(inventory_path.read_text())["files"]

    materializer = load_script(MATERIALIZER, "unsigned_channel_materializer_test")
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="channel differs from its authority identity",
    ):
        materializer._canonical_windows_scope(
            canonical,
            rows,
            allow_ancillary_files=True,
            expected_channel="preview",
        )

    projection = load_projection()
    with pytest.raises(
        projection.ProjectionBlocked,
        match="channel differs from its authority identity",
    ):
        projection._candidate_windows_scope(
            canonical,
            rows,
            candidate,
            allow_ancillary_files=True,
            expected_channel="preview",
        )


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
    assert authority["contractVersion"] == 2
    assert authority["exactIncomingDesktopScope"] == "avalonia:windows:win-x64"
    assert authority["candidate"]["fileCount"] == 4
    assert authority["custody"]["canonicalManifest"]["base64"]
    evidence = authority["custody"]["nativeWindowsFinalizedEvidence"]
    assert evidence["reviewer"] == "scope-approver"
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
    assert authority["custody"]["registryFinalization"]["status"] == "finalized"


def test_materializer_rejects_independent_windows_finalized_root(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
        windows_finalized_root=fixture[4],
    )

    assert completed.returncode != 0
    assert "publication-stage proof/windows-native" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize("actor_field", ["candidateProducer", "nativeCapture"])
def test_projection_requires_independent_final_review_owner(
    tmp_path: Path,
    actor_field: str,
) -> None:
    completed, authority_path, _ = run_materializer(tmp_path)
    assert completed.returncode == 0, completed.stderr
    authority = json.loads(authority_path.read_text())
    actors = authority["custody"]["finalizedPublicationEvidence"]["actors"]
    actors[actor_field] = actors["scopeApprover"]

    module = load_projection()
    with pytest.raises(
        module.ProjectionBlocked,
        match="candidate finalized publication review owner is not independent",
    ):
        module._validate_candidate_import_authority(
            json.dumps(authority, separators=(",", ":"), sort_keys=True).encode()
        )


def test_projection_rejects_legacy_candidate_authority_v1(tmp_path: Path) -> None:
    completed, authority_path, _ = run_materializer(tmp_path)
    assert completed.returncode == 0, completed.stderr
    authority = json.loads(authority_path.read_text())
    authority["contractName"] = "chummer.release-upload.candidate-import-authority/v1"
    authority["contractVersion"] = 1

    module = load_projection()
    with pytest.raises(module.ProjectionBlocked):
        module._validate_candidate_import_authority(
            json.dumps(authority, separators=(",", ":"), sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    ("reference_name", "contract_name", "contract_version", "reference_path"),
    [
        (
            "wrapper",
            "chummer6-ui.preview-nightly-native-windows-evidence",
            1,
            "NATIVE_WINDOWS_EVIDENCE.generated.json",
        ),
        (
            "nativeFinalization",
            "chummer6-ui.preview-nightly-native-windows-finalization",
            2,
            "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
        ),
        (
            "visualProof",
            "chummer6-ui.windows_installer_visual_proof",
            1,
            "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json",
        ),
        (
            "authenticodeVerification",
            "chummer6-ui.windows-authenticode-verification",
            1,
            (
                "proof/windows-native/authenticode/"
                "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"
            ),
        ),
    ],
)
@pytest.mark.parametrize(
    "numeric_drift",
    ["boolean_contract_version", "float_contract_version", "float_size"],
)
def test_native_composite_rejects_python_numeric_equality_aliases(
    tmp_path: Path,
    reference_name: str,
    contract_name: str,
    contract_version: int,
    reference_path: str,
    numeric_drift: str,
) -> None:
    materializer = load_script(
        MATERIALIZER,
        "candidate_materializer_composite_numeric_test",
    )
    held = b"held-native-reference"
    reference = {
        "contractName": contract_name,
        "contractVersion": contract_version,
        "path": reference_path,
        "sha256": hashlib.sha256(held).hexdigest(),
        "sizeBytes": len(held),
    }
    if numeric_drift == "boolean_contract_version":
        reference["contractVersion"] = True
    elif numeric_drift == "float_contract_version":
        reference["contractVersion"] = float(contract_version)
    else:
        reference["sizeBytes"] = float(len(held))
    with pytest.raises(materializer.CandidateAuthorityBlocked):
        materializer._native_contract_reference(
            reference,
            label=reference_name,
            contract_name=contract_name,
            contract_version=contract_version,
            path=reference_path,
            raw=held,
        )

    completed, authority_path, _ = run_materializer(tmp_path)
    assert completed.returncode == 0, completed.stderr
    authority = json.loads(authority_path.read_text())
    finalized = authority["custody"]["finalizedPublicationEvidence"]
    scope_entry = next(
        entry
        for entry in finalized["files"]
        if entry["path"] == "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json"
    )
    scope = json.loads(base64.b64decode(scope_entry["base64"]))
    scope_reference = scope["nativeEvidenceComposite"][reference_name]
    if numeric_drift == "boolean_contract_version":
        scope_reference["contractVersion"] = True
    elif numeric_drift == "float_contract_version":
        scope_reference["contractVersion"] = float(scope_reference["contractVersion"])
    else:
        scope_reference["sizeBytes"] = float(scope_reference["sizeBytes"])
    scope_raw = (
        json.dumps(scope, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    scope_entry["base64"] = base64.b64encode(scope_raw).decode()
    scope_entry["sha256"] = hashlib.sha256(scope_raw).hexdigest()
    scope_entry["sizeBytes"] = len(scope_raw)
    finalized["publicationScopeSha256"] = scope_entry["sha256"]

    verifier = load_projection()
    with pytest.raises(verifier.ProjectionBlocked):
        verifier._validate_candidate_import_authority(
            json.dumps(authority, separators=(",", ":"), sort_keys=True).encode()
        )


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
    assert "candidate" in completed.stderr
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


def test_fully_aligned_blazor_scope_cannot_become_promoted_authority(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(
        tmp_path,
        required_heads=("avalonia", "blazor-desktop"),
        artifact_heads=("avalonia", "blazor-desktop"),
        evidence_heads=("avalonia", "blazor-desktop"),
    )
    completed, output, _ = invoke_materializer(
        fixture, tmp_path / "candidate-authority.json"
    )

    assert completed.returncode != 0
    assert "promoted Avalonia head" in completed.stderr
    assert not output.exists()

    _, canonical_path, summary_path, inventory_path, _ = fixture
    module = load_projection()
    with pytest.raises(module.ProjectionBlocked, match="promoted Avalonia head"):
        module._candidate_windows_scope(
            json.loads(canonical_path.read_text()),
            json.loads(inventory_path.read_text())["files"],
            json.loads(summary_path.read_text()),
        )


def test_candidate_inventory_rejects_extra_root_level_row(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    bundle, canonical_path, summary_path, inventory_path, _ = fixture
    (bundle / "UNEXPECTED.generated.json").write_text("{}\n", encoding="utf-8")
    resummarize_fixture(fixture)

    completed, output, _ = invoke_materializer(
        fixture, tmp_path / "candidate-authority.json"
    )

    assert completed.returncode != 0
    assert "only the two finalized shelf manifests" in completed.stderr
    assert not output.exists()

    module = load_projection()
    with pytest.raises(module.ProjectionBlocked, match="exact finalized desktop shelf"):
        module._candidate_windows_scope(
            json.loads(canonical_path.read_text()),
            json.loads(inventory_path.read_text())["files"],
            json.loads(summary_path.read_text()),
        )


def test_native_preserved_provenance_must_retain_release_binding(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    finalized_inventory = (
        fixture[-1]
        / "candidate-provenance"
        / "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
    )
    document = json.loads(finalized_inventory.read_text())
    document["release"]["channel"] = "tampered-preview"
    write_json(finalized_inventory, document)
    refresh_directory_evidence_bindings(fixture[-1])

    completed, output, _ = invoke_materializer(
        fixture, tmp_path / "candidate-authority.json"
    )

    assert completed.returncode != 0
    assert "provenance inventory release binding drifted" in completed.stderr
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
    assert "exact finalized desktop shelf" in completed.stderr or "desktop tuple" in completed.stderr
    assert not output.exists()

    _, canonical_path, summary_path, inventory_path, _ = fixture
    module = load_projection()
    with pytest.raises(
        module.ProjectionBlocked,
        match="required desktop tuple|exact finalized desktop shelf",
    ):
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
    assert "candidate export source differs" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "publication_scope_extra",
        "supply_chain_divergent",
        "verification_non_authoritative",
    ],
)
def test_materializer_rejects_fully_rehashed_windows_only_export_authority_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    fixture = candidate_fixture(tmp_path)
    write_publication_stage(fixture)
    finalized = fixture[-1]
    export_path = (
        finalized
        / "candidate-provenance"
        / "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
    )
    export = json.loads(export_path.read_text())
    if tamper == "publication_scope_extra":
        export["publicationScope"]["unexpected"] = True
    elif tamper == "supply_chain_divergent":
        export["supplyChain"] = {"divergent": True}
    else:
        export["supplyChainVerification"] = {
            "mode": "advisory",
            "releaseAuthoritative": False,
        }
    write_json(export_path, export)
    refresh_directory_evidence_bindings(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert "candidate export Windows-only authority drifted" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize("mismatch", ["bool_number", "numeric_lexeme"])
def test_materializer_rejects_fully_rehashed_supply_chain_json_kind_mismatch(
    tmp_path: Path,
    mismatch: str,
) -> None:
    fixture = candidate_fixture(tmp_path)
    capture_supply_chain = {
        "typedValue": True if mismatch == "bool_number" else 1.0
    }
    export_supply_chain = {"typedValue": 1 if mismatch == "bool_number" else 1.0}

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
        capture_supply_chain=capture_supply_chain,
        export_supply_chain=export_supply_chain,
        export_numeric_lexeme="1e0" if mismatch == "numeric_lexeme" else None,
    )

    finalized = fixture[-1]
    capture = json.loads(
        (finalized / "WINDOWS_NATIVE_CAPTURE.generated.json").read_text()
    )
    export_path = (
        finalized
        / "candidate-provenance"
        / "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
    )
    export = json.loads(export_path.read_text())
    assert capture["candidate"]["supplyChain"] == export["supplyChain"]
    if mismatch == "numeric_lexeme":
        assert b'"typedValue": 1e0' in export_path.read_bytes()
    assert completed.returncode != 0
    assert "candidate export Windows-only authority drifted" in completed.stderr
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


@pytest.mark.parametrize(
    "tamper",
    [
        "empty",
        "extra",
        "receipt_fields",
        "progress_path",
        "extra_screenshot",
        "boolean_width",
    ],
)
def test_materializer_rejects_rehashed_capture_head_drift(
    tmp_path: Path,
    tamper: str,
) -> None:
    fixture = candidate_fixture(tmp_path)
    capture_path = fixture[-1] / "WINDOWS_NATIVE_CAPTURE.generated.json"
    capture = json.loads(capture_path.read_text())
    head = capture["heads"][0]
    if tamper == "empty":
        capture["heads"] = []
    elif tamper == "extra":
        capture["heads"].append(json.loads(json.dumps(head)))
    elif tamper == "receipt_fields":
        head["receipt"]["sizeBytes"] = 1
    elif tamper == "progress_path":
        head["progressLog"]["path"] = (
            "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"
        )
    elif tamper == "extra_screenshot":
        head["screenshots"].append(json.loads(json.dumps(head["screenshots"][0])))
    else:
        head["screenshots"][0]["width"] = True
    write_json(capture_path, capture)
    refresh_directory_evidence_bindings(fixture[-1])

    completed, output, _ = invoke_materializer(
        fixture, tmp_path / "candidate-authority.json"
    )

    assert completed.returncode != 0
    assert "capture" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "binding",
    ["capture_installer", "export_payload", "startup_payload"],
)
def test_materializer_rejects_boolean_size_for_one_byte_artifact_binding(
    tmp_path: Path,
    binding: str,
) -> None:
    fixture = candidate_fixture(tmp_path, one_byte_artifacts=True)
    bundle, _, _, _, finalized = fixture
    if binding == "capture_installer":
        target = finalized / "WINDOWS_NATIVE_CAPTURE.generated.json"
        document = json.loads(target.read_text())
        document["heads"][0]["installer"]["sizeBytes"] = True
        write_json(target, document)
    elif binding == "export_payload":
        target = (
            finalized
            / "candidate-provenance"
            / "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
        )
        document = json.loads(target.read_text())
        document["heads"][0]["payload"]["sizeBytes"] = True
        payload = write_json(target, document)
        (bundle / target.name).write_bytes(payload)
        resummarize_fixture(fixture)
    else:
        target = (
            finalized
            / "startup-smoke"
            / "startup-smoke-avalonia-win-x64.receipt.json"
        )
        document = json.loads(target.read_text())
        document["bootstrapPayloadSizeBytes"] = True
        write_json(target, document)
    refresh_directory_evidence_bindings(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_materializer_rejects_numeric_human_review_boolean(tmp_path: Path) -> None:
    fixture = candidate_fixture(tmp_path)
    finalized = fixture[-1]
    proof = (
        finalized
        / "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json"
    )
    document = json.loads(proof.read_text())
    document["checks"]["human_review_confirmed"] = 1
    write_json(proof, document)
    refresh_directory_evidence_bindings(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_materializer_rejects_rehashed_capture_inventory_row_drift(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    finalized = fixture[-1]
    capture_inventory = finalized / "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
    document = json.loads(capture_inventory.read_text())
    document["files"][0]["unexpected"] = True
    write_json(capture_inventory, document)
    refresh_directory_evidence_bindings(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert "capture inventory" in completed.stderr
    assert not output.exists()


def test_materializer_rejects_self_consistent_extra_finalized_file(
    tmp_path: Path,
) -> None:
    fixture = candidate_fixture(tmp_path)
    finalized = fixture[-1]
    (finalized / "zz-unexpected.bin").write_bytes(b"x")
    refresh_finalized_inventory(finalized)

    completed, output, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )

    assert completed.returncode != 0
    assert "inventory file scope drifted" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize("document", ["capture", "finalization", "upload_inventory"])
def test_python_contract_versions_reject_boolean_one(
    tmp_path: Path,
    document: str,
) -> None:
    fixture = candidate_fixture(tmp_path)
    if document == "upload_inventory":
        target = fixture[3]
        payload = json.loads(target.read_text())
        payload["contractVersion"] = True
        write_json(target, payload)
    else:
        target = fixture[-1] / (
            "WINDOWS_NATIVE_CAPTURE.generated.json"
            if document == "capture"
            else "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
        )
        payload = json.loads(target.read_text())
        payload["contractVersion"] = True
        write_json(target, payload)
        refresh_directory_evidence_bindings(fixture[-1])

    completed, output, _ = invoke_materializer(
        fixture, tmp_path / "candidate-authority.json"
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
    review_pointer = (snapshot_root / module.CURRENT_POINTER_NAME).read_bytes()
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
    current = json.loads(
        (snapshot_root / module.CURRENT_POINTER_NAME).read_text(encoding="utf-8")
    )
    assert result.manifest_sha256 == current["manifestSha256"]
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

    (snapshot_root / module.CURRENT_POINTER_NAME).write_bytes(review_pointer)
    advanced = module.resolve_current_snapshot(
        snapshot_root, purpose=module.PROJECTION_PURPOSE_CODE_DEPLOY
    )
    assert advanced.snapshot_sha256 != result.snapshot_sha256
    generation = module.resolve_snapshot_generation(
        snapshot_root,
        snapshot_id=result.snapshot_id,
        snapshot_sha256=result.snapshot_sha256,
        manifest_sha256=result.manifest_sha256,
        purpose=module.PROJECTION_PURPOSE_CANDIDATE_IMPORT,
    )
    assert generation.snapshot_sha256 == result.snapshot_sha256
    with pytest.raises(module.ProjectionBlocked, match="not authorized for release upload"):
        module.resolve_snapshot_generation(
            snapshot_root,
            snapshot_id=result.snapshot_id,
            snapshot_sha256=result.snapshot_sha256,
            manifest_sha256=result.manifest_sha256,
        )


def test_candidate_publication_rejects_replaced_authenticated_source_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed, authority_path, _ = run_materializer(tmp_path / "candidate")
    assert completed.returncode == 0, completed.stderr
    module = load_projection()
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(mode=0o700)
    publish_review_snapshot(module, snapshot_root)
    original_pointer = (snapshot_root / module.CURRENT_POINTER_NAME).read_bytes()
    source = module.resolve_current_snapshot(
        snapshot_root,
        purpose=module.PROJECTION_PURPOSE_CODE_DEPLOY,
    )
    source_manifest_path = source.snapshot_directory / module.SNAPSHOT_MANIFEST_NAME
    forged = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    forged["authorityInputs"] = {"forgedAfterAuthentication": True}
    forged_bytes = (
        json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    real_stable_read = module._stable_read
    manifest_reads = 0

    def raced_stable_read(path, *args, **kwargs):
        nonlocal manifest_reads
        payload = real_stable_read(path, *args, **kwargs)
        if Path(path) == source_manifest_path:
            manifest_reads += 1
            if manifest_reads == 2:
                return forged_bytes
        return payload

    monkeypatch.setattr(module, "_stable_read", raced_stable_read)
    with pytest.raises(
        module.ProjectionBlocked,
        match="source current snapshot manifest changed during candidate staging",
    ):
        module.publish_candidate_import_snapshot(
            snapshot_root,
            authority_path=authority_path,
            expected_authority_sha256=sha(authority_path),
        )

    assert manifest_reads == 2
    assert (snapshot_root / module.CURRENT_POINTER_NAME).read_bytes() == original_pointer


@pytest.mark.parametrize(
    "tamper",
    [
        "empty_capture",
        "capture_actor",
        "capture_workflow",
        "capture_run_id_whitespace",
        "capture_artifact_identity",
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
        "export_publication_scope_extra",
        "export_supply_chain_divergent",
        "export_verification_non_authoritative",
        "export_supply_chain_bool_number",
        "export_supply_chain_numeric_lexeme",
        "export_heads",
        "capture_heads_empty",
        "capture_heads_extra",
        "capture_receipt_fields",
        "capture_progress_path",
        "capture_screenshot_extra",
        "capture_width_type",
        "finalization_contract_type",
        "candidate_root_inventory_digest",
        "candidate_root_export_digest",
        "upload_inventory_contract_type",
        "authority_root_extra",
        "candidate_extra",
        "custody_extra",
        "canonical_manifest_path",
        "inventory_path",
        "inventory_root_extra",
        "inventory_row_extra",
        "embedded_entry_extra",
        "visual_screenshot_order",
        "visual_checks_extra",
        "visual_checks_numeric",
        "visual_review_extra",
        "finalized_inventory_extra_row",
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

    if tamper == "authority_root_extra":
        authority["unexpected"] = True
    elif tamper == "candidate_extra":
        authority["candidate"]["unexpected"] = True
    elif tamper == "custody_extra":
        authority["custody"]["unexpected"] = True
    elif tamper == "canonical_manifest_path":
        authority["custody"]["canonicalManifest"]["path"] = "renamed-release-channel.json"
    elif tamper == "inventory_path":
        authority["custody"]["inventory"]["path"] = "renamed-candidate-inventory.json"
    elif tamper in {"inventory_root_extra", "inventory_row_extra"}:
        def mutate_inventory_shape(value):
            if tamper == "inventory_root_extra":
                value["unexpected"] = True
            else:
                value["files"][0]["unexpected"] = True
            return value

        rewrite_candidate_inventory(authority, mutate_inventory_shape)
    elif tamper == "embedded_entry_extra":
        entry = next(
            item
            for item in native["files"]
            if item["path"] == "WINDOWS_NATIVE_CAPTURE.generated.json"
        )
        entry["unexpected"] = True
    elif tamper == "finalized_inventory_extra_row":
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json",
            lambda value: {
                **value,
                "files": [
                    *value["files"],
                    {
                        "path": "zz-unexpected.bin",
                        "sha256": "0" * 64,
                        "sizeBytes": 1,
                    },
                ],
            },
        )
    elif tamper == "visual_screenshot_order":
        rewrite_embedded_document(
            authority,
            proof_path,
            lambda value: {
                **value,
                "screenshots": list(reversed(value["screenshots"])),
            },
        )
    elif tamper in {"visual_checks_extra", "visual_checks_numeric"}:
        rewrite_embedded_document(
            authority,
            proof_path,
            lambda value: {
                **value,
                "checks": {
                    **value["checks"],
                    **(
                        {"unexpected": True}
                        if tamper == "visual_checks_extra"
                        else {"human_review_confirmed": 1}
                    ),
                },
            },
        )
    elif tamper == "visual_review_extra":
        rewrite_embedded_document(
            authority,
            proof_path,
            lambda value: {
                **value,
                "readabilityReview": {
                    **value["readabilityReview"],
                    "unexpected": True,
                },
            },
        )
    elif tamper == "empty_capture":
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
    elif tamper in {"capture_run_id_whitespace", "capture_artifact_identity"}:
        if tamper == "capture_run_id_whitespace":
            native["captureSource"]["runId"] = "   "
        else:
            native["captureSource"]["artifactName"] = "unbound-capture-artifact"
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
    elif tamper == "export_publication_scope_extra":
        rewrite_embedded_document(
            authority,
            export_path,
            lambda value: {
                **value,
                "publicationScope": {
                    **value["publicationScope"],
                    "unexpected": True,
                },
            },
        )
    elif tamper == "export_supply_chain_divergent":
        rewrite_embedded_document(
            authority,
            export_path,
            lambda value: {**value, "supplyChain": {"divergent": True}},
        )
    elif tamper == "export_verification_non_authoritative":
        rewrite_embedded_document(
            authority,
            export_path,
            lambda value: {
                **value,
                "supplyChainVerification": {
                    "mode": "advisory",
                    "releaseAuthoritative": False,
                },
            },
        )
    elif tamper in {
        "export_supply_chain_bool_number",
        "export_supply_chain_numeric_lexeme",
    }:
        numeric_lexeme = tamper == "export_supply_chain_numeric_lexeme"
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            lambda value: {
                **value,
                "candidate": {
                    **value["candidate"],
                    "supplyChain": {
                        "typedValue": 1.0 if numeric_lexeme else True,
                    },
                },
            },
        )
        rewrite_embedded_document(
            authority,
            export_path,
            lambda value: {
                **value,
                "supplyChain": {
                    "typedValue": 1.0 if numeric_lexeme else 1,
                },
            },
        )
        if numeric_lexeme:
            def replace_numeric_lexeme(payload: bytes) -> bytes:
                marker = b'"typedValue":1.0'
                assert payload.count(marker) == 1
                return payload.replace(marker, b'"typedValue":1e0')

            rewrite_embedded_document_raw(
                authority,
                export_path,
                replace_numeric_lexeme,
            )
    elif tamper == "export_heads":
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
    elif tamper in {
        "candidate_root_inventory_digest",
        "candidate_root_export_digest",
        "upload_inventory_contract_type",
    }:
        def mutate_inventory(value):
            if tamper == "upload_inventory_contract_type":
                value["contractVersion"] = True
                return value
            target = (
                "releases.json"
                if tamper == "candidate_root_inventory_digest"
                else "files/chummer-avalonia-win-x64-installer.exe"
            )
            row = next(row for row in value["files"] if row["path"] == target)
            row["sha256"] = "f" * 64
            return value

        rewrite_candidate_inventory(authority, mutate_inventory)
    elif tamper.startswith("capture_"):
        def mutate_capture(value):
            heads = value["heads"]
            head = heads[0]
            if tamper == "capture_heads_empty":
                value["heads"] = []
            elif tamper == "capture_heads_extra":
                heads.append(json.loads(json.dumps(head)))
            elif tamper == "capture_receipt_fields":
                head["receipt"]["sizeBytes"] = 1
            elif tamper == "capture_progress_path":
                head["progressLog"]["path"] = "startup-smoke/other.log"
            elif tamper == "capture_screenshot_extra":
                head["screenshots"].append(
                    json.loads(json.dumps(head["screenshots"][0]))
                )
            else:
                head["screenshots"][0]["width"] = True
            return value

        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            mutate_capture,
        )
    else:
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
            lambda value: {**value, "contractVersion": True},
        )

    refresh_rehashed_evidence_bindings(authority)
    tampered = tmp_path / "tampered-authority.json"
    write_rehashed_authority(tampered, authority)
    module = load_projection()
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(mode=0o700)
    publish_review_snapshot(module, snapshot_root)

    with pytest.raises(module.ProjectionBlocked) as blocked:
        module.publish_candidate_import_snapshot(
            snapshot_root,
            authority_path=tampered,
            expected_authority_sha256=sha(tampered),
        )
    if tamper in {
        "export_publication_scope_extra",
        "export_supply_chain_divergent",
        "export_verification_non_authoritative",
        "export_supply_chain_bool_number",
        "export_supply_chain_numeric_lexeme",
    }:
        assert str(blocked.value) == "candidate export Windows-only authority drifted"


@pytest.mark.parametrize(
    "binding",
    ["capture_installer", "export_payload", "startup_payload"],
)
def test_projection_rejects_boolean_size_for_one_byte_artifact_binding(
    tmp_path: Path,
    binding: str,
) -> None:
    fixture = candidate_fixture(tmp_path / "candidate", one_byte_artifacts=True)
    completed, authority_path, _ = invoke_materializer(
        fixture,
        tmp_path / "candidate-authority.json",
    )
    assert completed.returncode == 0, completed.stderr
    authority = json.loads(authority_path.read_text())
    if binding == "capture_installer":
        rewrite_embedded_document(
            authority,
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            lambda value: {
                **value,
                "heads": [
                    {
                        **value["heads"][0],
                        "installer": {
                            **value["heads"][0]["installer"],
                            "sizeBytes": True,
                        },
                    }
                ],
            },
        )
    elif binding == "export_payload":
        rewrite_embedded_document(
            authority,
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
            lambda value: {
                **value,
                "heads": [
                    {
                        **value["heads"][0],
                        "payload": {
                            **value["heads"][0]["payload"],
                            "sizeBytes": True,
                        },
                    }
                ],
            },
        )
    else:
        rewrite_embedded_document(
            authority,
            "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
            lambda value: {**value, "bootstrapPayloadSizeBytes": True},
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
