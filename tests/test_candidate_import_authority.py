from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = REPO_ROOT / "scripts" / "release" / "release_upload_attempt_receipt.py"
MATERIALIZER = REPO_ROOT / "scripts" / "release" / "materialize_candidate_import_authority.py"
PROJECTION = REPO_ROOT / "scripts" / "release" / "verify_public_projection.py"
UNSIGNED_V3_AUTHORITY_FIXTURE = (
    REPO_ROOT
    / "Chummer.Tests"
    / "Fixtures"
    / "unsigned_candidate_import_authority_v3.json.gz.b64"
)
UNSIGNED_FRESH_DELTA_MANIFEST_PAIR_FIXTURE = (
    REPO_ROOT
    / "Chummer.Tests"
    / "Fixtures"
    / "unsigned_windows_fresh_delta_manifest_pair.json.gz.b64"
)
UNSIGNED_FRESH_DELTA_AUTHORITY_FIXTURE = (
    REPO_ROOT
    / "Chummer.Tests"
    / "Fixtures"
    / "unsigned_windows_fresh_delta_candidate_import_authority_v3.json.gz.b64"
)
UNSIGNED_NATIVE_V4_CONTRACT_FIXTURE = (
    REPO_ROOT
    / "Chummer.Tests"
    / "Fixtures"
    / "unsigned_native_evidence_v4_contract.json.gz.b64"
)
UNSIGNED_V4_AUTHORITY_FIXTURE = (
    REPO_ROOT
    / "Chummer.Tests"
    / "Fixtures"
    / "unsigned_candidate_import_authority_v4_distinct_source.json.gz.b64"
)
DEFAULT_HEADS = ("avalonia",)
UNSIGNED_RETAINED_POINTER_KEYS = {
    "atomicallyRetained",
    "authority",
    "bundleInventoryCount",
    "bundleInventorySha256",
    "consumerCommit",
    "contractName",
    "contractVersion",
    "manifest",
    "manifestIsAuthoritative",
    "release",
    "status",
    "targetPath",
}
UNSIGNED_BUNDLE_INVENTORY_COUNT = 344
UNSIGNED_BUNDLE_INVENTORY_SHA256 = (
    "0f26e227d658d3986bd54969d8b994fa89046807325f5367f1a5b23572eb6026"
)


def real_unsigned_cross_platform_shelf() -> tuple[
    dict[str, object],
    list[dict[str, object]],
    dict[str, object],
]:
    version = "run-cross-platform-shelf"
    artifacts: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []

    def add_primary(
        *,
        head: str,
        platform: str,
        rid: str,
        kind: str,
        file_name: str,
    ) -> dict[str, object]:
        raw = f"{head}:{platform}:{rid}:{kind}:{file_name}".encode()
        artifact: dict[str, object] = {
            "artifactId": file_name,
            "head": head,
            "platform": platform,
            "rid": rid,
            "kind": kind,
            "fileName": file_name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sizeBytes": len(raw),
        }
        artifacts.append(artifact)
        rows.append(
            {
                "path": f"files/{file_name}",
                "sha256": artifact["sha256"],
                "sizeBytes": artifact["sizeBytes"],
            }
        )
        return artifact

    for head in ("blazor-desktop", "avalonia"):
        add_primary(
            head=head,
            platform="macos",
            rid="osx-arm64",
            kind="installer",
            file_name=f"chummer-{head}-osx-arm64-installer.dmg",
        )
        add_primary(
            head=head,
            platform="macos",
            rid="osx-arm64",
            kind="archive",
            file_name=f"chummer-{head}-osx-arm64.zip",
        )
    add_primary(
        head="avalonia",
        platform="linux",
        rid="linux-x64",
        kind="installer",
        file_name="chummer-avalonia-linux-x64-installer.deb",
    )

    windows = add_primary(
        head="avalonia",
        platform="windows",
        rid="win-x64",
        kind="installer",
        file_name="chummer-avalonia-win-x64-installer.exe",
    )
    payload_raw = b"fresh-avalonia-windows-bootstrap-payload"
    windows.update(
        {
            "installerMode": "bootstrap",
            "payloadAcquisitionMode": "download",
            "payloadFileName": "chummer-avalonia-win-x64-payload.zip",
            "payloadSha256": hashlib.sha256(payload_raw).hexdigest(),
            "payloadSizeBytes": len(payload_raw),
        }
    )
    rows.append(
        {
            "path": "files/chummer-avalonia-win-x64-payload.zip",
            "sha256": windows["payloadSha256"],
            "sizeBytes": windows["payloadSizeBytes"],
        }
    )
    rows.extend(
        [
            {
                "path": "RELEASE_CHANNEL.generated.json",
                "sha256": hashlib.sha256(b"canonical").hexdigest(),
                "sizeBytes": len(b"canonical"),
            },
            {
                "path": "releases.json",
                "sha256": hashlib.sha256(b"compatibility").hexdigest(),
                "sizeBytes": len(b"compatibility"),
            },
        ]
    )
    rows.sort(key=lambda row: str(row["path"]))
    canonical: dict[str, object] = {
        "version": version,
        "releaseVersion": version,
        "channel": "preview",
        "channelId": "preview",
        "desktopTupleCoverage": {"requiredDesktopHeads": ["avalonia"]},
        "artifacts": artifacts,
    }
    return canonical, rows, {"version": version}


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


def load_unsigned_v3_authority_fixture() -> dict[str, object]:
    encoded = "".join(UNSIGNED_V3_AUTHORITY_FIXTURE.read_text().splitlines())
    authority = json.loads(gzip.decompress(base64.b64decode(encoded)))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    authority["generatedAtUtc"] = now.isoformat().replace("+00:00", "Z")
    authority["expiresAtUtc"] = (now + timedelta(hours=2)).isoformat().replace(
        "+00:00", "Z"
    )
    return authority


def load_unsigned_native_v4_contract_fixture() -> dict[str, object]:
    encoded = "".join(UNSIGNED_NATIVE_V4_CONTRACT_FIXTURE.read_text().splitlines())
    value = json.loads(gzip.decompress(base64.b64decode(encoded)))
    assert isinstance(value, dict)
    return value


def load_unsigned_v4_authority_fixture() -> dict[str, object]:
    encoded = "".join(UNSIGNED_V4_AUTHORITY_FIXTURE.read_text().splitlines())
    value = json.loads(gzip.decompress(base64.b64decode(encoded)))
    assert isinstance(value, dict)
    return value


