#!/usr/bin/env python3
"""Materialize one provider-authenticated public-download successor authority.

The candidate-import v4 contract remains an identity/custody contract whose
publication, deployment, and route authority fields are false.  This module
never widens those fields.  It combines those exact candidate bytes with a
separate GitHub-provider decision, an already completed ordinary topology-B
retirement, and the exact post-retirement Cloudflare configuration to authorize
one fresh sidecar cutover.
"""

from __future__ import annotations

import argparse
import copy
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any
import urllib.error
import urllib.request
import zipfile


PUBLIC_DOWNLOAD_SUCCESSOR_DECISION_FILENAME = (
    "PUBLIC_DOWNLOAD_SUCCESSOR_DECISION.generated.json"
)
PUBLIC_DOWNLOAD_SUCCESSOR_DECISION_CONTRACT = (
    "chummer.public-download-successor-decision/v1"
)
PUBLIC_DOWNLOAD_SUCCESSOR_AUTHORITY_CONTRACT = (
    "chummer.public-download-successor-authority/v1"
)
PUBLIC_DOWNLOAD_SUCCESSOR_SERVING_AUTHORITY_CONTRACT = (
    "chummer.public-download-successor-serving-authority/v1"
)

# Short aliases are intentionally public for controller and test consumers.
DECISION_ARTIFACT_FILENAME = PUBLIC_DOWNLOAD_SUCCESSOR_DECISION_FILENAME
DECISION_CONTRACT = PUBLIC_DOWNLOAD_SUCCESSOR_DECISION_CONTRACT
SUCCESSOR_AUTHORITY_CONTRACT = PUBLIC_DOWNLOAD_SUCCESSOR_AUTHORITY_CONTRACT
SERVING_AUTHORITY_CONTRACT = (
    PUBLIC_DOWNLOAD_SUCCESSOR_SERVING_AUTHORITY_CONTRACT
)

SOURCE_REPOSITORY = "ArchonMegalon/chummer6-hub"
SOURCE_REF = "refs/heads/main"
WORKFLOW_PATH = ".github/workflows/public-download-successor-decision.yml"
SOLE_OPERATOR_GITHUB_LOGIN = "ArchonMegalon"
SOLE_OPERATOR_GITHUB_ACTOR_ID = 11421547
CUTOVER_OPERATION = "initial-release-shelf-public-download-cutover"
RETIRE_OPERATION = "initial-release-shelf-public-download-cutover-retire"
EXACT_INCOMING_SCOPE = "avalonia:windows:win-x64"
SUCCESSOR_ORIGIN = "http://172.17.0.1:18091"
PUBLIC_HOSTS = ("chummer.run", "www.chummer.run")
V4_CONTRACT = "chummer.release-upload.candidate-import-authority/v4"
GITHUB_API_ROOT = f"https://api.github.com/repos/{SOURCE_REPOSITORY}"
GITHUB_WEB_ROOT = f"https://github.com/{SOURCE_REPOSITORY}"
GITHUB_API_VERSION = "2026-03-10"
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_DECISION_LIFETIME = timedelta(hours=24)

SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TRANSITION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{7,80}$")
PROJECT_NAME = re.compile(r"^chummer-public-download-[a-z0-9-]{8,80}$")
ACCOUNT_ID = re.compile(r"^[0-9a-f]{32}$")
TUNNEL_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-"
    r"(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)

V4_ROOT_FIELDS = {
    "candidate",
    "candidateImportAuthority",
    "candidateReviewAuthority",
    "codeDeploymentAuthority",
    "contractName",
    "contractVersion",
    "crossRunBitReproducible",
    "custody",
    "deployAuthority",
    "exactIncomingDesktopScope",
    "expiresAtUtc",
    "generatedAtUtc",
    "ownerNativeFinalizationBridgeAuthority",
    "platformScope",
    "publicationAuthorized",
    "publicationEligible",
    "releaseUploadAuthority",
    "routeAuthority",
    "signaturePolicy",
    "status",
}
V4_CUSTODY_FIELDS = {
    "canonicalManifest",
    "compatibilityManifest",
    "inventory",
    "nativeWindowsFinalizedEvidence",
    "registryFinalization",
    "registryFinalizeAuthority",
    "registryFinalizeReceipt",
    "registryPrepareCandidateReceipt",
    "unsignedPublicationEvidence",
}
CANDIDATE_FIELDS = {
    "bundleIdentitySha256",
    "canonicalManifestSha256",
    "fileCount",
    "inventorySha256",
    "totalBytes",
    "version",
}
CANDIDATE_AUTHORITY_CEILING = {
    "candidateImportAuthority": True,
    "candidateReviewAuthority": True,
    "codeDeploymentAuthority": False,
    "deployAuthority": False,
    "ownerNativeFinalizationBridgeAuthority": True,
    "publicationAuthorized": False,
    "publicationEligible": False,
    "releaseUploadAuthority": False,
    "routeAuthority": False,
}

DECISION_FIELDS = {
    "authorizedAtUtc",
    "candidateAuthoritySha256",
    "contractName",
    "contractVersion",
    "decision",
    "exactIncomingDesktopScope",
    "expiresAtUtc",
    "operation",
    "provider",
    "publicServing",
    "release",
    "status",
    "transitionId",
}
DECISION_OPERATION_FIELDS = {"name", "projectName", "root"}
DECISION_PROVIDER_FIELDS = {
    "actor",
    "actorId",
    "eventName",
    "ref",
    "refProtected",
    "repository",
    "runAttempt",
    "runId",
    "sourceHead",
    "triggeringActor",
    "workflow",
}
DECISION_RELEASE_FIELDS = {"generationId", "version"}
DECISION_SERVING_FIELDS = {"origin", "publicHosts"}
DECISION_PREDECESSOR_FIELDS = {
    "operationJournalSha256",
    "operationRoot",
    "projectName",
    "retainedGenerationId",
    "retainedShelfTreeSha256",
    "retiredAuthoritySha256",
    "retirementSha256",
    "shelfReceiptSha256",
}
DECISION_FIELDS.add("predecessor")

TERMINAL_RETIREMENT_FIELDS = {
    "cleanupSha256",
    "completedAtUtc",
    "connectorGateSha256",
    "contractName",
    "controllerSourceHead",
    "incumbentBaselineSha256",
    "incumbentObservationSha256",
    "latestConnectorGateSha256",
    "operation",
    "operationRoot",
    "operationSourceHead",
    "postMarkerConnectorGateSha256",
    "priorConfigSha256",
    "projectName",
    "restoredVersion",
    "retiredAuthorityPath",
    "retiredAuthoritySha256",
    "retirementEvidencePath",
    "retirementEvidenceSha256",
    "status",
}
OPERATION_JOURNAL_FIELDS = {
    "bindAddress",
    "bindPort",
    "canonicalProject",
    "canonicalShelfRoot",
    "createdAtUtc",
    "incumbentBaseline",
    "operation",
    "operationRoot",
    "phase",
    "projectName",
    "receipts",
    "schema",
    "sourceHead",
    "updatedAtUtc",
    "volumes",
}
SIDECAR_SHELF_FIELDS = {
    "activationCandidateSha256",
    "activationReceiptId",
    "canonicalMirrorSha256",
    "compatibilityMirrorSha256",
    "contractName",
    "generationCanonicalSha256",
    "generationCompatibilitySha256",
    "generationId",
    "generationRoot",
    "incumbentMigrationAuthority",
    "inventoryDigest",
    "pointerSha256",
    "releaseCandidateAuthority",
    "shelfTreeSha256",
    "sourceHead",
    "status",
    "writerPolicy",
}
RETIRED_AUTHORITY_RECEIPT_FIELDS = {
    "activeAuthorityPath",
    "activeAuthoritySha256",
    "connectorGateSha256",
    "contractName",
    "disposition",
    "retiredAtUtc",
    "retiredAuthorityPath",
    "retirementEvidenceSha256",
    "status",
}
TERMINAL_SHA_FIELDS = {
    "cleanupSha256",
    "connectorGateSha256",
    "incumbentBaselineSha256",
    "incumbentObservationSha256",
    "latestConnectorGateSha256",
    "postMarkerConnectorGateSha256",
    "priorConfigSha256",
    "retiredAuthoritySha256",
    "retirementEvidenceSha256",
}


class SuccessorAuthorityError(ValueError):
    """The requested successor authority cannot be proven exactly."""


