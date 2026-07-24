#!/usr/bin/env python3
"""Seal one approved Windows preview byte tree for topology-B import.

This offline materializer does not publish, deploy, upload, or activate
anything. It emits the bounded v3 candidate-import authority consumed by the
public-projection transaction and the adjacent, secret-free direct-import
receipt consumed by the isolated public-download cutover.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Sequence
from urllib.parse import urlsplit

import materialize_candidate_import_authority as candidate_tools
import verify_public_projection as projection


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
import verify_release_scope_decision as scope_verifier  # noqa: E402


AUTHORITY_NAME = "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
DIRECT_IMPORT_NAME = "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
INVENTORY_PATH = "CANDIDATE_UPLOAD_INVENTORY.generated.json"
PROFILE = projection.CANDIDATE_SCOPE_BOUND_EXISTING_BYTES_PROFILE
SCOPE_PATH = projection.CANDIDATE_SCOPE_DECISION_FILE
GENERATION_INVENTORY_PATH = projection.CANDIDATE_GENERATION_INVENTORY_FILE
EXACT_SCOPE = projection.CANDIDATE_EXACT_SCOPE
SIDECAR_NAME = projection.CANDIDATE_UNSIGNED_PAYLOAD_SIDECAR_NAME
COMMIT = re.compile(r"^[0-9a-f]{40}$")
MAX_AUTHORITY_LIFETIME_SECONDS = 6 * 60 * 60
SIGNATURE_POLICY = {
    "signatureStatus": "unsigned",
    "signingRequired": False,
    "unsignedReason": "preview_policy",
}
DIRECT_SIGNATURE = {
    "policy": "preview_policy",
    "required": False,
    "status": "unsigned",
}


class ImportMaterializationError(ValueError):
    pass


def _fail(message: str) -> None:
    raise ImportMaterializationError(message)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _reference(path: str, raw: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
    }


def _embedded(path: str, raw: bytes) -> dict[str, Any]:
    return {
        **_reference(path, raw),
        "base64": base64.b64encode(raw).decode("ascii"),
    }


def _private_parent(path: Path, *, label: str) -> Path:
    if not path.is_absolute():
        _fail(f"{label} must be absolute")
    try:
        parent = path.parent.resolve(strict=True)
        metadata = parent.lstat()
    except OSError as exc:
        raise ImportMaterializationError(
            f"{label} parent is unavailable"
        ) from exc
    if (
        path.parent != parent
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
        or metadata.st_mode & 0o300 != 0o300
    ):
        _fail(
            f"{label} parent must be a current-owner real directory not "
            "writable by other users"
        )
    if path.exists() or path.is_symlink():
        _fail(f"{label} already exists")
    return parent


def _safe_tree_modes(
    root: Path,
    file_modes: dict[str, int],
    directory_modes: list[dict[str, Any]],
) -> int:
    metadata = root.lstat()
    root_mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or root_mode & 0o022
        or root_mode & 0o500 != 0o500
    ):
        _fail("candidate root has unsafe ownership or mode")
    for path, mode in file_modes.items():
        if mode & 0o022 or mode & 0o400 != 0o400:
            _fail(f"candidate file has unsafe mode: {path}")
    for row in directory_modes:
        mode = int(row["mode"])
        if mode & 0o022 or mode & 0o500 != 0o500:
            _fail(f"candidate directory has unsafe mode: {row['path']}")
    return root_mode


def _strict_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    value = candidate_tools._strict_json_bytes(raw, label=label)
    projection._scope_bound_secret_free(value, label=label)
    return value


def _source_commits(args: argparse.Namespace) -> dict[str, str]:
    commits = {
        "hub": args.hub_commit.strip(),
        "registry": args.registry_commit.strip(),
        "ui": args.ui_commit.strip(),
    }
    for name, value in commits.items():
        if COMMIT.fullmatch(value) is None:
            _fail(f"{name} source commit must be lowercase 40-hex")
    return commits


def _candidate_identity(
    version: str,
    canonical_raw: bytes,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate = {
        "version": version,
        "canonicalManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "inventorySha256": candidate_tools._inventory_digest(rows),
        "fileCount": len(rows),
        "totalBytes": sum(int(row["sizeBytes"]) for row in rows),
    }
    candidate["bundleIdentitySha256"] = hashlib.sha256(
        candidate_tools._identity_material(candidate)
    ).hexdigest()
    return candidate_tools._validate_candidate(candidate)


def _validate_scope(
    args: argparse.Namespace,
    *,
    version: str,
) -> tuple[bytes, dict[str, Any], str]:
    expected_sha = args.expected_release_scope_sha256.strip()
    if projection.SHA256_RE.fullmatch(expected_sha) is None:
        _fail("expected release-scope SHA-256 is invalid")
    decision_path = Path(args.release_scope_decision)
    try:
        decision_metadata = decision_path.lstat()
    except OSError as exc:
        raise ImportMaterializationError(
            "approved release-scope decision is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(decision_metadata.st_mode)
        or stat.S_ISLNK(decision_metadata.st_mode)
        or decision_metadata.st_uid != os.geteuid()
        or decision_metadata.st_nlink != 1
        or decision_metadata.st_mode & 0o022
    ):
        _fail(
            "approved release-scope decision has unsafe ownership or mode"
        )
    decision_raw = scope_verifier._stable_bytes(
        decision_path, "approved release-scope decision"
    )
    if hashlib.sha256(decision_raw).hexdigest() != expected_sha:
        _fail("approved release-scope decision SHA-256 drifted")
    decision = scope_verifier._strict_json(
        decision_raw, "approved release-scope decision"
    )
    if decision_raw != _canonical_bytes(decision):
        _fail("approved release-scope decision is not canonical JSON")
    identity, platforms = scope_verifier._parse_decision(decision)
    authority = scope_verifier._authority(
        args.release_scope_authority,
        identity["decisionId"],
        expected_sha,
    )
    expected_platform = {
        "platform": "windows",
        "rid": "win-x64",
        "primaryHead": "avalonia",
        "fallbackHeads": [],
        "artifactAccessClass": "open_public",
        "signingRequirement": "preview_unsigned_allowed",
    }
    if (
        identity["releaseVersion"] != version
        or identity["channel"] != "preview"
        or identity["releaseTarget"] != "preview"
        or platforms != [expected_platform]
    ):
        _fail(
            "approved scope is not the exact open-public Avalonia win-x64 "
            "unsigned-preview decision"
        )
    projection._scope_bound_secret_free(
        decision, label="approved release-scope decision"
    )
    return decision_raw, decision, authority


def _validate_manifest_pair(
    canonical: dict[str, Any],
    compatibility: dict[str, Any],
    *,
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
    generation_id: str,
) -> dict[str, Any]:
    if (
        projection.CANDIDATE_GENERATION_RE.fullmatch(generation_id) is None
        or ".." in generation_id
    ):
        _fail("generation ID is not a safe canonical token")
    scope = candidate_tools._canonical_windows_scope(
        canonical,
        rows,
        allow_ancillary_files=True,
        expected_channel="preview",
    )
    if (
        canonical.get("generationId") != generation_id
        or compatibility.get("generationId") != generation_id
        or canonical.get("platformScope") != "windows_only"
        or compatibility.get("platformScope") != "windows_only"
        or scope["version"] != candidate["version"]
    ):
        _fail("manifest pair is not the requested Windows-only generation")
    compatibility_version = candidate_tools._matching_alias(
        compatibility,
        "version",
        "releaseVersion",
        label="compatibility release version",
    )
    compatibility_channel = candidate_tools._matching_alias(
        compatibility,
        "channelId",
        "channel",
        label="compatibility release channel",
    )
    artifacts = canonical.get("artifacts")
    downloads = compatibility.get("downloads")
    if (
        compatibility_version != candidate["version"]
        or compatibility_channel != "preview"
        or not isinstance(artifacts, list)
        or len(artifacts) != 1
        or not isinstance(downloads, list)
        or len(downloads) != 1
        or not isinstance(artifacts[0], dict)
        or not isinstance(downloads[0], dict)
    ):
        _fail("manifest pair must contain exactly one preview artifact")
    canonical_row = artifacts[0]
    compatibility_row = downloads[0]
    if (
        canonical_row.get("platform") != "windows"
        or canonical_row.get("head") != "avalonia"
        or canonical_row.get("rid") != "win-x64"
        or canonical_row.get("kind") != "installer"
        or canonical_row.get("installAccessClass") != "open_public"
        or canonical_row.get("installerMode") != "bootstrap"
        or canonical_row.get("payloadAcquisitionMode") != "download"
        or compatibility_row.get("platform") != "windows"
        or compatibility_row.get("head") != "avalonia"
        or compatibility_row.get("rid") != "win-x64"
        or compatibility_row.get("installAccessClass") != "open_public"
        or any(
            compatibility_row.get(key) != canonical_row.get(key)
            for key in (
                "artifactId",
                "fileName",
                "installerMode",
                "payloadAcquisitionMode",
                "payloadFileName",
                "payloadSha256",
                "payloadSizeBytes",
                "sha256",
                "sizeBytes",
            )
        )
    ):
        _fail("manifest pair Windows byte bindings disagree")
    return canonical_row


def _validate_sidecar(
    bundle_root: Path,
    *,
    release_version: str,
    installer: dict[str, Any],
) -> None:
    sidecar_path = bundle_root / "files" / SIDECAR_NAME
    sidecar_raw = candidate_tools._plain_file(
        sidecar_path,
        label="Windows payload sidecar",
        maximum_bytes=1024 * 1024,
    ).read_bytes()
    sidecar = _strict_json_bytes(
        sidecar_raw, label="Windows payload sidecar"
    )
    expected_keys = {
        "contractName",
        "downloadUrl",
        "fileName",
        "installerFileName",
        "payloadAcquisitionMode",
        "releaseVersion",
        "sha256",
        "sizeBytes",
    }
    parsed = urlsplit(str(sidecar.get("downloadUrl") or ""))
    payload_name = str(installer.get("payloadFileName") or "")
    expected_public_path = f"/downloads/files/{payload_name}"
    if (
        set(sidecar) != expected_keys
        or sidecar.get("contractName")
        != "chummer6-ui.windows_bootstrap_payload"
        or sidecar.get("fileName") != payload_name
        or sidecar.get("installerFileName") != installer.get("fileName")
        or sidecar.get("payloadAcquisitionMode") != "download"
        or sidecar.get("releaseVersion") != release_version
        or sidecar.get("sha256") != installer.get("payloadSha256")
        or sidecar.get("sizeBytes") != installer.get("payloadSizeBytes")
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_public_path
        or parsed.scheme not in {"", "https"}
        or parsed.scheme == ""
        and bool(parsed.netloc)
        or parsed.scheme == "https"
        and (
            parsed.netloc != "chummer.run"
            or parsed.hostname != "chummer.run"
            or parsed.username is not None
            or parsed.password is not None
        )
    ):
        _fail("Windows payload sidecar differs from the manifest byte graph")


def _materialize(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle_input = Path(args.bundle_root)
    if not bundle_input.is_absolute():
        _fail("candidate bundle root must be absolute")
    try:
        bundle_metadata = bundle_input.lstat()
        bundle_root = bundle_input.resolve(strict=True)
    except OSError as exc:
        raise ImportMaterializationError(
            "candidate bundle root is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(bundle_metadata.st_mode)
        or not stat.S_ISDIR(bundle_metadata.st_mode)
        or bundle_input != bundle_root
    ):
        _fail("candidate bundle root must be one real directory")
    authority_output = Path(args.authority_output)
    direct_output = Path(args.direct_import_output)
    if authority_output.name != AUTHORITY_NAME:
        _fail(f"authority output must be named {AUTHORITY_NAME}")
    if direct_output.name != DIRECT_IMPORT_NAME:
        _fail(f"direct-import output must be named {DIRECT_IMPORT_NAME}")
    _private_parent(authority_output, label="candidate authority output")
    _private_parent(direct_output, label="direct-import output")
    if bundle_root in authority_output.parents:
        _fail("candidate authority output must be outside the candidate bundle")
    if direct_output.parent.resolve(strict=True) != bundle_root.parent:
        _fail("direct-import output must be adjacent to the candidate bundle")

    rows, file_modes, directory_modes, captured = (
        candidate_tools._scan_bundle_tree(bundle_root)
    )
    root_mode = _safe_tree_modes(
        bundle_root, file_modes, directory_modes
    )
    expected_paths = {
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
        "files/chummer-avalonia-win-x64-installer.exe",
        "files/chummer-avalonia-win-x64-payload.zip",
        f"files/{SIDECAR_NAME}",
    }
    if {row["path"] for row in rows} != expected_paths or {
        row["path"] for row in directory_modes
    } != {"files"}:
        _fail(
            "candidate must contain only the generation manifest pair and "
            "Windows installer/payload/sidecar"
        )
    canonical_raw = captured["RELEASE_CHANNEL.generated.json"]
    compatibility_raw = captured["releases.json"]
    canonical = _strict_json_bytes(
        canonical_raw, label="candidate canonical manifest"
    )
    compatibility = _strict_json_bytes(
        compatibility_raw, label="candidate compatibility manifest"
    )
    version = candidate_tools._matching_alias(
        canonical,
        "version",
        "releaseVersion",
        label="candidate release version",
    )
    candidate = _candidate_identity(version, canonical_raw, rows)
    installer = _validate_manifest_pair(
        canonical,
        compatibility,
        candidate=candidate,
        rows=rows,
        generation_id=args.generation_id.strip(),
    )
    _validate_sidecar(
        bundle_root,
        release_version=version,
        installer=installer,
    )
    decision_raw, _decision, scope_authority = _validate_scope(
        args, version=version
    )
    commits = _source_commits(args)

    inventory = {
        "contractName": "chummer.release-upload.candidate-inventory/v1",
        "contractVersion": 1,
        "files": rows,
    }
    inventory_raw = _canonical_bytes(inventory)
    generation_inventory = {
        "contractName": (
            "chummer.release-shelf."
            "existing-bytes-generation-inventory/v1"
        ),
        "contractVersion": 1,
        "status": "pass",
        "projectionProfile": PROFILE,
        "releaseVersion": version,
        "channel": "preview",
        "generationId": args.generation_id.strip(),
        "canonicalManifestSha256": hashlib.sha256(
            canonical_raw
        ).hexdigest(),
        "compatibilityManifestSha256": hashlib.sha256(
            compatibility_raw
        ).hexdigest(),
        "inventorySha256": candidate["inventorySha256"],
        "bundleIdentitySha256": candidate["bundleIdentitySha256"],
        "fileCount": candidate["fileCount"],
        "totalBytes": candidate["totalBytes"],
        "rootMode": root_mode,
        "files": [
            {**row, "mode": file_modes[str(row["path"])]}
            for row in rows
        ],
        "directories": directory_modes,
    }
    generation_inventory_raw = _canonical_bytes(generation_inventory)
    file_by_path = {
        str(row["path"]): row for row in generation_inventory["files"]
    }
    fresh_delta = [
        {
            "artifactRole": role,
            "mode": file_by_path[path]["mode"],
            "path": path,
            "sha256": file_by_path[path]["sha256"],
            "sizeBytes": file_by_path[path]["sizeBytes"],
        }
        for role, path in (
            (
                "installer",
                "files/chummer-avalonia-win-x64-installer.exe",
            ),
            (
                "bootstrap_payload",
                "files/chummer-avalonia-win-x64-payload.zip",
            ),
            (
                "bootstrap_payload_sidecar",
                f"files/{SIDECAR_NAME}",
            ),
        )
    ]
    binding = {
        "contractName": (
            "chummer.release-upload.scope-bound-existing-bytes/v1"
        ),
        "contractVersion": 1,
        "status": "sealed_review_required",
        "projectionProfile": PROFILE,
        "releaseVersion": version,
        "channel": "preview",
        "generationId": args.generation_id.strip(),
        "platformScope": "windows_only",
        "exactIncomingDesktopScope": EXACT_SCOPE,
        "signaturePolicy": SIGNATURE_POLICY,
        "releaseScopeDecisionSha256": hashlib.sha256(
            decision_raw
        ).hexdigest(),
        "releaseScopeAuthority": scope_authority,
        "canonicalManifestSha256": hashlib.sha256(
            canonical_raw
        ).hexdigest(),
        "compatibilityManifestSha256": hashlib.sha256(
            compatibility_raw
        ).hexdigest(),
        "inventorySha256": candidate["inventorySha256"],
        "generationInventorySha256": hashlib.sha256(
            generation_inventory_raw
        ).hexdigest(),
        "sourceCommits": commits,
        "freshDelta": fresh_delta,
        "retainedFromIncumbent": [],
        "retainedPlatforms": [],
        "shelfPlatforms": ["windows"],
    }
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if args.now
        else datetime.now(timezone.utc)
    )
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        _fail("materialization time must be UTC")
    lifetime = args.authority_lifetime_seconds
    if (
        isinstance(lifetime, bool)
        or not isinstance(lifetime, int)
        or not 60 <= lifetime <= MAX_AUTHORITY_LIFETIME_SECONDS
    ):
        _fail("authority lifetime must be 60 through 21600 seconds")
    authority = {
        "contractName": (
            "chummer.release-upload.candidate-import-authority/v3"
        ),
        "contractVersion": 3,
        "projectionProfile": PROFILE,
        "status": "candidate_import_ready",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "publicationAuthorized": False,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "codeDeploymentAuthority": False,
        "platformScope": "windows_only",
        "crossRunBitReproducible": False,
        "signaturePolicy": SIGNATURE_POLICY,
        "exactIncomingDesktopScope": EXACT_SCOPE,
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": (
            now + timedelta(seconds=lifetime)
        ).isoformat().replace("+00:00", "Z"),
        "candidate": candidate,
        "custody": {
            "canonicalManifest": _embedded(
                "RELEASE_CHANNEL.generated.json", canonical_raw
            ),
            "compatibilityManifest": _embedded(
                "releases.json", compatibility_raw
            ),
            "inventory": _embedded(INVENTORY_PATH, inventory_raw),
            "releaseScopeDecision": _embedded(
                SCOPE_PATH, decision_raw
            ),
            "generationInventory": _embedded(
                GENERATION_INVENTORY_PATH, generation_inventory_raw
            ),
            "scopeBoundExistingBytes": binding,
        },
    }
    authority_raw = _canonical_bytes(authority)
    projection._validate_candidate_import_authority(authority_raw)
    authority_sha = hashlib.sha256(authority_raw).hexdigest()
    direct_import = {
        "contractName": (
            "chummer6-ui.preview-nightly-unsigned-direct-import"
        ),
        "contractVersion": 1,
        "projectionProfile": PROFILE,
        "status": "sealed_review_required",
        "platformScope": "windows_only",
        "crossRunBitReproducible": False,
        "signature": DIRECT_SIGNATURE,
        "publicationAuthorized": False,
        "uploadAuthorized": False,
        "deployAuthorized": False,
        "release": {"channel": "preview", "version": version},
        "sourceCommits": commits,
        "hubCandidateImportAuthority": {
            "path": AUTHORITY_NAME,
            "sha256": authority_sha,
            "sizeBytes": len(authority_raw),
        },
        "releaseScopeDecision": _reference(
            SCOPE_PATH, decision_raw
        ),
        "generationInventory": _reference(
            GENERATION_INVENTORY_PATH, generation_inventory_raw
        ),
        "canonicalManifest": _reference(
            "RELEASE_CHANNEL.generated.json", canonical_raw
        ),
        "compatibilityManifest": _reference(
            "releases.json", compatibility_raw
        ),
        "transport": {
            "bundleIdentitySha256": candidate[
                "bundleIdentitySha256"
            ],
            "generationId": args.generation_id.strip(),
            "mode": "existing_bytes",
        },
    }
    projection._scope_bound_secret_free(
        direct_import, label="scope-bound direct-import receipt"
    )
    (
        final_rows,
        final_file_modes,
        final_directory_modes,
        final_captured,
    ) = candidate_tools._scan_bundle_tree(bundle_root)
    if (
        final_rows != rows
        or final_file_modes != file_modes
        or final_directory_modes != directory_modes
        or final_captured != captured
        or _safe_tree_modes(
            bundle_root, final_file_modes, final_directory_modes
        )
        != root_mode
    ):
        _fail("candidate bundle changed before authority sealing")
    _write_pair(
        authority_output,
        authority_raw,
        direct_output,
        _canonical_bytes(direct_import),
    )
    return authority, direct_import


def _write_pair(
    authority_path: Path,
    authority_raw: bytes,
    direct_path: Path,
    direct_raw: bytes,
) -> None:
    staged: list[tuple[Path, int]] = []
    committed_authority = False
    try:
        for output, raw in (
            (authority_path, authority_raw),
            (direct_path, direct_raw),
        ):
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{output.name}.", dir=output.parent
            )
            temporary = Path(temporary_name)
            staged.append((temporary, descriptor))
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            staged[-1] = (temporary, -1)
        os.replace(staged[0][0], authority_path)
        committed_authority = True
        os.replace(staged[1][0], direct_path)
        for parent in {authority_path.parent, direct_path.parent}:
            descriptor = os.open(
                parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except BaseException:
        if committed_authority:
            authority_path.unlink(missing_ok=True)
        direct_path.unlink(missing_ok=True)
        raise
    finally:
        for path, descriptor in staged:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            path.unlink(missing_ok=True)


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seal exact existing Windows preview bytes into the topology-B "
            "candidate-import and direct-import handoffs."
        )
    )
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--release-scope-decision", required=True)
    parser.add_argument("--expected-release-scope-sha256", required=True)
    parser.add_argument("--release-scope-authority", required=True)
    parser.add_argument("--hub-commit", required=True)
    parser.add_argument("--registry-commit", required=True)
    parser.add_argument("--ui-commit", required=True)
    parser.add_argument("--authority-output", required=True)
    parser.add_argument("--direct-import-output", required=True)
    parser.add_argument(
        "--authority-lifetime-seconds",
        type=int,
        default=MAX_AUTHORITY_LIFETIME_SECONDS,
    )
    parser.add_argument("--now", default="", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        authority, _direct = _materialize(args)
    except (
        ImportMaterializationError,
        candidate_tools.CandidateAuthorityBlocked,
        projection.ProjectionBlocked,
        scope_verifier.ScopeError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"scope-bound existing-bytes import blocked: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "bundleIdentitySha256": authority["candidate"][
                    "bundleIdentitySha256"
                ],
                "expiresAtUtc": authority["expiresAtUtc"],
                "projectionProfile": PROFILE,
                "status": authority["status"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