def rehydrate_unsigned_native_v4_root(
    tmp_path: Path,
) -> tuple[
    object,
    Path,
    dict[str, object],
    list[dict[str, object]],
    bytes,
    bytes,
    dict[str, object],
    datetime,
]:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_v4_materializer_test",
    )
    fixture = load_unsigned_native_v4_contract_fixture()
    native = fixture["nativeEvidence"]
    assert isinstance(native, dict)
    root = tmp_path / "proof" / "windows-native"
    root.mkdir(parents=True)
    files = native["files"]
    assert isinstance(files, list)
    for row in files:
        assert isinstance(row, dict)
        path = root / str(row["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(str(row["bytesBase64"]), validate=True))
    (root / materializer.UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE).write_text(
        json.dumps(native, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate_rows = fixture["inventory"]
    assert isinstance(candidate_rows, list)
    canonical = base64.b64decode(
        str(fixture["canonicalManifestBase64"]),
        validate=True,
    )
    compatibility = base64.b64decode(
        str(fixture["compatibilityManifestBase64"]),
        validate=True,
    )
    canonical_document = json.loads(canonical)
    scope = materializer._canonical_windows_scope(
        canonical_document,
        candidate_rows,
        allow_ancillary_files=True,
        expected_channel="preview",
    )
    now = datetime.fromisoformat(str(fixture["nowUtc"]).replace("Z", "+00:00"))
    return (
        materializer,
        root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    )


def rewrite_unsigned_native_embedded_document(
    root: Path,
    outer: dict[str, object],
    path: str,
    document: dict[str, object],
) -> bytes:
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    rows = outer["files"]
    assert isinstance(rows, list)
    row = next(
        item
        for item in rows
        if isinstance(item, dict) and item.get("path") == path
    )
    row["bytesBase64"] = base64.b64encode(payload).decode("ascii")
    row["sha256"] = hashlib.sha256(payload).hexdigest()
    row["sizeBytes"] = len(payload)
    (root / path).write_bytes(payload)
    return payload


def upgrade_embedded_v4_authority_to_current_startup(
    authority: dict[str, object],
    *,
    process_path: str = "Chummer.Avalonia.exe",
    capture_executable: dict[str, object] | None = None,
    receipt_executable: dict[str, object] | None = None,
) -> None:
    custody = authority["custody"]
    assert isinstance(custody, dict)
    evidence = custody["nativeWindowsFinalizedEvidence"]
    assert isinstance(evidence, dict)
    rows = evidence["files"]
    assert isinstance(rows, list)
    payloads = {
        str(row["path"]): base64.b64decode(
            str(row["bytesBase64"]),
            validate=True,
        )
        for row in rows
        if isinstance(row, dict)
    }

    def document(path: str) -> dict[str, object]:
        value = json.loads(payloads[path])
        assert isinstance(value, dict)
        return value

    def write_document(path: str, value: dict[str, object]) -> None:
        payloads[path] = (
            json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

    def binding(path: str) -> dict[str, object]:
        payload = payloads[path]
        return {
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "sizeBytes": len(payload),
        }

    head = "avalonia"
    rid = "win-x64"
    receipt_path = f"startup-smoke/startup-smoke-{head}-{rid}.receipt.json"
    startup_log_path = f"startup-smoke/startup-smoke-{head}-{rid}.log"
    payload_http_path = (
        f"startup-smoke/startup-smoke-payload-http-{head}-{rid}.log"
    )
    startup_visual_path = (
        f"startup-visual/windows-application-{head}-{rid}"
        "-startup.receipt.json"
    )
    capture_path = "UNSIGNED_WINDOWS_PREVIEW_NATIVE_CAPTURE.generated.json"
    capture_inventory_path = (
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_CAPTURE_INVENTORY.generated.json"
    )
    finalization_path = (
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZATION.generated.json"
    )
    finalized_inventory_path = (
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_INVENTORY.generated.json"
    )
    visual_path = (
        "UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-"
        f"{head}-{rid}.generated.json"
    )

    startup = document(receipt_path)
    installer_name = str(startup["artifactFileName"])
    payload_name = str(startup["bootstrapPayloadFileName"])
    timestamp = str(evidence["captureGeneratedAtUtc"])
    startup.update(
        {
            "arch": "x64",
            "artifactDigestSource": "environment",
            "artifactId": f"{head}-{rid}-installer",
            "artifactInstallMode": "nsis_bootstrap_installer",
            "artifactPath": f"files/{installer_name}",
            "artifactPathDisclosure": "artifact_shelf_relative_path",
            "artifactRelativePath": f"files/{installer_name}",
            "artifactSha256": str(startup["artifactDigest"]).removeprefix(
                "sha256:"
            ),
            "bootstrapPayloadDownloadUrl": (
                f"http://127.0.0.1:50023/{payload_name}"
            ),
            "completedAtUtc": timestamp,
            "fileName": installer_name,
            "framework": ".NET 10.0.3",
            "hostClass": "github-hosted-windows-latest-native",
            "installLinkingInstallationId": f"ins-{'c' * 32}",
            "installLinkingLaunchCount": 1,
            "installLinkingPromptReason": "claim_required",
            "installLinkingPromptRequired": True,
            "installLinkingStatus": "guest",
            "operatingSystem": "Microsoft Windows 10.0.26100",
            "processPath": process_path,
            "processPathDisclosure": "file_name_only",
            "recordedAtUtc": timestamp,
            "startedAtUtc": timestamp,
            "verificationScope": "native_windows_startup",
            "version": startup["releaseVersion"],
        }
    )
    startup["nativeHostEvidence"] = {
        "contractName": "chummer6-ui.native_windows_host_evidence",
        "evidenceSource": "host_kernel_and_runner_selection",
        "hostKernel": "MINGW64_NT-10.0-26100",
        "hostPlatform": "windows",
        "isNativeWindows": True,
        "runner": "pwsh",
        "status": "verified",
    }
    write_document(receipt_path, startup)
    payloads[startup_log_path] = (
        b"startup smoke ready: head=avalonia platform=windows "
        b"arch=x64 checkpoint=pre_ui_event_loop\n"
    )
    payloads[payload_http_path] = (
        b'127.0.0.1 - - [26/Jul/2026 22:54:53] "GET /'
        + payload_name.encode("ascii")
        + b' HTTP/1.1" 200 -\n'
    )

    startup_visual = document(startup_visual_path)
    original_executable = startup_visual["installedExecutable"]
    assert isinstance(original_executable, dict)
    startup_visual["installedExecutable"] = (
        receipt_executable
        if receipt_executable is not None
        else dict(original_executable)
    )
    write_document(startup_visual_path, startup_visual)

    capture = document(capture_path)
    heads = capture["heads"]
    native_evidence = capture["nativeEvidence"]
    assert isinstance(heads, list) and isinstance(heads[0], dict)
    assert isinstance(native_evidence, dict)
    native_head = native_evidence["head"]
    startup_visual_binding = native_evidence["startupVisual"]
    assert isinstance(native_head, dict)
    assert isinstance(startup_visual_binding, dict)
    receipt_digest = binding(receipt_path)["sha256"]
    heads[0]["receipt"]["sha256"] = receipt_digest
    native_head["receipt"]["sha256"] = receipt_digest
    native_evidence["startupLog"] = binding(startup_log_path)
    native_evidence["payloadHttpLog"] = binding(payload_http_path)
    startup_visual_binding["receipt"] = binding(startup_visual_path)
    startup_visual_binding["installedExecutable"] = (
        capture_executable
        if capture_executable is not None
        else dict(original_executable)
    )
    write_document(capture_path, capture)

    capture_inventory = document(capture_inventory_path)
    capture_inventory["files"] = [
        binding(str(row["path"]))
        for row in capture_inventory["files"]
        if isinstance(row, dict)
    ]
    capture_inventory["captureManifest"] = binding(capture_path)
    write_document(capture_inventory_path, capture_inventory)
    capture_inventory_sha = hashlib.sha256(
        payloads[capture_inventory_path]
    ).hexdigest()

    visual = document(visual_path)
    visual["captureBinding"]["inventorySha256"] = capture_inventory_sha
    write_document(visual_path, visual)

    finalization = document(finalization_path)
    finalization["captureInventorySha256"] = capture_inventory_sha
    finalization["proofs"][0]["sha256"] = binding(visual_path)["sha256"]
    write_document(finalization_path, finalization)

    finalized_inventory = document(finalized_inventory_path)
    finalized_inventory["captureInventorySha256"] = capture_inventory_sha
    finalized_inventory["finalization"] = binding(finalization_path)
    finalized_inventory["files"] = [
        binding(str(row["path"]))
        for row in finalized_inventory["files"]
        if isinstance(row, dict)
    ]
    write_document(finalized_inventory_path, finalized_inventory)

    for row in rows:
        assert isinstance(row, dict)
        path = str(row["path"])
        payload = payloads[path]
        row["bytesBase64"] = base64.b64encode(payload).decode("ascii")
        row["sha256"] = hashlib.sha256(payload).hexdigest()
        row["sizeBytes"] = len(payload)


def test_unsigned_native_v4_validator_accepts_exact_final_head_fixture(
    tmp_path: Path,
) -> None:
    (
        materializer,
        root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    ) = rehydrate_unsigned_native_v4_root(tmp_path)
    source_sha = native["candidateContentInventory"]["sourceSha"]
    expected_content_rows = [
        dict(row)
        for row in native["candidateContentInventory"]["files"]
    ]

    validated, oldest = materializer._validate_unsigned_native_evidence(
        root,
        candidate_rows=candidate_rows,
        source_canonical_bytes=canonical,
        source_compatibility_bytes=compatibility,
        expected_content_rows=expected_content_rows,
        scope=scope,
        publication_source_sha=source_sha,
        now=now,
        max_age=timedelta(hours=24),
    )

    assert validated == native
    assert oldest <= now
    assert validated["captureSource"]["sha"] == validated["finalizationSource"]["sha"]
    assert validated["captureSource"]["sha"] != source_sha


def test_unsigned_native_logs_accept_current_startup_ready_marker() -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_current_startup_log_test",
    )
    head = "avalonia"
    rid = materializer.RID
    materializer._validate_unsigned_native_logs(
        {
            f"startup-smoke/startup-smoke-{head}-{rid}.receipt.json": (
                b'{"verificationScope":"native_windows_startup"}\n'
            ),
            f"startup-smoke/startup-smoke-{head}-{rid}.log": (
                b"startup smoke ready: head=avalonia platform=windows "
                b"arch=x64 checkpoint=pre_ui_event_loop\n"
            ),
            f"startup-smoke/startup-smoke-payload-http-{head}-{rid}.log": (
                b'127.0.0.1 - - [27/Jul/2026 07:08:47] '
                b'"GET /chummer-avalonia-win-x64-payload.zip HTTP/1.1" '
                b"200 -\n"
            ),
            f"startup-smoke/windows-installer-progress-{head}-{rid}.log": (
                b"Bootstrap temp root:\n"
                b"Payload download target:\n"
                b"Downloading application files\n"
                b"Verifying payload size\n"
                b"Verifying payload checksum\n"
                b"Extracting application files\n"
                b"Install complete\n"
            ),
        },
        head=head,
    )


def test_unsigned_native_logs_reject_incomplete_current_startup_marker() -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_incomplete_startup_log_test",
    )
    head = "avalonia"
    rid = materializer.RID
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="recognized startup-ready marker",
    ):
        materializer._validate_unsigned_native_logs(
            {
                f"startup-smoke/startup-smoke-{head}-{rid}.receipt.json": (
                    b'{"verificationScope":"native_windows_startup"}\n'
                ),
                f"startup-smoke/startup-smoke-{head}-{rid}.log": (
                    b"startup smoke ready: head=avalonia platform=windows\n"
                ),
                f"startup-smoke/startup-smoke-payload-http-{head}-{rid}.log": (
                    b'127.0.0.1 - - [27/Jul/2026 07:08:47] '
                    b'"GET /chummer-avalonia-win-x64-payload.zip HTTP/1.1" '
                    b"200 -\n"
                ),
                f"startup-smoke/windows-installer-progress-{head}-{rid}.log": (
                    b"Bootstrap temp root:\n"
                    b"Payload download target:\n"
                    b"Downloading application files\n"
                    b"Verifying payload size\n"
                    b"Verifying payload checksum\n"
                    b"Extracting application files\n"
                    b"Install complete\n"
                ),
            },
            head=head,
        )


def test_unsigned_native_logs_reject_failed_payload_download() -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_failed_payload_download_log_test",
    )
    head = "avalonia"
    rid = materializer.RID
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="recognized payload-download success marker",
    ):
        materializer._validate_unsigned_native_logs(
            {
                f"startup-smoke/startup-smoke-{head}-{rid}.receipt.json": (
                    b'{"verificationScope":"native_windows_startup"}\n'
                ),
                f"startup-smoke/startup-smoke-{head}-{rid}.log": (
                    b"startup smoke ready: head=avalonia platform=windows "
                    b"arch=x64 checkpoint=pre_ui_event_loop\n"
                ),
                f"startup-smoke/startup-smoke-payload-http-{head}-{rid}.log": (
                    b'127.0.0.1 - - [27/Jul/2026 07:08:47] '
                    b'"GET /chummer-avalonia-win-x64-payload.zip HTTP/1.1" '
                    b"500 -\n"
                ),
                f"startup-smoke/windows-installer-progress-{head}-{rid}.log": (
                    b"Bootstrap temp root:\n"
                    b"Payload download target:\n"
                    b"Downloading application files\n"
                    b"Verifying payload size\n"
                    b"Verifying payload checksum\n"
                    b"Extracting application files\n"
                    b"Install complete\n"
                ),
            },
            head=head,
        )