class LiveGitHubApi:
    """Bounded public GitHub REST reader used at both materialize and verify."""

    def _get(self, url: str, *, label: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "chummer-public-download-successor/1",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if (
                    response.status != 200
                    or response.geturl() != url
                    or "application/json"
                    not in str(response.headers.get("Content-Type", ""))
                ):
                    raise SuccessorAuthorityError(
                        f"{label} did not return the exact GitHub JSON resource"
                    )
                raw = response.read(MAX_JSON_BYTES + 1)
        except SuccessorAuthorityError:
            raise
        except (OSError, urllib.error.URLError) as exc:
            raise SuccessorAuthorityError(
                f"{label} could not be fetched from GitHub"
            ) from exc
        if not 1 <= len(raw) <= MAX_JSON_BYTES:
            raise SuccessorAuthorityError(
                f"{label} exceeded its bounded response size"
            )
        return _strict_json(raw, label)

    def get_workflow_run(self, run_id: int) -> dict[str, Any]:
        return self._get(
            f"{GITHUB_API_ROOT}/actions/runs/{run_id}",
            label="live GitHub workflow-run response",
        )

    def get_artifact(self, artifact_id: int) -> dict[str, Any]:
        return self._get(
            f"{GITHUB_API_ROOT}/actions/artifacts/{artifact_id}",
            label="live GitHub artifact response",
        )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise SuccessorAuthorityError(f"{label} must be a lowercase SHA-256")
    return value


def _require_commit(value: Any, label: str) -> str:
    if not isinstance(value, str) or COMMIT.fullmatch(value) is None:
        raise SuccessorAuthorityError(f"{label} must be a lowercase full commit")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SuccessorAuthorityError(f"{label} must be a positive JSON integer")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise SuccessorAuthorityError(
            f"{label} must be whole-second canonical UTC"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError as exc:
        raise SuccessorAuthorityError(
            f"{label} must be whole-second canonical UTC"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise SuccessorAuthorityError(
            f"{label} must be whole-second canonical UTC"
        )
    return parsed


def _utc_now(now: datetime | None = None) -> datetime:
    value = datetime.now(UTC) if now is None else now
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise SuccessorAuthorityError("observation time must be UTC")
    return value.astimezone(UTC).replace(microsecond=0)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise ValueError(f"duplicate or case-shadowed key {key}")
            folded.add(normalized)
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SuccessorAuthorityError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SuccessorAuthorityError(f"{label} must be a JSON object")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SuccessorAuthorityError(
            "authority contains a non-canonical JSON value"
        ) from exc


def _same_json(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(
                _same_json(actual[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _same_json(left, right)
                for left, right in zip(actual, expected, strict=True)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _canonical_absolute_path(value: Path | str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path != Path(os.path.normpath(str(path))):
        raise SuccessorAuthorityError(f"{label} must be a canonical absolute path")
    return path


def _operation_identity(operation_root: Path, project_name: str) -> None:
    if (
        PROJECT_NAME.fullmatch(project_name) is None
        or operation_root.name != project_name
    ):
        raise SuccessorAuthorityError(
            "successor operation root and project identity disagree"
        )


def _stable_regular_bytes(
    path: Path | str,
    *,
    label: str,
    maximum_bytes: int | None = MAX_JSON_BYTES,
) -> bytes:
    candidate = _canonical_absolute_path(path, label)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise SuccessorAuthorityError(f"{label} could not be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_mode & 0o022
            or before.st_size < 1
            or (
                maximum_bytes is not None
                and before.st_size > maximum_bytes
            )
        ):
            raise SuccessorAuthorityError(
                f"{label} must be a caller-owned single-link regular file "
                "not writable by other users"
            )
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
        item.st_uid,
    )
    try:
        final = os.lstat(candidate)
    except OSError as exc:
        raise SuccessorAuthorityError(f"{label} changed during read") from exc
    if (
        identity(before) != identity(after)
        or len(raw) != before.st_size
        or stat.S_ISLNK(final.st_mode)
        or identity(after) != identity(final)
    ):
        raise SuccessorAuthorityError(f"{label} changed during read")
    return raw


def _tree_file_bytes(path: Path, label: str) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SuccessorAuthorityError(
            f"{label} contains an unreadable file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_mode & 0o022
        ):
            raise SuccessorAuthorityError(
                f"{label} contains an unsafe file"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_uid,
    )
    if identity(before) != identity(after):
        raise SuccessorAuthorityError(f"{label} changed while hashed")
    return b"".join(chunks)


def _tree_sha256_file_stream(root: Path, *, label: str) -> str:
    """Implement the controller's exact ``sha256-file-tree-v1`` stream."""

    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise SuccessorAuthorityError(f"{label} root is unavailable") from exc
    if (
        not root.is_absolute()
        or root.resolve(strict=True) != root
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or root_metadata.st_mode & 0o022
    ):
        raise SuccessorAuthorityError(f"{label} root is unsafe")
    files: list[tuple[bytes, str, Path]] = []

    def walk(directory: Path, relative: str) -> None:
        before = directory.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o022
        ):
            raise SuccessorAuthorityError(
                f"{label} contains an unsafe directory"
            )
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise SuccessorAuthorityError(
                f"{label} directory is unreadable"
            ) from exc
        for entry in entries:
            if "\n" in entry.name or "\r" in entry.name:
                raise SuccessorAuthorityError(
                    f"{label} contains an unsafe path name"
                )
            child = directory / entry.name
            child_relative = (
                entry.name if not relative else f"{relative}/{entry.name}"
            )
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise SuccessorAuthorityError(
                    f"{label} contains a symbolic link"
                )
            if stat.S_ISDIR(metadata.st_mode):
                walk(child, child_relative)
            elif stat.S_ISREG(metadata.st_mode):
                if (
                    metadata.st_uid != os.geteuid()
                    or metadata.st_nlink != 1
                    or metadata.st_mode & 0o022
                ):
                    raise SuccessorAuthorityError(
                        f"{label} contains an unsafe file"
                    )
                display = f"./{child_relative}"
                files.append((os.fsencode(display), display, child))
            else:
                raise SuccessorAuthorityError(
                    f"{label} contains a special entry"
                )
        after = directory.lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_uid,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_uid,
        ):
            raise SuccessorAuthorityError(
                f"{label} directory changed while hashed"
            )

    walk(root, "")
    stream = hashlib.sha256()
    for _sort_key, display, path in sorted(files, key=lambda row: row[0]):
        digest = hashlib.sha256(_tree_file_bytes(path, label)).hexdigest()
        stream.update(f"{digest}  {display}\n".encode("utf-8"))
    return stream.hexdigest()


def _write_new(path: Path | str, raw: bytes, *, mode: int) -> Path:
    target = _canonical_absolute_path(path, "output")
    try:
        parent = target.parent.resolve(strict=True)
        metadata = parent.stat()
    except OSError as exc:
        raise SuccessorAuthorityError("output parent is unavailable") from exc
    if (
        parent != target.parent
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise SuccessorAuthorityError(
            "output parent must be caller-owned and not writable by other users"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise SuccessorAuthorityError("output already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        directory = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return target


def _safe_id(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or SAFE_ID.fullmatch(value) is None
        or ".." in value
    ):
        raise SuccessorAuthorityError(f"{label} is not a safe identifier")
    return value


def decision_from_github_context(
    *,
    environment: Mapping[str, str],
    transition_id: str,
    operation_root: Path | str,
    project_name: str,
    candidate_authority_sha256: str,
    release_version: str,
    generation_id: str,
    predecessor_operation_root: Path | str,
    predecessor_project_name: str,
    predecessor_retirement_sha256: str,
    predecessor_operation_journal_sha256: str,
    predecessor_shelf_receipt_sha256: str,
    predecessor_retired_authority_sha256: str,
    retained_generation_id: str,
    retained_shelf_tree_sha256: str,
    lifetime_seconds: int = 7200,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the exact one-file decision payload from GitHub provider context."""

    observed_now = _utc_now(now)
    root = _canonical_absolute_path(operation_root, "successor operation root")
    _operation_identity(root, project_name)
    predecessor_root = _canonical_absolute_path(
        predecessor_operation_root,
        "predecessor operation root",
    )
    _operation_identity(predecessor_root, predecessor_project_name)
    if predecessor_root == root:
        raise SuccessorAuthorityError(
            "successor operation root must differ from its predecessor"
        )
    if TRANSITION_ID.fullmatch(transition_id) is None:
        raise SuccessorAuthorityError("transition id is invalid")
    _require_sha256(candidate_authority_sha256, "candidate authority digest")
    for value, label in (
        (predecessor_retirement_sha256, "predecessor retirement digest"),
        (
            predecessor_operation_journal_sha256,
            "predecessor operation journal digest",
        ),
        (
            predecessor_shelf_receipt_sha256,
            "predecessor shelf receipt digest",
        ),
        (
            predecessor_retired_authority_sha256,
            "predecessor retired authority digest",
        ),
        (
            retained_shelf_tree_sha256,
            "retained predecessor shelf tree digest",
        ),
    ):
        _require_sha256(value, label)
    _safe_id(release_version, "release version")
    _safe_id(generation_id, "generation id")
    _safe_id(retained_generation_id, "retained predecessor generation id")
    if (
        isinstance(lifetime_seconds, bool)
        or not isinstance(lifetime_seconds, int)
        or not 300 <= lifetime_seconds <= int(MAX_DECISION_LIFETIME.total_seconds())
    ):
        raise SuccessorAuthorityError("decision lifetime is outside its bounded range")

    actor = environment.get("GITHUB_ACTOR", "")
    triggering_actor = environment.get("GITHUB_TRIGGERING_ACTOR", "")
    actor_id_raw = environment.get("GITHUB_ACTOR_ID", "")
    source_head = environment.get("GITHUB_SHA", "")
    workflow_ref = environment.get("GITHUB_WORKFLOW_REF", "")
    expected_workflow_ref = (
        f"{SOURCE_REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}"
    )
    try:
        actor_id = int(actor_id_raw)
        run_id = int(environment.get("GITHUB_RUN_ID", ""))
        run_attempt = int(environment.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError as exc:
        raise SuccessorAuthorityError(
            "GitHub provider numeric identity is invalid"
        ) from exc
    if (
        environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environment.get("GITHUB_REPOSITORY") != SOURCE_REPOSITORY
        or environment.get("GITHUB_REF") != SOURCE_REF
        or environment.get("GITHUB_REF_PROTECTED") != "true"
        or workflow_ref != expected_workflow_ref
        or run_attempt != 1
        or actor != SOLE_OPERATOR_GITHUB_LOGIN
        or triggering_actor != SOLE_OPERATOR_GITHUB_LOGIN
        or actor_id_raw != str(SOLE_OPERATOR_GITHUB_ACTOR_ID)
        or actor_id != SOLE_OPERATOR_GITHUB_ACTOR_ID
        or run_id < 1
        or COMMIT.fullmatch(source_head) is None
    ):
        raise SuccessorAuthorityError(
            "successor decision requires the exact sole GitHub operator on a "
            "first-attempt workflow_dispatch from protected Hub main"
        )

    expires = observed_now + timedelta(seconds=lifetime_seconds)
    return {
        "contractName": DECISION_CONTRACT,
        "contractVersion": 1,
        "status": "approved",
        "decision": "authorize_exact_unsigned_preview_successor",
        "transitionId": transition_id,
        "authorizedAtUtc": _utc_text(observed_now),
        "expiresAtUtc": _utc_text(expires),
        "candidateAuthoritySha256": candidate_authority_sha256,
        "exactIncomingDesktopScope": EXACT_INCOMING_SCOPE,
        "operation": {
            "name": CUTOVER_OPERATION,
            "root": str(root),
            "projectName": project_name,
        },
        "release": {
            "version": release_version,
            "generationId": generation_id,
        },
        "predecessor": {
            "operationRoot": str(predecessor_root),
            "projectName": predecessor_project_name,
            "retirementSha256": predecessor_retirement_sha256,
            "operationJournalSha256": (
                predecessor_operation_journal_sha256
            ),
            "shelfReceiptSha256": predecessor_shelf_receipt_sha256,
            "retiredAuthoritySha256": (
                predecessor_retired_authority_sha256
            ),
            "retainedGenerationId": retained_generation_id,
            "retainedShelfTreeSha256": retained_shelf_tree_sha256,
        },
        "publicServing": {
            "origin": SUCCESSOR_ORIGIN,
            "publicHosts": list(PUBLIC_HOSTS),
        },
        "provider": {
            "eventName": "workflow_dispatch",
            "repository": SOURCE_REPOSITORY,
            "ref": SOURCE_REF,
            "refProtected": True,
            "sourceHead": source_head,
            "actor": actor,
            "triggeringActor": triggering_actor,
            "actorId": actor_id,
            "runId": run_id,
            "runAttempt": 1,
            "workflow": WORKFLOW_PATH,
        },
    }


def emit_decision_artifact(
    *,
    output: Path | str,
    environment: Mapping[str, str],
    transition_id: str,
    operation_root: Path | str,
    project_name: str,
    candidate_authority_sha256: str,
    release_version: str,
    generation_id: str,
    predecessor_operation_root: Path | str,
    predecessor_project_name: str,
    predecessor_retirement_sha256: str,
    predecessor_operation_journal_sha256: str,
    predecessor_shelf_receipt_sha256: str,
    predecessor_retired_authority_sha256: str,
    retained_generation_id: str,
    retained_shelf_tree_sha256: str,
    lifetime_seconds: int = 7200,
    now: datetime | None = None,
) -> dict[str, Any]:
    decision = decision_from_github_context(
        environment=environment,
        transition_id=transition_id,
        operation_root=operation_root,
        project_name=project_name,
        candidate_authority_sha256=candidate_authority_sha256,
        release_version=release_version,
        generation_id=generation_id,
        predecessor_operation_root=predecessor_operation_root,
        predecessor_project_name=predecessor_project_name,
        predecessor_retirement_sha256=predecessor_retirement_sha256,
        predecessor_operation_journal_sha256=(
            predecessor_operation_journal_sha256
        ),
        predecessor_shelf_receipt_sha256=(
            predecessor_shelf_receipt_sha256
        ),
        predecessor_retired_authority_sha256=(
            predecessor_retired_authority_sha256
        ),
        retained_generation_id=retained_generation_id,
        retained_shelf_tree_sha256=retained_shelf_tree_sha256,
        lifetime_seconds=lifetime_seconds,
        now=now,
    )
    target = _canonical_absolute_path(output, "decision output")
    if target.name != DECISION_ARTIFACT_FILENAME:
        raise SuccessorAuthorityError(
            "decision output filename is not the exact artifact contract"
        )
    _write_new(target, _canonical_bytes(decision), mode=0o444)
    return decision


def _validate_decision(
    decision: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    if (
        set(decision) != DECISION_FIELDS
        or decision.get("contractName") != DECISION_CONTRACT
        or type(decision.get("contractVersion")) is not int
        or decision.get("contractVersion") != 1
        or decision.get("status") != "approved"
        or decision.get("decision")
        != "authorize_exact_unsigned_preview_successor"
        or decision.get("exactIncomingDesktopScope") != EXACT_INCOMING_SCOPE
        or not isinstance(decision.get("transitionId"), str)
        or TRANSITION_ID.fullmatch(decision["transitionId"]) is None
    ):
        raise SuccessorAuthorityError("successor decision contract drifted")
    authorized = _timestamp(
        decision.get("authorizedAtUtc"), "decision authorizedAtUtc"
    )
    expires = _timestamp(decision.get("expiresAtUtc"), "decision expiresAtUtc")
    if (
        expires <= authorized
        or expires - authorized > MAX_DECISION_LIFETIME
        or authorized > now + timedelta(minutes=5)
        or now >= expires
    ):
        raise SuccessorAuthorityError(
            "successor decision is expired, future-dated, or overlong"
        )
    _require_sha256(
        decision.get("candidateAuthoritySha256"),
        "decision candidate authority digest",
    )

    operation = decision.get("operation")
    if (
        not isinstance(operation, dict)
        or set(operation) != DECISION_OPERATION_FIELDS
        or operation.get("name") != CUTOVER_OPERATION
        or not isinstance(operation.get("root"), str)
        or not isinstance(operation.get("projectName"), str)
    ):
        raise SuccessorAuthorityError("decision operation identity drifted")
    operation_root = _canonical_absolute_path(
        operation["root"], "decision operation root"
    )
    _operation_identity(operation_root, operation["projectName"])

    release = decision.get("release")
    if (
        not isinstance(release, dict)
        or set(release) != DECISION_RELEASE_FIELDS
    ):
        raise SuccessorAuthorityError("decision release identity drifted")
    _safe_id(release.get("version"), "decision release version")
    _safe_id(release.get("generationId"), "decision generation id")

    predecessor = decision.get("predecessor")
    if (
        not isinstance(predecessor, dict)
        or set(predecessor) != DECISION_PREDECESSOR_FIELDS
        or not isinstance(predecessor.get("operationRoot"), str)
        or not isinstance(predecessor.get("projectName"), str)
    ):
        raise SuccessorAuthorityError(
            "decision predecessor identity drifted"
        )
    predecessor_root = _canonical_absolute_path(
        predecessor["operationRoot"],
        "decision predecessor operation root",
    )
    _operation_identity(predecessor_root, predecessor["projectName"])
    if predecessor_root == operation_root:
        raise SuccessorAuthorityError(
            "decision predecessor reuses the successor operation root"
        )
    for field in (
        "retirementSha256",
        "operationJournalSha256",
        "shelfReceiptSha256",
        "retiredAuthoritySha256",
        "retainedShelfTreeSha256",
    ):
        _require_sha256(
            predecessor.get(field),
            f"decision predecessor {field}",
        )
    _safe_id(
        predecessor.get("retainedGenerationId"),
        "decision retained predecessor generation id",
    )

    serving = decision.get("publicServing")
    if (
        not isinstance(serving, dict)
        or set(serving) != DECISION_SERVING_FIELDS
        or serving.get("origin") != SUCCESSOR_ORIGIN
        or serving.get("publicHosts") != list(PUBLIC_HOSTS)
    ):
        raise SuccessorAuthorityError("decision public serving scope drifted")

    provider = decision.get("provider")
    if (
        not isinstance(provider, dict)
        or set(provider) != DECISION_PROVIDER_FIELDS
        or provider.get("eventName") != "workflow_dispatch"
        or provider.get("repository") != SOURCE_REPOSITORY
        or provider.get("ref") != SOURCE_REF
        or provider.get("refProtected") is not True
        or provider.get("workflow") != WORKFLOW_PATH
        or provider.get("actor") != SOLE_OPERATOR_GITHUB_LOGIN
        or provider.get("triggeringActor") != SOLE_OPERATOR_GITHUB_LOGIN
        or type(provider.get("actorId")) is not int
        or provider["actorId"] != SOLE_OPERATOR_GITHUB_ACTOR_ID
        or type(provider.get("runId")) is not int
        or provider["runId"] < 1
        or type(provider.get("runAttempt")) is not int
        or provider["runAttempt"] != 1
        or not isinstance(provider.get("sourceHead"), str)
        or COMMIT.fullmatch(provider["sourceHead"]) is None
    ):
        raise SuccessorAuthorityError(
            "decision provider authentication drifted"
        )
    return copy.deepcopy(dict(decision))


def read_decision_artifact(
    path: Path | str,
    expected_sha256: str,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bytes, bytes]:
    """Read an exact one-entry GitHub artifact ZIP and validate its decision."""

    expected = _require_sha256(expected_sha256, "decision artifact digest")
    artifact_raw = _stable_regular_bytes(
        path,
        label="decision artifact ZIP",
        maximum_bytes=MAX_ARTIFACT_BYTES,
    )
    if _sha256(artifact_raw) != expected:
        raise SuccessorAuthorityError(
            "decision artifact ZIP does not match its provider digest"
        )
    try:
        with zipfile.ZipFile(io.BytesIO(artifact_raw), "r") as archive:
            if archive.comment:
                raise SuccessorAuthorityError(
                    "decision artifact ZIP contains an archive comment"
                )
            entries = archive.infolist()
            if len(entries) != 1:
                raise SuccessorAuthorityError(
                    "decision artifact ZIP must contain exactly one file"
                )
            entry = entries[0]
            unix_mode = (entry.external_attr >> 16) & 0o170000
            if (
                entry.filename != DECISION_ARTIFACT_FILENAME
                or entry.is_dir()
                or entry.flag_bits & 0x1
                or entry.compress_type
                not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or unix_mode == stat.S_IFLNK
                or not 1 <= entry.file_size <= 1024 * 1024
            ):
                raise SuccessorAuthorityError(
                    "decision artifact ZIP entry contract drifted"
                )
            decision_raw = archive.read(entry)
            if len(decision_raw) != entry.file_size or archive.testzip() is not None:
                raise SuccessorAuthorityError(
                    "decision artifact ZIP integrity check failed"
                )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, SuccessorAuthorityError):
            raise
        raise SuccessorAuthorityError(
            "decision artifact is not a valid bounded ZIP"
        ) from exc
    decision = _strict_json(decision_raw, "successor decision")
    if decision_raw != _canonical_bytes(decision):
        raise SuccessorAuthorityError(
            "successor decision is not canonical JSON"
        )
    return (
        _validate_decision(decision, now=_utc_now(now)),
        decision_raw,
        artifact_raw,
    )


def _live_github_provider_evidence(
    *,
    github: Any,
    decision: Mapping[str, Any],
    github_artifact_id: int,
    artifact_raw: bytes,
) -> dict[str, Any]:
    if (
        isinstance(github_artifact_id, bool)
        or not isinstance(github_artifact_id, int)
        or github_artifact_id < 1
    ):
        raise SuccessorAuthorityError(
            "GitHub decision artifact id must be a positive integer"
        )
    provider = decision.get("provider")
    if not isinstance(provider, dict):
        raise SuccessorAuthorityError(
            "decision has no GitHub provider identity"
        )
    run_id = provider.get("runId")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise SuccessorAuthorityError(
            "decision GitHub run id is invalid"
        )
    try:
        run = github.get_workflow_run(run_id)
        artifact = github.get_artifact(github_artifact_id)
    except SuccessorAuthorityError:
        raise
    except Exception as exc:
        raise SuccessorAuthorityError(
            "live GitHub provider evidence could not be fetched"
        ) from exc
    if not isinstance(run, dict) or not isinstance(artifact, dict):
        raise SuccessorAuthorityError(
            "live GitHub provider evidence is malformed"
        )

    run_api_url = f"{GITHUB_API_ROOT}/actions/runs/{run_id}"
    run_web_url = f"{GITHUB_WEB_ROOT}/actions/runs/{run_id}"
    actor = run.get("actor")
    triggering_actor = run.get("triggering_actor")
    repository = run.get("repository")
    head_repository = run.get("head_repository")
    expected_actor = {
        "login": SOLE_OPERATOR_GITHUB_LOGIN,
        "id": SOLE_OPERATOR_GITHUB_ACTOR_ID,
    }
    expected_workflow_path = WORKFLOW_PATH
    if (
        run.get("id") != run_id
        or run.get("url") != run_api_url
        or run.get("html_url") != run_web_url
        or run.get("artifacts_url") != f"{run_api_url}/artifacts"
        or run.get("path") != expected_workflow_path
        or run.get("head_branch") != "main"
        or run.get("head_sha") != provider.get("sourceHead")
        or run.get("event") != "workflow_dispatch"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or type(run.get("run_attempt")) is not int
        or run["run_attempt"] != 1
        or provider.get("actor") != SOLE_OPERATOR_GITHUB_LOGIN
        or provider.get("triggeringActor") != SOLE_OPERATOR_GITHUB_LOGIN
        or provider.get("actorId") != SOLE_OPERATOR_GITHUB_ACTOR_ID
        or not isinstance(actor, dict)
        or {
            "login": actor.get("login"),
            "id": actor.get("id"),
        }
        != expected_actor
        or not isinstance(triggering_actor, dict)
        or {
            "login": triggering_actor.get("login"),
            "id": triggering_actor.get("id"),
        }
        != expected_actor
        or not isinstance(repository, dict)
        or repository.get("full_name") != SOURCE_REPOSITORY
        or not isinstance(head_repository, dict)
        or head_repository.get("full_name") != SOURCE_REPOSITORY
    ):
        raise SuccessorAuthorityError(
            "live GitHub workflow run does not prove the exact successful "
            "first-attempt protected-main decision"
        )

    artifact_api_url = (
        f"{GITHUB_API_ROOT}/actions/artifacts/{github_artifact_id}"
    )
    archive_url = f"{artifact_api_url}/zip"
    artifact_name = f"public-download-successor-decision-{run_id}-1"
    artifact_workflow_run = artifact.get("workflow_run")
    zip_sha = _sha256(artifact_raw)
    if (
        artifact.get("id") != github_artifact_id
        or artifact.get("node_id") in {None, ""}
        or artifact.get("name") != artifact_name
        or artifact.get("url") != artifact_api_url
        or artifact.get("archive_download_url") != archive_url
        or artifact.get("expired") is not False
        or artifact.get("digest") != f"sha256:{zip_sha}"
        or type(artifact.get("size_in_bytes")) is not int
        or artifact["size_in_bytes"] != len(artifact_raw)
        or not isinstance(artifact_workflow_run, dict)
        or artifact_workflow_run.get("id") != run_id
        or artifact_workflow_run.get("head_branch") != "main"
        or artifact_workflow_run.get("head_sha")
        != provider.get("sourceHead")
    ):
        raise SuccessorAuthorityError(
            "live GitHub artifact does not bind the exact downloaded "
            "one-file decision ZIP"
        )

    return {
        "contractName": "chummer.github-actions-successor-evidence/v1",
        "source": "live_github_rest_api",
        "workflowRun": {
            "id": run_id,
            "apiUrl": run_api_url,
            "htmlUrl": run_web_url,
            "repository": SOURCE_REPOSITORY,
            "workflowPath": expected_workflow_path,
            "headBranch": "main",
            "headSha": provider["sourceHead"],
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "runAttempt": 1,
            "actor": expected_actor,
            "triggeringActor": expected_actor,
        },
        "artifact": {
            "id": github_artifact_id,
            "apiUrl": artifact_api_url,
            "archiveDownloadUrl": archive_url,
            "name": artifact_name,
            "expired": False,
            "providerDigest": f"sha256:{zip_sha}",
            "downloadedZipSha256": zip_sha,
            "sizeBytes": len(artifact_raw),
            "workflowRun": {
                "id": run_id,
                "headBranch": "main",
                "headSha": provider["sourceHead"],
            },
        },
    }


def _validate_v4_identity(
    candidate_authority: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    if (
        set(candidate_authority) != V4_ROOT_FIELDS
        or candidate_authority.get("contractName") != V4_CONTRACT
        or type(candidate_authority.get("contractVersion")) is not int
        or candidate_authority.get("contractVersion") != 4
        or candidate_authority.get("status") != "candidate_import_ready"
        or candidate_authority.get("platformScope") != "windows_only"
        or candidate_authority.get("exactIncomingDesktopScope")
        != EXACT_INCOMING_SCOPE
        or candidate_authority.get("crossRunBitReproducible") is not False
        or not all(
            candidate_authority.get(field) is expected
            for field, expected in CANDIDATE_AUTHORITY_CEILING.items()
        )
        or not _same_json(
            candidate_authority.get("signaturePolicy"),
            {
                "signatureStatus": "unsigned",
                "signingRequired": False,
                "unsignedReason": "preview_policy",
            },
        )
    ):
        raise SuccessorAuthorityError(
            "candidate authority is not the exact non-serving v4 identity"
        )
    generated = _timestamp(
        candidate_authority.get("generatedAtUtc"),
        "candidate authority generatedAtUtc",
    )
    expires = _timestamp(
        candidate_authority.get("expiresAtUtc"),
        "candidate authority expiresAtUtc",
    )
    if generated > now + timedelta(minutes=5) or now >= expires:
        raise SuccessorAuthorityError(
            "candidate v4 identity is future-dated or expired"
        )
    custody = candidate_authority.get("custody")
    if not isinstance(custody, dict) or set(custody) != V4_CUSTODY_FIELDS:
        raise SuccessorAuthorityError("candidate v4 custody property set drifted")
    candidate = candidate_authority.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != CANDIDATE_FIELDS:
        raise SuccessorAuthorityError("candidate v4 summary property set drifted")
    _safe_id(candidate.get("version"), "candidate version")
    for name in (
        "bundleIdentitySha256",
        "canonicalManifestSha256",
        "inventorySha256",
    ):
        _require_sha256(candidate.get(name), f"candidate {name}")
    _positive_int(candidate.get("fileCount"), "candidate fileCount")
    if (
        isinstance(candidate.get("totalBytes"), bool)
        or not isinstance(candidate.get("totalBytes"), int)
        or candidate["totalBytes"] < 0
    ):
        raise SuccessorAuthorityError(
            "candidate totalBytes must be a nonnegative JSON integer"
        )
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
    if candidate["bundleIdentitySha256"] != _sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ):
        raise SuccessorAuthorityError(
            "candidate bundle identity does not bind its exact summary"
        )
    return copy.deepcopy(dict(candidate_authority))


def _load_candidate_identity(
    *,
    candidate_authority: Mapping[str, Any],
    candidate_authority_path: Path | str,
    candidate_authority_sha256: str,
    now: datetime,
) -> tuple[dict[str, Any], bytes]:
    expected = _require_sha256(
        candidate_authority_sha256, "candidate authority digest"
    )
    raw = _stable_regular_bytes(
        candidate_authority_path,
        label="candidate authority",
    )
    if _sha256(raw) != expected:
        raise SuccessorAuthorityError(
            "candidate authority bytes differ from their digest"
        )
    parsed = _strict_json(raw, "candidate authority")
    if not _same_json(parsed, candidate_authority):
        raise SuccessorAuthorityError(
            "candidate authority object differs from its exact file bytes"
        )
    return _validate_v4_identity(parsed, now=now), raw


def _validate_terminal_retirement(
    path: Path | str,
    expected_sha256: str,
    *,
    now: datetime,
) -> tuple[dict[str, Any], bytes]:
    expected = _require_sha256(
        expected_sha256, "predecessor retirement digest"
    )
    raw = _stable_regular_bytes(
        path,
        label="terminal predecessor retirement",
    )
    if _sha256(raw) != expected:
        raise SuccessorAuthorityError(
            "terminal predecessor retirement digest drifted"
        )
    terminal = _strict_json(raw, "terminal predecessor retirement")
    if (
        set(terminal) != TERMINAL_RETIREMENT_FIELDS
        or terminal.get("contractName")
        != "chummer.public-download-committed-retirement/v1"
        or terminal.get("status") != "retired"
        or terminal.get("operation") != RETIRE_OPERATION
        or type(terminal.get("restoredVersion")) is not int
        or terminal["restoredVersion"] < 0
        or not isinstance(terminal.get("operationRoot"), str)
        or not isinstance(terminal.get("projectName"), str)
        or not isinstance(terminal.get("retiredAuthorityPath"), str)
        or not isinstance(terminal.get("retirementEvidencePath"), str)
        or any(
            not isinstance(terminal.get(field), str)
            or SHA256.fullmatch(terminal[field]) is None
            for field in TERMINAL_SHA_FIELDS
        )
        or any(
            not isinstance(terminal.get(field), str)
            or COMMIT.fullmatch(terminal[field]) is None
            for field in ("operationSourceHead", "controllerSourceHead")
        )
        or terminal.get("incumbentBaselineSha256")
        != terminal.get("incumbentObservationSha256")
    ):
        raise SuccessorAuthorityError(
            "terminal ordinary predecessor retirement contract drifted"
        )
    operation_root = _canonical_absolute_path(
        terminal["operationRoot"], "predecessor operation root"
    )
    _operation_identity(operation_root, terminal["projectName"])
    retirement_path = _canonical_absolute_path(
        path, "terminal predecessor retirement path"
    )
    if (
        retirement_path != operation_root / "topology-b-retirement.json"
        or _canonical_absolute_path(
            terminal["retiredAuthorityPath"], "retired authority path"
        )
        != operation_root / "retired-active-runtime-authority.json"
        or _canonical_absolute_path(
            terminal["retirementEvidencePath"], "retirement evidence path"
        )
        != operation_root / "cloudflare-retirement-committed.json"
    ):
        raise SuccessorAuthorityError(
            "terminal predecessor retirement path binding drifted"
        )
    completed = _timestamp(
        terminal.get("completedAtUtc"), "predecessor retirement completedAtUtc"
    )
    if completed > now + timedelta(minutes=5):
        raise SuccessorAuthorityError(
            "terminal predecessor retirement is future-dated"
        )
    return terminal, raw


def _validate_retained_predecessor_custody(
    *,
    terminal: Mapping[str, Any],
    terminal_raw: bytes,
    decision: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    predecessor_root = _canonical_absolute_path(
        str(terminal["operationRoot"]),
        "retained predecessor operation root",
    )
    predecessor_project = str(terminal["projectName"])
    predecessor_decision = decision.get("predecessor")
    if not isinstance(predecessor_decision, dict):
        raise SuccessorAuthorityError(
            "decision has no retained predecessor custody"
        )

    journal_path = predecessor_root.parent / (
        f"{predecessor_project}.operation.json"
    )
    shelf_receipt_path = predecessor_root / "sidecar-shelf-receipt.json"
    retired_authority_path = _canonical_absolute_path(
        str(terminal["retiredAuthorityPath"]),
        "retained predecessor retired authority path",
    )
    journal_raw = _stable_regular_bytes(
        journal_path,
        label="retained predecessor operation journal",
    )
    shelf_receipt_raw = _stable_regular_bytes(
        shelf_receipt_path,
        label="retained predecessor shelf receipt",
    )
    retired_authority_raw = _stable_regular_bytes(
        retired_authority_path,
        label="retained predecessor retired authority",
    )
    journal_sha = _sha256(journal_raw)
    shelf_receipt_sha = _sha256(shelf_receipt_raw)
    retired_authority_sha = _sha256(retired_authority_raw)
    if (
        predecessor_decision.get("operationRoot") != str(predecessor_root)
        or predecessor_decision.get("projectName") != predecessor_project
        or predecessor_decision.get("retirementSha256")
        != _sha256(terminal_raw)
        or predecessor_decision.get("operationJournalSha256")
        != journal_sha
        or predecessor_decision.get("shelfReceiptSha256")
        != shelf_receipt_sha
        or predecessor_decision.get("retiredAuthoritySha256")
        != retired_authority_sha
        or retired_authority_sha != terminal["retiredAuthoritySha256"]
    ):
        raise SuccessorAuthorityError(
            "provider decision differs from surviving predecessor custody"
        )

    journal = _strict_json(
        journal_raw,
        "retained predecessor operation journal",
    )
    shelf = _strict_json(
        shelf_receipt_raw,
        "retained predecessor shelf receipt",
    )
    # The retired runtime authority is itself JSON. Its exact bytes are
    # authenticated by the terminal receipt; parsing it closes the file type.
    _strict_json(
        retired_authority_raw,
        "retained predecessor retired authority",
    )
    if (
        set(journal) != OPERATION_JOURNAL_FIELDS
        or journal.get("schema")
        != "chummer.public-download-only-operation/v1"
        or journal.get("phase") != "retired"
        or journal.get("operation") != CUTOVER_OPERATION
        or journal.get("operationRoot") != str(predecessor_root)
        or journal.get("projectName") != predecessor_project
        or journal.get("sourceHead") != terminal["operationSourceHead"]
        or not isinstance(journal.get("receipts"), dict)
        or not isinstance(journal.get("incumbentBaseline"), dict)
    ):
        raise SuccessorAuthorityError(
            "retained predecessor operation journal is not terminal"
        )
    created = _timestamp(
        journal.get("createdAtUtc"),
        "predecessor journal createdAtUtc",
    )
    updated = _timestamp(
        journal.get("updatedAtUtc"),
        "predecessor journal updatedAtUtc",
    )
    completed = _timestamp(
        terminal.get("completedAtUtc"),
        "predecessor retirement completedAtUtc",
    )
    if (
        updated < created
        or updated < completed
        or updated > now + timedelta(minutes=5)
    ):
        raise SuccessorAuthorityError(
            "retained predecessor journal timing drifted"
        )
    receipts = journal["receipts"]
    if not _same_json(receipts.get("retirement"), terminal):
        raise SuccessorAuthorityError(
            "predecessor journal does not close over terminal retirement"
        )
    if not _same_json(receipts.get("shelf"), shelf):
        raise SuccessorAuthorityError(
            "predecessor journal does not close over its retained shelf"
        )

    if (
        set(shelf) != SIDECAR_SHELF_FIELDS
        or shelf.get("contractName")
        != "chummer.public-download-sidecar-shelf/v1"
        or shelf.get("status") != "pass"
        or shelf.get("sourceHead") != terminal["operationSourceHead"]
        or not isinstance(shelf.get("generationRoot"), str)
        or not isinstance(shelf.get("generationId"), str)
        or not isinstance(shelf.get("incumbentMigrationAuthority"), dict)
        or not isinstance(shelf.get("releaseCandidateAuthority"), dict)
    ):
        raise SuccessorAuthorityError(
            "retained predecessor shelf receipt contract drifted"
        )
    generation_id = _safe_id(
        shelf["generationId"],
        "retained predecessor generation id",
    )
    for field in (
        "activationCandidateSha256",
        "canonicalMirrorSha256",
        "compatibilityMirrorSha256",
        "generationCanonicalSha256",
        "generationCompatibilitySha256",
        "inventoryDigest",
        "pointerSha256",
        "shelfTreeSha256",
    ):
        _require_sha256(
            shelf.get(field),
            f"retained predecessor shelf {field}",
        )
    _safe_id(
        shelf.get("activationReceiptId"),
        "retained predecessor activation receipt id",
    )
    shelf_root = predecessor_root / "release-shelf"
    generation_root = _canonical_absolute_path(
        shelf["generationRoot"],
        "retained predecessor generation root",
    )
    if generation_root != shelf_root / "generations" / generation_id:
        raise SuccessorAuthorityError(
            "retained predecessor generation root escaped its shelf"
        )
    try:
        generation_metadata = generation_root.lstat()
    except OSError as exc:
        raise SuccessorAuthorityError(
            "retained predecessor generation root is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(generation_metadata.st_mode)
        or stat.S_ISLNK(generation_metadata.st_mode)
        or generation_metadata.st_uid != os.geteuid()
        or generation_metadata.st_mode & 0o022
        or generation_root.resolve(strict=True) != generation_root
    ):
        raise SuccessorAuthorityError(
            "retained predecessor generation root is unsafe"
        )
    actual_shelf_sha = _tree_sha256_file_stream(
        shelf_root,
        label="retained predecessor release shelf",
    )
    if (
        actual_shelf_sha != shelf["shelfTreeSha256"]
        or predecessor_decision.get("retainedGenerationId")
        != generation_id
        or predecessor_decision.get("retainedShelfTreeSha256")
        != actual_shelf_sha
    ):
        raise SuccessorAuthorityError(
            "retained predecessor generation custody drifted"
        )

    retired_receipt = receipts.get("retiredAuthority")
    if (
        not isinstance(retired_receipt, dict)
        or set(retired_receipt) != RETIRED_AUTHORITY_RECEIPT_FIELDS
        or retired_receipt.get("contractName")
        != "chummer.public-download-retired-authority/v1"
        or retired_receipt.get("status") != "retired"
        or retired_receipt.get("retiredAuthorityPath")
        != str(retired_authority_path)
        or retired_receipt.get("activeAuthoritySha256")
        != retired_authority_sha
        or retired_receipt.get("retirementEvidenceSha256")
        != terminal["retirementEvidenceSha256"]
        or retired_receipt.get("connectorGateSha256")
        != terminal["connectorGateSha256"]
        or retired_receipt.get("disposition")
        not in {"atomically-retired", "already-atomically-retired"}
        or not isinstance(retired_receipt.get("activeAuthorityPath"), str)
    ):
        raise SuccessorAuthorityError(
            "retained predecessor retired-authority receipt drifted"
        )
    _canonical_absolute_path(
        retired_receipt["activeAuthorityPath"],
        "predecessor active authority path",
    )
    retired_at = _timestamp(
        retired_receipt.get("retiredAtUtc"),
        "predecessor authority retiredAtUtc",
    )
    if retired_at > completed:
        raise SuccessorAuthorityError(
            "predecessor authority retirement timing drifted"
        )

    return {
        "operationJournal": {
            "path": str(journal_path),
            "sha256": journal_sha,
            "sizeBytes": len(journal_raw),
            "schema": journal["schema"],
            "phase": journal["phase"],
        },
        "shelfReceipt": {
            "path": str(shelf_receipt_path),
            "sha256": shelf_receipt_sha,
            "sizeBytes": len(shelf_receipt_raw),
            "contractName": shelf["contractName"],
        },
        "retiredAuthority": {
            "path": str(retired_authority_path),
            "sha256": retired_authority_sha,
            "sizeBytes": len(retired_authority_raw),
            "contractName": retired_receipt["contractName"],
            "receipt": copy.deepcopy(retired_receipt),
        },
        "retainedIncumbentRoot": str(generation_root),
        "retainedIncumbentGenerationId": generation_id,
        "retainedIncumbentShelfTreeSha256": actual_shelf_sha,
    }


def _validate_cloudflare_identity(
    *,
    account_id: str,
    tunnel_id: str,
    origin: str,
    public_hosts: Sequence[str],
    cloudflare: Any,
) -> None:
    if ACCOUNT_ID.fullmatch(account_id) is None:
        raise SuccessorAuthorityError("Cloudflare account id is invalid")
    if TUNNEL_ID.fullmatch(tunnel_id) is None:
        raise SuccessorAuthorityError("Cloudflare tunnel id is invalid")
    if origin != SUCCESSOR_ORIGIN:
        raise SuccessorAuthorityError("successor origin is not the fixed sidecar")
    if tuple(public_hosts) != PUBLIC_HOSTS:
        raise SuccessorAuthorityError("successor public host closure drifted")
    try:
        normalized_origin = cloudflare.validate_origin(origin)
        managed_hosts = tuple(cloudflare.MANAGED_HOSTS)
    except Exception as exc:
        raise SuccessorAuthorityError(
            "Cloudflare helper identity is unavailable"
        ) from exc
    if normalized_origin != SUCCESSOR_ORIGIN or managed_hosts != PUBLIC_HOSTS:
        raise SuccessorAuthorityError(
            "Cloudflare helper serving scope differs from the fixed successor"
        )


def _serving_authority(
    *,
    transition_id: str,
    operation_root: Path,
    project_name: str,
    source_head: str,
    version: str,
    generation_id: str,
    candidate_authority_sha256: str,
    decision_artifact_sha256: str,
    github_artifact_id: int,
    github_provider_evidence_sha256: str,
    predecessor_retirement_sha256: str,
    predecessor_operation_journal_sha256: str,
    predecessor_shelf_receipt_sha256: str,
    predecessor_retired_authority_sha256: str,
    retained_incumbent_root: str,
    retained_incumbent_generation_id: str,
    retained_incumbent_shelf_tree_sha256: str,
    prior_config_sha256: str,
    prior_version: int,
    target_config_sha256: str,
    origin: str,
    public_hosts: Sequence[str],
) -> dict[str, Any]:
    return {
        "contractName": SERVING_AUTHORITY_CONTRACT,
        "contractVersion": 1,
        "status": "authorized",
        "scope": "one_fresh_public_download_successor_cutover",
        "singleUse": True,
        "transitionId": transition_id,
        "operation": CUTOVER_OPERATION,
        "operationRoot": str(operation_root),
        "projectName": project_name,
        "sourceHead": source_head,
        "releaseVersion": version,
        "generationId": generation_id,
        "origin": origin,
        "publicHosts": list(public_hosts),
        "candidateAuthoritySha256": candidate_authority_sha256,
        "decisionArtifactSha256": decision_artifact_sha256,
        "githubArtifactId": github_artifact_id,
        "githubProviderEvidenceSha256": (
            github_provider_evidence_sha256
        ),
        "predecessorRetirementSha256": predecessor_retirement_sha256,
        "predecessorOperationJournalSha256": (
            predecessor_operation_journal_sha256
        ),
        "predecessorShelfReceiptSha256": (
            predecessor_shelf_receipt_sha256
        ),
        "predecessorRetiredAuthoritySha256": (
            predecessor_retired_authority_sha256
        ),
        "retainedIncumbentRoot": retained_incumbent_root,
        "retainedIncumbentGenerationId": (
            retained_incumbent_generation_id
        ),
        "retainedIncumbentShelfTreeSha256": (
            retained_incumbent_shelf_tree_sha256
        ),
        "priorConfigSha256": prior_config_sha256,
        "priorVersion": prior_version,
        "targetConfigSha256": target_config_sha256,
    }


def _validate_authority_content(
    authority: Mapping[str, Any],
    *,
    authority_path: Path,
    decision: Mapping[str, Any],
    decision_artifact_path: Path,
    decision_artifact_raw: bytes,
    decision_artifact_sha256: str,
    github_provider_evidence: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_authority_path: Path,
    candidate_authority_raw: bytes,
    candidate_authority_sha256: str,
    terminal: Mapping[str, Any],
    predecessor_retirement_path: Path,
    predecessor_retirement_raw: bytes,
    predecessor_retirement_sha256: str,
    retained_custody: Mapping[str, Any],
    operation_root: Path,
    project_name: str,
    source_head: str,
    account_id: str,
    tunnel_id: str,
    origin: str,
    public_hosts: Sequence[str],
    cloudflare: Any,
    now: datetime,
) -> dict[str, Any]:
    expected_fields = {
        "authorityPath",
        "authorityScope",
        "candidate",
        "cloudflare",
        "contractName",
        "contractVersion",
        "decisionArtifact",
        "expiresAtUtc",
        "generatedAtUtc",
        "githubProviderEvidence",
        "operation",
        "predecessorRetirement",
        "retainedPredecessor",
        "servingAuthority",
        "singleUse",
        "source",
        "status",
        "transitionId",
    }
    if (
        set(authority) != expected_fields
        or authority.get("contractName") != SUCCESSOR_AUTHORITY_CONTRACT
        or type(authority.get("contractVersion")) is not int
        or authority.get("contractVersion") != 1
        or authority.get("status") != "authorized"
        or authority.get("authorityScope")
        != "one_fresh_public_download_successor_cutover"
        or authority.get("singleUse") is not True
        or authority.get("authorityPath") != str(authority_path)
        or authority.get("transitionId") != decision.get("transitionId")
    ):
        raise SuccessorAuthorityError("successor authority contract drifted")
    generated = _timestamp(
        authority.get("generatedAtUtc"), "successor authority generatedAtUtc"
    )
    expires = _timestamp(
        authority.get("expiresAtUtc"), "successor authority expiresAtUtc"
    )
    decision_authorized = _timestamp(
        decision.get("authorizedAtUtc"), "decision authorizedAtUtc"
    )
    decision_expires = _timestamp(
        decision.get("expiresAtUtc"), "decision expiresAtUtc"
    )
    terminal_completed = _timestamp(
        terminal.get("completedAtUtc"), "predecessor retirement completedAtUtc"
    )
    if (
        expires != decision_expires
        or decision_authorized < terminal_completed
        or generated < decision_authorized
        or generated > now + timedelta(minutes=5)
        or now >= expires
        or generated >= expires
    ):
        raise SuccessorAuthorityError(
            "successor authority time ordering does not prove retire-then-fresh"
        )

    source = authority.get("source")
    operation = authority.get("operation")
    candidate_summary = candidate["candidate"]
    decision_release = decision["release"]
    if not _same_json(
        source,
        {
            "repository": SOURCE_REPOSITORY,
            "ref": SOURCE_REF,
            "commit": source_head,
        },
    ) or not _same_json(
        operation,
        {
            "name": CUTOVER_OPERATION,
            "root": str(operation_root),
            "projectName": project_name,
        },
    ):
        raise SuccessorAuthorityError(
            "successor source or operation binding drifted"
        )

    expected_candidate = {
        "path": str(candidate_authority_path),
        "sha256": candidate_authority_sha256,
        "sizeBytes": len(candidate_authority_raw),
        "contractName": V4_CONTRACT,
        "contractVersion": 4,
        "version": candidate_summary["version"],
        "generationId": decision_release["generationId"],
        "canonicalManifestSha256": candidate_summary[
            "canonicalManifestSha256"
        ],
        "inventorySha256": candidate_summary["inventorySha256"],
        "bundleIdentitySha256": candidate_summary[
            "bundleIdentitySha256"
        ],
        "exactIncomingDesktopScope": EXACT_INCOMING_SCOPE,
        "authorityCeiling": CANDIDATE_AUTHORITY_CEILING,
    }
    if not _same_json(authority.get("candidate"), expected_candidate):
        raise SuccessorAuthorityError(
            "successor candidate identity or authority ceiling drifted"
        )

    expected_decision = {
        "path": str(decision_artifact_path),
        "sha256": decision_artifact_sha256,
        "sizeBytes": len(decision_artifact_raw),
        "filename": DECISION_ARTIFACT_FILENAME,
        "contractName": DECISION_CONTRACT,
        "artifactId": github_provider_evidence["artifact"]["id"],
        "githubProviderEvidenceSha256": _sha256(
            _canonical_bytes(github_provider_evidence)
        ),
        "provider": decision["provider"],
    }
    if not _same_json(authority.get("decisionArtifact"), expected_decision):
        raise SuccessorAuthorityError(
            "successor decision artifact binding drifted"
        )
    if not _same_json(
        authority.get("githubProviderEvidence"),
        github_provider_evidence,
    ):
        raise SuccessorAuthorityError(
            "successor live GitHub provider evidence drifted"
        )

    predecessor_root = Path(str(terminal["operationRoot"]))
    expected_retirement = {
        "path": str(predecessor_retirement_path),
        "sha256": predecessor_retirement_sha256,
        "sizeBytes": len(predecessor_retirement_raw),
        "contractName": terminal["contractName"],
        "operationRoot": str(predecessor_root),
        "projectName": terminal["projectName"],
        "controllerSourceHead": terminal["controllerSourceHead"],
        "priorConfigSha256": terminal["priorConfigSha256"],
        "restoredVersion": terminal["restoredVersion"],
        "completedAtUtc": terminal["completedAtUtc"],
    }
    if not _same_json(
        authority.get("predecessorRetirement"), expected_retirement
    ):
        raise SuccessorAuthorityError(
            "successor predecessor retirement binding drifted"
        )
    if predecessor_root == operation_root:
        raise SuccessorAuthorityError(
            "fresh successor operation must not reuse the retired operation root"
        )
    if not _same_json(
        authority.get("retainedPredecessor"),
        retained_custody,
    ):
        raise SuccessorAuthorityError(
            "successor retained predecessor custody drifted"
        )
    operation_journal = retained_custody.get("operationJournal")
    shelf_receipt = retained_custody.get("shelfReceipt")
    retired_authority = retained_custody.get("retiredAuthority")
    retained_root = retained_custody.get("retainedIncumbentRoot")
    retained_generation = retained_custody.get(
        "retainedIncumbentGenerationId"
    )
    retained_shelf_sha = retained_custody.get(
        "retainedIncumbentShelfTreeSha256"
    )
    if (
        not isinstance(operation_journal, dict)
        or not isinstance(shelf_receipt, dict)
        or not isinstance(retired_authority, dict)
        or not isinstance(retained_root, str)
        or not isinstance(retained_generation, str)
        or not isinstance(retained_shelf_sha, str)
    ):
        raise SuccessorAuthorityError(
            "successor retained predecessor custody is malformed"
        )

    cloudflare_binding = authority.get("cloudflare")
    cloudflare_fields = {
        "accountId",
        "origin",
        "postRetirementSnapshotResponseSha256",
        "priorConfig",
        "priorConfigSha256",
        "priorVersion",
        "publicHosts",
        "targetConfig",
        "targetConfigSha256",
        "tunnelId",
    }
    if not isinstance(cloudflare_binding, dict) or set(
        cloudflare_binding
    ) != cloudflare_fields:
        raise SuccessorAuthorityError(
            "successor Cloudflare binding property set drifted"
        )
    prior_config = cloudflare_binding.get("priorConfig")
    target_config = cloudflare_binding.get("targetConfig")
    prior_version = cloudflare_binding.get("priorVersion")
    if (
        cloudflare_binding.get("accountId") != account_id
        or cloudflare_binding.get("tunnelId") != tunnel_id
        or cloudflare_binding.get("origin") != origin
        or cloudflare_binding.get("publicHosts") != list(public_hosts)
        or type(prior_version) is not int
        or prior_version < 0
        or prior_version != terminal.get("restoredVersion")
        or not isinstance(prior_config, dict)
        or not isinstance(target_config, dict)
        or not isinstance(
            cloudflare_binding.get("postRetirementSnapshotResponseSha256"),
            str,
        )
        or SHA256.fullmatch(
            cloudflare_binding["postRetirementSnapshotResponseSha256"]
        )
        is None
    ):
        raise SuccessorAuthorityError(
            "successor Cloudflare identity or version drifted"
        )
    try:
        prior_sha = cloudflare.canonical_sha256(prior_config)
        expected_target = cloudflare.plan_public_download_config(
            prior_config, origin
        )
        target_sha = cloudflare.canonical_sha256(expected_target)
    except Exception as exc:
        raise SuccessorAuthorityError(
            "successor Cloudflare configuration plan is invalid"
        ) from exc
    if (
        prior_sha != terminal.get("priorConfigSha256")
        or cloudflare_binding.get("priorConfigSha256") != prior_sha
        or not _same_json(target_config, expected_target)
        or cloudflare_binding.get("targetConfigSha256") != target_sha
    ):
        raise SuccessorAuthorityError(
            "successor Cloudflare prior/target transition drifted"
        )

    expected_serving = _serving_authority(
        transition_id=decision["transitionId"],
        operation_root=operation_root,
        project_name=project_name,
        source_head=source_head,
        version=candidate_summary["version"],
        generation_id=decision_release["generationId"],
        candidate_authority_sha256=candidate_authority_sha256,
        decision_artifact_sha256=decision_artifact_sha256,
        github_artifact_id=github_provider_evidence["artifact"]["id"],
        github_provider_evidence_sha256=_sha256(
            _canonical_bytes(github_provider_evidence)
        ),
        predecessor_retirement_sha256=predecessor_retirement_sha256,
        predecessor_operation_journal_sha256=(
            operation_journal["sha256"]
        ),
        predecessor_shelf_receipt_sha256=shelf_receipt["sha256"],
        predecessor_retired_authority_sha256=(
            retired_authority["sha256"]
        ),
        retained_incumbent_root=retained_root,
        retained_incumbent_generation_id=retained_generation,
        retained_incumbent_shelf_tree_sha256=retained_shelf_sha,
        prior_config_sha256=prior_sha,
        prior_version=prior_version,
        target_config_sha256=target_sha,
        origin=origin,
        public_hosts=public_hosts,
    )
    if not _same_json(authority.get("servingAuthority"), expected_serving):
        raise SuccessorAuthorityError(
            "separate successor serving authority drifted"
        )
    return {
        "generationId": decision_release["generationId"],
        "transitionId": decision["transitionId"],
        "priorConfig": copy.deepcopy(prior_config),
        "priorConfigSha256": prior_sha,
        "priorVersion": prior_version,
        "targetConfig": copy.deepcopy(target_config),
        "targetConfigSha256": target_sha,
        "retainedIncumbentRoot": retained_root,
        "retainedIncumbentGenerationId": retained_generation,
        "retainedIncumbentShelfTreeSha256": retained_shelf_sha,
        "servingAuthority": copy.deepcopy(expected_serving),
    }


def validate_successor_authority(
    authority_raw: bytes,
    *,
    authority_path: Path | str,
    authority_sha256: str,
    decision_artifact_path: Path | str,
    decision_artifact_sha256: str,
    github_artifact_id: int,
    candidate_authority: Mapping[str, Any],
    candidate_authority_path: Path | str,
    candidate_authority_sha256: str,
    predecessor_retirement_path: Path | str,
    predecessor_retirement_sha256: str,
    operation_root: Path | str,
    project_name: str,
    source_head: str,
    account_id: str,
    tunnel_id: str,
    origin: str,
    public_hosts: Sequence[str],
    cloudflare: Any,
    github: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and normalize one exact, already materialized successor authority."""

    observed_now = _utc_now(now)
    authority_file = _canonical_absolute_path(authority_path, "successor authority")
    expected_authority_sha = _require_sha256(
        authority_sha256, "successor authority digest"
    )
    file_raw = _stable_regular_bytes(
        authority_file,
        label="successor authority",
    )
    if (
        not isinstance(authority_raw, bytes)
        or file_raw != authority_raw
        or _sha256(authority_raw) != expected_authority_sha
    ):
        raise SuccessorAuthorityError(
            "successor authority bytes differ from their exact file or digest"
        )
    authority = _strict_json(authority_raw, "successor authority")
    if authority_raw != _canonical_bytes(authority):
        raise SuccessorAuthorityError(
            "successor authority is not canonical JSON"
        )

    root = _canonical_absolute_path(operation_root, "successor operation root")
    _operation_identity(root, project_name)
    source_head = _require_commit(source_head, "successor source head")
    decision_path = _canonical_absolute_path(
        decision_artifact_path, "decision artifact path"
    )
    candidate_path = _canonical_absolute_path(
        candidate_authority_path, "candidate authority path"
    )
    retirement_path = _canonical_absolute_path(
        predecessor_retirement_path, "predecessor retirement path"
    )
    _validate_cloudflare_identity(
        account_id=account_id,
        tunnel_id=tunnel_id,
        origin=origin,
        public_hosts=public_hosts,
        cloudflare=cloudflare,
    )
    decision, _decision_raw, decision_artifact_raw = read_decision_artifact(
        decision_path,
        decision_artifact_sha256,
        now=observed_now,
    )
    github_provider_evidence = _live_github_provider_evidence(
        github=github if github is not None else LiveGitHubApi(),
        decision=decision,
        github_artifact_id=github_artifact_id,
        artifact_raw=decision_artifact_raw,
    )
    candidate, candidate_raw = _load_candidate_identity(
        candidate_authority=candidate_authority,
        candidate_authority_path=candidate_path,
        candidate_authority_sha256=candidate_authority_sha256,
        now=observed_now,
    )
    terminal, terminal_raw = _validate_terminal_retirement(
        retirement_path,
        predecessor_retirement_sha256,
        now=observed_now,
    )
    retained_custody = _validate_retained_predecessor_custody(
        terminal=terminal,
        terminal_raw=terminal_raw,
        decision=decision,
        now=observed_now,
    )
    if (
        decision["operation"]
        != {
            "name": CUTOVER_OPERATION,
            "root": str(root),
            "projectName": project_name,
        }
        or decision["provider"]["sourceHead"] != source_head
        or decision["candidateAuthoritySha256"]
        != candidate_authority_sha256
        or decision["release"]["version"]
        != candidate["candidate"]["version"]
    ):
        raise SuccessorAuthorityError(
            "decision, source, operation, and candidate identity disagree"
        )
    return _validate_authority_content(
        authority,
        authority_path=authority_file,
        decision=decision,
        decision_artifact_path=decision_path,
        decision_artifact_raw=decision_artifact_raw,
        decision_artifact_sha256=decision_artifact_sha256,
        github_provider_evidence=github_provider_evidence,
        candidate=candidate,
        candidate_authority_path=candidate_path,
        candidate_authority_raw=candidate_raw,
        candidate_authority_sha256=candidate_authority_sha256,
        terminal=terminal,
        predecessor_retirement_path=retirement_path,
        predecessor_retirement_raw=terminal_raw,
        predecessor_retirement_sha256=predecessor_retirement_sha256,
        retained_custody=retained_custody,
        operation_root=root,
        project_name=project_name,
        source_head=source_head,
        account_id=account_id,
        tunnel_id=tunnel_id,
        origin=origin,
        public_hosts=public_hosts,
        cloudflare=cloudflare,
        now=observed_now,
    )


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SuccessorAuthorityError(f"could not load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_cloudflare_helper() -> Any:
    return _load_module(
        Path(__file__).resolve().parents[1]
        / "cloudflare_public_download_transaction.py",
        f"public_download_successor_cloudflare_{os.getpid()}",
    )


def load_projection_verifier() -> Any:
    return _load_module(
        Path(__file__).resolve().with_name("verify_public_projection.py"),
        f"public_download_successor_projection_{os.getpid()}",
    )


def materialize_successor_authority(
    *,
    output: Path | str,
    decision_artifact_path: Path | str,
    decision_artifact_sha256: str,
    github_artifact_id: int,
    candidate_authority: Mapping[str, Any],
    candidate_authority_path: Path | str,
    candidate_authority_sha256: str,
    predecessor_retirement_path: Path | str,
    predecessor_retirement_sha256: str,
    post_retirement_response: Mapping[str, Any],
    post_retirement_response_sha256: str,
    post_retirement_response_raw: bytes | None = None,
    operation_root: Path | str,
    project_name: str,
    source_head: str,
    account_id: str,
    tunnel_id: str,
    origin: str = SUCCESSOR_ORIGIN,
    public_hosts: Sequence[str] = PUBLIC_HOSTS,
    cloudflare: Any | None = None,
    github: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Materialize one new authority after ordinary retirement has completed."""

    observed_now = _utc_now(now)
    helper = cloudflare if cloudflare is not None else load_cloudflare_helper()
    output_path = _canonical_absolute_path(output, "successor authority output")
    root = _canonical_absolute_path(operation_root, "successor operation root")
    _operation_identity(root, project_name)
    source_head = _require_commit(source_head, "successor source head")
    decision_path = _canonical_absolute_path(
        decision_artifact_path, "decision artifact path"
    )
    candidate_path = _canonical_absolute_path(
        candidate_authority_path, "candidate authority path"
    )
    retirement_path = _canonical_absolute_path(
        predecessor_retirement_path, "predecessor retirement path"
    )
    _validate_cloudflare_identity(
        account_id=account_id,
        tunnel_id=tunnel_id,
        origin=origin,
        public_hosts=public_hosts,
        cloudflare=helper,
    )
    decision, _decision_raw, artifact_raw = read_decision_artifact(
        decision_path,
        decision_artifact_sha256,
        now=observed_now,
    )
    github_provider_evidence = _live_github_provider_evidence(
        github=github if github is not None else LiveGitHubApi(),
        decision=decision,
        github_artifact_id=github_artifact_id,
        artifact_raw=artifact_raw,
    )
    candidate, candidate_raw = _load_candidate_identity(
        candidate_authority=candidate_authority,
        candidate_authority_path=candidate_path,
        candidate_authority_sha256=candidate_authority_sha256,
        now=observed_now,
    )
    terminal, terminal_raw = _validate_terminal_retirement(
        retirement_path,
        predecessor_retirement_sha256,
        now=observed_now,
    )
    retained_custody = _validate_retained_predecessor_custody(
        terminal=terminal,
        terminal_raw=terminal_raw,
        decision=decision,
        now=observed_now,
    )
    if (
        decision["operation"]
        != {
            "name": CUTOVER_OPERATION,
            "root": str(root),
            "projectName": project_name,
        }
        or decision["provider"]["sourceHead"] != source_head
        or decision["candidateAuthoritySha256"]
        != candidate_authority_sha256
        or decision["release"]["version"]
        != candidate["candidate"]["version"]
    ):
        raise SuccessorAuthorityError(
            "decision, source, operation, and candidate identity disagree"
        )
    response_sha = _require_sha256(
        post_retirement_response_sha256,
        "post-retirement Cloudflare response digest",
    )
    response_raw = (
        _canonical_bytes(post_retirement_response)
        if post_retirement_response_raw is None
        else post_retirement_response_raw
    )
    if not isinstance(response_raw, bytes):
        raise SuccessorAuthorityError(
            "post-retirement Cloudflare response bytes are invalid"
        )
    if _sha256(response_raw) != response_sha:
        raise SuccessorAuthorityError(
            "post-retirement Cloudflare response differs from its digest"
        )
    try:
        snapshot = helper.parse_configuration_response(post_retirement_response)
        target_config = helper.plan_public_download_config(
            snapshot.config, origin
        )
        target_sha = helper.canonical_sha256(target_config)
    except Exception as exc:
        raise SuccessorAuthorityError(
            "post-retirement Cloudflare snapshot cannot plan the successor"
        ) from exc
    if (
        snapshot.sha256 != terminal["priorConfigSha256"]
        or snapshot.version != terminal["restoredVersion"]
    ):
        raise SuccessorAuthorityError(
            "actual post-retirement Cloudflare snapshot differs from "
            "the terminal retirement"
        )

    candidate_summary = candidate["candidate"]
    generation_id = decision["release"]["generationId"]
    operation_journal = retained_custody["operationJournal"]
    shelf_receipt = retained_custody["shelfReceipt"]
    retired_authority = retained_custody["retiredAuthority"]
    serving = _serving_authority(
        transition_id=decision["transitionId"],
        operation_root=root,
        project_name=project_name,
        source_head=source_head,
        version=candidate_summary["version"],
        generation_id=generation_id,
        candidate_authority_sha256=candidate_authority_sha256,
        decision_artifact_sha256=decision_artifact_sha256,
        github_artifact_id=github_artifact_id,
        github_provider_evidence_sha256=_sha256(
            _canonical_bytes(github_provider_evidence)
        ),
        predecessor_retirement_sha256=predecessor_retirement_sha256,
        predecessor_operation_journal_sha256=(
            operation_journal["sha256"]
        ),
        predecessor_shelf_receipt_sha256=shelf_receipt["sha256"],
        predecessor_retired_authority_sha256=(
            retired_authority["sha256"]
        ),
        retained_incumbent_root=retained_custody[
            "retainedIncumbentRoot"
        ],
        retained_incumbent_generation_id=retained_custody[
            "retainedIncumbentGenerationId"
        ],
        retained_incumbent_shelf_tree_sha256=retained_custody[
            "retainedIncumbentShelfTreeSha256"
        ],
        prior_config_sha256=snapshot.sha256,
        prior_version=snapshot.version,
        target_config_sha256=target_sha,
        origin=origin,
        public_hosts=public_hosts,
    )
    authority = {
        "contractName": SUCCESSOR_AUTHORITY_CONTRACT,
        "contractVersion": 1,
        "status": "authorized",
        "authorityScope": "one_fresh_public_download_successor_cutover",
        "singleUse": True,
        "transitionId": decision["transitionId"],
        "authorityPath": str(output_path),
        "generatedAtUtc": _utc_text(observed_now),
        "expiresAtUtc": decision["expiresAtUtc"],
        "source": {
            "repository": SOURCE_REPOSITORY,
            "ref": SOURCE_REF,
            "commit": source_head,
        },
        "operation": {
            "name": CUTOVER_OPERATION,
            "root": str(root),
            "projectName": project_name,
        },
        "candidate": {
            "path": str(candidate_path),
            "sha256": candidate_authority_sha256,
            "sizeBytes": len(candidate_raw),
            "contractName": V4_CONTRACT,
            "contractVersion": 4,
            "version": candidate_summary["version"],
            "generationId": generation_id,
            "canonicalManifestSha256": candidate_summary[
                "canonicalManifestSha256"
            ],
            "inventorySha256": candidate_summary["inventorySha256"],
            "bundleIdentitySha256": candidate_summary[
                "bundleIdentitySha256"
            ],
            "exactIncomingDesktopScope": EXACT_INCOMING_SCOPE,
            "authorityCeiling": CANDIDATE_AUTHORITY_CEILING,
        },
        "decisionArtifact": {
            "path": str(decision_path),
            "sha256": decision_artifact_sha256,
            "sizeBytes": len(artifact_raw),
            "filename": DECISION_ARTIFACT_FILENAME,
            "contractName": DECISION_CONTRACT,
            "artifactId": github_artifact_id,
            "githubProviderEvidenceSha256": _sha256(
                _canonical_bytes(github_provider_evidence)
            ),
            "provider": decision["provider"],
        },
        "githubProviderEvidence": github_provider_evidence,
        "predecessorRetirement": {
            "path": str(retirement_path),
            "sha256": predecessor_retirement_sha256,
            "sizeBytes": len(terminal_raw),
            "contractName": terminal["contractName"],
            "operationRoot": terminal["operationRoot"],
            "projectName": terminal["projectName"],
            "controllerSourceHead": terminal["controllerSourceHead"],
            "priorConfigSha256": terminal["priorConfigSha256"],
            "restoredVersion": terminal["restoredVersion"],
            "completedAtUtc": terminal["completedAtUtc"],
        },
        "retainedPredecessor": retained_custody,
        "cloudflare": {
            "accountId": account_id,
            "tunnelId": tunnel_id,
            "origin": origin,
            "publicHosts": list(public_hosts),
            "postRetirementSnapshotResponseSha256": response_sha,
            "priorConfig": copy.deepcopy(snapshot.config),
            "priorConfigSha256": snapshot.sha256,
            "priorVersion": snapshot.version,
            "targetConfig": target_config,
            "targetConfigSha256": target_sha,
        },
        "servingAuthority": serving,
    }
    _validate_authority_content(
        authority,
        authority_path=output_path,
        decision=decision,
        decision_artifact_path=decision_path,
        decision_artifact_raw=artifact_raw,
        decision_artifact_sha256=decision_artifact_sha256,
        github_provider_evidence=github_provider_evidence,
        candidate=candidate,
        candidate_authority_path=candidate_path,
        candidate_authority_raw=candidate_raw,
        candidate_authority_sha256=candidate_authority_sha256,
        terminal=terminal,
        predecessor_retirement_path=retirement_path,
        predecessor_retirement_raw=terminal_raw,
        predecessor_retirement_sha256=predecessor_retirement_sha256,
        retained_custody=retained_custody,
        operation_root=root,
        project_name=project_name,
        source_head=source_head,
        account_id=account_id,
        tunnel_id=tunnel_id,
        origin=origin,
        public_hosts=public_hosts,
        cloudflare=helper,
        now=observed_now,
    )
    _write_new(output_path, _canonical_bytes(authority), mode=0o600)
    return authority


def _parse_now(value: str | None) -> datetime | None:
    return _timestamp(value, "--now") if value else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    decision = subparsers.add_parser(
        "emit-decision",
        help="emit the exact provider-authenticated one-file decision",
    )
    decision.add_argument("--transition-id", required=True)
    decision.add_argument("--operation-root", type=Path, required=True)
    decision.add_argument("--project-name", required=True)
    decision.add_argument("--candidate-authority-sha256", required=True)
    decision.add_argument("--release-version", required=True)
    decision.add_argument("--generation-id", required=True)
    decision.add_argument("--predecessor-binding-json", required=True)
    decision.add_argument("--lifetime-seconds", type=int, default=7200)
    decision.add_argument("--output", type=Path, required=True)
    decision.add_argument("--now")

    materialize = subparsers.add_parser(
        "materialize",
        help="materialize one post-retirement successor authority",
    )
    materialize.add_argument("--decision-artifact", type=Path, required=True)
    materialize.add_argument("--decision-artifact-sha256", required=True)
    materialize.add_argument(
        "--github-artifact-id",
        type=int,
        required=True,
    )
    materialize.add_argument("--candidate-authority", type=Path, required=True)
    materialize.add_argument("--candidate-authority-sha256", required=True)
    materialize.add_argument(
        "--predecessor-retirement", type=Path, required=True
    )
    materialize.add_argument(
        "--predecessor-retirement-sha256", required=True
    )
    materialize.add_argument(
        "--cloudflare-current-response", type=Path, required=True
    )
    materialize.add_argument(
        "--cloudflare-current-response-sha256", required=True
    )
    materialize.add_argument("--operation-root", type=Path, required=True)
    materialize.add_argument("--project-name", required=True)
    materialize.add_argument("--source-head", required=True)
    materialize.add_argument("--account-id", required=True)
    materialize.add_argument("--tunnel-id", required=True)
    materialize.add_argument("--origin", default=SUCCESSOR_ORIGIN)
    materialize.add_argument(
        "--public-host",
        action="append",
        dest="public_hosts",
        default=[],
    )
    materialize.add_argument("--output", type=Path, required=True)
    materialize.add_argument("--now")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        now = _parse_now(args.now)
        if args.command == "emit-decision":
            predecessor_binding_raw = (
                args.predecessor_binding_json.encode("utf-8")
            )
            predecessor_binding = _strict_json(
                predecessor_binding_raw,
                "--predecessor-binding-json",
            )
            if (
                set(predecessor_binding)
                != DECISION_PREDECESSOR_FIELDS
                or predecessor_binding_raw
                != _canonical_bytes(predecessor_binding).rstrip(b"\n")
            ):
                raise SuccessorAuthorityError(
                    "--predecessor-binding-json must be the exact "
                    "canonical predecessor property set"
                )
            result = emit_decision_artifact(
                output=args.output,
                environment=os.environ,
                transition_id=args.transition_id,
                operation_root=args.operation_root,
                project_name=args.project_name,
                candidate_authority_sha256=(
                    args.candidate_authority_sha256
                ),
                release_version=args.release_version,
                generation_id=args.generation_id,
                predecessor_operation_root=(
                    predecessor_binding["operationRoot"]
                ),
                predecessor_project_name=predecessor_binding[
                    "projectName"
                ],
                predecessor_retirement_sha256=(
                    predecessor_binding["retirementSha256"]
                ),
                predecessor_operation_journal_sha256=(
                    predecessor_binding["operationJournalSha256"]
                ),
                predecessor_shelf_receipt_sha256=(
                    predecessor_binding["shelfReceiptSha256"]
                ),
                predecessor_retired_authority_sha256=(
                    predecessor_binding["retiredAuthoritySha256"]
                ),
                retained_generation_id=predecessor_binding[
                    "retainedGenerationId"
                ],
                retained_shelf_tree_sha256=(
                    predecessor_binding["retainedShelfTreeSha256"]
                ),
                lifetime_seconds=args.lifetime_seconds,
                now=now,
            )
        else:
            candidate_raw = _stable_regular_bytes(
                args.candidate_authority,
                label="candidate authority",
            )
            candidate = _strict_json(candidate_raw, "candidate authority")
            verifier = load_projection_verifier()
            try:
                candidate = verifier._validate_candidate_import_authority_v4(
                    candidate,
                    now=_utc_now(now),
                )
            except Exception as exc:
                raise SuccessorAuthorityError(
                    "candidate authority failed the strict v4 verifier"
                ) from exc
            response_raw = _stable_regular_bytes(
                args.cloudflare_current_response,
                label="post-retirement Cloudflare response",
            )
            expected_response_sha = _require_sha256(
                args.cloudflare_current_response_sha256,
                "post-retirement Cloudflare response digest",
            )
            if _sha256(response_raw) != expected_response_sha:
                raise SuccessorAuthorityError(
                    "post-retirement Cloudflare response digest drifted"
                )
            response = _strict_json(
                response_raw, "post-retirement Cloudflare response"
            )
            public_hosts = (
                tuple(args.public_hosts)
                if args.public_hosts
                else PUBLIC_HOSTS
            )
            result = materialize_successor_authority(
                output=args.output,
                decision_artifact_path=args.decision_artifact,
                decision_artifact_sha256=args.decision_artifact_sha256,
                github_artifact_id=args.github_artifact_id,
                candidate_authority=candidate,
                candidate_authority_path=args.candidate_authority,
                candidate_authority_sha256=(
                    args.candidate_authority_sha256
                ),
                predecessor_retirement_path=(
                    args.predecessor_retirement
                ),
                predecessor_retirement_sha256=(
                    args.predecessor_retirement_sha256
                ),
                post_retirement_response=response,
                post_retirement_response_sha256=expected_response_sha,
                post_retirement_response_raw=response_raw,
                operation_root=args.operation_root,
                project_name=args.project_name,
                source_head=args.source_head,
                account_id=args.account_id,
                tunnel_id=args.tunnel_id,
                origin=args.origin,
                public_hosts=public_hosts,
                now=now,
            )
    except (SuccessorAuthorityError, OSError, ValueError) as exc:
        print(
            f"public_download_successor_authority: {exc}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
