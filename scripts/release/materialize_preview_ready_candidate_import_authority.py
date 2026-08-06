#!/usr/bin/env python3
"""Seal a Registry-ready preview shelf behind a stage-only v6 authority.

The v6 envelope composes, but never broadens, three independently verified
inputs: one fresh native-Windows v4 candidate authority, one Registry-owned
preview-readiness receipt, and one deterministic generation projection.  It
authorizes candidate import/staging only.  Publication, completion, deployment,
route mutation, and activation remain false and owner-finalizer controlled.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any


V6_CONTRACT = "chummer.release-upload.candidate-import-authority/v6"
V4_CONTRACT = "chummer.release-upload.candidate-import-authority/v4"
READY_PROFILE = "v4_unsigned_windows_preview_ready"
READINESS_CONTRACT = "chummer.registry.preview-publication-readiness/v1"
SOURCE_AUTHORITY_PATH = (
    "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.source-v4.generated.json"
)
READINESS_PATH = "PREVIEW_PUBLICATION_READINESS.generated.json"
NATIVE_PATH = (
    "proof/windows-native/"
    "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_EVIDENCE.generated.json"
)
PREPROJECTION_CANONICAL_PATH = "preprojection/RELEASE_CHANNEL.generated.json"
PREPROJECTION_COMPATIBILITY_PATH = "preprojection/releases.json"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MAX_LIFETIME_SECONDS = 6 * 60 * 60


class PreviewReadyAuthorityBlocked(ValueError):
    pass


def _blocked(message: str) -> None:
    raise PreviewReadyAuthorityBlocked(message)


def _tools() -> Any:
    path = Path(__file__).with_name("materialize_candidate_import_authority.py")
    spec = importlib.util.spec_from_file_location(
        "chummer_preview_ready_candidate_tools", path
    )
    if spec is None or spec.loader is None:
        _blocked("candidate authority tools cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reference(value: object, *, path: str, raw: bytes, label: str) -> None:
    expected = {"path": path, "sha256": _sha(raw), "sizeBytes": len(raw)}
    if value != expected:
        _blocked(f"{label} byte reference drifted")


def _decode_embedded(value: object, *, path: str, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "sha256",
        "sizeBytes",
        "base64",
    }:
        _blocked(f"{label} embedded-byte contract drifted")
    try:
        raw = base64.b64decode(value.get("base64"), validate=True)
    except (TypeError, ValueError) as exc:
        raise PreviewReadyAuthorityBlocked(f"{label} base64 is invalid") from exc
    if value != {
        "path": path,
        "sha256": _sha(raw),
        "sizeBytes": len(raw),
        "base64": value.get("base64"),
    }:
        _blocked(f"{label} embedded-byte binding drifted")
    return raw


def _false_authority(document: dict[str, Any], *, label: str) -> None:
    for field in (
        "publicationAuthorized",
        "publicationEligible",
        "releaseUploadAuthority",
        "deployAuthority",
        "routeAuthority",
        "codeDeploymentAuthority",
    ):
        if document.get(field) is not False:
            _blocked(f"{label} unexpectedly grants {field}")


def _validate_ready_pair(
    canonical: dict[str, Any],
    compatibility: dict[str, Any],
    *,
    release_version: str,
) -> None:
    for label, value in (("canonical", canonical), ("compatibility", compatibility)):
        if (
            value.get("projectionProfile") != READY_PROFILE
            or value.get("version") != release_version
            or value.get("releaseVersion") != release_version
            or value.get("channel") != "preview"
            or value.get("channelId") != "preview"
            or value.get("status") != "published"
            or value.get("rolloutState") != "promoted_preview"
            or value.get("supportabilityState") != "preview_supported"
            or value.get("publicationEligible") is not True
            or value.get("routeAuthority") is not True
            or value.get("releaseUploadAuthority") is not False
            or value.get("deployAuthority") is not False
        ):
            _blocked(f"{label} manifest is not the exact ready preview profile")
    coverage = canonical.get("desktopTupleCoverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("complete") is not True
        or coverage.get("routeAuthority") is not True
        or coverage.get("missingRequiredPlatforms") != []
        or coverage.get("missingRequiredHeads") != []
        or coverage.get("missingRequiredPlatformHeadRidTuples") != []
    ):
        _blocked("ready preview desktop coverage is incomplete")


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    tools = _tools()
    now = (
        tools._timestamp(args.now, label="materialization time")
        if args.now
        else datetime.now(timezone.utc)
    )
    lifetime = tools._positive_int(
        args.authority_lifetime_seconds,
        label="authority lifetime seconds",
    )
    if lifetime > MAX_LIFETIME_SECONDS:
        _blocked("v6 authority lifetime exceeds the fixed six-hour maximum")

    bundle_root = Path(args.bundle_root).resolve(strict=True)
    preprojection_root = Path(args.preprojection_bundle_root).resolve(strict=True)
    candidate, _candidate_raw = tools._strict_json(
        Path(args.candidate_summary), label="candidate summary"
    )
    tools._validate_candidate(candidate)
    inventory, inventory_raw = tools._strict_json(
        Path(args.candidate_inventory), label="candidate upload inventory"
    )
    (
        candidate_rows,
        candidate_file_modes,
        candidate_directory_modes,
        captured_files,
    ) = tools._validate_bundle_inventory(
        bundle_root,
        inventory,
        candidate,
        allow_root_ancillary_files=True,
    )
    canonical_raw = captured_files.get("RELEASE_CHANNEL.generated.json")
    compatibility_raw = captured_files.get("releases.json")
    if canonical_raw is None or compatibility_raw is None:
        _blocked("v6 candidate bundle omits its manifest pair")
    canonical = tools._strict_json_bytes(canonical_raw, label="v6 canonical manifest")
    compatibility = tools._strict_json_bytes(
        compatibility_raw, label="v6 compatibility manifest"
    )
    if (
        candidate.get("canonicalManifestSha256") != _sha(canonical_raw)
        or candidate.get("version") != canonical.get("releaseVersion")
    ):
        _blocked("v6 candidate summary does not bind its canonical manifest")

    projection = tools._validate_generation_projection_bridge(
        preprojection_bundle_root=preprojection_root,
        bundle_root=bundle_root,
        candidate_rows=candidate_rows,
        candidate_file_modes=candidate_file_modes,
        candidate_directory_modes=candidate_directory_modes,
        canonical=canonical,
        canonical_bytes=canonical_raw,
        compatibility=compatibility,
        compatibility_bytes=compatibility_raw,
        evaluated_at=args.generation_projection_evaluated_at,
    )
    source = projection.pop("source")
    preprojection_canonical_raw = source["canonicalBytes"]
    preprojection_compatibility_raw = source["compatibilityBytes"]
    _validate_ready_pair(
        source["canonical"],
        source["compatibility"],
        release_version=candidate["version"],
    )
    _validate_ready_pair(
        canonical,
        compatibility,
        release_version=candidate["version"],
    )

    source_authority, source_authority_raw = tools._strict_json(
        Path(args.source_v4_authority), label="source v4 candidate authority"
    )
    if (
        source_authority.get("contractName") != V4_CONTRACT
        or source_authority.get("contractVersion") != 4
        or source_authority.get("status") != "candidate_import_ready"
        or source_authority.get("candidateImportAuthority") is not True
        or source_authority.get("ownerNativeFinalizationBridgeAuthority") is not True
    ):
        _blocked("source authority is not the exact native v4 contract")
    _false_authority(source_authority, label="source v4 authority")
    source_expiry = tools._timestamp(
        source_authority.get("expiresAtUtc"), label="source v4 expiry"
    )
    if source_expiry <= now:
        _blocked("source v4 candidate authority is expired")

    readiness, readiness_raw = tools._strict_json(
        Path(args.readiness_receipt), label="Registry readiness receipt"
    )
    expected_readiness_keys = {
        "canonicalManifest",
        "compatibilityManifest",
        "contractName",
        "contractVersion",
        "deployAuthority",
        "generatedAtUtc",
        "localizationGateSha256",
        "nativeWindowsEvidenceSha256",
        "platforms",
        "publicationEligible",
        "registryCommit",
        "releaseProofSha256",
        "releaseUploadAuthority",
        "releaseVersion",
        "routeAuthority",
        "sourceCandidateAuthoritySha256",
        "sourceCanonicalManifestSha256",
        "sourceCompatibilityManifestSha256",
        "status",
    }
    if (
        set(readiness) != expected_readiness_keys
        or readiness.get("contractName") != READINESS_CONTRACT
        or readiness.get("contractVersion") != 1
        or readiness.get("status") != "preview_ready"
        or readiness.get("releaseVersion") != candidate["version"]
        or readiness.get("platforms") != ["linux", "windows"]
        or readiness.get("publicationEligible") is not True
        or readiness.get("routeAuthority") is not True
        or readiness.get("releaseUploadAuthority") is not False
        or readiness.get("deployAuthority") is not False
        or readiness.get("sourceCandidateAuthoritySha256")
        != _sha(source_authority_raw)
    ):
        _blocked("Registry readiness receipt contract drifted")
    _reference(
        readiness.get("canonicalManifest"),
        path="RELEASE_CHANNEL.generated.json",
        raw=preprojection_canonical_raw,
        label="Registry readiness canonical manifest",
    )
    _reference(
        readiness.get("compatibilityManifest"),
        path="releases.json",
        raw=preprojection_compatibility_raw,
        label="Registry readiness compatibility manifest",
    )

    native, native_raw = tools._strict_json(
        Path(args.native_evidence), label="native Windows finalized evidence"
    )
    source_custody = source_authority.get("custody")
    if not isinstance(source_custody, dict):
        _blocked("source v4 custody is unavailable")
    if (
        native.get("status") != "passed"
        or readiness.get("nativeWindowsEvidenceSha256") != _sha(native_raw)
        or source_custody.get("nativeWindowsFinalizedEvidence") != native
    ):
        _blocked("v6 authority does not preserve the v4 native evidence bytes")
    source_canonical = _decode_embedded(
        source_custody.get("canonicalManifest"),
        label="source v4 canonical manifest",
        path="RELEASE_CHANNEL.generated.json",
    )
    source_compatibility = _decode_embedded(
        source_custody.get("compatibilityManifest"),
        label="source v4 compatibility manifest",
        path="releases.json",
    )
    if (
        readiness.get("sourceCanonicalManifestSha256") != _sha(source_canonical)
        or readiness.get("sourceCompatibilityManifestSha256")
        != _sha(source_compatibility)
    ):
        _blocked("Registry readiness receipt does not bind the v4 source manifests")
    for field in ("releaseProofSha256", "localizationGateSha256"):
        if not isinstance(readiness.get(field), str) or SHA256_RE.fullmatch(readiness[field]) is None:
            _blocked(f"Registry readiness {field} is invalid")

    expires_at = min(now + timedelta(seconds=lifetime), source_expiry)
    if expires_at <= now + timedelta(minutes=1):
        _blocked("v6 authority has insufficient remaining lifetime")
    custody = {
        "canonicalManifest": tools._embedded(
            "RELEASE_CHANNEL.generated.json", canonical_raw
        ),
        "compatibilityManifest": tools._embedded("releases.json", compatibility_raw),
        "inventory": tools._embedded(
            "CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory_raw
        ),
        "sourceCandidateAuthority": tools._embedded(
            SOURCE_AUTHORITY_PATH, source_authority_raw
        ),
        "publicationReadinessReceipt": tools._embedded(
            READINESS_PATH, readiness_raw
        ),
        "nativeWindowsFinalizedEvidence": tools._embedded(
            NATIVE_PATH, native_raw
        ),
        "preprojectionCanonicalManifest": tools._embedded(
            PREPROJECTION_CANONICAL_PATH, preprojection_canonical_raw
        ),
        "preprojectionCompatibilityManifest": tools._embedded(
            PREPROJECTION_COMPATIBILITY_PATH, preprojection_compatibility_raw
        ),
        "generationProjection": projection,
    }
    authority = {
        "contractName": V6_CONTRACT,
        "contractVersion": 6,
        "status": "candidate_import_ready",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "ownerNativeFinalizationBridgeAuthority": True,
        "ownerNativeStageAuthoritySeedBridgeAuthority": True,
        "previewPublicationReadinessBridgeAuthority": True,
        "publicationAuthorized": False,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "codeDeploymentAuthority": False,
        "platformScope": "windows_only",
        "exactIncomingDesktopScope": tools.EXACT_SCOPE_TUPLE,
        "crossRunBitReproducible": False,
        "signaturePolicy": {
            "signatureStatus": "unsigned",
            "signingRequired": False,
            "unsignedReason": "preview_policy",
        },
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": expires_at.isoformat().replace("+00:00", "Z"),
        "candidate": candidate,
        "custody": custody,
    }
    rendered = (
        json.dumps(authority, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    tools._atomic_write(Path(args.output), rendered)
    return authority


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize one proof-bound preview-ready v6 candidate authority."
    )
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--preprojection-bundle-root", required=True)
    parser.add_argument("--generation-projection-evaluated-at", required=True)
    parser.add_argument("--candidate-summary", required=True)
    parser.add_argument("--candidate-inventory", required=True)
    parser.add_argument("--source-v4-authority", required=True)
    parser.add_argument("--readiness-receipt", required=True)
    parser.add_argument("--native-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--authority-lifetime-seconds", type=int, default=MAX_LIFETIME_SECONDS
    )
    parser.add_argument("--now", default="", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        authority = materialize(args)
    except (OSError, PreviewReadyAuthorityBlocked, ValueError) as exc:
        print(f"preview-ready candidate authority blocked: {exc}", file=__import__("sys").stderr)
        return 1
    print(
        json.dumps(
            {
                "status": authority["status"],
                "bundleIdentitySha256": authority["candidate"]["bundleIdentitySha256"],
                "expiresAtUtc": authority["expiresAtUtc"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