def test_unsigned_native_logs_reject_legacy_dialect_for_current_receipt() -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_legacy_log_current_receipt_test",
    )
    head = "avalonia"
    rid = materializer.RID
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="recognized startup-ready marker",
    ):
        materializer._validate_unsigned_native_logs(
            {
                f"startup-smoke/startup-smoke-{head}-{rid}.receipt.json": (
                    b'{"verificationScope":"native_windows_startup"}\n'
                ),
                f"startup-smoke/startup-smoke-{head}-{rid}.log": (
                    b"native startup passed\n"
                ),
                f"startup-smoke/startup-smoke-payload-http-{head}-{rid}.log": (
                    b"candidate payload download passed\n"
                ),
                f"startup-smoke/windows-installer-progress-{head}-{rid}.log": (
                    b"Bootstrap temp root:\n"
                    b"Payload download target:\n"
                    b"Downloading application files\n"
                    b"Verifying payload size\n"
                    b"Verifying payload checksum\n"
                    b"Extracting application files\n"
                    b"Install complete\n"
                ),
            },
            head=head,
        )


def current_unsigned_native_startup_receipt_fixture(
    *,
    process_path: str = "Chummer.Avalonia.exe",
) -> tuple[dict[str, object], dict[str, object], datetime]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    recorded_at = now.isoformat().replace("+00:00", "Z")
    installer_sha = "a" * 64
    payload_sha = "b" * 64
    scope: dict[str, object] = {
        "channel": "preview",
        "version": "run-20260727-065724",
        "artifacts": {
            "avalonia": {
                "installer": {
                    "fileName": "chummer-avalonia-win-x64-installer.exe",
                    "sha256": installer_sha,
                },
                "payload": {
                    "fileName": "chummer-avalonia-win-x64-payload.zip",
                    "sha256": payload_sha,
                    "sizeBytes": 51231899,
                },
            }
        },
    }
    return (
        {
            "status": "pass",
            "headId": "avalonia",
            "version": "run-20260727-065724",
            "releaseVersion": "run-20260727-065724",
            "channelId": "preview",
            "platform": "windows",
            "arch": "x64",
            "rid": "win-x64",
            "readyCheckpoint": "pre_ui_event_loop",
            "hostClass": "github-hosted-windows-latest-native",
            "processPath": process_path,
            "processPathDisclosure": "file_name_only",
            "artifactDigest": f"sha256:{installer_sha}",
            "artifactDigestSource": "environment",
            "installLinkingStatus": "guest",
            "installLinkingPromptRequired": True,
            "installLinkingPromptReason": "claim_required",
            "installLinkingLaunchCount": 1,
            "installLinkingInstallationId": f"ins-{'c' * 32}",
            "framework": ".NET 10.0.3",
            "operatingSystem": "Microsoft Windows 10.0.26100",
            "recordedAtUtc": recorded_at,
            "startedAtUtc": recorded_at,
            "completedAtUtc": recorded_at,
            "executionEnvironment": "native_windows",
            "verificationScope": "native_windows_startup",
            "nativeHostEvidence": {
                "contractName": "chummer6-ui.native_windows_host_evidence",
                "status": "verified",
                "isNativeWindows": True,
                "hostPlatform": "windows",
                "hostKernel": "MINGW64_NT-10.0-26100",
                "runner": "pwsh",
                "evidenceSource": "host_kernel_and_runner_selection",
            },
            "artifactInstallMode": "nsis_bootstrap_installer",
            "artifactPath": (
                "files/chummer-avalonia-win-x64-installer.exe"
            ),
            "bootstrapPayloadAcquisitionMode": "download",
            "bootstrapPayloadDownloadUrl": (
                "http://127.0.0.1:50023/"
                "chummer-avalonia-win-x64-payload.zip"
            ),
            "bootstrapPayloadSha256": payload_sha,
            "bootstrapPayloadSizeBytes": 51231899,
            "bootstrapPayloadFileName": (
                "chummer-avalonia-win-x64-payload.zip"
            ),
            "artifactPathDisclosure": "artifact_shelf_relative_path",
            "artifactFileName": (
                "chummer-avalonia-win-x64-installer.exe"
            ),
            "fileName": "chummer-avalonia-win-x64-installer.exe",
            "artifactRelativePath": (
                "files/chummer-avalonia-win-x64-installer.exe"
            ),
            "artifactSha256": installer_sha,
            "artifactId": "avalonia-win-x64-installer",
        },
        scope,
        now,
    )


def test_unsigned_native_startup_receipt_accepts_current_producer_shape() -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_current_startup_receipt_test",
    )
    startup, scope, now = current_unsigned_native_startup_receipt_fixture()
    materializer._validate_unsigned_native_startup_receipt(
        startup,
        head="avalonia",
        scope=scope,
        expected_installed_executable={"fileName": "Chummer.Avalonia.exe"},
        now=now,
        max_age=timedelta(hours=24),
    )


def test_unsigned_native_startup_receipt_rejects_sealed_process_mismatch() -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_current_startup_process_mismatch_test",
    )
    startup, scope, now = current_unsigned_native_startup_receipt_fixture(
        process_path="Other.exe",
    )
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="current startup receipt drifted",
    ):
        materializer._validate_unsigned_native_startup_receipt(
            startup,
            head="avalonia",
            scope=scope,
            expected_installed_executable={
                "fileName": "Chummer.Avalonia.exe",
            },
            now=now,
            max_age=timedelta(hours=24),
        )


@pytest.mark.parametrize(
    "native_host",
    [
        {
            "contractName": "chummer6-ui.native_windows_host_evidence",
            "status": "verified",
            "isNativeWindows": True,
            "hostPlatform": "windows",
            "runner": "pwsh",
            "evidenceSource": "host_kernel_and_runner_selection",
        },
        {
            "contractName": "chummer6-ui.native_windows_host_evidence",
            "status": "verified",
            "isNativeWindows": True,
            "hostPlatform": "windows",
            "hostKernel": "Linux",
            "runner": "pwsh",
            "evidenceSource": "host_kernel_and_runner_selection",
        },
    ],
)
def test_current_native_host_requires_windows_kernel(
    native_host: dict[str, object],
) -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_native_current_host_kernel_test",
    )
    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="current native host kernel drifted",
    ):
        materializer._validate_native_host(
            native_host,
            label="current native host",
            expected_evidence_sources=frozenset(
                {"host_kernel_and_runner_selection"}
            ),
        )


def test_unsigned_native_v4_embedded_custody_reuses_exact_tree_validator(
    tmp_path: Path,
) -> None:
    (
        materializer,
        _root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    ) = rehydrate_unsigned_native_v4_root(tmp_path)
    source_sha = native["candidateContentInventory"]["sourceSha"]
    expected_content_rows = [
        dict(row)
        for row in native["candidateContentInventory"]["files"]
    ]

    validated, oldest = (
        materializer._validate_embedded_unsigned_native_evidence(
            native,
            candidate_rows=candidate_rows,
            source_canonical_bytes=canonical,
            source_compatibility_bytes=compatibility,
            expected_content_rows=expected_content_rows,
            scope=scope,
            publication_source_sha=source_sha,
            now=now,
            max_age=timedelta(hours=24),
        )
    )

    assert validated == native
    assert oldest <= now


def test_projection_accepts_exact_owner_native_v4_bridge_custody() -> None:
    projection = load_script(
        PROJECTION, "owner_native_v4_authority_projection_test"
    )
    authority = load_unsigned_v4_authority_fixture()

    validated = projection._validate_candidate_import_authority_v4(
        authority,
        now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
    )

    assert validated["contractName"] == (
        "chummer.release-upload.candidate-import-authority/v4"
    )
    assert validated["ownerNativeFinalizationBridgeAuthority"] is True
    assert validated["deployAuthority"] is False
    assert validated["routeAuthority"] is False
    assert validated["publicationAuthorized"] is False


def test_projection_accepts_current_v4_startup_with_sealed_executable() -> None:
    projection = load_script(
        PROJECTION, "owner_native_current_v4_authority_projection_test"
    )
    authority = load_unsigned_v4_authority_fixture()
    upgrade_embedded_v4_authority_to_current_startup(authority)

    validated = projection._validate_candidate_import_authority_v4(
        authority,
        now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
    )

    assert validated["candidate"]["version"] == "run-20260722-150000"
    assert validated["ownerNativeFinalizationBridgeAuthority"] is True


