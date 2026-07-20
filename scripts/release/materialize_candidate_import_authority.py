#!/usr/bin/env python3
"""Seal one upload candidate behind fresh finalized native-Windows proof.

This command has no network or publication behavior.  It authenticates the
candidate tree and the exact finalized UI evidence already in operator custody,
then emits a bounded authority document whose embedded bytes can be placed in a
digest-bound public-projection snapshot.
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
import tempfile
from typing import Any, Iterable


AUTHORITY_CONTRACT = "chummer.release-upload.candidate-import-authority/v1"
INVENTORY_CONTRACT = "chummer.release-upload.candidate-inventory/v1"
CAPTURE_CONTRACT = "chummer6-ui.preview-nightly-native-windows-capture"
CAPTURE_INVENTORY_CONTRACT = "chummer6-ui.preview-nightly-native-windows-capture-inventory"
FINALIZATION_CONTRACT = "chummer6-ui.preview-nightly-native-windows-finalization"
FINALIZED_INVENTORY_CONTRACT = "chummer6-ui.preview-nightly-native-windows-finalized-inventory"
VISUAL_PROOF_CONTRACT = "chummer6-ui.windows_installer_visual_proof"
NATIVE_HOST_CONTRACT = "chummer6-ui.native_windows_host_evidence"
CANDIDATE_CONTENT_INVENTORY_CONTRACT = "chummer6-ui.preview-nightly-candidate-content-inventory"
CAPTURE_FILE = "WINDOWS_NATIVE_CAPTURE.generated.json"
CAPTURE_INVENTORY_FILE = "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"
FINALIZATION_FILE = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"
FINALIZED_INVENTORY_FILE = "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"
CANDIDATE_PROVENANCE_INVENTORY = (
    "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"
)
CANDIDATE_PROVENANCE_EXPORT = (
    "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json"
)
CAPTURE_WORKFLOW = ".github/workflows/windows-native-evidence-capture.yml"
FINALIZE_WORKFLOW = ".github/workflows/windows-native-evidence-finalize.yml"
UI_REPOSITORY = "ArchonMegalon/chummer6-ui"
PRODUCER_REF = "refs/heads/main"
RID = "win-x64"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REVIEWER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
HEAD_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_EVIDENCE_FILES = 512
MAX_AUTHORITY_LIFETIME_SECONDS = 6 * 60 * 60
DEFAULT_MAX_PROOF_AGE_SECONDS = 24 * 60 * 60


class CandidateAuthorityBlocked(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise CandidateAuthorityBlocked(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plain_file(path: Path, *, label: str, maximum_bytes: int | None = None) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CandidateAuthorityBlocked(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size < 1
        or (maximum_bytes is not None and metadata.st_size > maximum_bytes)
    ):
        _fail(f"{label} must be a bounded single-link regular file")
    return path


def _strict_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    path = _plain_file(path, label=label, maximum_bytes=MAX_JSON_BYTES)
    payload = path.read_bytes()

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateAuthorityBlocked(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value, payload


def _sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(f"{label} must be an exact lowercase SHA-256")
    return value


def _positive_int(value: object, *, label: str, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{label} is invalid")
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateAuthorityBlocked(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail(f"{label} must be expressed in UTC")
    return parsed.astimezone(timezone.utc)


def _fresh_timestamp(
    value: object,
    *,
    label: str,
    now: datetime,
    max_age: timedelta,
) -> datetime:
    parsed = _timestamp(value, label=label)
    if parsed > now + timedelta(minutes=5) or now - parsed > max_age:
        _fail(f"{label} is stale or future-dated")
    return parsed


def _identity_material(candidate: dict[str, Any]) -> bytes:
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
    return json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "version",
        "canonicalManifestSha256",
        "inventorySha256",
        "fileCount",
        "totalBytes",
        "bundleIdentitySha256",
    }
    if set(candidate) != expected or not isinstance(candidate.get("version"), str):
        _fail("candidate summary property set drifted")
    if VERSION_RE.fullmatch(candidate["version"]) is None:
        _fail("candidate version is invalid")
    for name in (
        "canonicalManifestSha256",
        "inventorySha256",
        "bundleIdentitySha256",
    ):
        _sha256(candidate.get(name), label=f"candidate {name}")
    _positive_int(candidate.get("fileCount"), label="candidate fileCount")
    _positive_int(candidate.get("totalBytes"), label="candidate totalBytes", allow_zero=True)
    expected_identity = hashlib.sha256(_identity_material(candidate)).hexdigest()
    if candidate["bundleIdentitySha256"] != expected_identity:
        _fail("candidate bundle identity does not bind its exact summary")
    return candidate


def _inventory_digest(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        encoded = row["path"].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(row["sizeBytes"].to_bytes(8, "big"))
        digest.update(bytes.fromhex(row["sha256"]))
    return digest.hexdigest()


def _validate_relative_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        _fail(f"{label} is not a canonical relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        _fail(f"{label} is not a canonical relative path")
    return value


def _inventory_rows(value: object, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 100_000:
        _fail(f"{label} must be a bounded non-empty list")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256", "sizeBytes"}:
            _fail(f"{label} row {index} drifted")
        rows.append(
            {
                "path": _validate_relative_path(raw.get("path"), label=f"{label} path"),
                "sha256": _sha256(raw.get("sha256"), label=f"{label} sha256"),
                "sizeBytes": _positive_int(
                    raw.get("sizeBytes"), label=f"{label} sizeBytes", allow_zero=True
                ),
            }
        )
    if rows != sorted(rows, key=lambda row: row["path"]) or len(
        {row["path"] for row in rows}
    ) != len(rows):
        _fail(f"{label} is not uniquely sorted")
    return rows


def _validate_bundle_inventory(
    bundle_root: Path,
    inventory: dict[str, Any],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    if (
        inventory.get("contractName") != INVENTORY_CONTRACT
        or inventory.get("contractVersion") != 1
        or set(inventory) != {"contractName", "contractVersion", "files"}
    ):
        _fail("candidate upload inventory contract drifted")
    rows = _inventory_rows(inventory.get("files"), label="candidate upload inventory")
    actual_rows: list[dict[str, Any]] = []
    for row in rows:
        path = bundle_root / row["path"]
        _plain_file(path, label=f"candidate file {row['path']}")
        actual_rows.append(
            {
                "path": row["path"],
                "sha256": _sha256_file(path),
                "sizeBytes": path.stat().st_size,
            }
        )
    if rows != actual_rows:
        _fail("candidate upload inventory does not match exact bundle bytes")
    if (
        len(rows) != candidate["fileCount"]
        or sum(row["sizeBytes"] for row in rows) != candidate["totalBytes"]
        or _inventory_digest(rows) != candidate["inventorySha256"]
    ):
        _fail("candidate upload inventory summary drifted")
    return rows


def _matching_alias(value: dict[str, Any], first: str, second: str, *, label: str) -> str:
    first_value = value.get(first)
    second_value = value.get(second)
    if first_value is not None and second_value is not None and first_value != second_value:
        _fail(f"{label} aliases disagree")
    selected = first_value if first_value is not None else second_value
    if not isinstance(selected, str) or not selected:
        _fail(f"{label} is missing")
    return selected


def _canonical_windows_scope(
    manifest: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    version = _matching_alias(
        manifest, "version", "releaseVersion", label="candidate release version"
    )
    channel = _matching_alias(
        manifest, "channelId", "channel", label="candidate release channel"
    )
    coverage = manifest.get("desktopTupleCoverage")
    heads_value = coverage.get("requiredDesktopHeads") if isinstance(coverage, dict) else None
    if (
        not isinstance(heads_value, list)
        or not heads_value
        or any(not isinstance(head, str) or HEAD_RE.fullmatch(head) is None for head in heads_value)
        or len(set(heads_value)) != len(heads_value)
    ):
        _fail("candidate requiredDesktopHeads is invalid")
    heads = tuple(heads_value)
    artifacts_value = manifest.get("artifacts")
    if not isinstance(artifacts_value, list) or not artifacts_value:
        _fail("candidate release manifest has no artifacts")
    candidate_by_path = {row["path"]: row for row in candidate_rows}
    scope_by_head: dict[str, dict[str, Any]] = {}
    for head in heads:
        matching = [
            artifact
            for artifact in artifacts_value
            if isinstance(artifact, dict)
            and artifact.get("head") == head
            and artifact.get("platform") == "windows"
            and artifact.get("rid") == RID
        ]
        installers = [artifact for artifact in matching if artifact.get("kind") == "installer"]
        payloads = [
            artifact
            for artifact in matching
            if artifact.get("kind") in {"archive", "payload"}
            and str(artifact.get("fileName") or "").endswith("-payload.zip")
        ]
        if len(installers) != 1 or len(payloads) != 1:
            _fail(f"candidate manifest must name one Windows installer and payload for {head}")
        scope_by_head[head] = {}
        for role, artifact in (("installer", installers[0]), ("payload", payloads[0])):
            file_name = artifact.get("fileName")
            digest = artifact.get("sha256")
            size = artifact.get("sizeBytes")
            if (
                not isinstance(file_name, str)
                or not file_name
                or "/" in file_name
                or "\\" in file_name
                or SHA256_RE.fullmatch(str(digest or "")) is None
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size < 1
                or role == "installer"
                and not file_name.lower().endswith(".exe")
            ):
                _fail(f"candidate {head} {role} artifact metadata is invalid")
            path = f"files/{file_name}"
            candidate_row = candidate_by_path.get(path)
            if candidate_row != {"path": path, "sha256": digest, "sizeBytes": size}:
                _fail(f"candidate {head} {role} manifest bytes differ from upload inventory")
            scope_by_head[head][role] = {
                "path": path,
                "fileName": file_name,
                "sha256": digest,
                "sizeBytes": size,
            }
    return {
        "version": version,
        "channel": channel,
        "heads": heads,
        "artifacts": scope_by_head,
    }


def _exact_tree_rows(root: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _fail("finalized native-Windows evidence contains a symbolic link")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _fail("finalized native-Windows evidence contains a non-regular file")
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        rows.append(
            {"path": relative, "sha256": _sha256_file(path), "sizeBytes": metadata.st_size}
        )
        if len(rows) > MAX_EVIDENCE_FILES:
            _fail("finalized native-Windows evidence file count is unbounded")
    return rows


def _source(value: object, *, label: str, workflow: str) -> dict[str, Any]:
    required = {
        "repository",
        "workflow",
        "runId",
        "runAttempt",
        "ref",
        "sha",
        "actor",
        "artifactName",
    }
    if not isinstance(value, dict) or set(value) != required:
        _fail(f"{label} property set drifted")
    if value.get("repository") != UI_REPOSITORY or value.get("workflow") != workflow:
        _fail(f"{label} repository/workflow drifted")
    if value.get("ref") != PRODUCER_REF or not isinstance(value.get("sha"), str) or COMMIT_RE.fullmatch(value["sha"]) is None:
        _fail(f"{label} source revision drifted")
    for name in ("runId", "runAttempt", "actor", "artifactName"):
        if not isinstance(value.get(name), str) or not value[name].strip():
            _fail(f"{label} {name} is missing")
    return value


def _validate_candidate_provenance(
    root: Path,
    *,
    bundle_root: Path,
    canonical_manifest_sha256: str,
    scope: dict[str, Any],
) -> dict[str, Any]:
    inventory, _ = _strict_json(
        root / CANDIDATE_PROVENANCE_INVENTORY,
        label="native-Windows candidate provenance inventory",
    )
    if (
        inventory.get("contractName") != CANDIDATE_CONTENT_INVENTORY_CONTRACT
        or inventory.get("contractVersion") != 1
        or inventory.get("release")
        != {"channel": scope["channel"], "version": scope["version"]}
        or inventory.get("manifest")
        != {"path": "RELEASE_CHANNEL.generated.json", "sha256": canonical_manifest_sha256}
    ):
        _fail("native-Windows candidate provenance inventory release binding drifted")
    required_paths = [
        "RELEASE_CHANNEL.generated.json",
        *[
            artifact["path"]
            for head in scope["heads"]
            for artifact in (
                scope["artifacts"][head]["installer"],
                scope["artifacts"][head]["payload"],
            )
        ],
    ]
    rows = _inventory_rows(inventory.get("files"), label="native-Windows candidate content inventory")
    if [row["path"] for row in rows] != sorted(required_paths):
        _fail("native-Windows proof does not bind the exact required-head candidate content set")
    for row in rows:
        path = bundle_root / row["path"]
        _plain_file(path, label=f"native-Windows candidate byte {row['path']}")
        if row["sha256"] != _sha256_file(path) or row["sizeBytes"] != path.stat().st_size:
            _fail("native-Windows proof candidate bytes differ from the upload candidate")
    return inventory


def _validate_native_evidence(
    root: Path,
    *,
    bundle_root: Path,
    canonical_manifest_sha256: str,
    scope: dict[str, Any],
    now: datetime,
    max_age: timedelta,
) -> tuple[dict[str, Any], datetime, list[tuple[str, bytes]]]:
    if root.is_symlink() or not root.is_dir():
        _fail("finalized native-Windows evidence root must be a real directory")
    finalized_inventory, finalized_inventory_bytes = _strict_json(
        root / FINALIZED_INVENTORY_FILE,
        label="finalized native-Windows inventory",
    )
    if (
        finalized_inventory.get("contractName") != FINALIZED_INVENTORY_CONTRACT
        or finalized_inventory.get("contractVersion") != 1
    ):
        _fail("finalized native-Windows inventory contract drifted")
    finalized_rows = _inventory_rows(
        finalized_inventory.get("files"), label="finalized native-Windows inventory"
    )
    if finalized_rows != _exact_tree_rows(root, exclude={FINALIZED_INVENTORY_FILE}):
        _fail("finalized native-Windows inventory does not match its exact artifact tree")
    finalized_by_path = {row["path"]: row for row in finalized_rows}

    finalization, finalization_bytes = _strict_json(
        root / FINALIZATION_FILE, label="native-Windows finalization receipt"
    )
    if (
        finalization.get("contractName") != FINALIZATION_CONTRACT
        or finalization.get("contractVersion") != 1
        or finalization.get("status") != "passed"
        or finalization.get("humanReviewConfirmed") is not True
        or finalization.get("reviewerWasCaptureActor") is not False
    ):
        _fail("native-Windows finalization is not a protected human pass")
    finalized_at = _fresh_timestamp(
        finalization.get("generatedAt"),
        label="native-Windows finalization generatedAt",
        now=now,
        max_age=max_age,
    )
    reviewer = finalization.get("reviewer")
    if not isinstance(reviewer, str) or REVIEWER_RE.fullmatch(reviewer) is None:
        _fail("native-Windows finalization reviewer provenance is invalid")
    capture_source = _source(
        finalization.get("captureSource"),
        label="native-Windows capture source",
        workflow=CAPTURE_WORKFLOW,
    )
    finalization_source = _source(
        finalization.get("finalizationSource"),
        label="native-Windows finalization source",
        workflow=FINALIZE_WORKFLOW,
    )
    if (
        capture_source["actor"] != "github-actions[bot]"
        or finalization_source["actor"] != reviewer
        or reviewer == capture_source["actor"]
        or capture_source["sha"] != finalization_source["sha"]
    ):
        _fail("native-Windows protected reviewer provenance drifted")

    capture, capture_bytes = _strict_json(
        root / CAPTURE_FILE, label="native-Windows capture receipt"
    )
    if (
        capture.get("contractName") != CAPTURE_CONTRACT
        or capture.get("contractVersion") != 1
        or capture.get("status") != "captured"
        or capture.get("captureMode") != "interactive"
        or capture.get("source") != capture_source
    ):
        _fail("native-Windows capture receipt drifted")
    captured_at = _fresh_timestamp(
        capture.get("generatedAt"),
        label="native-Windows capture generatedAt",
        now=now,
        max_age=max_age,
    )
    version = str(capture.get("version") or "")
    channel = str(capture.get("channelId") or "")
    if (
        version != scope["version"]
        or channel != scope["channel"]
        or VERSION_RE.fullmatch(version) is None
    ):
        _fail("native-Windows capture release identity is invalid")
    candidate_binding = capture.get("candidate")
    if (
        not isinstance(candidate_binding, dict)
        or candidate_binding.get("manifestSha256") != canonical_manifest_sha256
    ):
        _fail("native-Windows capture does not bind the candidate manifest")
    provenance_inventory = _validate_candidate_provenance(
        root,
        bundle_root=bundle_root,
        canonical_manifest_sha256=canonical_manifest_sha256,
        scope=scope,
    )
    provenance_path = root / CANDIDATE_PROVENANCE_INVENTORY
    if candidate_binding.get("contentInventorySha256") != _sha256_file(provenance_path):
        _fail("native-Windows capture candidate inventory digest drifted")

    capture_inventory, capture_inventory_bytes = _strict_json(
        root / CAPTURE_INVENTORY_FILE, label="native-Windows capture inventory"
    )
    if (
        capture_inventory.get("contractName") != CAPTURE_INVENTORY_CONTRACT
        or capture_inventory.get("contractVersion") != 1
        or capture_inventory.get("captureManifestSha256")
        != hashlib.sha256(capture_bytes).hexdigest()
        or not isinstance(capture_inventory.get("files"), list)
    ):
        _fail("native-Windows capture inventory binding drifted")
    if finalization.get("captureInventorySha256") != hashlib.sha256(capture_inventory_bytes).hexdigest():
        _fail("native-Windows finalization capture inventory binding drifted")

    proof_rows = finalization.get("proofs")
    if not isinstance(proof_rows, list) or len(proof_rows) != len(scope["heads"]):
        _fail("native-Windows finalization must bind every required-head visual proof exactly once")
    proof_by_head: dict[str, tuple[str, bytes, dict[str, Any]]] = {}
    custody: list[tuple[str, bytes]] = [
        (CAPTURE_FILE, capture_bytes),
        (CAPTURE_INVENTORY_FILE, capture_inventory_bytes),
        (FINALIZATION_FILE, finalization_bytes),
        (FINALIZED_INVENTORY_FILE, finalized_inventory_bytes),
    ]
    for row in proof_rows:
        if not isinstance(row, dict) or set(row) != {"headId", "path", "sha256"}:
            _fail("native-Windows finalization proof binding drifted")
        head = row.get("headId")
        if head not in scope["heads"] or head in proof_by_head:
            _fail("native-Windows finalization proof head drifted")
        relative = _validate_relative_path(row.get("path"), label="native-Windows visual proof path")
        proof, proof_bytes = _strict_json(root / relative, label=f"{head} visual proof")
        if row.get("sha256") != hashlib.sha256(proof_bytes).hexdigest():
            _fail("native-Windows visual proof digest drifted")
        finalized_row = finalized_by_path.get(relative)
        if finalized_row != {
            "path": relative,
            "sha256": row["sha256"],
            "sizeBytes": len(proof_bytes),
        }:
            _fail("native-Windows visual proof finalized inventory binding drifted")
        proof_by_head[head] = (relative, proof_bytes, proof)
        custody.append((relative, proof_bytes))

    for head in scope["heads"]:
        relative, _proof_bytes, proof = proof_by_head[head]
        installer_artifact = scope["artifacts"][head]["installer"]
        payload_artifact = scope["artifacts"][head]["payload"]
        installer_name = installer_artifact["fileName"]
        payload_name = payload_artifact["fileName"]
        installer = bundle_root / installer_artifact["path"]
        payload = bundle_root / payload_artifact["path"]
        startup_relative = f"startup-smoke/startup-smoke-{head}-{RID}.receipt.json"
        startup, startup_bytes = _strict_json(
            root / startup_relative, label=f"{head} native startup receipt"
        )
        if finalized_by_path.get(startup_relative) != {
            "path": startup_relative,
            "sha256": hashlib.sha256(startup_bytes).hexdigest(),
            "sizeBytes": len(startup_bytes),
        }:
            _fail(f"{head} startup proof finalized inventory binding drifted")
        native = startup.get("nativeHostEvidence")
        if (
            startup.get("status") != "pass"
            or startup.get("executionEnvironment") != "native_windows"
            or startup.get("headId") != head
            or startup.get("platform") != "windows"
            or startup.get("rid") != RID
            or startup.get("releaseVersion") != version
            or startup.get("channelId") != channel
            or startup.get("artifactFileName") != installer_name
            or startup.get("artifactDigest") != f"sha256:{installer_artifact['sha256']}"
            or startup.get("bootstrapPayloadAcquisitionMode") != "download"
            or startup.get("bootstrapPayloadFileName") != payload_name
            or startup.get("bootstrapPayloadSha256") != payload_artifact["sha256"]
            or startup.get("bootstrapPayloadSizeBytes") != payload_artifact["sizeBytes"]
            or not isinstance(native, dict)
            or native.get("contractName") != NATIVE_HOST_CONTRACT
            or native.get("status") != "verified"
            or native.get("isNativeWindows") is not True
            or native.get("hostPlatform") != "windows"
            or "wine" in str(native.get("runner") or "").lower()
        ):
            _fail(f"{head} startup proof is not exact native-Windows evidence")
        _fresh_timestamp(
            proof.get("generatedAt"),
            label=f"{head} visual proof generatedAt",
            now=now,
            max_age=max_age,
        )
        screenshots = proof.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != 2:
            _fail(f"{head} visual proof screenshot set drifted")
        screenshot_roles: set[str] = set()
        for screenshot in screenshots:
            if not isinstance(screenshot, dict) or set(screenshot) != {"role", "path", "sha256"}:
                _fail(f"{head} visual proof screenshot binding drifted")
            role = screenshot.get("role")
            path = _validate_relative_path(
                screenshot.get("path"), label=f"{head} visual proof screenshot path"
            )
            digest = _sha256(
                screenshot.get("sha256"), label=f"{head} visual proof screenshot digest"
            )
            if role not in {"progress", "completion"} or role in screenshot_roles:
                _fail(f"{head} visual proof screenshot role drifted")
            screenshot_roles.add(role)
            finalized_row = finalized_by_path.get(path)
            if finalized_row is None or finalized_row["sha256"] != digest:
                _fail(f"{head} visual proof screenshot finalized inventory binding drifted")
        if (
            proof.get("contractName") != VISUAL_PROOF_CONTRACT
            or proof.get("status") != "passed"
            or proof.get("headId") != head
            or proof.get("platform") != "windows"
            or proof.get("rid") != RID
            or proof.get("releaseVersion") != version
            or proof.get("channelId") != channel
            or proof.get("artifactFileName") != installer_name
            or proof.get("artifactDigest") != f"sha256:{installer_artifact['sha256']}"
            or proof.get("checks")
            != {"capture_mode": "interactive", "human_review_confirmed": True}
            or proof.get("readabilityReview")
            != {"status": "passed", "reviewer": reviewer}
            or proof.get("contrastReview")
            != {"status": "passed", "reviewer": reviewer}
            or proof.get("clippingReview")
            != {"status": "passed", "reviewer": reviewer}
            or proof.get("finalizationBinding") != finalization_source
        ):
            _fail(f"{head} visual proof is not an exact finalized human pass")
        custody.append((startup_relative, startup_bytes))

    for relative in (CANDIDATE_PROVENANCE_INVENTORY, CANDIDATE_PROVENANCE_EXPORT):
        evidence_document, evidence_bytes = _strict_json(
            root / relative, label=f"native-Windows {relative}"
        )
        if relative == CANDIDATE_PROVENANCE_EXPORT and (
            evidence_document.get("contractName")
            != "chummer6-ui.preview-nightly-candidate-export"
            or evidence_document.get("contractVersion") != 1
            or evidence_document.get("status") != "exported"
        ):
            _fail("native-Windows candidate export receipt drifted")
        custody.append((relative, evidence_bytes))

    evidence_summary = {
        "status": "passed",
        "captureGeneratedAtUtc": captured_at.isoformat().replace("+00:00", "Z"),
        "finalizationGeneratedAtUtc": finalized_at.isoformat().replace("+00:00", "Z"),
        "reviewer": reviewer,
        "captureSource": capture_source,
        "finalizationSource": finalization_source,
        "candidateContentInventorySha256": _sha256_file(provenance_path),
        "candidateContentInventory": provenance_inventory,
    }
    oldest = min(captured_at, finalized_at)
    return evidence_summary, oldest, custody


def _embedded(path: str, payload: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sizeBytes": len(payload),
        "base64": base64.b64encode(payload).decode("ascii"),
    }


def _atomic_write(path: Path, payload: bytes) -> None:
    parent = path.parent.resolve(strict=True)
    if path.exists() or path.is_symlink():
        _fail("candidate import authority output must not already exist")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    bundle_root = Path(args.bundle_root).resolve(strict=True)
    if not bundle_root.is_dir() or bundle_root.is_symlink():
        _fail("candidate bundle root must be a real directory")
    candidate, _ = _strict_json(Path(args.candidate_summary), label="candidate summary")
    _validate_candidate(candidate)
    inventory, inventory_bytes = _strict_json(
        Path(args.candidate_inventory), label="candidate upload inventory"
    )
    candidate_rows = _validate_bundle_inventory(bundle_root, inventory, candidate)
    canonical_manifest = _plain_file(
        Path(args.canonical_manifest), label="candidate canonical manifest", maximum_bytes=MAX_JSON_BYTES
    )
    canonical, canonical_bytes = _strict_json(
        canonical_manifest, label="candidate canonical manifest"
    )
    canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
    if canonical_digest != candidate["canonicalManifestSha256"]:
        _fail("candidate canonical manifest digest differs from its summary")
    if canonical_manifest.resolve() != (bundle_root / "RELEASE_CHANNEL.generated.json").resolve():
        _fail("candidate canonical manifest must be the upload tree RELEASE_CHANNEL.generated.json")
    scope = _canonical_windows_scope(canonical, candidate_rows)
    if scope["version"] != candidate["version"]:
        _fail("candidate release version differs from its upload summary")

    now = _timestamp(args.now, label="materialization time") if args.now else datetime.now(timezone.utc)
    max_age_seconds = _positive_int(args.max_proof_age_seconds, label="max proof age seconds")
    lifetime_seconds = _positive_int(args.authority_lifetime_seconds, label="authority lifetime seconds")
    if max_age_seconds > DEFAULT_MAX_PROOF_AGE_SECONDS or lifetime_seconds > MAX_AUTHORITY_LIFETIME_SECONDS:
        _fail("candidate authority freshness budget exceeds its hard maximum")
    max_age = timedelta(seconds=max_age_seconds)
    evidence, oldest_proof, custody_files = _validate_native_evidence(
        Path(args.windows_finalized_root).resolve(strict=True),
        bundle_root=bundle_root,
        canonical_manifest_sha256=canonical_digest,
        scope=scope,
        now=now,
        max_age=max_age,
    )
    expires_at = min(now + timedelta(seconds=lifetime_seconds), oldest_proof + max_age)
    if expires_at <= now + timedelta(minutes=1):
        _fail("fresh native-Windows evidence has insufficient remaining authority lifetime")
    authority = {
        "contractName": AUTHORITY_CONTRACT,
        "contractVersion": 1,
        "status": "candidate_import_ready",
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": expires_at.isoformat().replace("+00:00", "Z"),
        "candidate": candidate,
        "custody": {
            "canonicalManifest": _embedded("RELEASE_CHANNEL.generated.json", canonical_bytes),
            "inventory": _embedded("CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory_bytes),
            "nativeWindowsFinalizedEvidence": {
                **evidence,
                "files": [_embedded(path, payload) for path, payload in sorted(custody_files)],
            },
        },
    }
    rendered = (
        json.dumps(authority, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    _atomic_write(Path(args.output), rendered)
    return authority


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize one fresh, exact candidate-import authority."
    )
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--canonical-manifest", required=True)
    parser.add_argument("--candidate-summary", required=True)
    parser.add_argument("--candidate-inventory", required=True)
    parser.add_argument("--windows-finalized-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--max-proof-age-seconds", type=int, default=DEFAULT_MAX_PROOF_AGE_SECONDS
    )
    parser.add_argument(
        "--authority-lifetime-seconds", type=int, default=MAX_AUTHORITY_LIFETIME_SECONDS
    )
    parser.add_argument("--now", default="", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    if tuple(__import__("sys").version_info) < (3, 11):
        print("candidate import authority requires Python 3.11 or newer", file=__import__("sys").stderr)
        return 2
    args = _parser().parse_args(argv)
    try:
        authority = materialize(args)
    except (CandidateAuthorityBlocked, OSError, ValueError) as exc:
        print(f"candidate import authority blocked: {exc}", file=__import__("sys").stderr)
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
