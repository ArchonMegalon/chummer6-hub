#!/usr/bin/env python3
"""Materialize the isolated, preview-only Windows proof upload bundle.

This intentionally does not read or rewrite the canonical release manifests.  It
binds one Windows bootstrap installer to its payload, unsigned-preview receipt,
Wine compatibility smoke, build-time governed provenance/SBOM, and native-
Windows visual handoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from windows_proof_evidence import (  # noqa: E402
    MANIFEST_SCHEMA,
    PROVENANCE_TARGET_ID,
    validate_bootstrap_payload_zip,
    validate_governed_windows_evidence,
    validate_manifest_freshness,
)

SCHEMA_VERSION = MANIFEST_SCHEMA
ARTIFACT_ID = "avalonia-win-x64-installer"
HEAD = "avalonia"
RID = "win-x64"
INSTALLER_NAME = "chummer-avalonia-win-x64-installer.exe"
PAYLOAD_NAME = "chummer-avalonia-win-x64-payload.zip"
METADATA_NAME = f"{PAYLOAD_NAME}.json"
SIGNING_NAME = "signing-avalonia-win-x64.receipt.json"
SMOKE_NAME = "startup-smoke-avalonia-win-x64.receipt.json"
HANDOFF_NAME = "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"
MANIFEST_NAME = "WINDOWS_PROOF_MANIFEST.generated.json"
SBOM_NAME = f"{PROVENANCE_TARGET_ID}.cdx.json"
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VISUAL_REASON = (
    "Windows installer visual proof is pending; capture progress and completion "
    "screenshots on a native Windows host before promotion."
)


class DuplicateJsonKey(ValueError):
    pass


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, label: str) -> dict[str, Any]:
    require_regular_file(path, label)
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJsonKey) as exc:
        fail(f"{label} could not be loaded: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        fail(f"{label} must be a non-symlink regular file: {path}")
    for parent in [path.parent, *path.parents]:
        if parent.is_symlink():
            fail(f"{label} must not traverse a symbolic link: {parent}")


def require_exact(payload: dict[str, Any], key: str, expected: Any, label: str) -> None:
    if payload.get(key) != expected:
        fail(f"{label}.{key} must be {expected!r}")


def normalize_digest(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw.removeprefix("sha256:")


def require_digest(payload: dict[str, Any], key: str, expected: str, label: str) -> None:
    actual = normalize_digest(payload.get(key))
    if not SHA256_PATTERN.fullmatch(actual) or actual != expected:
        fail(f"{label}.{key} does not match the admitted bytes")


def require_int(payload: dict[str, Any], key: str, expected: int, label: str) -> None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        fail(f"{label}.{key} must be {expected}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def inventory_row(kind: str, relative_path: str, source: Path, content_type: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "artifactId": ARTIFACT_ID,
        "head": HEAD,
        "rid": RID,
        "fileName": Path(relative_path).name,
        "relativePath": relative_path,
        "contentType": content_type,
        "size": source.stat().st_size,
        "sha256": sha256_file(source),
    }


def validate_evidence(
    *,
    version: str,
    installer: Path,
    payload: Path,
    metadata_path: Path,
    signing_path: Path,
    smoke_path: Path,
) -> tuple[str, str, str, str]:
    validate_bootstrap_payload_zip(payload, "Windows bootstrap payload")
    installer_digest = sha256_file(installer)
    payload_digest = sha256_file(payload)
    payload_size = payload.stat().st_size
    expected_url = (
        "https://chummer.run/downloads/proof/windows/candidates/"
        f"{version}/files/{PAYLOAD_NAME}"
    )

    metadata = load_json(metadata_path, "bootstrap payload metadata")
    require_exact(metadata, "contractName", "chummer6-ui.windows_bootstrap_payload", "metadata")
    require_exact(metadata, "fileName", PAYLOAD_NAME, "metadata")
    require_exact(metadata, "downloadUrl", expected_url, "metadata")
    require_digest(metadata, "sha256", payload_digest, "metadata")
    require_int(metadata, "sizeBytes", payload_size, "metadata")
    require_exact(metadata, "payloadAcquisitionMode", "embedded", "metadata")
    require_exact(metadata, "installerFileName", INSTALLER_NAME, "metadata")
    require_exact(metadata, "releaseVersion", version, "metadata")

    signing = load_json(signing_path, "Windows signing receipt")
    for key, expected in (
        ("contractName", "chummer6-ui.desktop_artifact_signing"),
        ("platform", "windows"),
        ("app", HEAD),
        ("rid", RID),
        ("releaseChannel", "preview"),
        ("releaseVersion", version),
        ("signingStatus", "skipped_preview"),
    ):
        require_exact(signing, key, expected, "signing receipt")
    signing_rows = signing.get("artifacts")
    if not isinstance(signing_rows, list):
        fail("signing receipt.artifacts must be an array")
    installer_rows = [
        row
        for row in signing_rows
        if isinstance(row, dict) and row.get("fileName") == INSTALLER_NAME
    ]
    if len(installer_rows) != 1:
        fail("signing receipt must bind exactly one installer row")
    require_digest(installer_rows[0], "sha256", installer_digest, "signing receipt installer")
    require_exact(installer_rows[0], "signingStatus", "skipped_preview", "signing receipt installer")

    smoke = load_json(smoke_path, "Windows compatibility smoke receipt")
    for key, expected in (
        ("status", "pass"),
        ("headId", HEAD),
        ("version", version),
        ("releaseVersion", version),
        ("channelId", "preview"),
        ("platform", "windows"),
        ("rid", RID),
        ("artifactId", ARTIFACT_ID),
        ("artifactFileName", INSTALLER_NAME),
        ("artifactRelativePath", f"files/{INSTALLER_NAME}"),
        ("bootstrapPayloadFileName", PAYLOAD_NAME),
        ("executionEnvironment", "wine_compatibility"),
        ("verificationScope", "windows_compatibility_startup"),
    ):
        require_exact(smoke, key, expected, "startup smoke receipt")
    payload_mode = str(smoke.get("bootstrapPayloadAcquisitionMode") or "").strip()
    if payload_mode != "embedded":
        fail("startup smoke receipt.bootstrapPayloadAcquisitionMode must be 'embedded'")
    require_digest(smoke, "artifactDigest", installer_digest, "startup smoke receipt")
    require_digest(smoke, "artifactSha256", installer_digest, "startup smoke receipt")
    require_digest(smoke, "bootstrapPayloadSha256", payload_digest, "startup smoke receipt")
    require_int(smoke, "bootstrapPayloadSizeBytes", payload_size, "startup smoke receipt")
    native = smoke.get("nativeHostEvidence")
    if not isinstance(native, dict):
        fail("startup smoke receipt.nativeHostEvidence must be an object")
    require_exact(native, "contractName", "chummer6-ui.native_windows_host_evidence", "native host evidence")
    require_exact(native, "status", "not_native", "native host evidence")
    require_exact(native, "isNativeWindows", False, "native host evidence")
    require_exact(native, "runner", "wine", "native host evidence")

    embedded = installer.read_bytes()
    expected_trailer = (
        "\nCHUMMER6_BOOTSTRAP_METADATA\n"
        f"payloadFileName={PAYLOAD_NAME}\n"
        f"payloadDownloadUrl={expected_url}\n"
        f"payloadSha256={payload_digest}\n"
        f"payloadSizeBytes={payload_size}\n"
        "payloadAcquisitionMode=embedded\n"
    ).encode("utf-8")
    if not embedded.endswith(expected_trailer):
        fail("installer must end with the exact embedded bootstrap metadata trailer")

    return installer_digest, payload_digest, expected_url, payload_mode


def build_handoff(
    *,
    version: str,
    installer_digest: str,
    smoke_digest: str,
    payload_acquisition_mode: str,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "contract_name": "chummer6-ui.windows_installer_visual_proof_handoff",
        "handoff_only": True,
        "handoff_scope": "staged_nightly_windows_visual_proof",
        "stable_release_unchanged": True,
        "requires_separate_publish_lane": True,
        "generated_at": generated_at,
        "status": "ready_for_windows_host",
        "only_blocker": "visual_proof",
        "only_blocker_is_visual_proof": True,
        "blockers": [],
        "release": {
            "channel_id": "preview",
            "version": version,
            "release_version": version,
            "release_scope": "proof_only",
            "supportability_state": "review_required",
            "public_trust_posture": "blocked",
            "cf_access_gated": True,
        },
        "windows_installer": {
            "artifact_id": ARTIFACT_ID,
            "file_name": INSTALLER_NAME,
            "sha256": f"sha256:{installer_digest}",
        },
        "startup_smoke_path": f"startup-smoke/{SMOKE_NAME}",
        "startup_smoke": {
            "status": "pass",
            "version": version,
            "release_version": version,
            "receipt_file_name": SMOKE_NAME,
            "receipt_sha256": smoke_digest,
            "artifact_id": ARTIFACT_ID,
            "artifact_file_name": INSTALLER_NAME,
            "artifact_digest": f"sha256:{installer_digest}",
            "bootstrap_payload_acquisition_mode": payload_acquisition_mode,
            "matches_release_version": True,
            "matches_artifact_file_name": True,
            "matches_artifact_digest": True,
        },
        "windows_gate_status": "failed",
        "windows_gate_blocking_mode": "external_only",
        "windows_gate_reasons": [VISUAL_REASON],
    }


def materialize(stage_root: Path, output_root: Path, version: str) -> Path:
    if not VERSION_PATTERN.fullmatch(version) or ".." in version:
        fail("candidate version is not a portable identifier")
    if output_root.exists():
        fail(f"output root must not already exist: {output_root}")
    if stage_root.is_symlink() or not stage_root.is_dir():
        fail(f"stage root must be a non-symlink directory: {stage_root}")

    sources = {
        "installer": stage_root / "files" / INSTALLER_NAME,
        "payload": stage_root / "files" / PAYLOAD_NAME,
        "metadata": stage_root / "files" / METADATA_NAME,
        "signing": stage_root / "signing" / SIGNING_NAME,
        "smoke": stage_root / "startup-smoke" / SMOKE_NAME,
        "provenance": (
            stage_root
            / "proof"
            / "build-provenance"
            / "v1"
            / "invocations"
            / f"{version}.avalonia.win-x64.installer.json"
        ),
        "sbom": (
            stage_root
            / "proof"
            / "build-provenance"
            / "v1"
            / "sbom"
            / SBOM_NAME
        ),
    }
    for label, path in sources.items():
        require_regular_file(path, label)

    installer_digest, _, _, payload_acquisition_mode = validate_evidence(
        version=version,
        installer=sources["installer"],
        payload=sources["payload"],
        metadata_path=sources["metadata"],
        signing_path=sources["signing"],
        smoke_path=sources["smoke"],
    )
    smoke_digest = sha256_file(sources["smoke"])
    governed_evidence = validate_governed_windows_evidence(
        version=version,
        installer_path=sources["installer"],
        provenance_path=sources["provenance"],
        sbom_path=sources["sbom"],
    )
    materialized_at = datetime.now(UTC).replace(microsecond=0)
    generated_at = materialized_at.isoformat().replace("+00:00", "Z")
    expires_at = (materialized_at + timedelta(hours=24)).isoformat().replace("+00:00", "Z")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.tmp-", dir=output_root.parent))
    try:
        destinations = {
            "installer": temporary / "files" / INSTALLER_NAME,
            "payload": temporary / "files" / PAYLOAD_NAME,
            "metadata": temporary / "files" / METADATA_NAME,
            "signing": temporary / "signing" / SIGNING_NAME,
            "smoke": temporary / "startup-smoke" / SMOKE_NAME,
            "provenance": (
                temporary
                / "proof"
                / "build-provenance"
                / "v1"
                / "invocations"
                / sources["provenance"].name
            ),
            "sbom": (
                temporary
                / "proof"
                / "build-provenance"
                / "v1"
                / "sbom"
                / SBOM_NAME
            ),
        }
        for key, destination in destinations.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sources[key], destination)

        handoff_path = temporary / "proof" / HANDOFF_NAME
        handoff = build_handoff(
            version=version,
            installer_digest=installer_digest,
            smoke_digest=smoke_digest,
            payload_acquisition_mode=payload_acquisition_mode,
            generated_at=generated_at,
        )
        write_json(handoff_path, handoff)

        rows = [
            inventory_row("installer", f"files/{INSTALLER_NAME}", destinations["installer"], "application/vnd.microsoft.portable-executable"),
            inventory_row("bootstrap_payload", f"files/{PAYLOAD_NAME}", destinations["payload"], "application/zip"),
            inventory_row("bootstrap_metadata", f"files/{METADATA_NAME}", destinations["metadata"], "application/json"),
            inventory_row("signing_receipt", f"signing/{SIGNING_NAME}", destinations["signing"], "application/json"),
            inventory_row("startup_smoke_receipt", f"startup-smoke/{SMOKE_NAME}", destinations["smoke"], "application/json"),
            inventory_row("visual_handoff", f"proof/{HANDOFF_NAME}", handoff_path, "application/json"),
            inventory_row(
                "build_provenance_receipt",
                f"proof/build-provenance/v1/invocations/{sources['provenance'].name}",
                destinations["provenance"],
                "application/json",
            ),
            inventory_row(
                "sbom",
                f"proof/build-provenance/v1/sbom/{SBOM_NAME}",
                destinations["sbom"],
                "application/vnd.cyclonedx+json",
            ),
        ]
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "candidateVersion": version,
            "generatedAt": generated_at,
            "expiresAt": expires_at,
            "channel": "preview",
            "releaseScope": "proof_only",
            "supportabilityState": "review_required",
            "publicTrustPosture": "blocked",
            "cfAccessGated": True,
            "revoked": False,
            "proofOnlyPolicy": {
                "enabled": True,
                "unsignedPreviewAllowed": True,
                "nativeWindowsValidationRequired": True,
            },
            "signing": {
                "status": "skipped_preview",
                "proofOnlyPolicyRecorded": True,
                "receiptArtifactId": ARTIFACT_ID,
            },
            "compatibilitySmoke": {
                "status": "pass",
                "executionEnvironment": "wine_compatibility",
                "nativeWindows": False,
                "payloadAcquisitionMode": payload_acquisition_mode,
                "receiptArtifactId": ARTIFACT_ID,
            },
            "visualExitGate": {
                "status": "external_only",
                "evidenceArtifactId": None,
            },
            "nativeHostHandoff": {
                "status": "ready_for_windows_host",
                "onlyBlocker": "visual_proof",
                "onlyBlockerIsVisualProof": True,
                "handoffArtifactId": ARTIFACT_ID,
            },
            "artifacts": rows,
        }
        validate_manifest_freshness(
            manifest,
            now=materialized_at,
            not_before=governed_evidence.build_started_at,
        )
        write_json(temporary / MANIFEST_NAME, manifest)
        os.replace(temporary, output_root)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_root / MANIFEST_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--candidate-version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = materialize(
            args.stage_root.absolute(),
            args.output_root.absolute(),
            args.candidate_version,
        )
    except (OSError, ValueError) as exc:
        print(f"windows_proof_bundle:fail: {exc}", file=os.sys.stderr)
        return 1
    print(f"windows_proof_bundle:ok manifest={manifest} sha256={sha256_file(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