def test_projection_rejects_coherently_rehashed_non_chummer_executable() -> None:
    projection = load_script(
        PROJECTION, "owner_native_v4_executable_name_rebind_test"
    )
    authority = load_unsigned_v4_authority_fixture()
    rebound = {
        "fileName": "Other.exe",
        "payloadEntry": "Other.exe",
        "sha256": "e" * 64,
        "sizeBytes": 4096,
    }
    upgrade_embedded_v4_authority_to_current_startup(
        authority,
        process_path="Other.exe",
        capture_executable=rebound,
        receipt_executable=rebound,
    )

    with pytest.raises(
        projection.ProjectionBlocked,
        match="finalized evidence validation failed",
    ) as exc_info:
        projection._validate_candidate_import_authority_v4(
            authority,
            now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
        )

    assert "capture manifest executable identity drifted" in str(
        exc_info.value.__cause__
    )


def test_projection_rejects_installed_executable_custody_copy_mismatch() -> None:
    projection = load_script(
        PROJECTION, "owner_native_v4_executable_copy_mismatch_test"
    )
    authority = load_unsigned_v4_authority_fixture()
    rebound_receipt = {
        "fileName": "Chummer.Avalonia.exe",
        "payloadEntry": "Chummer.Avalonia.exe",
        "sha256": "e" * 64,
        "sizeBytes": 4096,
    }
    upgrade_embedded_v4_authority_to_current_startup(
        authority,
        receipt_executable=rebound_receipt,
    )

    with pytest.raises(
        projection.ProjectionBlocked,
        match="finalized evidence validation failed",
    ) as exc_info:
        projection._validate_candidate_import_authority_v4(
            authority,
            now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
        )

    assert "custody copies differ" in str(exc_info.value.__cause__)


def test_projection_rejects_current_v4_process_path_mismatch() -> None:
    projection = load_script(
        PROJECTION, "owner_native_current_v4_process_mismatch_test"
    )
    authority = load_unsigned_v4_authority_fixture()
    upgrade_embedded_v4_authority_to_current_startup(
        authority,
        process_path="Other.exe",
    )

    with pytest.raises(
        projection.ProjectionBlocked,
        match="finalized evidence validation failed",
    ) as exc_info:
        projection._validate_candidate_import_authority_v4(
            authority,
            now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
        )

    assert "current startup receipt drifted" in str(exc_info.value.__cause__)


def test_projection_rejects_v4_executable_rebound_from_exact_payload_zip() -> None:
    projection = load_script(
        PROJECTION, "owner_native_v4_exact_payload_executable_test"
    )
    authority = load_unsigned_v4_authority_fixture()

    with pytest.raises(
        projection.ProjectionBlocked,
        match="exact candidate payload ZIP",
    ):
        projection._validate_candidate_import_authority_v4(
            authority,
            expected_installed_executable={
                "fileName": "Chummer.Avalonia.exe",
                "payloadEntry": "Chummer.Avalonia.exe",
                "sha256": "e" * 64,
                "sizeBytes": 4096,
            },
            now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
        )


def test_projection_rejects_v4_bridge_posture_broadened_to_route_authority() -> None:
    projection = load_script(
        PROJECTION, "owner_native_v4_route_drift_projection_test"
    )
    authority = load_unsigned_v4_authority_fixture()
    authority["routeAuthority"] = True

    with pytest.raises(
        projection.ProjectionBlocked,
        match="candidate import authority contract drifted",
    ):
        projection._validate_candidate_import_authority_v4(
            authority,
            now=datetime(2026, 7, 26, 23, 5, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    (
        "native_bridge",
        "generation_bridge",
        "contract_name",
        "contract_version",
    ),
    [
        (
            False,
            False,
            "chummer.release-upload.candidate-import-authority/v3",
            3,
        ),
        (
            True,
            False,
            "chummer.release-upload.candidate-import-authority/v4",
            4,
        ),
        (
            True,
            True,
            "chummer.release-upload.candidate-import-authority/v5",
            5,
        ),
    ],
)
def test_unsigned_authority_shape_preserves_v3_and_adds_bounded_bridges(
    native_bridge: bool,
    generation_bridge: bool,
    contract_name: str,
    contract_version: int,
) -> None:
    materializer = load_script(
        MATERIALIZER,
        f"unsigned_authority_shape_{contract_version}_test",
    )
    custody: dict[str, object] = {"unsignedPublicationEvidence": {"status": "passed"}}
    if native_bridge:
        custody["nativeWindowsFinalizedEvidence"] = {"status": "passed"}
    if generation_bridge:
        custody["generationProjection"] = {"status": "passed"}
    now = datetime(2026, 7, 26, 22, 0, tzinfo=timezone.utc)

    authority = materializer._build_candidate_authority(
        unsigned_preview=True,
        unsigned_native_bridge=native_bridge,
        unsigned_native_generation_bridge=generation_bridge,
        now=now,
        expires_at=now + timedelta(hours=2),
        candidate={"version": "run-test"},
        custody=custody,
    )

    assert authority["contractName"] == contract_name
    assert authority["contractVersion"] == contract_version
    assert (
        authority.get("ownerNativeFinalizationBridgeAuthority")
        is True
        if native_bridge
        else "ownerNativeFinalizationBridgeAuthority" not in authority
    )
    assert (
        "nativeWindowsFinalizedEvidence" in authority["custody"]
    ) is native_bridge
    assert (
        authority.get("ownerNativeStageAuthoritySeedBridgeAuthority")
        is True
        if generation_bridge
        else "ownerNativeStageAuthoritySeedBridgeAuthority" not in authority
    )
    assert ("generationProjection" in authority["custody"]) is generation_bridge


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_file",
        "extra_file",
        "embedded_bytes",
        "candidate_windows",
        "source_manifest",
        "publication_source",
        "capture_final_source",
    ],
)
def test_unsigned_native_v4_validator_rejects_partial_or_mismatched_root(
    tmp_path: Path,
    tamper: str,
) -> None:
    (
        materializer,
        root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    ) = rehydrate_unsigned_native_v4_root(tmp_path)
    source_sha = native["candidateContentInventory"]["sourceSha"]
    expected_content_rows = [
        dict(row)
        for row in native["candidateContentInventory"]["files"]
    ]
    if tamper == "missing_file":
        (root / "startup-smoke/startup-smoke-avalonia-win-x64.log").unlink()
    elif tamper == "extra_file":
        (root / "smuggled.txt").write_bytes(b"smuggled")
    elif tamper == "embedded_bytes":
        outer_path = root / materializer.UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE
        outer = json.loads(outer_path.read_text())
        outer["files"][0]["bytesBase64"] = base64.b64encode(b"changed").decode()
        outer_path.write_text(json.dumps(outer) + "\n")
    elif tamper == "candidate_windows":
        candidate_rows = [
            {
                **row,
                "sha256": "0" * 64,
            }
            if row["path"].endswith("-installer.exe")
            else row
            for row in candidate_rows
        ]
    elif tamper == "source_manifest":
        canonical = b'{"tampered":true}\n'
    elif tamper == "publication_source":
        source_sha = "0" * 40
    elif tamper == "capture_final_source":
        outer_path = root / materializer.UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE
        outer = json.loads(outer_path.read_text())
        outer["finalizationSource"]["sha"] = "0" * 40
        outer_path.write_text(
            json.dumps(outer, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        raise AssertionError(tamper)

    with pytest.raises(materializer.CandidateAuthorityBlocked):
        materializer._validate_unsigned_native_evidence(
            root,
            candidate_rows=candidate_rows,
            source_canonical_bytes=canonical,
            source_compatibility_bytes=compatibility,
            expected_content_rows=expected_content_rows,
            scope=scope,
            publication_source_sha=source_sha,
            now=now,
            max_age=timedelta(hours=24),
        )


def test_unsigned_native_v4_rejects_rehashed_unbound_composition_custody(
    tmp_path: Path,
) -> None:
    (
        materializer,
        root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    ) = rehydrate_unsigned_native_v4_root(tmp_path)
    expected_content_rows = [
        dict(row)
        for row in native["candidateContentInventory"]["files"]
    ]
    outer_path = root / materializer.UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE
    outer = json.loads(outer_path.read_text())
    content_path = materializer.UNSIGNED_CANDIDATE_PROVENANCE_INVENTORY
    content = json.loads((root / content_path).read_text())
    composition = next(
        row
        for row in content["files"]
        if row["path"] == materializer.UNSIGNED_COMPOSITION_FILE
    )
    composition["sha256"] = "a" * 64
    composition["sizeBytes"] = 1
    content_payload = rewrite_unsigned_native_embedded_document(
        root,
        outer,
        content_path,
        content,
    )
    outer["candidateContentInventory"] = content
    outer["candidateContentInventorySha256"] = hashlib.sha256(
        content_payload
    ).hexdigest()

    export_path = materializer.UNSIGNED_CANDIDATE_PROVENANCE_EXPORT
    export = json.loads((root / export_path).read_text())
    export["exportedContent"] = content["files"]
    export["compositionRequest"] = composition
    export["inventory"]["sha256"] = hashlib.sha256(content_payload).hexdigest()
    export["inventory"]["sizeBytes"] = len(content_payload)
    rewrite_unsigned_native_embedded_document(
        root,
        outer,
        export_path,
        export,
    )
    outer_path.write_text(
        json.dumps(outer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="exact v3 and candidate custody",
    ):
        materializer._validate_unsigned_native_evidence(
            root,
            candidate_rows=candidate_rows,
            source_canonical_bytes=canonical,
            source_compatibility_bytes=compatibility,
            expected_content_rows=expected_content_rows,
            scope=scope,
            publication_source_sha=native["candidateContentInventory"]["sourceSha"],
            now=now,
            max_age=timedelta(hours=24),
        )


def test_unsigned_native_v4_rejects_unbound_accountable_finalization_leaf(
    tmp_path: Path,
) -> None:
    (
        materializer,
        root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    ) = rehydrate_unsigned_native_v4_root(tmp_path)
    expected_content_rows = [
        dict(row)
        for row in native["candidateContentInventory"]["files"]
    ]
    outer_path = root / materializer.UNSIGNED_NATIVE_FINALIZED_EVIDENCE_FILE
    outer = json.loads(outer_path.read_text())
    finalization_path = materializer.UNSIGNED_NATIVE_FINALIZATION_FILE
    finalization = json.loads((root / finalization_path).read_text())
    finalization["accountableReviewConfirmed"] = False
    rewrite_unsigned_native_embedded_document(
        root,
        outer,
        finalization_path,
        finalization,
    )
    outer_path.write_text(
        json.dumps(outer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="finalized inventory differs",
    ):
        materializer._validate_unsigned_native_evidence(
            root,
            candidate_rows=candidate_rows,
            source_canonical_bytes=canonical,
            source_compatibility_bytes=compatibility,
            expected_content_rows=expected_content_rows,
            scope=scope,
            publication_source_sha=native["candidateContentInventory"]["sourceSha"],
            now=now,
            max_age=timedelta(hours=24),
        )


def test_unsigned_payload_executable_is_derived_from_exact_nofollow_zip(
    tmp_path: Path,
) -> None:
    materializer = load_script(
        MATERIALIZER,
        "unsigned_payload_executable_derivation_test",
    )
    bundle = tmp_path / "bundle"
    payload_path = "files/chummer-avalonia-win-x64-payload.zip"
    payload = bundle / payload_path
    payload.parent.mkdir(parents=True)
    executable = b"MZ-tiny-valid-executable"
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Chummer.Avalonia.exe", executable)
    payload_bytes = payload.read_bytes()

    binding = materializer._derive_unsigned_payload_executable(
        bundle,
        payload_path=payload_path,
        payload_row={
            "path": payload_path,
            "sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "sizeBytes": len(payload_bytes),
        },
    )

    assert binding == {
        "fileName": "Chummer.Avalonia.exe",
        "payloadEntry": "Chummer.Avalonia.exe",
        "sha256": hashlib.sha256(executable).hexdigest(),
        "sizeBytes": len(executable),
    }


def test_unsigned_native_v4_rejects_installed_executable_rebound_from_payload(
    tmp_path: Path,
) -> None:
    (
        materializer,
        root,
        native,
        candidate_rows,
        canonical,
        compatibility,
        scope,
        now,
    ) = rehydrate_unsigned_native_v4_root(tmp_path)
    expected_content_rows = [
        dict(row)
        for row in native["candidateContentInventory"]["files"]
    ]

    with pytest.raises(
        materializer.CandidateAuthorityBlocked,
        match="exact candidate payload ZIP",
    ):
        materializer._validate_unsigned_native_evidence(
            root,
            candidate_rows=candidate_rows,
            source_canonical_bytes=canonical,
            source_compatibility_bytes=compatibility,
            expected_content_rows=expected_content_rows,
            expected_installed_executable={
                "fileName": "Chummer.Avalonia.exe",
                "payloadEntry": "Chummer.Avalonia.exe",
                "sha256": hashlib.sha256(b"different executable").hexdigest(),
                "sizeBytes": len(b"different executable"),
            },
            scope=scope,
            publication_source_sha=native["candidateContentInventory"]["sourceSha"],
            now=now,
            max_age=timedelta(hours=24),
        )


def load_unsigned_fresh_delta_manifest_pair() -> dict[str, dict[str, object]]:
    encoded = "".join(
        UNSIGNED_FRESH_DELTA_MANIFEST_PAIR_FIXTURE.read_text().splitlines()
    )
    pair = json.loads(gzip.decompress(base64.b64decode(encoded)))
    assert isinstance(pair, dict)
    assert isinstance(pair.get("canonical"), dict)
    assert isinstance(pair.get("compatibility"), dict)
    return pair


def load_unsigned_fresh_delta_authority() -> dict[str, object]:
    encoded = "".join(
        UNSIGNED_FRESH_DELTA_AUTHORITY_FIXTURE.read_text().splitlines()
    )
    authority = json.loads(gzip.decompress(base64.b64decode(encoded)))
    assert isinstance(authority, dict)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    authority["generatedAtUtc"] = now.isoformat().replace("+00:00", "Z")
    authority["expiresAtUtc"] = (now + timedelta(hours=2)).isoformat().replace(
        "+00:00", "Z"
    )
    return authority


def test_projection_accepts_registry_pinned_unsigned_fresh_delta_authority() -> None:
    projection = load_script(
        PROJECTION, "unsigned_fresh_delta_full_authority_projection_test"
    )
    authority = load_unsigned_fresh_delta_authority()

    validated = projection._validate_candidate_import_authority_v3(authority)

    assert validated["candidate"]["version"] == "run-20260722-165800"
    assert (
        validated["custody"]["unsignedPublicationEvidence"]["projectionProfile"]
        == "v3_unsigned_windows_fresh_delta"
    )
    assert len(
        validated["custody"]["unsignedPublicationEvidence"]["files"]
    ) == 9


def unsigned_fresh_delta_manifest_validator(layer: str):
    if layer == "materializer":
        module = load_script(
            MATERIALIZER, "unsigned_fresh_delta_manifest_materializer_test"
        )
        return (
            module._validate_unsigned_profile_manifest_pair,
            module.CandidateAuthorityBlocked,
        )
    module = load_script(
        PROJECTION, "unsigned_fresh_delta_manifest_projection_test"
    )
    return (
        module._candidate_validate_unsigned_profile_manifest_pair,
        module.ProjectionBlocked,
    )


def unsigned_retained_provenance_validator(layer: str):
    if layer == "materializer":
        module = load_script(
            MATERIALIZER,
            "unsigned_retained_provenance_materializer_test",
        )
        return (
            module._validate_profile_retained_provenance,
            module.CandidateAuthorityBlocked,
        )
    module = load_script(
        PROJECTION,
        "unsigned_retained_provenance_projection_test",
    )
    return (
        module._candidate_validate_profile_retained_provenance,
        module.ProjectionBlocked,
    )


def bind_retained_artifacts(
    provenance: dict[str, object],
    artifacts: list[dict[str, object]],
) -> None:
    bindings = [
        {
            "artifactId": artifact.get("artifactId") or artifact.get("id"),
            "manifestRowSha256": canonical_sha256(artifact),
            "sha256": artifact["sha256"],
            "sizeBytes": artifact["sizeBytes"],
        }
        for artifact in artifacts
    ]
    provenance["retainedArtifactBindings"] = bindings
    provenance["retainedArtifactBindingsSha256"] = canonical_sha256(bindings)


def windows_only_unsigned_fresh_delta_manifest_pair() -> (
    dict[str, dict[str, object]]
):
    pair = load_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    canonical["artifacts"] = [
        artifact
        for artifact in canonical["artifacts"]
        if artifact.get("platform") == "windows"
    ]
    compatibility["downloads"] = [
        artifact
        for artifact in compatibility["downloads"]
        if artifact.get("platform") == "windows"
    ]
    for manifest in (canonical, compatibility):
        provenance = manifest["retainedIncumbentProvenance"]
        provenance["retainedArtifactBindings"] = []
        provenance["retainedArtifactBindingsSha256"] = canonical_sha256([])
        provenance["retainedCompatibilityBindings"] = []
        provenance["retainedCompatibilityBindingsSha256"] = canonical_sha256([])
    coverage = canonical["desktopTupleCoverage"]
    coverage["requiredDesktopPlatforms"] = ["windows"]
    coverage["requiredDesktopPlatformHeadRidTuples"] = [
        "avalonia:win-x64:windows"
    ]
    coverage["missingRequiredHeads"] = ["avalonia"]
    coverage["promotedInstallerTuples"] = []
    coverage["promotedPlatformHeadRidTuples"] = []
    coverage["promotedPlatformHeads"] = {"windows": []}
    coverage["desktopRouteTruth"] = [
        row
        for row in coverage["desktopRouteTruth"]
        if row.get("platform") == "windows"
    ]
    artifact = canonical["artifacts"][0]
    inventory = [
        {
            "arch": artifact["arch"],
            "artifactId": artifact["artifactId"],
            "fileName": artifact["fileName"],
            "head": artifact["head"],
            "kind": artifact["kind"],
            "payloadFileName": artifact["payloadFileName"],
            "payloadSha256": artifact["payloadSha256"],
            "payloadSizeBytes": artifact["payloadSizeBytes"],
            "platform": artifact["platform"],
            "rid": artifact["rid"],
            "sha256": artifact["sha256"],
            "sizeBytes": artifact["sizeBytes"],
        }
    ]
    for manifest in (canonical, compatibility):
        review = manifest["codeDeployCurrentShelfAuthority"]
        review["projectedArtifactCount"] = 1
        review["projectedArtifactInventorySha256"] = canonical_sha256(inventory)
    return pair


def linux_retained_unsigned_fresh_delta_manifest_pair() -> (
    dict[str, dict[str, object]]
):
    pair = load_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    windows = next(
        artifact
        for artifact in canonical["artifacts"]
        if artifact.get("platform") == "windows"
    )
    compatibility_windows = next(
        artifact
        for artifact in compatibility["downloads"]
        if artifact.get("platform") == "windows"
    )
    linux = {
        "arch": "x64",
        "artifactId": "avalonia-linux-x64-installer",
        "downloadUrl": (
            "/downloads/g/gen-linux-fixture/files/"
            "chummer-avalonia-linux-x64-installer.deb"
        ),
        "fileName": "chummer-avalonia-linux-x64-installer.deb",
        "head": "avalonia",
        "id": "avalonia-linux-x64-installer",
        "kind": "installer",
        "platform": "linux",
        "rid": "linux-x64",
        "sha256": "1" * 64,
        "sizeBytes": 37192294,
    }
    compatibility_linux = {
        "artifactId": linux["artifactId"],
        "fileName": linux["fileName"],
        "head": "avalonia",
        "id": linux["artifactId"],
        "kind": "installer",
        "platform": "Avalonia Desktop Linux X64 Installer",
        "platformId": "linux",
        "rid": "linux-x64",
        "sha256": linux["sha256"],
        "sizeBytes": linux["sizeBytes"],
        "url": linux["downloadUrl"],
    }
    canonical["artifacts"] = [linux, windows]
    compatibility["downloads"] = [compatibility_linux, compatibility_windows]

    windows_routes = [
        row
        for row in canonical["desktopTupleCoverage"]["desktopRouteTruth"]
        if row.get("platform") == "windows"
    ]
    coverage = canonical["desktopTupleCoverage"]
    coverage.update(
        {
            "desktopRouteTruth": [
                {
                    "artifactId": linux["artifactId"],
                    "platform": "linux",
                    "promotionState": "promoted",
                    "publicInstallRoute": (
                        "/downloads/install/avalonia-linux-x64-installer"
                    ),
                    "routeAuthority": False,
                    "tupleId": "avalonia:linux:linux-x64",
                },
                {
                    "artifactId": "",
                    "platform": "linux",
                    "promotionState": "proof_required",
                    "publicInstallRoute": (
                        "/downloads/install/blazor-desktop-linux-x64-installer"
                    ),
                    "routeAuthority": False,
                    "tupleId": "blazor-desktop:linux:linux-x64",
                },
                *windows_routes,
            ],
            "missingRequiredHeads": [],
            "promotedInstallerTuples": [{"artifactId": linux["artifactId"]}],
            "promotedPlatformHeadRidTuples": ["avalonia:linux-x64:linux"],
            "promotedPlatformHeads": {"linux": ["avalonia"], "windows": []},
            "requiredDesktopPlatformHeadRidTuples": [
                "avalonia:linux-x64:linux",
                "avalonia:win-x64:windows",
            ],
            "requiredDesktopPlatforms": ["linux", "windows"],
        }
    )
    compatibility["desktopTupleCoverage"] = json.loads(json.dumps(coverage))

    retained_binding = {
        "artifactId": linux["artifactId"],
        "manifestRowSha256": canonical_sha256(linux),
        "sha256": linux["sha256"],
        "sizeBytes": linux["sizeBytes"],
    }
    compatibility_binding = {
        "artifactId": linux["artifactId"],
        "manifestRowSha256": canonical_sha256(compatibility_linux),
        "sha256": linux["sha256"],
        "sizeBytes": linux["sizeBytes"],
    }
    inventory = []
    for artifact in canonical["artifacts"]:
        row = {
            field: artifact[field]
            for field in (
                "artifactId",
                "head",
                "platform",
                "rid",
                "arch",
                "kind",
                "fileName",
                "sha256",
                "sizeBytes",
            )
        }
        if artifact.get("payloadFileName") is not None:
            row.update(
                {
                    field: artifact[field]
                    for field in (
                        "payloadFileName",
                        "payloadSha256",
                        "payloadSizeBytes",
                    )
                }
            )
        inventory.append(row)
    for manifest in (canonical, compatibility):
        provenance = manifest["retainedIncumbentProvenance"]
        provenance["retainedArtifactBindings"] = [retained_binding]
        provenance["retainedArtifactBindingsSha256"] = canonical_sha256(
            [retained_binding]
        )
        provenance["retainedCompatibilityBindings"] = [compatibility_binding]
        provenance["retainedCompatibilityBindingsSha256"] = canonical_sha256(
            [compatibility_binding]
        )
        review = manifest["codeDeployCurrentShelfAuthority"]
        review["projectedArtifactCount"] = len(inventory)
        review["projectedArtifactInventorySha256"] = canonical_sha256(inventory)
    return pair


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_fresh_delta_manifest_pair_accepts_registry_pushed_commit(
    layer: str,
) -> None:
    pair = load_unsigned_fresh_delta_manifest_pair()
    validate, _error = unsigned_fresh_delta_manifest_validator(layer)

    result = validate(pair["canonical"], pair["compatibility"])

    assert (
        result["registryCommit"]
        == "25ff1437a1f1bb6b04c823fa3cb47c0976d0e141"
    )
    assert result["retainedArtifactIds"] == [
        "avalonia-linux-x64-installer",
    ]


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_fresh_delta_manifest_pair_accepts_exact_retained_linux_profile(
    layer: str,
) -> None:
    pair = linux_retained_unsigned_fresh_delta_manifest_pair()
    validate, _error = unsigned_fresh_delta_manifest_validator(layer)

    result = validate(pair["canonical"], pair["compatibility"])

    assert result["retainedArtifactIds"] == [
        "avalonia-linux-x64-installer"
    ]


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_retained_linux_profile_rejects_platform_aliasing(
    layer: str,
) -> None:
    pair = linux_retained_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    retained = canonical["artifacts"][0]
    retained["platform"] = "macos"
    provenance = canonical["retainedIncumbentProvenance"]
    bind_retained_artifacts(provenance, [retained])
    validate, error = unsigned_retained_provenance_validator(layer)

    with pytest.raises(
        error,
        match="platform differs from its exact profile",
    ):
        validate(
            canonical,
            compatibility,
            provenance,
            review=canonical["codeDeployCurrentShelfAuthority"],
        )


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_fresh_delta_manifest_pair_accepts_exact_windows_only_mode(
    layer: str,
) -> None:
    pair = windows_only_unsigned_fresh_delta_manifest_pair()
    validate, _error = unsigned_fresh_delta_manifest_validator(layer)

    result = validate(pair["canonical"], pair["compatibility"])

    assert result["retainedArtifactIds"] == []


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_retained_provenance_accepts_exact_windows_only_empty_sets(
    layer: str,
) -> None:
    pair = load_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    canonical["artifacts"] = [
        artifact
        for artifact in canonical["artifacts"]
        if artifact.get("platform") == "windows"
    ]
    compatibility["downloads"] = [
        artifact
        for artifact in compatibility["downloads"]
        if artifact.get("platform") == "windows"
    ]
    for manifest in (canonical, compatibility):
        provenance = manifest["retainedIncumbentProvenance"]
        provenance["retainedArtifactBindings"] = []
        provenance["retainedArtifactBindingsSha256"] = canonical_sha256([])
        provenance["retainedCompatibilityBindings"] = []
        provenance["retainedCompatibilityBindingsSha256"] = canonical_sha256([])
    validate, _error = unsigned_retained_provenance_validator(layer)

    _provenance, retained_ids = validate(
        canonical,
        compatibility,
        canonical["retainedIncumbentProvenance"],
        review=canonical["codeDeployCurrentShelfAuthority"],
    )

    assert retained_ids == []


@pytest.mark.parametrize("layer", ["materializer", "projection"])
@pytest.mark.parametrize("drift", ["missing", "duplicate", "other"])
def test_unsigned_retained_provenance_rejects_artifact_binding_identity_drift(
    layer: str,
    drift: str,
) -> None:
    pair = load_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    provenance = canonical["retainedIncumbentProvenance"]
    bindings = provenance["retainedArtifactBindings"]
    if drift == "missing":
        bindings.pop()
    elif drift == "duplicate":
        bindings.append(json.loads(json.dumps(bindings[0])))
    elif drift == "other":
        bindings[0]["artifactId"] = "other-linux-x64-installer"
    else:
        raise AssertionError(f"unknown drift: {drift}")
    provenance["retainedArtifactBindingsSha256"] = canonical_sha256(bindings)
    validate, error = unsigned_retained_provenance_validator(layer)

    with pytest.raises(
        error,
        match="retained artifact binding",
    ):
        validate(
            canonical,
            compatibility,
            provenance,
            review=canonical["codeDeployCurrentShelfAuthority"],
        )


@pytest.mark.parametrize("layer", ["materializer", "projection"])
@pytest.mark.parametrize("drift", ["missing", "duplicate", "other"])
def test_unsigned_retained_provenance_rejects_compatibility_binding_drift(
    layer: str,
    drift: str,
) -> None:
    pair = load_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    provenance = canonical["retainedIncumbentProvenance"]
    bindings = provenance["retainedCompatibilityBindings"]
    if drift == "missing":
        bindings.pop()
    elif drift == "duplicate":
        bindings.append(json.loads(json.dumps(bindings[0])))
    elif drift == "other":
        bindings[0]["artifactId"] = "other-linux-x64-installer"
    else:
        raise AssertionError(f"unknown drift: {drift}")
    provenance["retainedCompatibilityBindingsSha256"] = canonical_sha256(
        bindings
    )
    validate, error = unsigned_retained_provenance_validator(layer)

    with pytest.raises(error, match="retained compatibility binding"):
        validate(
            canonical,
            compatibility,
            provenance,
            review=canonical["codeDeployCurrentShelfAuthority"],
        )


@pytest.mark.parametrize("layer", ["materializer", "projection"])
@pytest.mark.parametrize(
    ("tamper", "expected_failure"),
    [
        ("boolean_code_deploy_review", "code-deploy review posture drifted"),
        ("retained_compatibility_byte", "retained compatibility binding"),
        ("recursive_authority_true", "must be exactly false"),
        ("windows_public_identity", "Windows public-byte posture drifted"),
        (
            "extra_compatibility_artifact",
            "canonical/compatibility artifact identities drifted",
        ),
    ],
)
def test_unsigned_fresh_delta_manifest_pair_rejects_rehashed_policy_drift(
    layer: str,
    tamper: str,
    expected_failure: str,
) -> None:
    pair = load_unsigned_fresh_delta_manifest_pair()
    canonical = pair["canonical"]
    compatibility = pair["compatibility"]
    if tamper == "boolean_code_deploy_review":
        canonical["codeDeployCurrentShelfAuthority"] = False
    elif tamper == "retained_compatibility_byte":
        retained = next(
            row
            for row in compatibility["downloads"]
            if (row.get("artifactId") or row.get("id"))
            == "avalonia-linux-x64-installer"
        )
        retained["sha256"] = "f" * 64
    elif tamper == "recursive_authority_true":
        canonical["smuggledPolicy"] = {"uploadAuthorized": True}
    elif tamper == "windows_public_identity":
        windows = next(
            row
            for row in canonical["artifacts"]
            if row.get("artifactId") == "avalonia-win-x64-installer"
        )
        windows["artifactByteVisibility"] = "account_required"
    elif tamper == "extra_compatibility_artifact":
        extra = json.loads(json.dumps(compatibility["downloads"][0]))
        extra["artifactId"] = None
        extra["id"] = "smuggled-osx-arm64-installer"
        extra["fileName"] = "smuggled-osx-arm64-installer.dmg"
        compatibility["downloads"].append(extra)
    else:
        raise AssertionError(f"unknown tamper: {tamper}")

    validate, error = unsigned_fresh_delta_manifest_validator(layer)
    with pytest.raises(error, match=expected_failure):
        validate(canonical, compatibility)


def unsigned_provenance_documents() -> tuple[dict[str, bytes], str, str]:
    authority = load_unsigned_v3_authority_fixture()
    evidence = authority["custody"]["unsignedPublicationEvidence"]
    documents = {
        entry["path"]: base64.b64decode(entry["base64"])
        for entry in evidence["files"]
    }
    lock_path = "provenance/config/package-plane.lock.json"
    receipt_path = "provenance/UI_FRESH_PACKAGE_PLANE.generated.json"
    retained_path = "provenance/retained-windows-publish-closure/manifest.json"
    target_path = "/tmp/chummer-preview/retained-windows-bundle"
    lock_binding = {
        "path": "config/package-plane.lock.json",
        "sha256": hashlib.sha256(documents[lock_path]).hexdigest(),
        "sizeBytes": len(documents[lock_path]),
    }
    retained = json.loads(documents[retained_path])
    retained["packagePlaneLock"] = lock_binding
    retained["targetPath"] = target_path
    retained_raw = (
        json.dumps(retained, indent=2, sort_keys=True) + "\n"
    ).encode()
    documents[retained_path] = retained_raw
    receipt = json.loads(documents[receipt_path])
    receipt["consumerPackagePlaneLock"] = lock_binding
    pointer = receipt["retainedWindowsBundle"]
    pointer["bundleInventoryCount"] = UNSIGNED_BUNDLE_INVENTORY_COUNT
    pointer["bundleInventorySha256"] = UNSIGNED_BUNDLE_INVENTORY_SHA256
    pointer["targetPath"] = target_path
    pointer["manifest"] = {
        "path": f"{target_path}/manifest.json",
        "sha256": hashlib.sha256(retained_raw).hexdigest(),
        "sizeBytes": len(retained_raw),
    }
    documents[receipt_path] = (
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    ).encode()
    return documents, evidence["sourceSha"], authority["candidate"]["version"]


def validate_unsigned_provenance(layer: str, documents: dict[str, bytes]) -> None:
    _, source_sha, version = unsigned_provenance_documents()
    if layer == "materializer":
        materializer = load_script(MATERIALIZER, "unsigned_binding_materializer_test")
        materializer._validate_unsigned_provenance_documents(
            list(documents.items()),
            source_sha=source_sha,
            release_version=version,
        )
        return
    projection = load_projection()
    projection._candidate_unsigned_provenance(
        documents,
        source_sha=source_sha,
        version=version,
    )


def decode_unsigned_custody_entry(entry: dict[str, object]) -> dict[str, object]:
    return json.loads(base64.b64decode(entry["base64"]))


def rewrite_unsigned_custody_entry(
    entry: dict[str, object], document: dict[str, object]
) -> None:
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    entry["base64"] = base64.b64encode(payload).decode()
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    entry["sizeBytes"] = len(payload)


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


def parse_candidate_scope(
    layer: str,
    canonical: dict[str, object],
    rows: list[dict[str, object]],
    candidate: dict[str, object],
    *,
    allow_retained_cross_platform: bool,
) -> dict[str, object]:
    if layer == "materializer":
        module = load_script(MATERIALIZER, "cross_platform_shelf_materializer_test")
        return module._canonical_windows_scope(
            canonical,
            rows,
            allow_ancillary_files=allow_retained_cross_platform,
            expected_channel="preview" if allow_retained_cross_platform else None,
        )
    module = load_projection()
    return module._candidate_windows_scope(
        canonical,
        rows,
        candidate,
        allow_ancillary_files=allow_retained_cross_platform,
        expected_channel="preview" if allow_retained_cross_platform else None,
    )


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_scope_accepts_real_retained_macos_shelf_and_exact_windows_delta(
    layer: str,
) -> None:
    canonical, rows, candidate = real_unsigned_cross_platform_shelf()

    scope = parse_candidate_scope(
        layer,
        canonical,
        rows,
        candidate,
        allow_retained_cross_platform=True,
    )

    assert scope["heads"] == ("avalonia",)
    assert set(scope["artifacts"]) == {"avalonia"}
    assert set(scope["artifacts"]["avalonia"]) == {"installer", "payload"}
    assert scope["artifacts"]["avalonia"]["installer"]["path"] == (
        "files/chummer-avalonia-win-x64-installer.exe"
    )
    assert scope["artifacts"]["avalonia"]["payload"]["path"] == (
        "files/chummer-avalonia-win-x64-payload.zip"
    )
    inventory_by_path = {row["path"]: row for row in rows}
    for artifact in canonical["artifacts"]:
        path = f"files/{artifact['fileName']}"
        assert inventory_by_path[path] == {
            "path": path,
            "sha256": artifact["sha256"],
            "sizeBytes": artifact["sizeBytes"],
        }


@pytest.mark.parametrize("layer", ["materializer", "projection"])
@pytest.mark.parametrize(
    ("drift", "expected"),
    [
        ("extra_windows_head", "outside requiredDesktopHeads"),
        ("retained_head", "invalid desktop artifact head"),
        ("retained_unknown_head", "unknown retained desktop head"),
        ("retained_platform", "outside the exact finalized desktop shelf scope"),
        ("retained_rid", "outside the exact finalized desktop shelf scope"),
        ("retained_linux_rid", "outside the exact finalized desktop shelf scope"),
        ("retained_kind", "outside the exact finalized desktop shelf scope"),
        ("retained_linux_kind", "outside the exact finalized desktop shelf scope"),
        ("retained_bytes", "upload inventory"),
        ("windows_archive", "outside the exact finalized desktop shelf scope"),
    ],
)
def test_unsigned_scope_rejects_invalid_retained_shelf_or_windows_widening(
    layer: str,
    drift: str,
    expected: str,
) -> None:
    canonical, rows, candidate = real_unsigned_cross_platform_shelf()
    artifacts = canonical["artifacts"]
    retained = next(
        artifact
        for artifact in artifacts
        if artifact["head"] == "blazor-desktop" and artifact["kind"] == "archive"
    )
    windows = next(
        artifact for artifact in artifacts if artifact["platform"] == "windows"
    )
    linux = next(
        artifact for artifact in artifacts if artifact["platform"] == "linux"
    )
    if drift == "extra_windows_head":
        raw = b"undeclared-blazor-windows-installer"
        payload = b"undeclared-blazor-windows-payload"
        artifacts.append(
            {
                "artifactId": "blazor-desktop-win-x64-installer",
                "head": "blazor-desktop",
                "platform": "windows",
                "rid": "win-x64",
                "kind": "installer",
                "installerMode": "bootstrap",
                "payloadAcquisitionMode": "download",
                "fileName": "chummer-blazor-desktop-win-x64-installer.exe",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "sizeBytes": len(raw),
                "payloadFileName": "chummer-blazor-desktop-win-x64-payload.zip",
                "payloadSha256": hashlib.sha256(payload).hexdigest(),
                "payloadSizeBytes": len(payload),
            }
        )
        rows.extend(
            [
                {
                    "path": "files/chummer-blazor-desktop-win-x64-installer.exe",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "sizeBytes": len(raw),
                },
                {
                    "path": "files/chummer-blazor-desktop-win-x64-payload.zip",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "sizeBytes": len(payload),
                },
            ]
        )
    elif drift == "retained_head":
        retained["head"] = "Blazor Desktop"
    elif drift == "retained_unknown_head":
        retained["head"] = "future-desktop"
    elif drift == "retained_platform":
        retained["platform"] = "android"
    elif drift == "retained_rid":
        retained["rid"] = "osx-ppc64"
    elif drift == "retained_linux_rid":
        linux["rid"] = "linux-arm64"
    elif drift == "retained_kind":
        retained["kind"] = "symbols"
    elif drift == "retained_linux_kind":
        linux["kind"] = "symbols"
    elif drift == "retained_bytes":
        retained["sha256"] = "f" * 64
    elif drift == "windows_archive":
        windows["kind"] = "archive"
    else:
        raise AssertionError(f"unknown drift: {drift}")
    rows.sort(key=lambda row: str(row["path"]))

    with pytest.raises(Exception, match=expected):
        parse_candidate_scope(
            layer,
            canonical,
            rows,
            candidate,
            allow_retained_cross_platform=True,
        )


@pytest.mark.parametrize("layer", ["materializer", "projection"])
@pytest.mark.parametrize("legacy_drift", ["fallback_head", "archive_kind"])
def test_legacy_scope_does_not_inherit_unsigned_retained_shelf_relaxation(
    layer: str,
    legacy_drift: str,
) -> None:
    canonical, rows, candidate = real_unsigned_cross_platform_shelf()
    if legacy_drift == "archive_kind":
        canonical["artifacts"] = [
            artifact
            for artifact in canonical["artifacts"]
            if artifact["head"] == "avalonia"
        ]
        retained_paths = {
            f"files/{artifact['fileName']}" for artifact in canonical["artifacts"]
        }
        retained_paths.update(
            {
                "RELEASE_CHANNEL.generated.json",
                "releases.json",
                "files/chummer-avalonia-win-x64-payload.zip",
            }
        )
        rows = [row for row in rows if row["path"] in retained_paths]

    with pytest.raises(Exception):
        parse_candidate_scope(
            layer,
            canonical,
            rows,
            candidate,
            allow_retained_cross_platform=False,
        )


@pytest.mark.parametrize(
    ("entry_name", "expected_message"),
    [
        ("registryFinalizeAuthority", "Registry authority v2 posture drifted"),
        ("registryFinalizeReceipt", "Registry finalize v2 posture drifted"),
    ],
)
def test_unsigned_projection_rejects_rehashed_fractional_registry_contract_version(
    entry_name: str,
    expected_message: str,
) -> None:
    authority = load_unsigned_v3_authority_fixture()
    custody = authority["custody"]
    entry = custody[entry_name]
    document = decode_unsigned_custody_entry(entry)
    document["contractVersion"] = 2.0
    rewrite_unsigned_custody_entry(entry, document)

    if entry_name == "registryFinalizeAuthority":
        finalize_entry = custody["registryFinalizeReceipt"]
        finalize = decode_unsigned_custody_entry(finalize_entry)
        finalize["authority"]["sha256"] = entry["sha256"]
        finalize["authority"]["sizeBytes"] = entry["sizeBytes"]
        rewrite_unsigned_custody_entry(finalize_entry, finalize)
        custody["registryFinalization"]["authoritySha256"] = entry["sha256"]
        custody["registryFinalization"]["finalizeReceiptSha256"] = finalize_entry[
            "sha256"
        ]
    else:
        custody["registryFinalization"]["finalizeReceiptSha256"] = entry["sha256"]

    projection = load_projection()
    with pytest.raises(projection.ProjectionBlocked, match=expected_message):
        projection._validate_candidate_import_authority_v3(authority)


@pytest.mark.parametrize("layer", ["materializer", "projection"])
def test_unsigned_provenance_accepts_actual_producer_binding_paths(layer: str) -> None:
    documents, _, _ = unsigned_provenance_documents()
    receipt = json.loads(
        documents["provenance/UI_FRESH_PACKAGE_PLANE.generated.json"]
    )
    pointer = receipt["retainedWindowsBundle"]
    scope = json.loads(documents["PREVIEW_NIGHTLY_UNSIGNED_SCOPE.proposed.json"])

    assert set(pointer) == UNSIGNED_RETAINED_POINTER_KEYS
    assert pointer["bundleInventoryCount"] == UNSIGNED_BUNDLE_INVENTORY_COUNT
    assert pointer["bundleInventorySha256"] == UNSIGNED_BUNDLE_INVENTORY_SHA256
    assert all(
        set(binding) == {"sha256", "sizeBytes"}
        for binding in scope["provenance"].values()
    )

    validate_unsigned_provenance(layer, documents)


@pytest.mark.parametrize("layer", ["materializer", "projection"])
@pytest.mark.parametrize(
    "tamper",
    [
        "package_lock_path_traversal",
        "package_lock_property_smuggling",
        "retained_manifest_path_traversal",
        "retained_manifest_property_smuggling",
        "target_path_traversal",
        "target_path_unit_separator",
        "target_path_del",
        "pointer_property_smuggling",
        "missing_bundle_inventory_count",
        "bundle_inventory_count_zero",
        "bundle_inventory_count_bool",
        "bundle_inventory_count_fractional",
        "missing_bundle_inventory_sha256",
        "bundle_inventory_sha256_uppercase",
    ],
)
def test_unsigned_provenance_rejects_binding_path_or_property_smuggling(
    layer: str,
    tamper: str,
) -> None:
    documents, _, _ = unsigned_provenance_documents()
    receipt_path = "provenance/UI_FRESH_PACKAGE_PLANE.generated.json"
    retained_path = "provenance/retained-windows-publish-closure/manifest.json"
    receipt = json.loads(documents[receipt_path])
    retained = json.loads(documents[retained_path])
    pointer = receipt["retainedWindowsBundle"]
    rebind_manifest = False

    if tamper == "package_lock_path_traversal":
        receipt["consumerPackagePlaneLock"]["path"] = (
            "config/nested/../package-plane.lock.json"
        )
    elif tamper == "package_lock_property_smuggling":
        retained["packagePlaneLock"]["unexpectedProperty"] = True
    elif tamper == "retained_manifest_path_traversal":
        pointer["manifest"]["path"] = (
            f"{pointer['targetPath']}/nested/../manifest.json"
        )
    elif tamper == "retained_manifest_property_smuggling":
        pointer["manifest"]["unexpectedProperty"] = True
    elif tamper == "target_path_traversal":
        target = "/tmp/chummer-preview/nested/../retained-windows-bundle"
        pointer["targetPath"] = target
        pointer["manifest"]["path"] = f"{target}/manifest.json"
        retained["targetPath"] = target
        rebind_manifest = True
    elif tamper == "target_path_unit_separator":
        target = "/tmp/chummer-preview/unit\x1fseparator/retained-windows-bundle"
        pointer["targetPath"] = target
        pointer["manifest"]["path"] = f"{target}/manifest.json"
        retained["targetPath"] = target
        rebind_manifest = True
    elif tamper == "target_path_del":
        target = "/tmp/chummer-preview/del\x7fsegment/retained-windows-bundle"
        pointer["targetPath"] = target
        pointer["manifest"]["path"] = f"{target}/manifest.json"
        retained["targetPath"] = target
        rebind_manifest = True
    elif tamper == "pointer_property_smuggling":
        pointer["publicationAuthorized"] = False
    elif tamper == "missing_bundle_inventory_count":
        del pointer["bundleInventoryCount"]
    elif tamper == "bundle_inventory_count_zero":
        pointer["bundleInventoryCount"] = 0
    elif tamper == "bundle_inventory_count_bool":
        pointer["bundleInventoryCount"] = True
    elif tamper == "bundle_inventory_count_fractional":
        pointer["bundleInventoryCount"] = 1.0
    elif tamper == "missing_bundle_inventory_sha256":
        del pointer["bundleInventorySha256"]
    elif tamper == "bundle_inventory_sha256_uppercase":
        pointer["bundleInventorySha256"] = pointer[
            "bundleInventorySha256"
        ].upper()
    else:
        raise AssertionError(f"unknown tamper: {tamper}")

    retained_raw = (
        json.dumps(retained, indent=2, sort_keys=True) + "\n"
    ).encode()
    documents[retained_path] = retained_raw
    if rebind_manifest:
        pointer["manifest"] = {
            "path": f"{pointer['targetPath']}/manifest.json",
            "sha256": hashlib.sha256(retained_raw).hexdigest(),
            "sizeBytes": len(retained_raw),
        }
    documents[receipt_path] = (
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    ).encode()

    with pytest.raises(Exception) as rejected:
        validate_unsigned_provenance(layer, documents)
    assert rejected.type.__name__ in {
        "CandidateAuthorityBlocked",
        "ProjectionBlocked",
    }
    assert any(
        fragment in str(rejected.value).lower()
        for fragment in ("binding", "drifted", "exact held bytes", "target path")
    )


@pytest.mark.parametrize("tamper", ["package_lock_extra", "native_package_extra"])
def test_unsigned_projection_rejects_provenance_property_shape_drift(
    tamper: str,
) -> None:
    documents, source_sha, version = unsigned_provenance_documents()
    path = (
        "provenance/config/package-plane.lock.json"
        if tamper == "package_lock_extra"
        else "provenance/config/windows-native-bootstrap-toolchain.lock.json"
    )
    document = json.loads(documents[path])
    if tamper == "package_lock_extra":
        document["unexpectedProperty"] = True
    else:
        document["packages"][0]["unexpectedProperty"] = True
    documents[path] = (
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    ).encode()

    projection = load_projection()
    with pytest.raises(projection.ProjectionBlocked, match="package-plane lock|toolchain package"):
        projection._candidate_unsigned_provenance(
            documents,
            source_sha=source_sha,
            version=version,
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
