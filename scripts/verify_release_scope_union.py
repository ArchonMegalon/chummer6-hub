#!/usr/bin/env python3
"""Prepare a non-authorizing snapshot of the exact global release-scope union."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import selectors
import stat
import struct
import subprocess
import sys
import time
from typing import Any, Callable, Optional, Sequence

import verify_release_scope_decision as decision_contract


RECEIPT_CONTRACT = "chummer.release-scope-union-preparation/v1"
SNAPSHOT_CONTRACT = (
    "chummer.release-scope-union-artifact-snapshot/v1"
)
SNAPSHOT_COMMIT_CONTRACT = (
    "chummer.release-scope-union-artifact-snapshot-commit/v1"
)
SNAPSHOT_MANIFEST_NAME = "ARTIFACT_SNAPSHOT.generated.json"
SNAPSHOT_COMMIT_NAME = "ARTIFACT_SNAPSHOT_COMMIT.generated.json"
BINDING_CONTRACT = "chummer6-ui.campaign_operability_candidate_binding"
PROMOTION_CONTRACT = "chummer.run.desktop_release_publication"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
UPPER_FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")
TEAM_ID = re.compile(r"^[A-Z0-9]{10}$")
UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)
POSITIVE_DECIMAL = re.compile(r"^[1-9][0-9]*$")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_RELEASE_SOURCE_BYTES = 16 * 1024 * 1024
MAX_GIT_CONTROL_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_GIT_GRAPH_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_GIT_GRAPH_OBJECTS = 500_000
MAX_GIT_CONFIG_BYTES = 1024 * 1024
MAX_GIT_PACK_ENTRIES = 4096
MAX_GIT_OBJECT_ROOT_ENTRIES = 1024
PLATFORM_SPECS = {
    "linux": "linux-x64",
    "macos": "osx-arm64",
    "windows": "win-x64",
}
REGISTRY_PLATFORM_ORDER = ["linux", "windows", "macos"]
GATE_SPECS = {
    "visual": "chummer6-ui.desktop_visual_familiarity_exit_gate",
    "workflow": "chummer6-ui.desktop_workflow_execution_gate",
    "executable": "chummer6-ui.desktop_executable_exit_gate",
}
BINDING_FIELDS = {
    "authority_snapshot_sha256",
    "contract_name",
    "contract_version",
    "manifest_sha256",
    "platform",
    "primary_head",
    "registry_commit",
    "release_decision_sha256",
    "release_scope_decision_sha256",
    "release_version",
    "required_heads",
    "rid",
}
AUTHORITY_CURRENT_FIELDS = {
    "releaseVersion",
    "snapshotSha256",
    "decisionSha256",
    "status",
}
AUTHORITY_SNAPSHOT_FIELDS = {
    "authorityContract",
    "releaseVersion",
    "channel",
    "status",
    "rolloutState",
    "supportabilityState",
    "availablePlatforms",
    "primaryHeadByPlatform",
    "artifactCount",
    "downloadAccessPosture",
    "knownIssueSummary",
    "manifestSha256",
    "registryRepository",
    "registryCommit",
    "releaseDecisionStatus",
    "releaseDecisionSha256",
    "supportOwner",
    "nextActions",
    "artifacts",
    "manifestPath",
    "releaseDecisionPath",
}
AUTHORITY_ARTIFACT_FIELDS = {
    "artifactId",
    "head",
    "platform",
    "rid",
    "arch",
    "kind",
    "downloadUrl",
    "sha256",
    "sizeBytes",
    "compatibilityState",
    "promotionState",
    "publicationScope",
    "revokeState",
    "publicInstallRoute",
    "installAccessClass",
}
AUTHORITY_DECISION_FIELDS = {
    "contractName",
    "generatedAt",
    "status",
    "releaseDecisionStatus",
    "verdict",
    "releaseVersion",
    "releaseScopeDecisionSha256",
    "channel",
    "platforms",
    "primaryHeadByPlatform",
    "fallbackHeadsByPlatform",
    "artifactAccessClass",
    "supportOwner",
    "nextActions",
    "registryCommit",
    "manifestSha256",
    "authoritySnapshotSha256",
    "candidateDecisionStatus",
    "candidateDecisionSha256",
    "manifestGeneratedAt",
    "scorecardSha256",
    "convergenceSha256",
    "blockingFindings",
}
MAC_AUTHORITY_FIELDS = {
    "candidateId",
    "contractName",
    "contractVersion",
    "generationId",
    "github",
    "livePredecessorAuthority",
    "releaseVersion",
    "rid",
    "status",
}
MAC_GITHUB_FIELDS = {
    "actor",
    "ref",
    "repository",
    "rerunPolicy",
    "runAttempt",
    "runId",
    "sha",
    "triggeringActor",
    "workflow",
}
MAC_IDENTITY_FIELDS = {
    "artifact",
    "certificate",
    "contractName",
    "contractVersion",
    "generatedAtUtc",
    "notarization",
    "provenance",
    "releaseVersion",
    "rid",
    "signingReceiptSha256",
    "sourceAuthorityReceiptSha256",
    "status",
}
MAC_AGGREGATE_INPUT_BINDING_FIELDS = {
    "authorityReceiptSha256",
    "cleanStartupReceiptSha256",
    "completedUpdateStateSha256",
    "hostedNativeProofConsumptionSha256",
    "liveReleaseChannelSha256",
    "manualUpdateStateSha256",
    "notaryResultSha256",
    "pendingDeliveryReceiptSha256",
    "postUpdateStartupReceiptSha256",
    "predecessorVerificationSha256",
    "runtimeObservationsSha256",
    "signingIdentityReceiptSha256",
    "signingReceiptSha256",
    "stageManifestSha256",
    "stageOnlyReceiptSha256",
}


ScopeError = decision_contract.ScopeError


class _ReceiptDurabilityIndeterminate(ScopeError):
    """The create-only receipt link succeeded but its directory sync failed."""


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify three immutable per-platform stable scope decisions, the exact "
            "global candidate shelf, and all nine candidate-bound Presentation gates; "
            "emit preparation evidence that still requires publisher consumption."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--promotion-evidence", type=Path, required=True)
    parser.add_argument("--files-root", type=Path, required=True)
    parser.add_argument(
        "--artifact-snapshot-root",
        type=Path,
        required=True,
    )
    parser.add_argument("--registry-repository", type=Path, required=True)
    parser.add_argument("--expected-release-version", required=True)
    for platform in PLATFORM_SPECS:
        parser.add_argument(f"--{platform}-decision", type=Path, required=True)
        parser.add_argument(f"--{platform}-decision-sha256", required=True)
        parser.add_argument(f"--{platform}-decision-authority", required=True)
        parser.add_argument(f"--{platform}-review-manifest", type=Path, required=True)
        parser.add_argument(f"--{platform}-authority-current", type=Path, required=True)
        parser.add_argument(f"--{platform}-authority-snapshot", type=Path, required=True)
        parser.add_argument(f"--{platform}-release-decision", type=Path, required=True)
        parser.add_argument(f"--{platform}-signing-receipt", type=Path, required=True)
        parser.add_argument(f"--{platform}-signing-receipt-sha256", required=True)
        for gate in GATE_SPECS:
            parser.add_argument(
                f"--{platform}-{gate}-receipt",
                type=Path,
                required=True,
            )
    parser.add_argument("--linux-signed-export-receipt", type=Path, required=True)
    parser.add_argument("--macos-signing-identity-receipt", type=Path, required=True)
    parser.add_argument("--macos-notary-result", type=Path, required=True)
    parser.add_argument("--macos-source-authority-receipt", type=Path, required=True)
    parser.add_argument("--macos-aggregate-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _path_without_symlinks(path: Path, label: str, *, allow_missing: bool = False) -> None:
    absolute = path.absolute()
    current = Path(absolute.parts[0])
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if allow_missing:
                continue
            raise ScopeError(f"{label} is missing") from None
        except (OSError, ValueError) as error:
            raise ScopeError(f"{label} path could not be inspected safely") from error
        if stat.S_ISLNK(mode):
            raise ScopeError(f"{label} must not traverse a symlink")


def _identity(item: os.stat_result) -> tuple[int, ...]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_uid,
        item.st_gid,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _directory_identity(item: os.stat_result) -> tuple[int, ...]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_uid,
        item.st_gid,
        item.st_mode,
    )


def _close_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _open_existing_parent(path: Path, label: str) -> tuple[int, Path]:
    absolute = path.absolute()
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        directory_fd = os.open(absolute.anchor or os.sep, directory_flags)
    except OSError as error:
        raise ScopeError(f"{label} parent anchor could not be opened safely") from error
    try:
        for component in absolute.parent.parts[1:]:
            if component in {"", ".", ".."} or "\0" in component:
                raise ScopeError(f"{label} parent contains an unsafe component")
            try:
                before = os.stat(
                    component,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except (OSError, ValueError) as error:
                raise ScopeError(f"{label} parent could not be inspected safely") from error
            if not stat.S_ISDIR(before.st_mode):
                raise ScopeError(f"{label} must not traverse a symlink")
            try:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except OSError as error:
                raise ScopeError(f"{label} parent could not be opened safely") from error
            try:
                opened = os.fstat(next_fd)
            except OSError as error:
                os.close(next_fd)
                raise ScopeError(
                    f"{label} parent could not be opened safely"
                ) from error
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                os.close(next_fd)
                raise ScopeError(f"{label} parent changed while it was opened")
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd, absolute.parent
    except BaseException:
        os.close(directory_fd)
        raise


def _parent_still_bound(parent_fd: int, path: Path, label: str) -> None:
    try:
        observed = os.stat(path, follow_symlinks=False)
    except (OSError, ValueError) as error:
        raise ScopeError(f"{label} parent became unreachable") from error
    opened = os.fstat(parent_fd)
    if (
        observed.st_dev,
        observed.st_ino,
    ) != (
        opened.st_dev,
        opened.st_ino,
    ):
        raise ScopeError(f"{label} parent changed during stable access")


def _open_stable(
    path: Path,
    label: str,
    *,
    private: bool,
    bounded: bool,
) -> tuple[int, os.stat_result, int, Path]:
    parent_fd, absolute_parent = _open_existing_parent(path, label)
    try:
        before_path = os.stat(
            path.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except (OSError, ValueError) as error:
        os.close(parent_fd)
        raise ScopeError(f"{label} could not be inspected safely") from error
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
    except (OSError, ValueError) as error:
        os.close(parent_fd)
        raise ScopeError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if _identity(before_path) != _identity(before):
            raise ScopeError(f"{label} changed while it was opened")
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ScopeError(f"{label} must be a single-link regular file")
        if before.st_uid != os.geteuid():
            raise ScopeError(f"{label} must be owned by the current release operator")
        if before.st_mode & 0o022:
            raise ScopeError(f"{label} must not be group/world writable")
        if private and before.st_mode & 0o077:
            raise ScopeError(f"{label} must not be accessible by group or other users")
        if bounded and not 1 <= before.st_size <= MAX_JSON_BYTES:
            raise ScopeError(f"{label} must be non-empty and no larger than {MAX_JSON_BYTES} bytes")
        return descriptor, before, parent_fd, absolute_parent
    except BaseException:
        os.close(descriptor)
        os.close(parent_fd)
        raise


def _stable_bytes(path: Path, label: str, *, private: bool = False) -> bytes:
    descriptor, before, parent_fd, absolute_parent = _open_stable(
        path,
        label,
        private=private,
        bounded=True,
    )
    try:
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        _parent_still_bound(parent_fd, absolute_parent, label)
    finally:
        os.close(descriptor)
        os.close(parent_fd)
    raw = b"".join(chunks)
    if _identity(before) != _identity(after) or len(raw) != before.st_size:
        raise ScopeError(f"{label} changed during stable read")
    return raw


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            if not isinstance(key, str):
                raise ScopeError(f"{label} contains a non-string field")
            normalized = key.casefold()
            if normalized in folded:
                raise ScopeError(
                    f"{label} contains a duplicate or case-shadowed field"
                )
            folded.add(normalized)
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ScopeError(f"{label} contains a non-finite number")

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScopeError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ScopeError(f"{label} must be a JSON object")
    return payload


def _canonical_sha(value: str, label: str) -> str:
    if SHA256.fullmatch(value) is None:
        raise ScopeError(f"{label} must be a canonical lowercase SHA-256")
    return value


def _canonical_commit(value: str) -> str:
    if GIT_COMMIT.fullmatch(value) is None:
        raise ScopeError("expected Registry commit must be a canonical lowercase 40-character commit")
    return value


def _exact_string(value: Any, expected: str, label: str) -> str:
    if not isinstance(value, str) or value != expected:
        raise ScopeError(f"{label} must exactly equal {expected}")
    return value


def _exact_object(
    value: Any,
    fields: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ScopeError(f"{label} must have the exact required field set")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ScopeError(f"{label} must be a positive integer")
    return value


def _nonempty_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ScopeError(f"{label} must be a non-empty array")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise ScopeError(f"{label} must contain canonical non-empty strings")
        output.append(item)
    return output


def _alias(
    payload: dict[str, Any],
    names: tuple[str, ...],
    label: str,
    *,
    required: bool = True,
    exactly_one: bool = False,
) -> Optional[str]:
    present = [(name, payload[name]) for name in names if name in payload]
    if not present:
        if required:
            raise ScopeError(f"{label} is missing")
        return None
    if exactly_one and len(present) != 1:
        raise ScopeError(f"{label} must use exactly one canonical alias")
    values: list[str] = []
    for name, value in present:
        if not isinstance(value, str) or value != value.strip() or not value:
            raise ScopeError(f"{label} field {name} must be canonical non-empty text")
        values.append(value)
    if len(set(values)) != 1:
        raise ScopeError(f"{label} aliases disagree")
    return values[0]


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _load_decisions(args: argparse.Namespace) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, str]],
]:
    identities: dict[str, dict[str, Any]] = {}
    policies: list[dict[str, Any]] = []
    receipt_rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    shared: Optional[tuple[str, str, str]] = None
    for platform, rid in PLATFORM_SPECS.items():
        path = getattr(args, f"{platform}_decision")
        expected_sha = _canonical_sha(
            getattr(args, f"{platform}_decision_sha256"),
            f"{platform} decision SHA-256",
        )
        raw = _stable_bytes(path, f"{platform} release scope decision", private=True)
        observed_sha = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(observed_sha, expected_sha):
            raise ScopeError(f"{platform} release scope decision SHA-256 does not match")
        payload = _strict_json(raw, f"{platform} release scope decision")
        if not hmac.compare_digest(raw, _canonical_json(payload)):
            raise ScopeError(
                f"{platform} release scope decision is not canonical compact sorted UTF-8 JSON plus LF"
            )
        identity, rows = decision_contract._parse_decision(payload)
        if identity["decisionId"] in seen_ids:
            raise ScopeError("per-platform release scope decision ids must be unique")
        seen_ids.add(identity["decisionId"])
        if len(rows) != 1 or rows[0]["platform"] != platform or rows[0]["rid"] != rid:
            raise ScopeError(f"{platform} release scope decision must contain exactly {platform}/{rid}")
        policy = rows[0]
        if (
            policy["primaryHead"] != "avalonia"
            or policy["fallbackHeads"] != []
            or policy["artifactAccessClass"] != "open_public"
            or policy["signingRequirement"] != "signed"
        ):
            raise ScopeError(
                f"{platform} stable scope must require avalonia only, open_public access, and signing"
            )
        if identity["channel"] != "public_stable" or identity["releaseTarget"] != "stable":
            raise ScopeError(f"{platform} scope is not approved for public_stable/stable")
        if identity["releaseVersion"] != args.expected_release_version:
            raise ScopeError(f"{platform} scope releaseVersion disagrees with the requested release")
        current_shared = (
            identity["releaseVersion"],
            identity["supportOwner"],
            identity["approvedBy"],
        )
        if shared is None:
            shared = current_shared
        elif shared != current_shared:
            raise ScopeError(
                "per-platform scope decisions must share releaseVersion, supportOwner, and approvedBy"
            )
        authority = decision_contract._authority(
            getattr(args, f"{platform}_decision_authority"),
            identity["decisionId"],
            expected_sha,
        )
        identities[platform] = identity
        policies.append(policy)
        receipt_rows.append(
            {
                "platform": platform,
                "decisionId": identity["decisionId"],
                "decisionSha256": observed_sha,
                "decisionAuthority": authority,
            }
        )
    return identities, policies, receipt_rows


def _manifest_identity(manifest: dict[str, Any], expected_version: str) -> None:
    if _alias(manifest, ("version", "releaseVersion"), "manifest release version") != expected_version:
        raise ScopeError("manifest release version disagrees with the requested release")
    if _alias(manifest, ("channel", "channelId"), "manifest channel") != "public_stable":
        raise ScopeError("manifest channel must be public_stable")
    for field, expected in (
        ("status", "published"),
        ("rolloutState", "public_stable"),
        ("supportabilityState", "gold_supported"),
    ):
        _exact_string(manifest.get(field), expected, f"manifest {field}")


def _review_manifest_identity(
    manifest: dict[str, Any],
    expected_version: str,
    platform: str,
) -> None:
    if (
        _alias(manifest, ("version", "releaseVersion"), "review manifest release version")
        != expected_version
    ):
        raise ScopeError(f"{platform} review manifest release version disagrees")
    if _alias(manifest, ("channel", "channelId"), "review manifest channel") != "public_stable":
        raise ScopeError(f"{platform} review manifest channel must be public_stable")
    for field, expected in (
        ("status", "published"),
        ("rolloutState", "public_release_review_required"),
        ("supportabilityState", "review_required"),
        ("releaseDecisionStatus", "review_required"),
    ):
        _exact_string(
            manifest.get(field),
            expected,
            f"{platform} review manifest {field}",
        )


def _artifact_identity(
    row: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    if (
        row.get("artifactId") not in (None, "")
        and row.get("id") not in (None, "")
        and row.get("artifactId") != row.get("id")
    ):
        raise ScopeError(f"{label} artifactId/id aliases disagree")
    artifact_id = decision_contract._token(
        row.get("artifactId") or row.get("id"),
        f"{label}.artifactId",
    )
    output: dict[str, Any] = {
        "artifactId": artifact_id,
        "head": decision_contract._token(row.get("head"), f"{label}.head"),
        "platform": decision_contract._platform(
            row.get("platform"),
            f"{label}.platform",
        ),
        "rid": decision_contract._token(row.get("rid"), f"{label}.rid"),
        "kind": decision_contract._token(row.get("kind"), f"{label}.kind"),
        "fileName": _safe_basename(row.get("fileName"), f"{label}.fileName"),
        "sha256": _canonical_sha(row.get("sha256"), f"{label}.sha256")
        if isinstance(row.get("sha256"), str)
        else "",
        "sizeBytes": _positive_integer(row.get("sizeBytes"), f"{label}.sizeBytes"),
        "payloadFileName": None,
        "payloadSha256": None,
        "payloadSizeBytes": None,
    }
    payload_name = row.get("payloadFileName")
    if payload_name not in (None, ""):
        output["payloadFileName"] = _safe_basename(
            payload_name,
            f"{label}.payloadFileName",
        )
        payload_sha = row.get("payloadSha256")
        if not isinstance(payload_sha, str):
            raise ScopeError(f"{label}.payloadSha256 is missing")
        output["payloadSha256"] = _canonical_sha(
            payload_sha,
            f"{label}.payloadSha256",
        )
        output["payloadSizeBytes"] = _positive_integer(
            row.get("payloadSizeBytes"),
            f"{label}.payloadSizeBytes",
        )
    elif row.get("payloadSha256") not in (None, "") or row.get("payloadSizeBytes") not in (
        None,
        0,
    ):
        raise ScopeError(f"{label} has payload metadata without a payload file")
    return output


def _review_artifact_projection(
    row: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    identity = _artifact_identity(row, label)
    if set(row) & {"installAccessClass"} and row.get("installAccessClass") != "open_public":
        raise ScopeError(f"{label} is not open_public")
    return identity


def _snapshot_artifact_projection(
    row: Any,
    platform: str,
    rid: str,
    index: int,
) -> dict[str, Any]:
    label = f"{platform} authority snapshot artifact {index}"
    artifact = _exact_object(row, AUTHORITY_ARTIFACT_FIELDS, label)
    if (
        artifact.get("platform") != platform
        or artifact.get("rid") != rid
        or artifact.get("head") != "avalonia"
        or artifact.get("kind") != "installer"
        or artifact.get("compatibilityState") != "compatible"
        or artifact.get("promotionState") != "promoted"
        or artifact.get("publicationScope") != "signed-in-and-public"
        or artifact.get("revokeState") != "not_revoked"
        or artifact.get("installAccessClass") != "open_public"
    ):
        raise ScopeError(f"{label} is outside the approved stable review scope")
    return {
        "artifactId": decision_contract._token(
            artifact.get("artifactId"),
            f"{label}.artifactId",
        ),
        "head": "avalonia",
        "platform": platform,
        "rid": rid,
        "kind": "installer",
        "fileName": _safe_basename(
            Path(str(artifact.get("downloadUrl") or "")).name,
            f"{label}.downloadUrl file name",
        ),
        "sha256": _canonical_sha(
            artifact.get("sha256"),
            f"{label}.sha256",
        )
        if isinstance(artifact.get("sha256"), str)
        else "",
        "sizeBytes": _positive_integer(
            artifact.get("sizeBytes"),
            f"{label}.sizeBytes",
        ),
    }


def _verify_review_authorities(
    args: argparse.Namespace,
    identities: dict[str, dict[str, Any]],
    decision_rows: list[dict[str, str]],
    final_manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], str]:
    decision_sha_by_platform = {
        row["platform"]: row["decisionSha256"] for row in decision_rows
    }
    final_artifacts = final_manifest.get("artifacts")
    if not isinstance(final_artifacts, list):
        raise ScopeError("final manifest artifacts must be an array")
    final_by_platform: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(final_artifacts):
        if not isinstance(value, dict):
            raise ScopeError(f"final manifest artifact {index} must be an object")
        identity = _artifact_identity(value, f"final manifest artifact {index}")
        platform = identity["platform"]
        if platform in final_by_platform:
            raise ScopeError(
                "final global manifest must contain exactly one artifact per platform"
            )
        final_by_platform[platform] = identity

    contexts: dict[str, dict[str, str]] = {}
    registry_commits: set[str] = set()
    for platform, rid in PLATFORM_SPECS.items():
        review_raw = _stable_bytes(
            getattr(args, f"{platform}_review_manifest"),
            f"{platform} review manifest",
            private=True,
        )
        current_raw = _stable_bytes(
            getattr(args, f"{platform}_authority_current"),
            f"{platform} authority CURRENT",
            private=True,
        )
        snapshot_raw = _stable_bytes(
            getattr(args, f"{platform}_authority_snapshot"),
            f"{platform} authority SNAPSHOT",
            private=True,
        )
        release_decision_raw = _stable_bytes(
            getattr(args, f"{platform}_release_decision"),
            f"{platform} authority RELEASE_DECISION",
            private=True,
        )
        review_manifest = _strict_json(review_raw, f"{platform} review manifest")
        current = _exact_object(
            _strict_json(current_raw, f"{platform} authority CURRENT"),
            AUTHORITY_CURRENT_FIELDS,
            f"{platform} authority CURRENT",
        )
        snapshot = _exact_object(
            _strict_json(snapshot_raw, f"{platform} authority SNAPSHOT"),
            AUTHORITY_SNAPSHOT_FIELDS,
            f"{platform} authority SNAPSHOT",
        )
        release_decision = _exact_object(
            _strict_json(
                release_decision_raw,
                f"{platform} authority RELEASE_DECISION",
            ),
            AUTHORITY_DECISION_FIELDS,
            f"{platform} authority RELEASE_DECISION",
        )
        review_sha = hashlib.sha256(review_raw).hexdigest()
        snapshot_sha = hashlib.sha256(snapshot_raw).hexdigest()
        release_decision_sha = hashlib.sha256(release_decision_raw).hexdigest()
        _review_manifest_identity(
            review_manifest,
            args.expected_release_version,
            platform,
        )
        if current != {
            "releaseVersion": args.expected_release_version,
            "snapshotSha256": snapshot_sha,
            "decisionSha256": release_decision_sha,
            "status": "review_required",
        }:
            raise ScopeError(
                f"{platform} authority CURRENT does not bind the exact review envelope"
            )
        registry_commit = _canonical_commit(str(snapshot.get("registryCommit") or ""))
        registry_commits.add(registry_commit)
        expected_snapshot_values = {
            "authorityContract": "chummer.release-authority-snapshot/v2",
            "releaseVersion": args.expected_release_version,
            "channel": "public_stable",
            "status": "published",
            "rolloutState": "public_release_review_required",
            "supportabilityState": "review_required",
            "availablePlatforms": [platform],
            "primaryHeadByPlatform": {platform: "avalonia"},
            "downloadAccessPosture": "open_public",
            "manifestSha256": review_sha,
            "registryRepository": "ArchonMegalon/chummer6-hub-registry",
            "releaseDecisionStatus": "review_required",
            "releaseDecisionSha256": release_decision_sha,
            "supportOwner": identities[platform]["supportOwner"],
            "manifestPath": "RELEASE_CHANNEL.json",
            "releaseDecisionPath": "RELEASE_DECISION.json",
        }
        for field, expected in expected_snapshot_values.items():
            if snapshot.get(field) != expected:
                raise ScopeError(
                    f"{platform} authority SNAPSHOT.{field} contradicts the review candidate"
                )
        _nonempty_strings(
            snapshot.get("nextActions"),
            f"{platform} authority SNAPSHOT.nextActions",
        )
        snapshot_artifacts = snapshot.get("artifacts")
        if (
            not isinstance(snapshot_artifacts, list)
            or len(snapshot_artifacts) != 1
            or snapshot.get("artifactCount") != 1
        ):
            raise ScopeError(
                f"{platform} authority SNAPSHOT must contain one exact installer"
            )
        snapshot_projection = _snapshot_artifact_projection(
            snapshot_artifacts[0],
            platform,
            rid,
            0,
        )
        review_artifacts = review_manifest.get("artifacts")
        if not isinstance(review_artifacts, list) or len(review_artifacts) != 1:
            raise ScopeError(
                f"{platform} review manifest must contain one exact installer"
            )
        if not isinstance(review_artifacts[0], dict):
            raise ScopeError(f"{platform} review manifest artifact must be an object")
        review_projection = _review_artifact_projection(
            review_artifacts[0],
            f"{platform} review manifest artifact",
        )
        for field in (
            "artifactId",
            "head",
            "platform",
            "rid",
            "kind",
            "fileName",
            "sha256",
            "sizeBytes",
        ):
            if snapshot_projection[field] != review_projection[field]:
                raise ScopeError(
                    f"{platform} authority SNAPSHOT artifact does not bind review manifest"
                )
        if final_by_platform.get(platform) != review_projection:
            raise ScopeError(
                f"{platform} final gold artifact identity differs from reviewed bytes"
            )

        expected_decision_values: dict[str, Any] = {
            "contractName": "chummer.preview-release-decision/v1",
            "status": "review_required",
            "releaseDecisionStatus": "review_required",
            "verdict": "PREVIEW_RELEASE_REVIEW_REQUIRED",
            "releaseVersion": args.expected_release_version,
            "releaseScopeDecisionSha256": decision_sha_by_platform[platform],
            "channel": "public_stable",
            "platforms": [platform],
            "primaryHeadByPlatform": {platform: "avalonia"},
            "fallbackHeadsByPlatform": {platform: []},
            "artifactAccessClass": "open_public",
            "supportOwner": identities[platform]["supportOwner"],
            "nextActions": snapshot["nextActions"],
            "registryCommit": registry_commit,
            "manifestSha256": review_sha,
            "authoritySnapshotSha256": "",
            "candidateDecisionStatus": "",
            "candidateDecisionSha256": "",
            "scorecardSha256": "",
            "convergenceSha256": "",
        }
        for field, expected in expected_decision_values.items():
            if release_decision.get(field) != expected:
                raise ScopeError(
                    f"{platform} authority RELEASE_DECISION.{field} contradicts review authority"
                )
        manifest_generated_at = review_manifest.get("generatedAt")
        if manifest_generated_at is None:
            manifest_generated_at = review_manifest.get("publishedAt")
        if (
            not isinstance(manifest_generated_at, str)
            or release_decision.get("manifestGeneratedAt") != manifest_generated_at
        ):
            raise ScopeError(
                f"{platform} authority RELEASE_DECISION does not bind manifest generation time"
            )
        if not isinstance(release_decision.get("generatedAt"), str):
            raise ScopeError(
                f"{platform} authority RELEASE_DECISION.generatedAt is invalid"
            )
        findings = release_decision.get("blockingFindings")
        if not isinstance(findings, list) or not findings:
            raise ScopeError(
                f"{platform} review-required decision must retain explicit blocking findings"
            )
        for index, finding in enumerate(findings, start=1):
            if (
                not isinstance(finding, dict)
                or set(finding) != {"id", "severity", "summary"}
                or finding.get("id") != f"preview_{index}"
                or finding.get("severity") != "release_truth"
                or not isinstance(finding.get("summary"), str)
                or not finding["summary"].strip()
            ):
                raise ScopeError(
                    f"{platform} authority RELEASE_DECISION blocking finding is invalid"
                )
        contexts[platform] = {
            "manifestSha256": review_sha,
            "authoritySnapshotSha256": snapshot_sha,
            "releaseDecisionSha256": release_decision_sha,
            "registryCommit": registry_commit,
        }
    if len(registry_commits) != 1:
        raise ScopeError(
            "all three independently reviewed platform envelopes must share one Registry commit"
        )
    return contexts, registry_commits.pop()


@dataclass
class _VerificationGuard:
    verify_callback: Callable[[], None]
    close_callback: Callable[[], None]
    mutation_watch: _MutationWatch | None = None
    closed: bool = False

    def verify(self) -> None:
        if self.closed:
            raise ScopeError("verification guard is already closed")
        self.verify_callback()

    def close(self) -> None:
        if not self.closed:
            try:
                self.close_callback()
            finally:
                self.closed = True

    def ignore_mutation_path(self, path: Path) -> None:
        if self.closed or self.mutation_watch is None:
            raise ScopeError("verification guard mutation watch is unavailable")
        self.mutation_watch.ignore_path(path)


@dataclass(frozen=True)
class _GitObjectStoreInventory:
    root_entries: tuple[tuple[str, tuple[int, ...]], ...]
    loose_objects: tuple[tuple[str, tuple[int, ...]], ...]
    pack_entries: tuple[tuple[str, tuple[int, ...]], ...]


class _MutationWatch:
    _EVENT_HEADER = struct.Struct("iIII")
    _MASK = (
        0x00000002  # IN_MODIFY
        | 0x00000004  # IN_ATTRIB
        | 0x00000008  # IN_CLOSE_WRITE
        | 0x00000040  # IN_MOVED_FROM
        | 0x00000080  # IN_MOVED_TO
        | 0x00000100  # IN_CREATE
        | 0x00000200  # IN_DELETE
        | 0x00000400  # IN_DELETE_SELF
        | 0x00000800  # IN_MOVE_SELF
        | 0x00002000  # IN_UNMOUNT
        | 0x00004000  # IN_Q_OVERFLOW
        | 0x00008000  # IN_IGNORED
    )

    def __init__(
        self,
        paths: Sequence[Path],
        *,
        ignored_paths: Sequence[Path] = (),
        content_sensitive_directories: Sequence[Path] = (),
    ) -> None:
        self.descriptor: Optional[int] = None
        self.poisoned = False
        self._inotify_add_watch: Any = None
        self.paths_by_watch: dict[int, set[Path]] = {}
        self.ignored_paths = {
            path.absolute()
            for path in ignored_paths
        }
        self.content_sensitive_directories = {
            path.absolute()
            for path in content_sensitive_directories
        }
        target_paths = {
            path.absolute()
            for path in paths
        } | self.content_sensitive_directories
        if not target_paths:
            raise ScopeError("release authority mutation watch has no paths")
        watched: set[Path] = set()
        binding_paths: set[Path] = set()
        for target_path in target_paths:
            current = target_path
            while True:
                watched.add(current)
                binding_paths.add(current)
                if current.parent == current:
                    break
                current = current.parent
        self.authority_paths = frozenset(binding_paths)
        for ignored_path in self.ignored_paths:
            self._assert_disjoint(ignored_path)
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            init = libc.inotify_init1
            add = libc.inotify_add_watch
        except (AttributeError, OSError) as error:
            raise ScopeError(
                "release authority mutation watch is unavailable"
            ) from error
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int
        add.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        add.restype = ctypes.c_int
        descriptor = init(
            getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        if descriptor < 0:
            raise ScopeError(
                "release authority mutation watch could not be created"
            )
        self.descriptor = descriptor
        self._inotify_add_watch = add
        try:
            added = 0
            for watched_path in sorted(watched, key=str):
                try:
                    watched_path.lstat()
                except FileNotFoundError:
                    continue
                except (OSError, ValueError) as error:
                    raise ScopeError(
                        "release authority mutation watch path is unavailable"
                    ) from error
                result = add(
                    descriptor,
                    os.fsencode(watched_path),
                    self._MASK,
                )
                if result < 0:
                    raise ScopeError(
                        "release authority mutation watch path could not be held"
                    )
                self.paths_by_watch.setdefault(result, set()).add(
                    watched_path
                )
                added += 1
            if added == 0:
                raise ScopeError(
                    "release authority mutation watch has no live paths"
                )
            self.assert_quiet()
        except BaseException:
            os.close(descriptor)
            self.descriptor = None
            raise

    def assert_quiet(self) -> None:
        if self.poisoned:
            raise ScopeError(
                "release authority changed during receipt commit"
            )
        try:
            self._drain_events()
        except ScopeError:
            self.poisoned = True
            raise

    def accept_exact_creations(
        self,
        paths: Sequence[Path],
        *,
        closure_paths: Sequence[Path] = (),
    ) -> None:
        if self.poisoned or self.descriptor is None:
            raise ScopeError(
                "release authority changed during receipt commit"
            )
        expected = {path.absolute() for path in paths}
        expected_closures = {
            path.absolute()
            for path in closure_paths
        }
        if (
            not expected
            or not expected.issubset(self.authority_paths)
        ):
            self.poisoned = True
            raise ScopeError(
                "release authority planned creation set is invalid"
            )
        try:
            observed = self._drain_events(
                allowed_creations=expected,
                allowed_closures=expected_closures,
            )
            if observed != expected:
                raise ScopeError(
                    "release authority planned creation was not observed"
                )
            add = self._inotify_add_watch
            if add is None:
                raise ScopeError(
                    "release authority mutation watch is unavailable"
                )
            for path in sorted(expected, key=str):
                result = add(
                    self.descriptor,
                    os.fsencode(path),
                    self._MASK,
                )
                if result < 0:
                    raise ScopeError(
                        "release authority created path could not be held"
                    )
                self.paths_by_watch.setdefault(result, set()).add(path)
            self._drain_events()
        except ScopeError:
            self.poisoned = True
            raise

    def _drain_events(
        self,
        *,
        allowed_creations: set[Path] | None = None,
        allowed_closures: set[Path] | None = None,
    ) -> set[Path]:
        if self.descriptor is None:
            raise ScopeError("release authority mutation watch is closed")
        observed_creations: set[Path] = set()
        observed_closures: set[Path] = set()
        while True:
            try:
                observed = os.read(self.descriptor, 1024 * 1024)
            except BlockingIOError:
                if (
                    allowed_closures
                    and observed_closures != allowed_closures
                ):
                    raise ScopeError(
                        "release authority planned close was not observed"
                    )
                return observed_creations
            except OSError as error:
                raise ScopeError(
                    "release authority mutation watch could not be read"
                ) from error
            if not observed:
                raise ScopeError(
                    "release authority mutation watch closed unexpectedly"
                )
            offset = 0
            while offset < len(observed):
                if (
                    offset + self._EVENT_HEADER.size
                    > len(observed)
                ):
                    raise ScopeError(
                        "release authority mutation watch event is malformed"
                    )
                watch_descriptor, mask, _cookie, name_size = (
                    self._EVENT_HEADER.unpack_from(observed, offset)
                )
                offset += self._EVENT_HEADER.size
                end = offset + name_size
                if end > len(observed):
                    raise ScopeError(
                        "release authority mutation watch event is malformed"
                    )
                raw_name = observed[offset:end].split(b"\0", 1)[0]
                offset = end
                watched_paths = self.paths_by_watch.get(
                    watch_descriptor
                )
                if not watched_paths:
                    raise ScopeError(
                        "release authority changed during receipt commit"
                    )
                event_paths = {
                    (
                        watched_path / os.fsdecode(raw_name)
                        if raw_name
                        else watched_path
                    ).absolute()
                    for watched_path in watched_paths
                }
                relevant_paths = {
                    event_path
                    for event_path in event_paths
                    if (
                        event_path in self.authority_paths
                        or (
                            bool(raw_name)
                            and any(
                                watched_path
                                in self.content_sensitive_directories
                                for watched_path in watched_paths
                            )
                        )
                    )
                }
                if allowed_closures:
                    closure_paths = (
                        relevant_paths & allowed_closures
                    )
                    close_write_bit = 0x00000008
                    if closure_paths:
                        if (
                            len(closure_paths) != 1
                            or mask
                            & self._MASK
                            & ~close_write_bit
                            or not (mask & close_write_bit)
                            or closure_paths & observed_closures
                        ):
                            raise ScopeError(
                                "release authority planned close "
                                "event is invalid"
                            )
                        observed_closures.update(closure_paths)
                        relevant_paths -= closure_paths
                if allowed_creations:
                    creation_paths = (
                        relevant_paths & allowed_creations
                    )
                    creation_bits = 0x00000100 | 0x00000080
                    close_write_bit = 0x00000008
                    if creation_paths:
                        if len(creation_paths) != 1:
                            raise ScopeError(
                                "release authority planned creation "
                                "event is invalid"
                            )
                        creation_path = next(iter(creation_paths))
                        if mask & creation_bits:
                            if (
                                mask
                                & self._MASK
                                & ~creation_bits
                                or creation_path
                                in observed_creations
                            ):
                                raise ScopeError(
                                    "release authority planned creation "
                                    "event is invalid"
                                )
                            observed_creations.add(creation_path)
                        elif mask & close_write_bit:
                            if (
                                mask
                                & self._MASK
                                & ~close_write_bit
                                or creation_path
                                not in observed_creations
                                or creation_path
                                in observed_closures
                            ):
                                raise ScopeError(
                                    "release authority planned creation "
                                    "close event is invalid"
                                )
                            observed_closures.add(creation_path)
                        else:
                            raise ScopeError(
                                "release authority planned creation "
                                "event is invalid"
                            )
                        relevant_paths -= creation_paths
                if relevant_paths - self.ignored_paths:
                    raise ScopeError(
                        "release authority changed during receipt commit"
                    )

    def close(self) -> None:
        if self.descriptor is not None:
            _close_quietly(self.descriptor)
            self.descriptor = None

    def ignore_path(self, path: Path) -> None:
        absolute = path.absolute()
        self._assert_disjoint(absolute)
        self.ignored_paths.add(absolute)

    def _assert_disjoint(self, path: Path) -> None:
        if (
            path in self.authority_paths
            or any(
                directory == path or directory in path.parents
                for directory in self.content_sensitive_directories
            )
        ):
            raise ScopeError(
                "scope union output overlaps watched release authority"
            )


def _verify_registry_checkout(
    path: Path,
    expected_commit: str,
) -> _VerificationGuard:
    if not path.is_absolute():
        raise ScopeError("Registry repository path must be absolute")
    _path_without_symlinks(path, "Registry repository")
    absolute = path.absolute()
    git_binary = Path("/usr/bin/git")
    try:
        git_stat = git_binary.lstat()
    except OSError as error:
        raise ScopeError("Registry Git authority is unavailable") from error
    if (
        not stat.S_ISREG(git_stat.st_mode)
        or git_stat.st_uid != 0
        or git_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ScopeError(
            "Registry Git authority must be the absolute root-owned /usr/bin/git"
        )
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_fds: list[int] = []
    directory_bindings: list[tuple[int, str, int, tuple[int, ...]]] = []
    repository_fd: Optional[int] = None
    held_sources: list[dict[str, Any]] = []
    held_git_metadata: list[_HeldDigest | _HeldAbsence] = []
    reviewed_object_ids: set[str] = set()
    reachable_object_ids: set[str] = set()
    registry_watch: _MutationWatch | None = None
    guard_returned = False
    try:
        root_fd = os.open(os.sep, directory_flags)
        directory_fds.append(root_fd)
        root_stat = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != 0
            or root_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ScopeError("Registry repository root is unsafe")
        parent_fd = root_fd
        components = absolute.parts[1:]
        if not components:
            raise ScopeError("Registry repository must not be the filesystem root")
        for index, component in enumerate(components):
            if component in {"", ".", ".."} or "\0" in component:
                raise ScopeError("Registry repository path is unsafe")
            linked = os.stat(
                component,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            try:
                opened = os.fstat(child_fd)
            except OSError:
                os.close(child_fd)
                raise
            if _directory_identity(linked) != _directory_identity(opened):
                os.close(child_fd)
                raise ScopeError(
                    "Registry repository parent changed while it was opened"
                )
            final_component = index + 1 == len(components)
            owner_is_safe = (
                opened.st_uid == os.geteuid()
                if final_component
                else opened.st_uid in {0, os.geteuid()}
            )
            writable_by_others = bool(
                opened.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            )
            root_sticky_boundary = (
                not final_component
                and opened.st_uid == 0
                and bool(opened.st_mode & stat.S_ISVTX)
            )
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not owner_is_safe
                or (writable_by_others and not root_sticky_boundary)
            ):
                os.close(child_fd)
                raise ScopeError(
                    "Registry repository path permissions are unsafe"
                )
            directory_fds.append(child_fd)
            directory_bindings.append(
                (
                    parent_fd,
                    component,
                    child_fd,
                    _directory_identity(opened),
                )
            )
            parent_fd = child_fd
        repository_fd = directory_fds[-1]
        repository_stat = os.fstat(repository_fd)
    except OSError as error:
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)
        raise ScopeError("Registry repository could not be held safely") from error
    except BaseException:
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)
        raise
    assert repository_fd is not None
    root_identity = _directory_identity(root_stat)
    held_path = f"/proc/self/fd/{repository_fd}"
    command_prefix = [
        str(git_binary),
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "diff.external=",
        "-C",
        held_path,
    ]
    git_environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_EXTERNAL_DIFF": "",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    }

    def repository_still_bound() -> None:
        try:
            if (
                _directory_identity(os.stat(os.sep, follow_symlinks=False))
                != root_identity
                or _directory_identity(os.fstat(directory_fds[0]))
                != root_identity
            ):
                raise ScopeError(
                    "Registry repository changed during Git inspection"
                )
            for parent_fd, component, child_fd, expected in directory_bindings:
                linked = os.stat(
                    component,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                opened = os.fstat(child_fd)
                if (
                    _directory_identity(linked) != expected
                    or _directory_identity(opened) != expected
                ):
                    raise ScopeError(
                        "Registry repository changed during Git inspection"
                    )
        except OSError as error:
            raise ScopeError(
                "Registry repository changed during Git inspection"
            ) from error
        if (
            _directory_identity(os.fstat(repository_fd))
            != _directory_identity(repository_stat)
        ):
            raise ScopeError("Registry repository changed during Git inspection")

    def run(
        *arguments: str,
        output_limit: int = MAX_GIT_CONTROL_OUTPUT_BYTES,
        pass_descriptors: Sequence[int] = (),
    ) -> subprocess.CompletedProcess[str]:
        if output_limit <= 0:
            raise ScopeError("Registry Git output bound is invalid")
        if (
            any(
                not isinstance(descriptor, int)
                or descriptor < 0
                or descriptor == repository_fd
                for descriptor in pass_descriptors
            )
            or len(set(pass_descriptors)) != len(pass_descriptors)
        ):
            raise ScopeError("Registry Git descriptor authority is invalid")
        repository_still_bound()
        command = [*command_prefix, *arguments]
        process: Optional[subprocess.Popen[bytes]] = None
        stdout_pipe: Any = None
        stderr_pipe: Any = None
        stdout = bytearray()
        stderr = bytearray()
        deadline = time.monotonic() + 30
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=git_environment,
                close_fds=True,
                pass_fds=(repository_fd, *pass_descriptors),
            )
            stdout_pipe = process.stdout
            stderr_pipe = process.stderr
            if stdout_pipe is None or stderr_pipe is None:
                raise OSError("Registry Git output pipes are unavailable")
            with selectors.DefaultSelector() as selector:
                for stream, target in (
                    (stdout_pipe, stdout),
                    (stderr_pipe, stderr),
                ):
                    descriptor = stream.fileno()
                    os.set_blocking(descriptor, False)
                    selector.register(
                        descriptor,
                        selectors.EVENT_READ,
                        target,
                    )
                while selector.get_map():
                    remaining_time = deadline - time.monotonic()
                    if remaining_time <= 0:
                        raise subprocess.TimeoutExpired(command, 30)
                    events = selector.select(remaining_time)
                    if not events:
                        raise subprocess.TimeoutExpired(command, 30)
                    for key, _mask in events:
                        target = key.data
                        total_size = len(stdout) + len(stderr)
                        chunk = os.read(
                            key.fd,
                            min(
                                64 * 1024,
                                output_limit + 1 - total_size,
                            ),
                        )
                        if not chunk:
                            selector.unregister(key.fd)
                            continue
                        target.extend(chunk)
                        if len(stdout) + len(stderr) > output_limit:
                            raise ScopeError(
                                "Registry Git authority output exceeded its bound"
                            )
            return_code = process.wait(
                timeout=max(0.001, deadline - time.monotonic())
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            if process is not None and process.poll() is None:
                process.kill()
            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            raise ScopeError(
                "Registry Git authority could not be inspected"
            ) from error
        except BaseException:
            if process is not None and process.poll() is None:
                process.kill()
            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            raise
        finally:
            if stdout_pipe is not None:
                stdout_pipe.close()
            if stderr_pipe is not None:
                stderr_pipe.close()
        repository_still_bound()
        try:
            stdout_text = stdout.decode("utf-8", errors="strict")
            stderr_text = stderr.decode("utf-8", errors="strict")
        except UnicodeError as error:
            raise ScopeError(
                "Registry Git authority output is not canonical UTF-8"
            ) from error
        return subprocess.CompletedProcess(
            command,
            return_code,
            stdout_text,
            stderr_text,
        )

    def open_protected_source(
        source_path: str,
    ) -> tuple[
        int,
        os.stat_result,
        int,
        str,
        list[tuple[int, str, tuple[int, ...], int]],
        list[int],
    ]:
        label = f"Registry release producer {source_path}"
        components = Path(source_path).parts
        if (
            not components
            or Path(source_path).is_absolute()
            or any(component in {"", ".", ".."} for component in components)
        ):
            raise ScopeError("Registry protected source path is unsafe")
        owned_directory_fds: list[int] = []
        bindings: list[tuple[int, str, tuple[int, ...], int]] = []
        parent_fd = repository_fd
        descriptor: Optional[int] = None
        try:
            for component in components[:-1]:
                before_path = os.stat(
                    component,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                if not stat.S_ISDIR(before_path.st_mode):
                    raise ScopeError(f"{label} must not traverse a symlink")
                next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                try:
                    opened = os.fstat(next_fd)
                except OSError:
                    os.close(next_fd)
                    raise
                if _directory_identity(before_path) != _directory_identity(opened):
                    os.close(next_fd)
                    raise ScopeError(
                        f"{label} parent changed while it was opened"
                    )
                if (
                    opened.st_uid != os.geteuid()
                    or opened.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                ):
                    os.close(next_fd)
                    raise ScopeError(
                        f"{label} parent permissions are unsafe"
                    )
                owned_directory_fds.append(next_fd)
                bindings.append(
                    (
                        parent_fd,
                        component,
                        _directory_identity(opened),
                        next_fd,
                    )
                )
                parent_fd = next_fd

            file_name = components[-1]
            before_path = os.stat(
                file_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            descriptor = os.open(
                file_name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent_fd,
            )
            before = os.fstat(descriptor)
            if _identity(before_path) != _identity(before):
                raise ScopeError(f"{label} changed while it was opened")
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ScopeError(f"{label} must be a single-link regular file")
            if before.st_uid != os.geteuid():
                raise ScopeError(
                    f"{label} must be owned by the current release operator"
                )
            if before.st_mode & 0o022:
                raise ScopeError(f"{label} must not be group/world writable")
            if not 1 <= before.st_size <= MAX_RELEASE_SOURCE_BYTES:
                raise ScopeError(
                    f"{label} must be non-empty and no larger than "
                    f"{MAX_RELEASE_SOURCE_BYTES} bytes"
                )
            return (
                descriptor,
                before,
                parent_fd,
                file_name,
                bindings,
                owned_directory_fds,
            )
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            for directory_fd in reversed(owned_directory_fds):
                os.close(directory_fd)
            raise ScopeError(f"{label} could not be opened safely") from error
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            for directory_fd in reversed(owned_directory_fds):
                os.close(directory_fd)
            raise

    def read_held_source(
        descriptor: int,
        before: os.stat_result,
        source_path: str,
    ) -> bytes:
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        except OSError as error:
            raise ScopeError(
                f"Registry release producer {source_path} could not be read safely"
            ) from error
        raw = b"".join(chunks)
        if len(raw) != before.st_size:
            raise ScopeError(
                f"Registry release producer {source_path} changed during stable read"
            )
        return raw

    def held_source_still_bound(
        descriptor: int,
        before: os.stat_result,
        parent_fd: int,
        file_name: str,
        bindings: list[tuple[int, str, tuple[int, ...], int]],
        source_path: str,
    ) -> None:
        label = f"Registry release producer {source_path}"
        try:
            current_file = os.stat(
                file_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            opened_file = os.fstat(descriptor)
            for binding_parent_fd, component, expected, opened_fd in bindings:
                current_directory = os.stat(
                    component,
                    dir_fd=binding_parent_fd,
                    follow_symlinks=False,
                )
                opened_directory = os.fstat(opened_fd)
                if (
                    _directory_identity(current_directory) != expected
                    or _directory_identity(opened_directory) != expected
                ):
                    raise ScopeError(
                        f"{label} changed during protected source comparison"
                    )
        except OSError as error:
            raise ScopeError(
                f"{label} changed during protected source comparison"
            ) from error
        if (
            _identity(current_file) != _identity(before)
            or _identity(opened_file) != _identity(before)
        ):
            raise ScopeError(
                f"{label} changed during protected source comparison"
            )

    def read_git_object(
        object_id: str,
        object_kind: str,
        *,
        maximum_size: int,
    ) -> bytes:
        if (
            GIT_COMMIT.fullmatch(object_id) is None
            or object_kind not in {"blob", "commit", "tree"}
        ):
            raise ScopeError("Registry reviewed Git object request is invalid")
        object_type = run("cat-file", "-t", object_id)
        if (
            object_type.returncode != 0
            or object_type.stdout != f"{object_kind}\n"
        ):
            raise ScopeError("Registry reviewed Git object type is invalid")
        object_size = run("cat-file", "-s", object_id)
        size_text = object_size.stdout.strip()
        if (
            object_size.returncode != 0
            or POSITIVE_DECIMAL.fullmatch(size_text) is None
            or int(size_text) > maximum_size
        ):
            raise ScopeError("Registry reviewed Git object size is invalid")
        expected_size = int(size_text)
        repository_still_bound()
        process: Optional[subprocess.Popen[bytes]] = None
        stdout_pipe: Any = None
        raw = bytearray()
        deadline = time.monotonic() + 30
        try:
            process = subprocess.Popen(
                [*command_prefix, "cat-file", object_kind, object_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=git_environment,
                close_fds=True,
                pass_fds=(repository_fd,),
            )
            stdout_pipe = process.stdout
            if stdout_pipe is None:
                raise OSError("Git blob pipe is unavailable")
            stdout_fd = stdout_pipe.fileno()
            os.set_blocking(stdout_fd, False)
            reached_eof = False
            with selectors.DefaultSelector() as selector:
                selector.register(stdout_fd, selectors.EVENT_READ)
                while not reached_eof and len(raw) <= expected_size:
                    remaining_time = deadline - time.monotonic()
                    if remaining_time <= 0:
                        raise subprocess.TimeoutExpired(
                            process.args,
                            30,
                        )
                    events = selector.select(remaining_time)
                    if not events:
                        raise subprocess.TimeoutExpired(
                            process.args,
                            30,
                        )
                    for _key, _mask in events:
                        try:
                            chunk = os.read(
                                stdout_fd,
                                min(
                                    1024 * 1024,
                                    expected_size + 1 - len(raw),
                                ),
                            )
                        except BlockingIOError:
                            continue
                        if not chunk:
                            reached_eof = True
                            break
                        raw.extend(chunk)
            if len(raw) > expected_size and process.poll() is None:
                process.kill()
            return_code = process.wait(
                timeout=max(0.001, deadline - time.monotonic())
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            if process is not None and process.poll() is None:
                process.kill()
            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            raise ScopeError(
                "Registry reviewed Git object could not be read safely"
            ) from error
        finally:
            if stdout_pipe is not None:
                stdout_pipe.close()
        repository_still_bound()
        if return_code != 0 or len(raw) != expected_size:
            raise ScopeError("Registry reviewed Git object read is invalid")
        reviewed = bytes(raw)
        git_object = (
            f"{object_kind} {len(reviewed)}\0".encode("ascii")
            + reviewed
        )
        observed_object_id = hashlib.sha1(
            git_object,
            usedforsecurity=False,
        ).hexdigest()
        if not hmac.compare_digest(observed_object_id, object_id):
            raise ScopeError("Registry reviewed Git object identity is invalid")
        reviewed_object_ids.add(object_id)
        return reviewed

    def commit_tree_object() -> str:
        raw_commit = read_git_object(
            expected_commit,
            "commit",
            maximum_size=MAX_RELEASE_SOURCE_BYTES,
        )
        headers = raw_commit.split(b"\n\n", 1)[0].splitlines()
        tree_headers = [
            line.removeprefix(b"tree ")
            for line in headers
            if line.startswith(b"tree ")
        ]
        if (
            not headers
            or len(tree_headers) != 1
            or headers[0] != b"tree " + tree_headers[0]
        ):
            raise ScopeError("Registry reviewed commit tree binding is invalid")
        try:
            tree_id = tree_headers[0].decode("ascii", errors="strict")
        except UnicodeError as error:
            raise ScopeError(
                "Registry reviewed commit tree binding is invalid"
            ) from error
        if GIT_COMMIT.fullmatch(tree_id) is None:
            raise ScopeError("Registry reviewed commit tree binding is invalid")
        return tree_id

    def parse_tree(
        raw_tree: bytes,
    ) -> dict[bytes, tuple[bytes, str]]:
        entries: dict[bytes, tuple[bytes, str]] = {}
        offset = 0
        while offset < len(raw_tree):
            space = raw_tree.find(b" ", offset)
            nul = raw_tree.find(b"\0", space + 1)
            if (
                space <= offset
                or nul <= space + 1
                or nul + 21 > len(raw_tree)
            ):
                raise ScopeError("Registry reviewed tree object is malformed")
            mode = raw_tree[offset:space]
            name = raw_tree[space + 1 : nul]
            raw_object_id = raw_tree[nul + 1 : nul + 21]
            if (
                name in {b"", b".", b".."}
                or b"/" in name
                or name in entries
                or len(raw_object_id) != 20
            ):
                raise ScopeError("Registry reviewed tree object is malformed")
            entries[name] = (mode, raw_object_id.hex())
            offset = nul + 21
        if offset != len(raw_tree):
            raise ScopeError("Registry reviewed tree object is malformed")
        return entries

    def read_head_blob(source_path: str) -> tuple[bytes, bytes]:
        components = Path(source_path).parts
        if (
            not components
            or Path(source_path).is_absolute()
            or any(component in {"", ".", ".."} for component in components)
        ):
            raise ScopeError("Registry protected source path is unsafe")
        tree_id = commit_tree_object()
        for index, component in enumerate(components):
            tree = parse_tree(
                read_git_object(
                    tree_id,
                    "tree",
                    maximum_size=MAX_RELEASE_SOURCE_BYTES,
                )
            )
            try:
                mode, object_id = tree[
                    component.encode("utf-8", errors="strict")
                ]
            except (KeyError, UnicodeError) as error:
                raise ScopeError(
                    f"Registry reviewed HEAD is missing required source path "
                    f"{source_path}"
                ) from error
            final = index + 1 == len(components)
            if final:
                if mode not in {b"100644", b"100755"}:
                    raise ScopeError(
                        "Registry reviewed source tree mode is not regular"
                    )
                return (
                    read_git_object(
                        object_id,
                        "blob",
                        maximum_size=MAX_RELEASE_SOURCE_BYTES,
                    ),
                    mode,
                )
            if mode != b"40000":
                raise ScopeError(
                    f"Registry reviewed HEAD is missing required source path "
                    f"{source_path}"
                )
            tree_id = object_id
        raise ScopeError(
            f"Registry reviewed HEAD is missing required source path "
            f"{source_path}"
        )

    try:
        expected_git_dir = absolute / ".git"
        try:
            expected_git_dir_stat = expected_git_dir.lstat()
        except OSError as error:
            raise ScopeError(
                "Registry repository requires a local Git metadata directory"
            ) from error
        if (
            not stat.S_ISDIR(expected_git_dir_stat.st_mode)
            or stat.S_ISLNK(expected_git_dir_stat.st_mode)
            or expected_git_dir_stat.st_uid != os.geteuid()
            or expected_git_dir_stat.st_mode
            & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ScopeError(
                "Registry linked worktrees and Git metadata indirection "
                "are not allowed"
            )
        config_path = expected_git_dir / "config"
        held_config = _hold_stable_file_digest(
            config_path,
            "Registry local Git configuration",
            maximum_size=MAX_GIT_CONFIG_BYTES,
        )
        held_git_metadata.append(held_config)
        config_keys = run(
            "config",
            "--file",
            f"/proc/self/fd/{held_config.descriptor}",
            "--no-includes",
            "--name-only",
            "--null",
            "--list",
            pass_descriptors=(held_config.descriptor,),
        )
        raw_config_keys = config_keys.stdout.split("\0")
        if (
            config_keys.returncode != 0
            or not raw_config_keys
            or raw_config_keys[-1] != ""
            or any(not key for key in raw_config_keys[:-1])
        ):
            raise ScopeError(
                "Registry local Git configuration could not be "
                "inspected canonically"
            )
        for raw_key in raw_config_keys[:-1]:
            key = raw_key.casefold()
            if key.startswith("fsck."):
                raise ScopeError(
                    "Registry local Git fsck policy configuration is not "
                    "allowed"
                )
            if (
                key in {
                    "extensions.partialclone",
                    "extensions.worktreeconfig",
                    "include.path",
                }
                or (
                    key.startswith("includeif.")
                    and key.endswith(".path")
                )
                or (
                    key.startswith("remote.")
                    and (
                        key.endswith(".promisor")
                        or key.endswith(".partialclonefilter")
                    )
                )
            ):
                raise ScopeError(
                    "Registry shallow, partial, included, or split Git "
                    "configuration is not allowed"
                )
        held_config.recheck()

        top_level = run("rev-parse", "--show-toplevel")
        if top_level.returncode != 0:
            raise ScopeError("Registry repository is not a Git worktree")
        try:
            observed_root = Path(top_level.stdout.strip()).resolve(strict=True)
            expected_root = absolute.resolve(strict=True)
        except OSError as error:
            raise ScopeError("Registry repository root could not be resolved") from error
        if observed_root != expected_root:
            raise ScopeError("Registry repository path is not the worktree root")

        def metadata_path(metadata_name: str) -> Path:
            metadata_path_result = run(
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                metadata_name,
            )
            candidate = Path(metadata_path_result.stdout.strip())
            if (
                metadata_path_result.returncode != 0
                or not candidate.is_absolute()
                or not candidate.name
            ):
                raise ScopeError("Registry HEAD metadata path is invalid")
            return candidate

        absolute_git_dir = run(
            "rev-parse",
            "--path-format=absolute",
            "--absolute-git-dir",
        )
        common_git_dir = run(
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
        try:
            expected_git_dir_resolved = expected_git_dir.resolve(strict=True)
            observed_git_dir = Path(
                absolute_git_dir.stdout.strip()
            ).resolve(strict=True)
            observed_common_dir = Path(
                common_git_dir.stdout.strip()
            ).resolve(strict=True)
        except OSError as error:
            raise ScopeError(
                "Registry Git metadata directory could not be resolved"
            ) from error
        if (
            absolute_git_dir.returncode != 0
            or common_git_dir.returncode != 0
            or observed_git_dir != expected_git_dir_resolved
            or observed_common_dir != expected_git_dir_resolved
        ):
            raise ScopeError(
                "Registry linked worktrees and split Git metadata "
                "are not allowed"
            )

        def hold_required_absence(path: Path, label: str) -> None:
            try:
                path.lstat()
            except FileNotFoundError:
                held_git_metadata.append(
                    _hold_path_absence(path, label)
                )
            except (OSError, ValueError) as error:
                raise ScopeError(
                    f"{label} could not be inspected safely"
                ) from error
            else:
                raise ScopeError(f"{label} is not allowed")

        shallow_path = metadata_path("shallow")
        grafts_path = metadata_path("info/grafts")
        config_worktree_path = metadata_path("config.worktree")
        hold_required_absence(
            shallow_path,
            "Registry shallow boundary metadata",
        )
        hold_required_absence(
            grafts_path,
            "Registry graft metadata",
        )
        hold_required_absence(
            config_worktree_path,
            "Registry worktree-specific Git configuration",
        )
        shallow = run("rev-parse", "--is-shallow-repository")
        if shallow.returncode != 0 or shallow.stdout != "false\n":
            raise ScopeError(
                "Registry shallow repositories are not allowed"
            )
        object_root = metadata_path("objects")
        _path_without_symlinks(
            object_root,
            "Registry reviewed Git object store",
        )
        for alternates_name in (
            "info/alternates",
            "info/http-alternates",
        ):
            hold_required_absence(
                object_root / alternates_name,
                "Registry reviewed Git object alternates",
            )

        head = run("rev-parse", "--verify", "HEAD^{commit}")
        if (
            head.returncode != 0
            or head.stdout.strip() != expected_commit
            or GIT_COMMIT.fullmatch(head.stdout.strip()) is None
        ):
            raise ScopeError(
                "review authority Registry commit does not equal the checked-out HEAD"
            )

        held_git_metadata.append(
            _hold_stable_file_digest(
                metadata_path("HEAD"),
                "Registry HEAD metadata",
            )
        )
        symbolic_head = run("symbolic-ref", "-q", "HEAD")
        if symbolic_head.returncode == 0:
            symbolic_name = symbolic_head.stdout.strip()
            if (
                not symbolic_name.startswith("refs/heads/")
                or any(
                    component in {"", ".", ".."}
                    for component in Path(symbolic_name).parts
                )
            ):
                raise ScopeError("Registry symbolic HEAD is unsafe")
            symbolic_path = metadata_path(symbolic_name)
            try:
                symbolic_path.lstat()
            except FileNotFoundError:
                held_git_metadata.append(
                    _hold_path_absence(
                        symbolic_path,
                        "Registry loose symbolic HEAD metadata",
                    )
                )
                held_git_metadata.append(
                    _hold_stable_file_digest(
                        metadata_path("packed-refs"),
                        "Registry packed symbolic HEAD metadata",
                    )
                )
            except (OSError, ValueError) as error:
                raise ScopeError(
                    "Registry symbolic HEAD metadata is unavailable"
                ) from error
            else:
                held_git_metadata.append(
                    _hold_stable_file_digest(
                        symbolic_path,
                        "Registry symbolic HEAD metadata",
                    )
                )
        elif symbolic_head.returncode != 1:
            raise ScopeError("Registry symbolic HEAD could not be inspected")
        object_format = run("rev-parse", "--show-object-format")
        if object_format.returncode != 0 or object_format.stdout != "sha1\n":
            raise ScopeError(
                "Registry reviewed commit requires the canonical SHA-1 Git object format"
            )
        def verify_full_graph() -> None:
            fsck = run(
                "fsck",
                "--strict",
                "--full",
                "--no-dangling",
                "--no-reflogs",
                "--no-progress",
                expected_commit,
            )
            if fsck.returncode != 0:
                raise ScopeError(
                    "Registry reviewed Git object graph is invalid"
                )

        verify_full_graph()
        reachable = run(
            "rev-list",
            "--objects",
            "--no-object-names",
            "--missing=print",
            expected_commit,
            output_limit=MAX_GIT_GRAPH_OUTPUT_BYTES,
        )
        reachable_lines = reachable.stdout.splitlines()
        if (
            reachable.returncode != 0
            or not reachable_lines
            or len(reachable_lines) > MAX_GIT_GRAPH_OBJECTS
            or any(object_id.startswith("?") for object_id in reachable_lines)
            or any(
                GIT_COMMIT.fullmatch(object_id) is None
                for object_id in reachable_lines
            )
            or len(set(reachable_lines)) != len(reachable_lines)
        ):
            raise ScopeError(
                "Registry reviewed Git object reachable inventory is invalid"
            )
        reachable_object_ids.update(reachable_lines)
        protected_paths = (
            "scripts/release/promote_public_stable_release_channel.sh",
            "scripts/materialize_public_release_channel.py",
            "scripts/verify_public_release_channel.py",
        )
        for source_path in protected_paths:
            (
                descriptor,
                before,
                parent_fd,
                file_name,
                bindings,
                owned_directory_fds,
            ) = open_protected_source(source_path)
            held = {
                "descriptor": descriptor,
                "before": before,
                "parent_fd": parent_fd,
                "file_name": file_name,
                "bindings": bindings,
                "owned_directory_fds": owned_directory_fds,
                "source_path": source_path,
                "working_bytes": b"",
            }
            held_sources.append(held)
            working_bytes = read_held_source(
                descriptor,
                before,
                source_path,
            )
            held["working_bytes"] = working_bytes
            reviewed_bytes, reviewed_mode = read_head_blob(source_path)
            held_source_still_bound(
                descriptor,
                before,
                parent_fd,
                file_name,
                bindings,
                source_path,
            )
            working_sha256 = hashlib.sha256(working_bytes).digest()
            reviewed_sha256 = hashlib.sha256(reviewed_bytes).digest()
            if (
                not hmac.compare_digest(working_sha256, reviewed_sha256)
                or not hmac.compare_digest(working_bytes, reviewed_bytes)
                or bool(before.st_mode & stat.S_IXUSR)
                != (reviewed_mode == b"100755")
            ):
                raise ScopeError(
                    "Registry release producer paths must be clean at the reviewed HEAD"
                )
        head_after_comparison = run("rev-parse", "--verify", "HEAD^{commit}")
        if (
            head_after_comparison.returncode != 0
            or head_after_comparison.stdout.strip() != expected_commit
        ):
            raise ScopeError(
                "Registry reviewed HEAD changed during protected source comparison"
            )

        def verify_head_metadata() -> None:
            repository_still_bound()
            current_head = run("rev-parse", "--verify", "HEAD^{commit}")
            if (
                current_head.returncode != 0
                or current_head.stdout.strip() != expected_commit
            ):
                raise ScopeError(
                    "Registry reviewed HEAD changed during protected "
                    "source comparison"
                )
            for metadata in held_git_metadata:
                metadata.recheck()

        def verify_guard() -> None:
            if registry_watch is not None:
                registry_watch.assert_quiet()
            verify_object_store_inventory()
            if registry_watch is not None:
                registry_watch.assert_quiet()
            verify_full_graph()
            verify_head_metadata()
            for held in held_sources:
                held_source_still_bound(
                    held["descriptor"],
                    held["before"],
                    held["parent_fd"],
                    held["file_name"],
                    held["bindings"],
                    held["source_path"],
                )
                readback = read_held_source(
                    held["descriptor"],
                    held["before"],
                    held["source_path"],
                )
                held_source_still_bound(
                    held["descriptor"],
                    held["before"],
                    held["parent_fd"],
                    held["file_name"],
                    held["bindings"],
                    held["source_path"],
                )
                if not hmac.compare_digest(
                    readback,
                    held["working_bytes"],
                ):
                    raise ScopeError(
                        "Registry release producer changed during final "
                        "held recheck"
                    )
                reviewed_bytes, reviewed_mode = read_head_blob(
                    held["source_path"]
                )
                if (
                    not hmac.compare_digest(
                        reviewed_bytes,
                        held["working_bytes"],
                    )
                    or bool(
                        held["before"].st_mode & stat.S_IXUSR
                    )
                    != (reviewed_mode == b"100755")
                ):
                    raise ScopeError(
                        "Registry release producer paths must be clean at "
                        "the reviewed HEAD"
                    )
                held_source_still_bound(
                    held["descriptor"],
                    held["before"],
                    held["parent_fd"],
                    held["file_name"],
                    held["bindings"],
                    held["source_path"],
                )
            verify_head_metadata()
            for held in reversed(held_sources):
                held_source_still_bound(
                    held["descriptor"],
                    held["before"],
                    held["parent_fd"],
                    held["file_name"],
                    held["bindings"],
                    held["source_path"],
                )
                readback = read_held_source(
                    held["descriptor"],
                    held["before"],
                    held["source_path"],
                )
                held_source_still_bound(
                    held["descriptor"],
                    held["before"],
                    held["parent_fd"],
                    held["file_name"],
                    held["bindings"],
                    held["source_path"],
                )
                if not hmac.compare_digest(
                    readback,
                    held["working_bytes"],
                ):
                    raise ScopeError(
                        "Registry release producer changed during final "
                        "held recheck"
                    )
            verify_head_metadata()
            verify_full_graph()
            verify_object_store_inventory()
            if registry_watch is not None:
                registry_watch.assert_quiet()

        def close_guard() -> None:
            if registry_watch is not None:
                registry_watch.close()
            for held in reversed(held_sources):
                _close_quietly(held["descriptor"])
                for directory_fd in reversed(
                    held["owned_directory_fds"]
                ):
                    _close_quietly(directory_fd)
            for metadata in reversed(held_git_metadata):
                metadata.close()
            for directory_fd in reversed(directory_fds):
                _close_quietly(directory_fd)

        watch_paths = [absolute]
        watch_paths.extend(
            absolute / held["source_path"]
            for held in held_sources
        )
        for metadata in held_git_metadata:
            if isinstance(metadata, _HeldDigest):
                watch_paths.append(metadata.path)
            else:
                watch_paths.append(metadata.path)
        watch_paths.append(object_root)
        pack_root = object_root / "pack"
        watch_paths.append(pack_root)

        def inspect_object_store() -> tuple[
            _GitObjectStoreInventory,
            set[Path],
            list[Path],
        ]:
            object_prefix_directories: set[Path] = set()
            discovered_watch_paths: list[Path] = []
            root_inventory: list[tuple[str, tuple[int, ...]]] = []
            loose_inventory: list[tuple[str, tuple[int, ...]]] = []
            pack_inventory: list[tuple[str, tuple[int, ...]]] = []
            try:
                with os.scandir(object_root) as entries:
                    root_entry_count = 0
                    for entry in entries:
                        root_entry_count += 1
                        if (
                            root_entry_count
                            > MAX_GIT_OBJECT_ROOT_ENTRIES
                            or len(os.fsencode(entry.name)) > 255
                        ):
                            raise ScopeError(
                                "Registry reviewed Git object root exceeds "
                                "its inventory bound"
                            )
                        entry_stat = entry.stat(follow_symlinks=False)
                        root_inventory.append(
                            (entry.name, _identity(entry_stat))
                        )
                        if entry.name in {"info", "pack"}:
                            if (
                                stat.S_ISLNK(entry_stat.st_mode)
                                or not stat.S_ISDIR(entry_stat.st_mode)
                            ):
                                raise ScopeError(
                                    "Registry reviewed Git object root "
                                    "contains an unsafe entry"
                                )
                            continue
                        if re.fullmatch(r"[0-9a-f]{2}", entry.name) is None:
                            raise ScopeError(
                                "Registry reviewed Git object root contains "
                                "an unexpected entry"
                            )
                        if (
                            stat.S_ISLNK(entry_stat.st_mode)
                            or not stat.S_ISDIR(entry_stat.st_mode)
                        ):
                            raise ScopeError(
                                "Registry reviewed loose Git object store "
                                "is unsafe"
                            )
                        object_prefix_directories.add(Path(entry.path))
            except OSError as error:
                raise ScopeError(
                    "Registry reviewed loose Git object store is unavailable"
                ) from error
            for object_id in sorted(
                reachable_object_ids | reviewed_object_ids
            ):
                prefix_directory = object_root / object_id[:2]
                try:
                    prefix_stat = prefix_directory.lstat()
                except FileNotFoundError:
                    prefix_stat = None
                except OSError as error:
                    raise ScopeError(
                        "Registry reviewed loose Git object store is "
                        "unavailable"
                    ) from error
                if prefix_stat is not None:
                    if (
                        not stat.S_ISDIR(prefix_stat.st_mode)
                        or stat.S_ISLNK(prefix_stat.st_mode)
                    ):
                        raise ScopeError(
                            "Registry reviewed loose Git object store is "
                            "unsafe"
                        )
                    object_prefix_directories.add(prefix_directory)
                loose_object_path = (
                    object_root / object_id[:2] / object_id[2:]
                )
                _path_without_symlinks(
                    loose_object_path,
                    "Registry reviewed loose Git object",
                    allow_missing=True,
                )
                try:
                    loose_stat = loose_object_path.lstat()
                except FileNotFoundError:
                    continue
                except OSError as error:
                    raise ScopeError(
                        "Registry reviewed loose Git object is unavailable"
                    ) from error
                if (
                    not stat.S_ISREG(loose_stat.st_mode)
                    or stat.S_ISLNK(loose_stat.st_mode)
                    or loose_stat.st_uid != os.geteuid()
                    or loose_stat.st_nlink != 1
                    or loose_stat.st_mode
                    & (stat.S_IWGRP | stat.S_IWOTH)
                ):
                    raise ScopeError(
                        "Registry reviewed loose Git object is unsafe"
                    )
                loose_inventory.append(
                    (object_id, _identity(loose_stat))
                )
                discovered_watch_paths.append(loose_object_path)
            try:
                pack_root_stat = pack_root.lstat()
                if (
                    not stat.S_ISDIR(pack_root_stat.st_mode)
                    or stat.S_ISLNK(pack_root_stat.st_mode)
                ):
                    raise ScopeError(
                        "Registry reviewed Git pack store is unsafe"
                    )
                with os.scandir(pack_root) as entries:
                    entry_count = 0
                    for entry in entries:
                        entry_count += 1
                        if (
                            entry_count > MAX_GIT_PACK_ENTRIES
                            or len(os.fsencode(entry.name)) > 255
                        ):
                            raise ScopeError(
                                "Registry reviewed Git pack store exceeds "
                                "its inventory bound"
                            )
                        entry_stat = entry.stat(follow_symlinks=False)
                        if (
                            stat.S_ISLNK(entry_stat.st_mode)
                            or not stat.S_ISREG(entry_stat.st_mode)
                        ):
                            raise ScopeError(
                                "Registry reviewed Git pack store contains "
                                "an unsafe entry"
                            )
                        if entry.name.endswith(".promisor"):
                            raise ScopeError(
                                "Registry partial-clone promisor packs "
                                "are not allowed"
                            )
                        pack_inventory.append(
                            (entry.name, _identity(entry_stat))
                        )
                        discovered_watch_paths.append(Path(entry.path))
            except FileNotFoundError:
                pass
            except OSError as error:
                raise ScopeError(
                    "Registry reviewed Git pack store is unavailable"
                ) from error
            return (
                _GitObjectStoreInventory(
                    root_entries=tuple(sorted(root_inventory)),
                    loose_objects=tuple(sorted(loose_inventory)),
                    pack_entries=tuple(sorted(pack_inventory)),
                ),
                object_prefix_directories,
                discovered_watch_paths,
            )

        (
            expected_object_store_inventory,
            object_prefix_directories,
            object_store_watch_paths,
        ) = inspect_object_store()
        watch_paths.extend(object_store_watch_paths)

        def verify_object_store_inventory() -> None:
            observed_inventory, _, _ = inspect_object_store()
            if observed_inventory != expected_object_store_inventory:
                raise ScopeError(
                    "Registry reviewed Git object store changed before or "
                    "during guarded verification"
                )

        registry_watch = _MutationWatch(
            watch_paths,
            content_sensitive_directories=[
                object_root,
                pack_root,
                *sorted(object_prefix_directories, key=str),
            ],
        )
        guard = _VerificationGuard(
            verify_callback=verify_guard,
            close_callback=close_guard,
            mutation_watch=registry_watch,
        )
        guard.verify()
        guard_returned = True
        return guard
    finally:
        if not guard_returned:
            if registry_watch is not None:
                registry_watch.close()
            for held in reversed(held_sources):
                _close_quietly(held["descriptor"])
                for directory_fd in reversed(
                    held["owned_directory_fds"]
                ):
                    _close_quietly(directory_fd)
            for metadata in reversed(held_git_metadata):
                metadata.close()
            for directory_fd in reversed(directory_fds):
                _close_quietly(directory_fd)


def _manifest_coverage(manifest: dict[str, Any]) -> None:
    coverage = manifest.get("desktopTupleCoverage")
    if not isinstance(coverage, dict):
        raise ScopeError("manifest desktopTupleCoverage must be an object")
    expected_tuple_values = sorted(
        f"avalonia:{rid}:{platform}" for platform, rid in PLATFORM_SPECS.items()
    )
    exact_values: dict[str, Any] = {
        "requiredDesktopPlatforms": REGISTRY_PLATFORM_ORDER,
        "requiredDesktopHeads": ["avalonia"],
        "requiredDesktopPlatformHeadRidTuples": expected_tuple_values,
        "promotedPlatformHeadRidTuples": expected_tuple_values,
        "missingRequiredPlatforms": [],
        "missingRequiredHeads": [],
        "missingRequiredPlatformHeadPairs": [],
        "missingRequiredPlatformHeadRidTuples": [],
        "externalProofRequests": [],
        "complete": True,
        "promotedPlatformHeads": {
            "linux": ["avalonia"],
            "windows": ["avalonia"],
            "macos": ["avalonia"],
        },
    }
    for field, expected in exact_values.items():
        if coverage.get(field) != expected:
            raise ScopeError(f"manifest desktopTupleCoverage.{field} is not the exact global floor")
    promoted = coverage.get("promotedInstallerTuples")
    if not isinstance(promoted, list) or len(promoted) != 3:
        raise ScopeError(
            "manifest desktopTupleCoverage.promotedInstallerTuples must contain exactly three rows"
        )
    expected_rows = [
        {
            "tupleId": f"avalonia:{platform}:{PLATFORM_SPECS[platform]}",
            "head": "avalonia",
            "platform": platform,
            "rid": PLATFORM_SPECS[platform],
            "kind": "installer",
        }
        for platform in REGISTRY_PLATFORM_ORDER
    ]
    observed_rows: list[dict[str, Any]] = []
    artifact_ids: set[str] = set()
    for index, row in enumerate(promoted):
        if not isinstance(row, dict):
            raise ScopeError(f"manifest promoted installer tuple {index} must be an object")
        artifact_id = row.get("artifactId")
        if (
            not isinstance(artifact_id, str)
            or decision_contract.SAFE_ID.fullmatch(artifact_id) is None
            or artifact_id in artifact_ids
        ):
            raise ScopeError("manifest promoted installer tuple artifact ids must be safe and unique")
        artifact_ids.add(artifact_id)
        observed_rows.append(
            {
                "tupleId": row.get("tupleId"),
                "head": row.get("head"),
                "platform": row.get("platform"),
                "rid": row.get("rid"),
                "kind": row.get("kind"),
            }
        )
    if observed_rows != expected_rows:
        raise ScopeError("manifest promoted installer tuples do not exactly match the global floor")


def _safe_basename(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or "\0" in value
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise ScopeError(f"{label} must be a safe basename")
    return value


@dataclass
class _HeldDigest:
    path: Path
    label: str
    descriptor: int
    before: os.stat_result
    parent_fd: int
    absolute_parent: Path
    sha256: str
    size: int

    def recheck(self) -> None:
        digest = hashlib.sha256()
        size = 0
        try:
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            remaining = self.size + 1
            while remaining:
                chunk = os.read(
                    self.descriptor,
                    min(1024 * 1024, remaining),
                )
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                remaining -= len(chunk)
            after = os.fstat(self.descriptor)
            current = os.stat(
                self.path.name,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
            _parent_still_bound(
                self.parent_fd,
                self.absolute_parent,
                self.label,
            )
        except OSError as error:
            raise ScopeError(f"{self.label} changed during held recheck") from error
        if (
            _identity(after) != _identity(self.before)
            or _identity(current) != _identity(self.before)
            or size != self.size
            or not hmac.compare_digest(digest.hexdigest(), self.sha256)
        ):
            raise ScopeError(f"{self.label} changed during held recheck")

    def close(self) -> None:
        _close_quietly(self.descriptor)
        _close_quietly(self.parent_fd)


@dataclass
class _HeldAbsence:
    path: Path
    label: str
    parent_fd: int
    absolute_parent: Path
    before_parent: os.stat_result

    def recheck(self) -> None:
        try:
            os.stat(
                self.path.name,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            raise ScopeError(
                f"{self.label} absence changed during held recheck"
            ) from error
        else:
            raise ScopeError(
                f"{self.label} absence changed during held recheck"
            )
        try:
            after_parent = os.fstat(self.parent_fd)
            _parent_still_bound(
                self.parent_fd,
                self.absolute_parent,
                self.label,
            )
        except OSError as error:
            raise ScopeError(
                f"{self.label} absence changed during held recheck"
            ) from error
        if (
            _directory_identity(after_parent)
            != _directory_identity(self.before_parent)
        ):
            raise ScopeError(
                f"{self.label} absence changed during held recheck"
            )

    def close(self) -> None:
        _close_quietly(self.parent_fd)


def _hold_path_absence(path: Path, label: str) -> _HeldAbsence:
    _safe_basename(path.name, label)
    parent_fd, absolute_parent = _open_existing_parent(path, label)
    try:
        before_parent = os.fstat(parent_fd)
        try:
            os.stat(
                path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            raise ScopeError(
                f"{label} absence could not be held safely"
            ) from error
        else:
            raise ScopeError(f"{label} expected an absent path")
        after_parent = os.fstat(parent_fd)
        _parent_still_bound(parent_fd, absolute_parent, label)
        if (
            _directory_identity(after_parent)
            != _directory_identity(before_parent)
        ):
            raise ScopeError(f"{label} absence changed while it was held")
        return _HeldAbsence(
            path=path,
            label=label,
            parent_fd=parent_fd,
            absolute_parent=absolute_parent,
            before_parent=before_parent,
        )
    except BaseException:
        os.close(parent_fd)
        raise


def _hold_stable_file_digest(
    path: Path,
    label: str,
    *,
    expected_size: int | None = None,
    maximum_size: int | None = None,
) -> _HeldDigest:
    descriptor, before, parent_fd, absolute_parent = _open_stable(
        path,
        label,
        private=False,
        bounded=False,
    )
    digest = hashlib.sha256()
    size = 0
    try:
        if maximum_size is not None and (
            maximum_size <= 0 or before.st_size > maximum_size
        ):
            raise ScopeError(f"{label} exceeds its size bound")
        if (
            expected_size is not None
            and before.st_size != expected_size
        ):
            raise ScopeError(f"{label} disagree with manifest size")
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, remaining),
            )
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        current = os.stat(
            path.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        _parent_still_bound(parent_fd, absolute_parent, label)
        if (
            _identity(before) != _identity(after)
            or _identity(before) != _identity(current)
            or size != before.st_size
        ):
            raise ScopeError(f"{label} changed during stable hash")
        return _HeldDigest(
            path=path,
            label=label,
            descriptor=descriptor,
            before=before,
            parent_fd=parent_fd,
            absolute_parent=absolute_parent,
            sha256=digest.hexdigest(),
            size=size,
        )
    except BaseException:
        os.close(descriptor)
        os.close(parent_fd)
        raise


def _verify_files_held(
    manifest: dict[str, Any],
    files_root: Path,
    held_files: list[_HeldDigest],
) -> tuple[list[str], str]:
    _path_without_symlinks(files_root, "candidate files root")
    try:
        root_stat = files_root.stat()
    except OSError as error:
        raise ScopeError("candidate files root is unavailable") from error
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ScopeError("candidate files root must be a directory")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ScopeError("candidate manifest contains no artifacts")
    ids: list[str] = []
    file_names: set[str] = set()
    inventory: list[dict[str, Any]] = []
    promoted_tuple_ids: dict[str, str] = {}
    coverage_rows = manifest["desktopTupleCoverage"]["promotedInstallerTuples"]
    for row in coverage_rows:
        promoted_tuple_ids[row["tupleId"]] = row["artifactId"]
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            raise ScopeError(f"candidate artifact row {index} must be an object")
        artifact_id = decision_contract._token(
            row.get("artifactId") or row.get("id"),
            f"artifacts[{index}].artifactId",
        )
        if artifact_id in ids:
            raise ScopeError("candidate artifact ids must be unique")
        ids.append(artifact_id)
        platform = decision_contract._platform(
            row.get("platform"),
            f"artifacts[{index}].platform",
        )
        head = decision_contract._token(row.get("head"), f"artifacts[{index}].head")
        rid = decision_contract._token(row.get("rid"), f"artifacts[{index}].rid")
        kind = decision_contract._token(row.get("kind"), f"artifacts[{index}].kind")
        if head != "avalonia" or PLATFORM_SPECS.get(platform) != rid:
            raise ScopeError(f"candidate artifact {artifact_id} is outside exact global scope")
        if row.get("installAccessClass") != "open_public":
            raise ScopeError(f"candidate artifact {artifact_id} is not open_public")
        if kind in decision_contract.INSTALLER_KINDS:
            tuple_id = f"{head}:{platform}:{rid}"
            if promoted_tuple_ids.get(tuple_id) != artifact_id:
                raise ScopeError(
                    f"candidate installer {artifact_id} disagrees with promoted tuple binding"
                )
        fields = [("primary", "fileName", "sha256", "sizeBytes")]
        payload_name = row.get("payloadFileName")
        if payload_name not in (None, ""):
            fields.append(
                ("payload", "payloadFileName", "payloadSha256", "payloadSizeBytes")
            )
        elif row.get("payloadSha256") not in (None, "") or row.get("payloadSizeBytes") not in (
            None,
            0,
        ):
            raise ScopeError(
                f"candidate artifact {artifact_id} has payload digest/size without payload file"
            )
        for role, name_field, sha_field, size_field in fields:
            file_name = _safe_basename(
                row.get(name_field),
                f"candidate artifact {artifact_id} {name_field}",
            )
            if file_name in file_names:
                raise ScopeError("candidate artifact file names must be globally unique")
            file_names.add(file_name)
            expected_sha = row.get(sha_field)
            if not isinstance(expected_sha, str):
                raise ScopeError(f"candidate artifact {artifact_id} {sha_field} is missing")
            expected_sha = _canonical_sha(
                expected_sha,
                f"candidate artifact {artifact_id} {sha_field}",
            )
            expected_size = row.get(size_field)
            if (
                not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size <= 0
            ):
                raise ScopeError(f"candidate artifact {artifact_id} {size_field} is invalid")
            held_file = _hold_stable_file_digest(
                files_root / file_name,
                f"candidate artifact {artifact_id} {role} bytes",
                expected_size=expected_size,
            )
            held_files.append(held_file)
            observed_sha = held_file.sha256
            observed_size = held_file.size
            if not hmac.compare_digest(observed_sha, expected_sha) or observed_size != expected_size:
                raise ScopeError(
                    f"candidate artifact {artifact_id} {role} bytes disagree with manifest"
                )
            inventory.append(
                {
                    "artifactId": artifact_id,
                    "role": role,
                    "fileName": file_name,
                    "sha256": observed_sha,
                    "sizeBytes": observed_size,
                }
            )
    inventory.sort(key=lambda row: (row["artifactId"], row["role"], row["fileName"]))
    encoded = json.dumps(
        inventory,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sorted(ids), hashlib.sha256(encoded).hexdigest()


def _verify_files(
    manifest: dict[str, Any],
    files_root: Path,
) -> tuple[list[str], str, list[_HeldDigest]]:
    held_files: list[_HeldDigest] = []
    try:
        artifact_ids, inventory_sha256 = _verify_files_held(
            manifest,
            files_root,
            held_files,
        )
        for held_file in held_files:
            held_file.recheck()
        return artifact_ids, inventory_sha256, held_files
    except BaseException:
        for held_file in reversed(held_files):
            held_file.close()
        raise


def _candidate_artifact_paths(
    manifest: dict[str, Any],
    files_root: Path,
) -> list[Path]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ScopeError("candidate manifest contains no artifacts")
    paths: list[Path] = []
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            raise ScopeError(
                f"candidate artifact row {index} must be an object"
            )
        paths.append(
            files_root
            / _safe_basename(
                row.get("fileName"),
                f"candidate artifact row {index} fileName",
            )
        )
        payload_name = row.get("payloadFileName")
        if payload_name not in (None, ""):
            paths.append(
                files_root
                / _safe_basename(
                    payload_name,
                    f"candidate artifact row {index} payloadFileName",
                )
            )
    return paths


@dataclass
class _SnapshotFile:
    path: Path
    descriptor: int
    parent_fd: int
    before: os.stat_result
    sha256: str
    size: int

    def recheck(self) -> None:
        digest = hashlib.sha256()
        observed_size = 0
        try:
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            remaining = self.size + 1
            while remaining:
                chunk = os.read(
                    self.descriptor,
                    min(1024 * 1024, remaining),
                )
                if not chunk:
                    break
                digest.update(chunk)
                observed_size += len(chunk)
                remaining -= len(chunk)
            opened = os.fstat(self.descriptor)
            linked = os.stat(
                self.path.name,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise ScopeError(
                "artifact snapshot object changed during held recheck"
            ) from error
        if (
            _identity(opened) != _identity(self.before)
            or _identity(linked) != _identity(self.before)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o400
            or observed_size != self.size
            or not hmac.compare_digest(
                digest.hexdigest(),
                self.sha256,
            )
        ):
            raise ScopeError(
                "artifact snapshot object changed during held recheck"
            )

    def close(self) -> None:
        _close_quietly(self.descriptor)


@dataclass
class _ArtifactSnapshotGuard:
    root: Path
    parent_fd: int
    root_fd: int
    objects_fd: int
    parent_identity: tuple[int, ...]
    root_identity: tuple[int, ...]
    objects_identity: tuple[int, ...]
    files: list[_SnapshotFile]
    object_names: frozenset[str]
    mutation_watch: _MutationWatch
    receipt_binding: dict[str, Any]
    closed: bool = False

    def verify(self) -> None:
        if self.closed:
            raise ScopeError("artifact snapshot guard is already closed")
        self.mutation_watch.assert_quiet()
        try:
            parent_opened = os.fstat(self.parent_fd)
            parent_linked = os.stat(
                self.root.parent,
                follow_symlinks=False,
            )
            root_opened = os.fstat(self.root_fd)
            root_linked = os.stat(
                self.root.name,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
            objects_opened = os.fstat(self.objects_fd)
            objects_linked = os.stat(
                "objects",
                dir_fd=self.root_fd,
                follow_symlinks=False,
            )
            root_names = set(os.listdir(self.root_fd))
            object_names = set(os.listdir(self.objects_fd))
        except OSError as error:
            raise ScopeError(
                "artifact snapshot directory changed during held recheck"
            ) from error
        if (
            _directory_identity(parent_opened)
            != self.parent_identity
            or _directory_identity(parent_linked)
            != self.parent_identity
            or _directory_identity(root_opened)
            != self.root_identity
            or _directory_identity(root_linked)
            != self.root_identity
            or _directory_identity(objects_opened)
            != self.objects_identity
            or _directory_identity(objects_linked)
            != self.objects_identity
            or parent_opened.st_uid != os.geteuid()
            or stat.S_IMODE(parent_opened.st_mode) & 0o077
            or root_opened.st_uid != os.geteuid()
            or stat.S_IMODE(root_opened.st_mode) != 0o700
            or objects_opened.st_uid != os.geteuid()
            or stat.S_IMODE(objects_opened.st_mode) != 0o700
            or root_names
            != {
                "objects",
                SNAPSHOT_MANIFEST_NAME,
                SNAPSHOT_COMMIT_NAME,
            }
            or object_names != set(self.object_names)
        ):
            raise ScopeError(
                "artifact snapshot directory changed during held recheck"
            )
        for snapshot_file in self.files:
            snapshot_file.recheck()
        for snapshot_file in reversed(self.files):
            snapshot_file.recheck()
        self.mutation_watch.assert_quiet()

    def close(self) -> None:
        if not self.closed:
            try:
                self.mutation_watch.close()
                for snapshot_file in reversed(self.files):
                    snapshot_file.close()
                _close_quietly(self.objects_fd)
                _close_quietly(self.root_fd)
                _close_quietly(self.parent_fd)
            finally:
                self.closed = True


def _read_descriptor_sha256(
    descriptor: int,
    expected_size: int,
    label: str,
) -> str:
    digest = hashlib.sha256()
    observed_size = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        remaining = expected_size + 1
        while remaining:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, remaining),
            )
            if not chunk:
                break
            digest.update(chunk)
            observed_size += len(chunk)
            remaining -= len(chunk)
    except OSError as error:
        raise ScopeError(f"{label} could not be read safely") from error
    if observed_size != expected_size:
        raise ScopeError(f"{label} changed during bounded read")
    return digest.hexdigest()


def _open_snapshot_stage(directory_fd: int) -> int:
    temporary_flag = getattr(os, "O_TMPFILE", 0)
    if temporary_flag == 0:
        raise ScopeError("artifact snapshot requires anonymous file staging")
    try:
        descriptor = os.open(
            ".",
            os.O_RDWR
            | temporary_flag
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=directory_fd,
        )
    except OSError as error:
        raise ScopeError(
            "artifact snapshot object could not be staged anonymously"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 0
        ):
            raise ScopeError(
                "artifact snapshot staging identity is unsafe"
            )
    except BaseException:
        _close_quietly(descriptor)
        raise
    return descriptor


def _write_all_descriptor(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        try:
            written = os.write(descriptor, raw[offset:])
        except OSError as error:
            raise ScopeError(
                "artifact snapshot write failed"
            ) from error
        if written <= 0:
            raise ScopeError(
                "artifact snapshot write made no progress"
            )
        offset += written


def _stage_snapshot_bytes(
    directory_fd: int,
    raw: bytes,
    expected_sha256: str,
) -> int:
    descriptor = _open_snapshot_stage(directory_fd)
    try:
        _write_all_descriptor(descriptor, raw)
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        observed_sha256 = _read_descriptor_sha256(
            descriptor,
            len(raw),
            "artifact snapshot staging",
        )
        if (
            opened.st_nlink != 0
            or opened.st_size != len(raw)
            or stat.S_IMODE(opened.st_mode) != 0o400
            or not hmac.compare_digest(
                observed_sha256,
                expected_sha256,
            )
        ):
            raise ScopeError(
                "artifact snapshot staging verification failed"
            )
        return descriptor
    except BaseException:
        _close_quietly(descriptor)
        raise


def _stage_snapshot_held_file(
    directory_fd: int,
    held: _HeldDigest,
) -> int:
    held.recheck()
    descriptor = _open_snapshot_stage(directory_fd)
    digest = hashlib.sha256()
    observed_size = 0
    try:
        os.lseek(held.descriptor, 0, os.SEEK_SET)
        remaining = held.size + 1
        while remaining:
            chunk = os.read(
                held.descriptor,
                min(1024 * 1024, remaining),
            )
            if not chunk:
                break
            digest.update(chunk)
            observed_size += len(chunk)
            _write_all_descriptor(descriptor, chunk)
            remaining -= len(chunk)
        if (
            observed_size != held.size
            or not hmac.compare_digest(
                digest.hexdigest(),
                held.sha256,
            )
        ):
            raise ScopeError(
                "candidate artifact changed during snapshot copy"
            )
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        observed_sha256 = _read_descriptor_sha256(
            descriptor,
            held.size,
            "artifact snapshot object",
        )
        held.recheck()
        if (
            opened.st_nlink != 0
            or opened.st_size != held.size
            or stat.S_IMODE(opened.st_mode) != 0o400
            or not hmac.compare_digest(
                observed_sha256,
                held.sha256,
            )
        ):
            raise ScopeError(
                "artifact snapshot object verification failed"
            )
        return descriptor
    except BaseException:
        _close_quietly(descriptor)
        raise


def _snapshot_records(
    manifest: dict[str, Any],
    held_artifacts: Sequence[_HeldDigest],
) -> list[dict[str, Any]]:
    held_by_name = {
        held.path.name: held
        for held in held_artifacts
    }
    if len(held_by_name) != len(held_artifacts):
        raise ScopeError(
            "candidate artifact snapshot sources are not unique"
        )
    records: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for index, row in enumerate(manifest["artifacts"]):
        artifact_id = decision_contract._token(
            row.get("artifactId") or row.get("id"),
            f"artifacts[{index}].artifactId",
        )
        field_sets = [
            ("primary", "fileName", "sha256", "sizeBytes"),
        ]
        if row.get("payloadFileName") not in (None, ""):
            field_sets.append(
                (
                    "payload",
                    "payloadFileName",
                    "payloadSha256",
                    "payloadSizeBytes",
                )
            )
        for role, name_field, sha_field, size_field in field_sets:
            source_name = _safe_basename(
                row.get(name_field),
                f"artifact snapshot {artifact_id} {name_field}",
            )
            held = held_by_name.get(source_name)
            expected_sha256 = _canonical_sha(
                row.get(sha_field),
                f"artifact snapshot {artifact_id} {sha_field}",
            )
            expected_size = row.get(size_field)
            if (
                held is None
                or not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or held.size != expected_size
                or not hmac.compare_digest(
                    held.sha256,
                    expected_sha256,
                )
            ):
                raise ScopeError(
                    "artifact snapshot source binding is inconsistent"
                )
            used_names.add(source_name)
            records.append(
                {
                    "artifactId": artifact_id,
                    "role": role,
                    "sourceFileName": source_name,
                    "objectName": f"sha256-{expected_sha256}",
                    "sha256": expected_sha256,
                    "sizeBytes": expected_size,
                }
            )
    if used_names != set(held_by_name):
        raise ScopeError(
            "artifact snapshot source inventory is inconsistent"
        )
    return sorted(
        records,
        key=lambda row: (
            row["artifactId"],
            row["role"],
            row["sourceFileName"],
        ),
    )


def _materialize_artifact_snapshot(
    *,
    root: Path,
    output: Path,
    manifest: dict[str, Any],
    held_artifacts: Sequence[_HeldDigest],
    release_version: str,
    manifest_sha256: str,
    inventory_sha256: str,
    registry_commit: str,
) -> _ArtifactSnapshotGuard:
    if not root.is_absolute():
        raise ScopeError("artifact snapshot root must be absolute")
    _path_without_symlinks(
        root,
        "artifact snapshot root",
        allow_missing=True,
    )
    root_name = _safe_basename(
        root.name,
        "artifact snapshot root name",
    )
    parent_fd, absolute_parent = _open_private_output_parent(root)
    root_fd: Optional[int] = None
    objects_fd: Optional[int] = None
    mutation_watch: _MutationWatch | None = None
    staged: dict[str, int] = {}
    snapshot_files: list[_SnapshotFile] = []
    guard_returned = False
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        parent_identity = _directory_identity(os.fstat(parent_fd))
        try:
            os.mkdir(root_name, 0o700, dir_fd=parent_fd)
        except FileExistsError as error:
            raise ScopeError(
                "artifact snapshot root already exists"
            ) from error
        root_fd = os.open(root_name, directory_flags, dir_fd=parent_fd)
        root_stat = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise ScopeError("artifact snapshot root is unsafe")
        os.mkdir("objects", 0o700, dir_fd=root_fd)
        objects_fd = os.open("objects", directory_flags, dir_fd=root_fd)
        objects_stat = os.fstat(objects_fd)
        if (
            not stat.S_ISDIR(objects_stat.st_mode)
            or objects_stat.st_uid != os.geteuid()
            or stat.S_IMODE(objects_stat.st_mode) != 0o700
        ):
            raise ScopeError("artifact snapshot object store is unsafe")

        records = _snapshot_records(manifest, held_artifacts)
        held_by_name = {
            held.path.name: held
            for held in held_artifacts
        }
        for record in records:
            object_name = record["objectName"]
            if object_name in staged:
                continue
            held = held_by_name[record["sourceFileName"]]
            staged[object_name] = _stage_snapshot_held_file(
                objects_fd,
                held,
            )
        context = {
            "releaseVersion": release_version,
            "manifestSha256": manifest_sha256,
            "filesRootInventorySha256": inventory_sha256,
            "registryCommit": registry_commit,
            "artifacts": records,
        }
        context_sha256 = hashlib.sha256(
            _canonical_json(context)
        ).hexdigest()
        transaction_id = (
            f"scope-union-snapshot-{context_sha256}"
        )
        snapshot_manifest = {
            "contractName": SNAPSHOT_CONTRACT,
            "contractVersion": 1,
            "status": "prepared",
            "authorizesCandidateProduction": False,
            "storagePosture": "mutable_audit_snapshot",
            "consumerRequirement": (
                "rehash_and_seal_before_publication"
            ),
            "contextSha256": context_sha256,
            "transactionId": transaction_id,
            **context,
        }
        snapshot_manifest_raw = _canonical_json(snapshot_manifest)
        snapshot_manifest_sha256 = hashlib.sha256(
            snapshot_manifest_raw
        ).hexdigest()
        staged[SNAPSHOT_MANIFEST_NAME] = _stage_snapshot_bytes(
            root_fd,
            snapshot_manifest_raw,
            snapshot_manifest_sha256,
        )
        snapshot_commit = {
            "contractName": SNAPSHOT_COMMIT_CONTRACT,
            "contractVersion": 1,
            "status": "committed",
            "authorizesCandidateProduction": False,
            "authorizationStatus": (
                "requires_publisher_consumption_receipt"
            ),
            "preparationReceiptFileName": _safe_basename(
                output.name,
                "scope union preparation output name",
            ),
            "contextSha256": context_sha256,
            "transactionId": transaction_id,
            "snapshotManifestFileName": SNAPSHOT_MANIFEST_NAME,
            "snapshotManifestSha256": snapshot_manifest_sha256,
            "objectCount": len(
                {record["objectName"] for record in records}
            ),
        }
        snapshot_commit_raw = _canonical_json(snapshot_commit)
        snapshot_commit_sha256 = hashlib.sha256(
            snapshot_commit_raw
        ).hexdigest()
        staged[SNAPSHOT_COMMIT_NAME] = _stage_snapshot_bytes(
            root_fd,
            snapshot_commit_raw,
            snapshot_commit_sha256,
        )

        object_paths = [
            root / "objects" / object_name
            for object_name in sorted(
                name
                for name in staged
                if name.startswith("sha256-")
            )
        ]
        manifest_path = root / SNAPSHOT_MANIFEST_NAME
        commit_path = root / SNAPSHOT_COMMIT_NAME
        planned_paths = [
            *object_paths,
            manifest_path,
            commit_path,
        ]
        publication_plan = [
            *(
                (object_path, objects_fd, object_path.name)
                for object_path in object_paths
            ),
            (
                manifest_path,
                root_fd,
                SNAPSHOT_MANIFEST_NAME,
            ),
            (
                commit_path,
                root_fd,
                SNAPSHOT_COMMIT_NAME,
            ),
        ]
        mutation_watch = _MutationWatch(
            [root, root / "objects", *planned_paths],
            ignored_paths=[output],
            content_sensitive_directories=[
                root,
                root / "objects",
            ],
        )
        if set(os.listdir(root_fd)) != {"objects"}:
            raise ScopeError(
                "artifact snapshot root changed before publication"
            )
        if os.listdir(objects_fd):
            raise ScopeError(
                "artifact snapshot object store changed before publication"
            )

        for object_path in object_paths:
            descriptor = staged[object_path.name]
            os.link(
                f"/proc/self/fd/{descriptor}",
                object_path.name,
                dst_dir_fd=objects_fd,
                follow_symlinks=True,
            )
        os.link(
            f"/proc/self/fd/{staged[SNAPSHOT_MANIFEST_NAME]}",
            SNAPSHOT_MANIFEST_NAME,
            dst_dir_fd=root_fd,
            follow_symlinks=True,
        )
        os.link(
            f"/proc/self/fd/{staged[SNAPSHOT_COMMIT_NAME]}",
            SNAPSHOT_COMMIT_NAME,
            dst_dir_fd=root_fd,
            follow_symlinks=True,
        )
        planned_closure_paths: list[Path] = []
        for final_path, directory_fd, staged_name in publication_plan:
            writable_descriptor = staged[staged_name]
            readable_descriptor: Optional[int] = None
            try:
                writable_stat = os.fstat(writable_descriptor)
                planned_closure_paths.append(
                    final_path.parent / f"#{writable_stat.st_ino}"
                )
                readable_descriptor = os.open(
                    final_path.name,
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=directory_fd,
                )
                readable_stat = os.fstat(readable_descriptor)
                linked_stat = os.stat(
                    final_path.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if (
                    _identity(writable_stat)
                    != _identity(readable_stat)
                    or _identity(readable_stat)
                    != _identity(linked_stat)
                    or stat.S_IMODE(readable_stat.st_mode) != 0o400
                ):
                    raise ScopeError(
                        "artifact snapshot read-only reopen failed"
                    )
            except BaseException:
                if readable_descriptor is not None:
                    _close_quietly(readable_descriptor)
                raise
            staged[staged_name] = readable_descriptor
            _close_quietly(writable_descriptor)
            try:
                os.fstat(writable_descriptor)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise ScopeError(
                        "artifact snapshot writable staging close "
                        "could not be verified"
                    ) from error
            else:
                raise ScopeError(
                    "artifact snapshot retained a writable descriptor"
                )
        mutation_watch.accept_exact_creations(
            planned_paths,
            closure_paths=planned_closure_paths,
        )
        os.fsync(objects_fd)
        os.fsync(root_fd)
        os.fsync(parent_fd)

        record_by_object = {
            record["objectName"]: record
            for record in records
        }
        for object_path in object_paths:
            record = record_by_object[object_path.name]
            descriptor = staged.pop(object_path.name)
            before = os.fstat(descriptor)
            snapshot_files.append(
                _SnapshotFile(
                    path=object_path,
                    descriptor=descriptor,
                    parent_fd=objects_fd,
                    before=before,
                    sha256=record["sha256"],
                    size=record["sizeBytes"],
                )
            )
        for file_path, raw, raw_sha256 in (
            (
                manifest_path,
                snapshot_manifest_raw,
                snapshot_manifest_sha256,
            ),
            (
                commit_path,
                snapshot_commit_raw,
                snapshot_commit_sha256,
            ),
        ):
            descriptor = staged.pop(file_path.name)
            snapshot_files.append(
                _SnapshotFile(
                    path=file_path,
                    descriptor=descriptor,
                    parent_fd=root_fd,
                    before=os.fstat(descriptor),
                    sha256=raw_sha256,
                    size=len(raw),
                )
            )
        guard = _ArtifactSnapshotGuard(
            root=root,
            parent_fd=parent_fd,
            root_fd=root_fd,
            objects_fd=objects_fd,
            parent_identity=parent_identity,
            root_identity=_directory_identity(os.fstat(root_fd)),
            objects_identity=_directory_identity(
                os.fstat(objects_fd)
            ),
            files=snapshot_files,
            object_names=frozenset(
                object_path.name for object_path in object_paths
            ),
            mutation_watch=mutation_watch,
            receipt_binding={
                "contractName": SNAPSHOT_CONTRACT,
                "root": str(root),
                "authorizesCandidateProduction": False,
                "storagePosture": "mutable_audit_snapshot",
                "consumerRequirement": (
                    "rehash_and_seal_before_publication"
                ),
                "contextSha256": context_sha256,
                "transactionId": transaction_id,
                "manifestFileName": SNAPSHOT_MANIFEST_NAME,
                "manifestSha256": snapshot_manifest_sha256,
                "commitFileName": SNAPSHOT_COMMIT_NAME,
                "commitSha256": snapshot_commit_sha256,
                "inventorySha256": inventory_sha256,
                "objectCount": len(object_paths),
            },
        )
        guard.verify()
        guard_returned = True
        return guard
    except OSError as error:
        raise ScopeError(
            "artifact snapshot publication failed; any partial snapshot "
            "is non-authorizing and retained for quarantine"
        ) from error
    finally:
        if not guard_returned:
            if mutation_watch is not None:
                mutation_watch.close()
            for snapshot_file in reversed(snapshot_files):
                snapshot_file.close()
            for descriptor in staged.values():
                _close_quietly(descriptor)
            if objects_fd is not None:
                _close_quietly(objects_fd)
            if root_fd is not None:
                _close_quietly(root_fd)
            _close_quietly(parent_fd)


def _verify_promotion_binding(
    promotion: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha: str,
    expected_version: str,
) -> None:
    _exact_string(
        promotion.get("releaseVersion"),
        expected_version,
        "promotion evidence releaseVersion",
    )
    _exact_string(
        promotion.get("manifestSha256"),
        manifest_sha,
        "promotion evidence manifestSha256",
    )
    promotion_rows = promotion.get("artifacts")
    manifest_rows = manifest.get("artifacts")
    if not isinstance(promotion_rows, list) or not isinstance(manifest_rows, list):
        raise ScopeError("promotion/manifest artifacts must be arrays")
    expected: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(manifest_rows):
        if not isinstance(row, dict):
            raise ScopeError(f"manifest artifact {index} must be an object")
        identity = _artifact_identity(row, f"manifest artifact {index}")
        expected[identity["artifactId"]] = {
            "artifactId": identity["artifactId"],
            "fileName": identity["fileName"],
            "platform": identity["platform"],
            "kind": identity["kind"],
            "artifactSha256": identity["sha256"],
            "artifactSizeBytes": identity["sizeBytes"],
        }
    observed: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(promotion_rows):
        if not isinstance(row, dict):
            raise ScopeError(f"promotion artifact {index} must be an object")
        artifact_id = decision_contract._token(
            row.get("artifactId"),
            f"promotion artifacts[{index}].artifactId",
        )
        if artifact_id in observed:
            raise ScopeError("promotion artifact IDs must be unique")
        observed[artifact_id] = {
            "artifactId": artifact_id,
            "fileName": _safe_basename(
                row.get("fileName"),
                f"promotion artifacts[{index}].fileName",
            ),
            "platform": decision_contract._platform(
                row.get("platform"),
                f"promotion artifacts[{index}].platform",
            ),
            "kind": decision_contract._token(
                row.get("kind"),
                f"promotion artifacts[{index}].kind",
            ),
            "artifactSha256": _canonical_sha(
                row.get("artifactSha256"),
                f"promotion artifacts[{index}].artifactSha256",
            )
            if isinstance(row.get("artifactSha256"), str)
            else "",
            "artifactSizeBytes": _positive_integer(
                row.get("artifactSizeBytes"),
                f"promotion artifacts[{index}].artifactSizeBytes",
            ),
        }
    if observed != expected:
        raise ScopeError(
            "promotion evidence does not bind every exact manifest artifact digest and size"
        )


def _verify_presentation(
    args: argparse.Namespace,
    decision_rows: list[dict[str, str]],
    review_contexts: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    decision_sha_by_platform = {
        row["platform"]: row["decisionSha256"] for row in decision_rows
    }
    output: list[dict[str, str]] = []
    observed_hashes: set[str] = set()
    for platform, rid in PLATFORM_SPECS.items():
        review = review_contexts[platform]
        for gate, contract in GATE_SPECS.items():
            raw = _stable_bytes(
                getattr(args, f"{platform}_{gate}_receipt"),
                f"{platform} {gate} Presentation receipt",
                private=True,
            )
            receipt_sha = hashlib.sha256(raw).hexdigest()
            if receipt_sha in observed_hashes:
                raise ScopeError("all nine Presentation receipts must be byte-distinct")
            observed_hashes.add(receipt_sha)
            payload = _strict_json(raw, f"{platform} {gate} Presentation receipt")
            _exact_string(
                payload.get("contract_name"),
                contract,
                f"{platform} {gate} Presentation contract_name",
            )
            _exact_string(
                payload.get("status"),
                "pass",
                f"{platform} {gate} Presentation status",
            )
            _exact_string(
                payload.get("channelId"),
                "public_stable",
                f"{platform} {gate} Presentation channelId",
            )
            release_version = _alias(
                payload,
                ("releaseVersion", "release_version", "version"),
                f"{platform} {gate} Presentation release version",
                exactly_one=True,
            )
            if release_version != args.expected_release_version:
                raise ScopeError(
                    f"{platform} {gate} Presentation release version disagrees with candidate"
                )
            if payload.get("reasons") != []:
                raise ScopeError(f"{platform} {gate} Presentation reasons must be empty")
            binding = payload.get("campaign_operability_candidate_binding")
            if not isinstance(binding, dict) or set(binding) != BINDING_FIELDS:
                raise ScopeError(
                    f"{platform} {gate} Presentation candidate binding has an unexpected field set"
                )
            expected_binding: dict[str, Any] = {
                "authority_snapshot_sha256": review["authoritySnapshotSha256"],
                "contract_name": BINDING_CONTRACT,
                "contract_version": 1,
                "manifest_sha256": review["manifestSha256"],
                "platform": platform,
                "primary_head": "avalonia",
                "registry_commit": review["registryCommit"],
                "release_decision_sha256": review["releaseDecisionSha256"],
                "release_scope_decision_sha256": decision_sha_by_platform[platform],
                "release_version": args.expected_release_version,
                "required_heads": ["avalonia"],
                "rid": rid,
            }
            if binding != expected_binding:
                raise ScopeError(
                    f"{platform} {gate} Presentation candidate binding disagrees with exact candidate"
                )
            output.append(
                {
                    "platform": platform,
                    "evidenceId": f"{platform}:{gate}",
                    "contractName": contract,
                    "sha256": receipt_sha,
                }
            )
    return output


def _receipt_candidate_row(
    payload: dict[str, Any],
    expected: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    rows = payload.get("artifacts")
    if not isinstance(rows, list):
        raise ScopeError(f"{label}.artifacts must be an array")
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("fileName") == expected["fileName"]
        and row.get("sha256") == expected["sha256"]
    ]
    if len(matches) != 1:
        raise ScopeError(f"{label} must contain one exact candidate artifact row")
    return matches[0]


def _verify_windows_signing(
    payload: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    label = "windows signing receipt"
    if (
        payload.get("signingBackend") != "digicert_keylocker_linux_jsign"
        or payload.get("digestAlgorithm") != "sha256"
    ):
        raise ScopeError(f"{label} does not use the governed SHA-256 KeyLocker backend")
    signer = _exact_object(
        payload.get("signer"),
        {"certificateSha256", "spkiSha256"},
        f"{label}.signer",
    )
    certificate_sha = _canonical_sha(
        signer.get("certificateSha256"),
        f"{label}.signer.certificateSha256",
    )
    spki_sha = _canonical_sha(
        signer.get("spkiSha256"),
        f"{label}.signer.spkiSha256",
    )
    timestamp = payload.get("timestamp")
    if (
        not isinstance(timestamp, dict)
        or timestamp.get("protocol") != "rfc3161"
        or timestamp.get("digestAlgorithm") != "sha256"
        or timestamp.get("status") != "verified"
    ):
        raise ScopeError(f"{label} does not prove a verified RFC3161 timestamp")
    signatures = payload.get("artifactSignatures")
    if not isinstance(signatures, list):
        raise ScopeError(f"{label}.artifactSignatures must be an array")
    artifact_rows = payload.get("artifacts")
    if not isinstance(artifact_rows, list):
        raise ScopeError(f"{label}.artifacts must be an array")
    artifact_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(artifact_rows):
        if (
            not isinstance(row, dict)
            or set(row) != {"fileName", "sha256", "kind", "signingStatus"}
            or row.get("signingStatus") != "pass"
        ):
            raise ScopeError(f"{label}.artifacts[{index}] is not an exact signed row")
        pair = (str(row.get("fileName")), str(row.get("sha256")))
        if pair in artifact_pairs:
            raise ScopeError(f"{label} artifact rows are duplicated")
        artifact_pairs.add(pair)
    signature_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(signatures):
        if not isinstance(row, dict):
            raise ScopeError(f"{label}.artifactSignatures[{index}] must be an object")
        pair = (
            str(row.get("artifactFileName")),
            str(row.get("artifactSha256")),
        )
        if pair in signature_pairs:
            raise ScopeError(f"{label} artifactSignatures are duplicated")
        signature_pairs.add(pair)
        row_timestamp = row.get("timestamp")
        row_timestamp_chain = (
            row_timestamp.get("chain")
            if isinstance(row_timestamp, dict)
            else None
        )
        row_signer_chain = row.get("signerChain")
        row_verifier = row.get("verifier")
        if (
            row.get("digestAlgorithm") != "sha256"
            or row.get("cryptographicVerification") != "passed"
            or row.get("signer") != signer
            or not isinstance(row_signer_chain, dict)
            or row_signer_chain.get("trusted") is not True
            or not isinstance(row_timestamp, dict)
            or row_timestamp.get("status") != "verified"
            or row_timestamp.get("format") != "rfc3161"
            or row_timestamp.get("digestAlgorithm") != "sha256"
            or not isinstance(row_timestamp_chain, dict)
            or row_timestamp_chain.get("trusted") is not True
            or not isinstance(row_verifier, dict)
            or row_verifier.get("providerIndependent") is not True
            or row_verifier.get("jsignOutputTrusted") is not False
        ):
            raise ScopeError(
                f"{label}.artifactSignatures[{index}] cryptographic evidence is invalid"
            )
    if signature_pairs != artifact_pairs:
        raise ScopeError(
            f"{label} every safe artifact row must have one independent signature binding"
        )
    matches = [
        row
        for row in signatures
        if isinstance(row, dict)
        and row.get("artifactFileName") == expected["fileName"]
        and row.get("artifactSha256") == expected["sha256"]
    ]
    if len(matches) != 1:
        raise ScopeError(f"{label} must contain one exact candidate artifactSignature")
    signature = matches[0]
    signature_signer = signature["signer"]
    if (
        signature_signer.get("certificateSha256") != certificate_sha
        or signature_signer.get("spkiSha256") != spki_sha
    ):
        raise ScopeError(f"{label} signer authority is internally inconsistent")
    candidate_row = _receipt_candidate_row(payload, expected, label)
    if (
        set(candidate_row) != {"fileName", "sha256", "kind", "signingStatus"}
        or candidate_row.get("kind") != "installer"
        or candidate_row.get("signingStatus") != "pass"
    ):
        raise ScopeError(f"{label} primary artifact row is not the exact v2 contract")
    candidate_bindings = payload.get("candidateBindings")
    expected_bindings = [
        {
            "artifactRole": "installer",
            "authenticodeStatus": "pass",
            "fileName": expected["fileName"],
            "sha256": expected["sha256"],
            "sizeBytes": expected["sizeBytes"],
        }
    ]
    if expected["payloadFileName"] is not None:
        expected_bindings.append(
            {
                "artifactRole": "payload",
                "authenticodeStatus": "not_applicable_payload",
                "fileName": expected["payloadFileName"],
                "sha256": expected["payloadSha256"],
                "sizeBytes": expected["payloadSizeBytes"],
            }
        )
    if candidate_bindings != expected_bindings:
        raise ScopeError(
            f"{label} candidateBindings do not bind installer and payload bytes"
        )


def _linux_source(value: Any, label: str) -> dict[str, Any]:
    source = _exact_object(
        value,
        {
            "actor",
            "environment",
            "ref",
            "repository",
            "runAttempt",
            "runId",
            "sha",
            "workflow",
        },
        label,
    )
    expected = {
        "environment": "linux-deb-signing",
        "ref": "refs/heads/main",
        "repository": "ArchonMegalon/chummer6-ui",
        "workflow": ".github/workflows/linux-native-candidate-export.yml",
    }
    for field, expected_value in expected.items():
        if source.get(field) != expected_value:
            raise ScopeError(f"{label}.{field} is not governed Linux signing authority")
    if (
        not isinstance(source.get("actor"), str)
        or not source["actor"].strip()
        or GIT_COMMIT.fullmatch(str(source.get("sha") or "")) is None
        or POSITIVE_DECIMAL.fullmatch(str(source.get("runId") or "")) is None
        or POSITIVE_DECIMAL.fullmatch(str(source.get("runAttempt") or "")) is None
    ):
        raise ScopeError(f"{label} GitHub producer identity is invalid")
    return source


def _linux_binding(value: Any, label: str) -> dict[str, Any]:
    binding = _exact_object(
        value,
        {"memberPath", "sha256", "sizeBytes"},
        label,
    )
    member_path = binding.get("memberPath")
    if (
        not isinstance(member_path, str)
        or not member_path
        or member_path.startswith("/")
        or ".." in Path(member_path).parts
        or "\\" in member_path
    ):
        raise ScopeError(f"{label}.memberPath is unsafe")
    _canonical_sha(binding.get("sha256"), f"{label}.sha256")
    _positive_integer(binding.get("sizeBytes"), f"{label}.sizeBytes")
    return binding


def _linux_export_source(value: Any, label: str) -> dict[str, Any]:
    source = _exact_object(
        value,
        {
            "actor",
            "ref",
            "repository",
            "runAttempt",
            "runId",
            "sha",
            "workflow",
        },
        label,
    )
    if (
        source.get("ref") != "refs/heads/main"
        or source.get("repository") != "ArchonMegalon/chummer6-ui"
        or source.get("workflow")
        != ".github/workflows/linux-native-candidate-export.yml"
        or not isinstance(source.get("actor"), str)
        or not source["actor"].strip()
        or GIT_COMMIT.fullmatch(str(source.get("sha") or "")) is None
        or POSITIVE_DECIMAL.fullmatch(str(source.get("runId") or "")) is None
        or POSITIVE_DECIMAL.fullmatch(str(source.get("runAttempt") or "")) is None
    ):
        raise ScopeError(f"{label} producer identity is invalid")
    return source


def _linux_export_artifact(value: Any, label: str) -> dict[str, Any]:
    artifact = _exact_object(
        value,
        {"fileName", "memberPath", "sha256", "sizeBytes"},
        label,
    )
    _safe_basename(artifact.get("fileName"), f"{label}.fileName")
    _linux_binding(
        {
            "memberPath": artifact.get("memberPath"),
            "sha256": artifact.get("sha256"),
            "sizeBytes": artifact.get("sizeBytes"),
        },
        label,
    )
    return artifact


def _verify_linux_export(
    args: argparse.Namespace,
    signing_payload: dict[str, Any],
    signing_raw: bytes,
    expected: dict[str, Any],
) -> None:
    raw = _stable_bytes(
        args.linux_signed_export_receipt,
        "linux signed export receipt",
        private=True,
    )
    export = _exact_object(
        _strict_json(raw, "linux signed export receipt"),
        {
            "artifact",
            "contractName",
            "contractVersion",
            "generatedAt",
            "livePredecessorAuthority",
            "nonPublishing",
            "package",
            "publicKeyring",
            "releaseVersion",
            "signingReceipt",
            "source",
            "status",
            "unsignedArtifact",
            "verificationPolicy",
        },
        "linux signed export receipt",
    )
    artifact = _linux_export_artifact(
        export.get("artifact"),
        "linux signed export artifact",
    )
    _linux_export_artifact(
        export.get("unsignedArtifact"),
        "linux signed export unsignedArtifact",
    )
    signing_binding = _linux_binding(
        export.get("signingReceipt"),
        "linux signed export signingReceipt",
    )
    policy_binding = _linux_binding(
        export.get("verificationPolicy"),
        "linux signed export verificationPolicy",
    )
    keyring_binding = _linux_binding(
        export.get("publicKeyring"),
        "linux signed export publicKeyring",
    )
    package = _exact_object(
        export.get("package"),
        {"architecture", "name", "version"},
        "linux signed export package",
    )
    predecessor = _exact_object(
        export.get("livePredecessorAuthority"),
        {
            "liveReleaseChannelSha256",
            "nMinusOneReleaseSha256",
            "selectedTupleSha256",
        },
        "linux signed export livePredecessorAuthority",
    )
    for field in predecessor:
        _canonical_sha(
            predecessor.get(field),
            f"linux signed export livePredecessorAuthority.{field}",
        )
    export_source = _linux_export_source(
        export.get("source"),
        "linux signed export source",
    )
    signing_source = signing_payload["source"]
    for field in export_source:
        if export_source[field] != signing_source[field]:
            raise ScopeError(
                "linux signing receipt and signed export producer identity disagree"
            )
    material = signing_payload["verificationMaterial"]
    if (
        export.get("contractName") != "chummer6-ui.linux-native-candidate-export"
        or export.get("contractVersion") != 3
        or export.get("releaseVersion") != args.expected_release_version
        or export.get("status") != "signed"
        or export.get("nonPublishing") is not True
        or artifact
        != {
            "fileName": expected["fileName"],
            "memberPath": f"files/{expected['fileName']}",
            "sha256": expected["sha256"],
            "sizeBytes": expected["sizeBytes"],
        }
        or signing_binding["sha256"] != hashlib.sha256(signing_raw).hexdigest()
        or signing_binding["sizeBytes"] != len(signing_raw)
        or policy_binding != material["policy"]
        or keyring_binding != material["publicKeyring"]
        or package.get("architecture") != "amd64"
        or package.get("name") != "chummer6-avalonia"
        or not isinstance(package.get("version"), str)
        or not package["version"].strip()
    ):
        raise ScopeError(
            "linux signed export does not bind the signed artifact, v2 signing "
            "receipt, verification policy, public keyring, and producer authority"
        )


def _verify_linux_signing(
    args: argparse.Namespace,
    payload: dict[str, Any],
    raw: bytes,
    expected: dict[str, Any],
) -> None:
    label = "linux signing receipt"
    exact_root = {
        "app",
        "contractName",
        "contractVersion",
        "platform",
        "rid",
        "releaseChannel",
        "releaseVersion",
        "generatedAt",
        "signingStatus",
        "signingBackend",
        "digestAlgorithm",
        "signer",
        "artifacts",
        "artifactSignatures",
        "verificationMaterial",
        "tools",
        "source",
    }
    _exact_object(payload, exact_root, label)
    if (
        payload.get("releaseChannel") != "stable"
        or payload.get("signingBackend") != "debsigs-origin-openpgp"
        or payload.get("digestAlgorithm") != "sha256"
    ):
        raise ScopeError(f"{label} does not use the governed debsigs stable backend")
    signer = _exact_object(
        payload.get("signer"),
        {"primaryFingerprint", "signingFingerprint", "longKeyId"},
        f"{label}.signer",
    )
    primary = str(signer.get("primaryFingerprint") or "")
    signing = str(signer.get("signingFingerprint") or "")
    long_id = str(signer.get("longKeyId") or "")
    if (
        UPPER_FINGERPRINT.fullmatch(primary) is None
        or signing != primary
        or long_id != primary[-16:]
    ):
        raise ScopeError(f"{label} signer must use one exact full dedicated fingerprint")
    rows = payload.get("artifacts")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ScopeError(f"{label}.artifacts must contain exactly one signed installer")
    row = rows[0]
    if row != {
        "fileName": expected["fileName"],
        "kind": "installer",
        "sha256": expected["sha256"],
        "signingStatus": "pass",
    }:
        raise ScopeError(f"{label} artifact row does not bind the exact signed package")
    signatures = payload.get("artifactSignatures")
    if not isinstance(signatures, list) or len(signatures) != 1:
        raise ScopeError(f"{label}.artifactSignatures must contain exactly one row")
    signature = signatures[0]
    if not isinstance(signature, dict):
        raise ScopeError(f"{label} artifactSignature must be an object")
    signature_fields = {
        "artifactFileName",
        "artifactSha256",
        "artifactSizeBytes",
        "cryptographicVerification",
        "digestAlgorithm",
        "signatureType",
        "signer",
        "verifier",
    }
    _exact_object(signature, signature_fields, f"{label}.artifactSignatures[0]")
    if (
        signature.get("artifactFileName") != expected["fileName"]
        or signature.get("artifactSha256") != expected["sha256"]
        or signature.get("artifactSizeBytes") != expected["sizeBytes"]
        or signature.get("cryptographicVerification") != "passed"
        or signature.get("digestAlgorithm") != "sha256"
        or signature.get("signatureType") != "origin"
        or signature.get("signer") != signer
    ):
        raise ScopeError(f"{label} artifactSignature does not bind signed candidate")
    verifier = _exact_object(
        signature.get("verifier"),
        {
            "backend",
            "providerIndependent",
            "positiveExitCode",
            "policySha256",
            "publicKeyringSha256",
            "openPgpSignature",
            "tamperNegative",
        },
        f"{label}.artifactSignatures[0].verifier",
    )
    openpgp = _exact_object(
        verifier.get("openPgpSignature"),
        {
            "fingerprint",
            "primaryFingerprint",
            "createdAt",
            "creationTimestamp",
            "hashAlgorithm",
        },
        f"{label}.artifactSignatures[0].verifier.openPgpSignature",
    )
    tamper = _exact_object(
        verifier.get("tamperNegative"),
        {"mutation", "expectedExitCode", "observedExitCode", "status"},
        f"{label}.artifactSignatures[0].verifier.tamperNegative",
    )
    if (
        verifier.get("backend") != "debsig-verify"
        or verifier.get("providerIndependent") is not True
        or verifier.get("positiveExitCode") != 0
        or openpgp.get("fingerprint") != primary
        or openpgp.get("primaryFingerprint") != primary
        or openpgp.get("hashAlgorithm") != "sha256"
        or not isinstance(openpgp.get("createdAt"), str)
        or not isinstance(openpgp.get("creationTimestamp"), int)
        or tamper
        != {
            "mutation": "data-member-byte-flip",
            "expectedExitCode": 13,
            "observedExitCode": 13,
            "status": "rejected",
        }
    ):
        raise ScopeError(f"{label} independent OpenPGP/tamper verification is invalid")
    material = _exact_object(
        payload.get("verificationMaterial"),
        {"policy", "publicKeyring"},
        f"{label}.verificationMaterial",
    )
    policy = _linux_binding(
        material.get("policy"),
        f"{label}.verificationMaterial.policy",
    )
    keyring = _linux_binding(
        material.get("publicKeyring"),
        f"{label}.verificationMaterial.publicKeyring",
    )
    if (
        policy["memberPath"]
        != f"signing/policies/{long_id}/chummer6-origin.pol"
        or keyring["memberPath"]
        != f"signing/keyrings/{long_id}/chummer6-origin.pgp"
        or verifier.get("policySha256") != policy["sha256"]
        or verifier.get("publicKeyringSha256") != keyring["sha256"]
    ):
        raise ScopeError(f"{label} policy/keyring authority is inconsistent")
    tools = _exact_object(
        payload.get("tools"),
        {"debsigs", "debsigVerify", "gpg", "gpgv"},
        f"{label}.tools",
    )
    for name, value in tools.items():
        tool = _exact_object(
            value,
            {"binarySha256", "packageName", "packageVersion"},
            f"{label}.tools.{name}",
        )
        _canonical_sha(
            tool.get("binarySha256"),
            f"{label}.tools.{name}.binarySha256",
        )
        if not isinstance(tool.get("packageName"), str) or not tool["packageName"]:
            raise ScopeError(f"{label}.tools.{name}.packageName is invalid")
        if not isinstance(tool.get("packageVersion"), str) or not tool["packageVersion"]:
            raise ScopeError(f"{label}.tools.{name}.packageVersion is invalid")
    if (
        tools["debsigs"]["packageVersion"] != "0.1.26"
        or tools["debsigVerify"]["packageVersion"] != "0.29"
    ):
        raise ScopeError(f"{label} debsigs/debsig-verify versions are not pinned")
    _linux_source(payload.get("source"), f"{label}.source")
    _verify_linux_export(args, payload, raw, expected)


def _verify_macos_signing_chain(
    args: argparse.Namespace,
    signing: dict[str, Any],
    signing_raw: bytes,
    expected: dict[str, Any],
) -> None:
    label = "macos signing authority"
    candidate_row = _receipt_candidate_row(signing, expected, "macos signing receipt")
    if (
        candidate_row.get("signingStatus") != "pass"
        or candidate_row.get("notarizationStatus") != "pass"
    ):
        raise ScopeError("macos signing receipt candidate is not signed and notarized")
    identity_raw = _stable_bytes(
        args.macos_signing_identity_receipt,
        "macos signing identity receipt",
        private=True,
    )
    notary_raw = _stable_bytes(
        args.macos_notary_result,
        "macos notarytool result",
        private=True,
    )
    authority_raw = _stable_bytes(
        args.macos_source_authority_receipt,
        "macos source authority receipt",
        private=True,
    )
    aggregate_raw = _stable_bytes(
        args.macos_aggregate_evidence,
        "macos flagship aggregate evidence",
        private=True,
    )
    identity = _exact_object(
        _strict_json(identity_raw, "macos signing identity receipt"),
        MAC_IDENTITY_FIELDS,
        "macos signing identity receipt",
    )
    notary = _strict_json(notary_raw, "macos notarytool result")
    authority = _exact_object(
        _strict_json(authority_raw, "macos source authority receipt"),
        MAC_AUTHORITY_FIELDS,
        "macos source authority receipt",
    )
    aggregate = _exact_object(
        _strict_json(aggregate_raw, "macos flagship aggregate evidence"),
        {
            "candidate",
            "cleanInstall",
            "contractName",
            "contractVersion",
            "generatedAtUtc",
            "github",
            "globalCandidateIdentity",
            "inputBindings",
            "inventorySha256",
            "livePredecessorAuthority",
            "nonPublishing",
            "references",
            "releaseVersion",
            "rid",
            "runner",
            "signing",
            "sourceUnsignedCandidate",
            "status",
            "updateDelivery",
        },
        "macos flagship aggregate evidence",
    )
    github = _exact_object(
        authority.get("github"),
        MAC_GITHUB_FIELDS,
        "macos source authority github",
    )
    if (
        authority.get("contractName")
        != "chummer6-ui.macos-flagship-authority-validation"
        or authority.get("contractVersion") != 2
        or authority.get("releaseVersion") != args.expected_release_version
        or authority.get("rid") != "osx-arm64"
        or authority.get("status") != "pass"
        or github.get("repository") != "ArchonMegalon/chummer6-ui"
        or github.get("workflow") != ".github/workflows/macos-flagship-evidence.yml"
        or github.get("ref") != "refs/heads/main"
        or github.get("rerunPolicy") != "same-actor-only"
        or github.get("actor") != github.get("triggeringActor")
        or GIT_COMMIT.fullmatch(str(github.get("sha") or "")) is None
        or POSITIVE_DECIMAL.fullmatch(str(github.get("runId") or "")) is None
        or POSITIVE_DECIMAL.fullmatch(str(github.get("runAttempt") or "")) is None
    ):
        raise ScopeError(f"{label} protected workflow provenance is invalid")
    live = _exact_object(
        authority.get("livePredecessorAuthority"),
        {
            "liveReleaseChannelSha256",
            "nMinusOneReleaseSha256",
            "selectedTupleSha256",
            "url",
        },
        "macos source authority livePredecessorAuthority",
    )
    if live.get("url") != "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
        raise ScopeError(f"{label} live predecessor URL is invalid")
    for field in (
        "liveReleaseChannelSha256",
        "nMinusOneReleaseSha256",
        "selectedTupleSha256",
    ):
        _canonical_sha(live.get(field), f"{label}.{field}")
    artifact = _exact_object(
        identity.get("artifact"),
        {"fileName", "sha256", "sizeBytes"},
        "macos signing identity artifact",
    )
    certificate = _exact_object(
        identity.get("certificate"),
        {
            "developerIdApplicationIdentity",
            "sha256",
            "spkiSha256",
            "teamId",
        },
        "macos signing identity certificate",
    )
    notarization = _exact_object(
        identity.get("notarization"),
        {"resultSha256", "status", "submissionId"},
        "macos signing identity notarization",
    )
    team_id = str(certificate.get("teamId") or "")
    developer_id = str(certificate.get("developerIdApplicationIdentity") or "")
    submission_id = str(notarization.get("submissionId") or "")
    if (
        identity.get("contractName")
        != "chummer6-ui.macos-signing-notarization-identity.v1"
        or identity.get("contractVersion") != 1
        or identity.get("status") != "pass"
        or identity.get("releaseVersion") != args.expected_release_version
        or identity.get("rid") != "osx-arm64"
        or identity.get("provenance") != github
        or artifact
        != {
            "fileName": expected["fileName"],
            "sha256": expected["sha256"],
            "sizeBytes": expected["sizeBytes"],
        }
        or TEAM_ID.fullmatch(team_id) is None
        or not developer_id.startswith("Developer ID Application:")
        or not developer_id.endswith(f"({team_id})")
        or not isinstance(certificate.get("sha256"), str)
        or not isinstance(certificate.get("spkiSha256"), str)
        or _canonical_sha(certificate["sha256"], f"{label} certificate SHA-256")
        != certificate["sha256"]
        or _canonical_sha(certificate["spkiSha256"], f"{label} SPKI SHA-256")
        != certificate["spkiSha256"]
        or notarization.get("status") != "Accepted"
        or UUID.fullmatch(submission_id) is None
        or notary.get("status") != "Accepted"
        or str(notary.get("id") or "").lower() != submission_id
        or notarization.get("resultSha256") != hashlib.sha256(notary_raw).hexdigest()
        or identity.get("signingReceiptSha256")
        != hashlib.sha256(signing_raw).hexdigest()
        or identity.get("sourceAuthorityReceiptSha256")
        != hashlib.sha256(authority_raw).hexdigest()
    ):
        raise ScopeError(f"{label} certificate/notary/staple identity chain is invalid")
    aggregate_candidate = _exact_object(
        aggregate.get("candidate"),
        {"artifactId", "fileName", "sha256", "sizeBytes"},
        "macos aggregate candidate",
    )
    aggregate_signing = _exact_object(
        aggregate.get("signing"),
        {
            "candidateDmgGatekeeperStatus",
            "certificateSha256",
            "certificateSpkiSha256",
            "developerIdApplicationIdentity",
            "gatekeeperAssessmentsEnabled",
            "installedAppGatekeeperStatus",
            "notarizationStatus",
            "notarySubmissionId",
            "postUpdateAppGatekeeperStatus",
            "staplerValidationStatus",
            "signingStatus",
            "teamId",
        },
        "macos aggregate signing authority",
    )
    input_bindings = _exact_object(
        aggregate.get("inputBindings"),
        MAC_AGGREGATE_INPUT_BINDING_FIELDS,
        "macos aggregate inputBindings",
    )
    for field, value in input_bindings.items():
        _canonical_sha(value, f"macos aggregate inputBindings.{field}")
    if (
        aggregate.get("contractName") != "chummer6-ui.macos-flagship-evidence"
        or aggregate.get("contractVersion") != 3
        or aggregate.get("status") != "pass"
        or aggregate.get("releaseVersion") != args.expected_release_version
        or aggregate.get("rid") != "osx-arm64"
        or aggregate.get("github") != github
        or aggregate.get("livePredecessorAuthority") != live
        or aggregate_candidate
        != {
            "artifactId": expected["artifactId"],
            "fileName": expected["fileName"],
            "sha256": expected["sha256"],
            "sizeBytes": expected["sizeBytes"],
        }
        or input_bindings.get("authorityReceiptSha256")
        != hashlib.sha256(authority_raw).hexdigest()
        or input_bindings.get("notaryResultSha256")
        != hashlib.sha256(notary_raw).hexdigest()
        or input_bindings.get("signingReceiptSha256")
        != hashlib.sha256(signing_raw).hexdigest()
        or input_bindings.get("signingIdentityReceiptSha256")
        != hashlib.sha256(identity_raw).hexdigest()
        or aggregate_signing
        != {
            "candidateDmgGatekeeperStatus": "pass",
            "certificateSha256": certificate["sha256"],
            "certificateSpkiSha256": certificate["spkiSha256"],
            "developerIdApplicationIdentity": developer_id,
            "gatekeeperAssessmentsEnabled": True,
            "installedAppGatekeeperStatus": "pass",
            "notarizationStatus": "Accepted",
            "notarySubmissionId": submission_id,
            "postUpdateAppGatekeeperStatus": "pass",
            "staplerValidationStatus": "pass",
            "signingStatus": "pass",
            "teamId": team_id,
        }
    ):
        raise ScopeError(
            "macos aggregate does not prove exact Developer ID, notarization, "
            "stapling, Gatekeeper, and candidate bindings"
        )


def _verify_signing_receipts(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ScopeError("candidate manifest artifacts must be an array")
    expected_by_platform: dict[str, dict[str, Any]] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ScopeError(f"candidate artifact row {index} must be an object")
        identity = _artifact_identity(artifact, f"artifacts[{index}]")
        platform = identity["platform"]
        if platform in expected_by_platform:
            raise ScopeError("signing authority requires one exact artifact per platform")
        expected_by_platform[platform] = identity
    output: list[dict[str, str]] = []
    observed_hashes: set[str] = set()
    for platform, rid in PLATFORM_SPECS.items():
        raw = _stable_bytes(
            getattr(args, f"{platform}_signing_receipt"),
            f"{platform} signing receipt",
            private=True,
        )
        receipt_sha = hashlib.sha256(raw).hexdigest()
        expected_receipt_sha = _canonical_sha(
            getattr(args, f"{platform}_signing_receipt_sha256"),
            f"{platform} signing receipt expected SHA-256",
        )
        if not hmac.compare_digest(receipt_sha, expected_receipt_sha):
            raise ScopeError(f"{platform} signing receipt SHA-256 does not match")
        if receipt_sha in observed_hashes:
            raise ScopeError("platform signing receipts must be byte-distinct")
        observed_hashes.add(receipt_sha)
        payload = _strict_json(raw, f"{platform} signing receipt")
        _exact_string(
            payload.get("contractName"),
            "chummer6-ui.desktop_artifact_signing",
            f"{platform} signing receipt contractName",
        )
        if payload.get("contractVersion") != 2:
            raise ScopeError(f"{platform} signing receipt contractVersion must be exactly 2")
        _exact_string(payload.get("platform"), platform, f"{platform} signing receipt platform")
        _exact_string(payload.get("app"), "avalonia", f"{platform} signing receipt app")
        _exact_string(payload.get("rid"), rid, f"{platform} signing receipt rid")
        release_channel = payload.get("releaseChannel")
        if release_channel is not None and release_channel not in {"stable", "public_stable"}:
            raise ScopeError(
                f"{platform} signing receipt releaseChannel is not stable/public_stable"
            )
        _exact_string(
            payload.get("releaseVersion"),
            args.expected_release_version,
            f"{platform} signing receipt releaseVersion",
        )
        _exact_string(
            payload.get("signingStatus"),
            "pass",
            f"{platform} signing receipt signingStatus",
        )
        notarization = payload.get("notarizationStatus")
        if platform == "macos":
            _exact_string(
                notarization,
                "pass",
                "macos signing receipt notarizationStatus",
            )
        elif notarization not in (None, "not_applicable"):
            raise ScopeError(
                f"{platform} signing receipt notarizationStatus must be null/not_applicable"
            )
        rows = payload.get("artifacts")
        if not isinstance(rows, list) or not rows:
            raise ScopeError(f"{platform} signing receipt artifacts must be non-empty")
        observed: list[dict[str, str]] = []
        seen_names: set[str] = set()
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ScopeError(
                    f"{platform} signing receipt artifact row {row_index} must be an object"
                )
            file_name = _safe_basename(
                row.get("fileName"),
                f"{platform} signing receipt artifacts[{row_index}].fileName",
            )
            if file_name in seen_names:
                raise ScopeError(f"{platform} signing receipt artifact file names must be unique")
            seen_names.add(file_name)
            signing = row.get("signingStatus")
            if signing != "pass":
                raise ScopeError(
                    f"{platform} signing receipt artifact {file_name} is not signed"
                )
            row_notarization = row.get("notarizationStatus")
            if platform == "macos" and row_notarization != "pass":
                raise ScopeError(
                    f"macos signing receipt artifact {file_name} is not notarized"
                )
            if platform != "macos" and row_notarization not in (None, "not_applicable"):
                raise ScopeError(
                    f"{platform} signing receipt artifact {file_name} has invalid notarization"
                )
            sha = row.get("sha256")
            if not isinstance(sha, str):
                raise ScopeError(
                    f"{platform} signing receipt artifact {file_name} sha256 is missing"
                )
            observed.append(
                {
                    "fileName": file_name,
                    "sha256": _canonical_sha(
                        sha,
                        f"{platform} signing receipt artifact {file_name} sha256",
                    ),
                    "kind": decision_contract._token(
                        row.get("kind"),
                        f"{platform} signing receipt artifact {file_name} kind",
                    ),
                }
            )
        expected = expected_by_platform[platform]
        primary_matches = [
            row
            for row in observed
            if row
            == {
                "fileName": expected["fileName"],
                "sha256": expected["sha256"],
                "kind": expected["kind"],
            }
        ]
        if len(primary_matches) != 1:
            raise ScopeError(
                f"{platform} signing receipt does not bind exactly one primary manifest artifact"
            )
        if platform == "windows":
            _verify_windows_signing(payload, expected)
        elif platform == "linux":
            _verify_linux_signing(args, payload, raw, expected)
        else:
            _verify_macos_signing_chain(args, payload, raw, expected)
        output.append(
            {
                "platform": platform,
                "contractName": "chummer6-ui.desktop_artifact_signing",
                "contractVersion": "2",
                "sha256": receipt_sha,
            }
        )
    return output


def _open_private_output_parent(path: Path) -> tuple[int, Path]:
    absolute = path.absolute()
    if absolute.name in {"", ".", ".."} or "\0" in absolute.name:
        raise ScopeError("scope union output name is invalid")
    parent = absolute.parent
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        directory_fd = os.open(absolute.anchor or os.sep, directory_flags)
    except OSError as error:
        raise ScopeError("scope union output anchor could not be opened safely") from error
    try:
        for component in parent.parts[1:]:
            if component in {"", ".", ".."} or "\0" in component:
                raise ScopeError("scope union output parent contains an unsafe component")
            try:
                before = os.stat(
                    component,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o700, dir_fd=directory_fd)
                    before = os.stat(
                        component,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except (OSError, ValueError) as error:
                    raise ScopeError(
                        "scope union output parent could not be created safely"
                    ) from error
            if not stat.S_ISDIR(before.st_mode):
                raise ScopeError(
                    "scope union output parent contains a symlink or non-directory"
                )
            try:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except OSError as error:
                raise ScopeError(
                    "scope union output parent could not be opened safely"
                ) from error
            try:
                opened = os.fstat(next_fd)
            except OSError as error:
                os.close(next_fd)
                raise ScopeError(
                    "scope union output parent could not be opened safely"
                ) from error
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                os.close(next_fd)
                raise ScopeError("scope union output parent changed while it was opened")
            try:
                os.fsync(next_fd)
                os.fsync(directory_fd)
            except OSError as error:
                os.close(next_fd)
                raise ScopeError(
                    "scope union output parent could not be made durable"
                ) from error
            os.close(directory_fd)
            directory_fd = next_fd
        parent_stat = os.fstat(directory_fd)
        if (
            parent_stat.st_uid != os.geteuid()
            or stat.S_IMODE(parent_stat.st_mode) & 0o077
        ):
            raise ScopeError(
                "scope union output parent must be caller-owned and private"
            )
        return directory_fd, parent
    except BaseException:
        os.close(directory_fd)
        raise


def _write_new(
    path: Path,
    payload: dict[str, Any],
    *,
    post_write_check: Callable[[], None] | None = None,
    mutation_watch: _MutationWatch | None = None,
) -> None:
    raw = _canonical_json(payload)
    output_name = _safe_basename(path.name, "scope union output name")
    parent_fd, absolute_parent = _open_private_output_parent(path)
    try:
        expected_parent_identity = _directory_identity(os.fstat(parent_fd))
    except OSError as error:
        os.close(parent_fd)
        raise ScopeError(
            "scope union output parent could not be held safely"
        ) from error
    descriptor: Optional[int] = None

    def parent_still_bound() -> None:
        try:
            observed_parent = os.stat(
                absolute_parent,
                follow_symlinks=False,
            )
            opened_parent = os.fstat(parent_fd)
        except OSError as error:
            raise ScopeError(
                "scope union output parent became unreachable during write"
            ) from error
        if (
            observed_parent.st_dev,
            observed_parent.st_ino,
        ) != (
            opened_parent.st_dev,
            opened_parent.st_ino,
        ):
            raise ScopeError("scope union output parent changed during write")
        if (
            _directory_identity(observed_parent)
            != expected_parent_identity
            or _directory_identity(opened_parent)
            != expected_parent_identity
            or not stat.S_ISDIR(opened_parent.st_mode)
            or opened_parent.st_uid != os.geteuid()
            or stat.S_IMODE(opened_parent.st_mode) & 0o077
        ):
            raise ScopeError(
                "scope union output parent permissions changed during write"
            )

    def read_exact_descriptor(expected: bytes) -> bytes:
        if descriptor is None:
            raise ScopeError("scope union verification staging is absent")
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = bytearray()
        remaining = len(expected) + 1
        while remaining:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, remaining),
            )
            if not chunk:
                break
            readback.extend(chunk)
            remaining -= len(chunk)
        return bytes(readback)

    def verify_staged(
        *,
        expected_links: int,
        committed: bool,
    ) -> None:
        if descriptor is None:
            raise ScopeError("scope union verification staging is absent")
        try:
            opened_before = os.fstat(descriptor)
            committed_before: os.stat_result | None = None
            if committed:
                committed_before = os.stat(
                    output_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            readback = read_exact_descriptor(raw)
            opened_after = os.fstat(descriptor)
            committed_after: os.stat_result | None = None
            if committed:
                committed_after = os.stat(
                    output_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
        except OSError as error:
            raise ScopeError(
                "scope union verification staging changed during write"
            ) from error
        parent_still_bound()
        if (
            not stat.S_ISREG(opened_after.st_mode)
            or opened_after.st_uid != os.geteuid()
            or opened_after.st_nlink != expected_links
            or stat.S_IMODE(opened_after.st_mode) != 0o600
            or opened_after.st_size != len(raw)
            or _identity(opened_before) != _identity(opened_after)
            or not hmac.compare_digest(readback, raw)
        ):
            raise ScopeError(
                "scope union verification staging changed during write"
            )
        if committed:
            if (
                committed_before is None
                or committed_after is None
                or _identity(committed_before)
                != _identity(committed_after)
                or _identity(committed_after) != _identity(opened_after)
            ):
                raise ScopeError(
                    "scope union verification output changed during commit"
                )

    def write_all(payload_bytes: bytes) -> None:
        if descriptor is None:
            raise ScopeError("scope union verification staging is absent")
        offset = 0
        while offset < len(payload_bytes):
            written = os.write(descriptor, payload_bytes[offset:])
            if written <= 0:
                raise ScopeError(
                    "scope union verification output write made no progress"
                )
            offset += written

    try:
        temporary_flag = getattr(os, "O_TMPFILE", 0)
        if temporary_flag == 0:
            raise ScopeError(
                "scope union verification requires anonymous file staging"
            )
        try:
            descriptor = os.open(
                ".",
                os.O_RDWR
                | temporary_flag
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
                0o600,
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise ScopeError(
                "scope union verification output could not be staged "
                "anonymously"
            ) from error
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 0
        ):
            raise ScopeError("scope union verification output identity is unsafe")
        os.fchmod(descriptor, 0o600)
        write_all(raw)
        os.fsync(descriptor)
        verify_staged(expected_links=0, committed=False)
        if post_write_check is not None:
            post_write_check()
        verify_staged(expected_links=0, committed=False)
        if mutation_watch is not None:
            mutation_watch.assert_quiet()
        os.fsync(parent_fd)
        verify_staged(expected_links=0, committed=False)
        if post_write_check is not None:
            post_write_check()
        verify_staged(expected_links=0, committed=False)
        if mutation_watch is not None:
            mutation_watch.assert_quiet()
        try:
            os.link(
                f"/proc/self/fd/{descriptor}",
                output_name,
                dst_dir_fd=parent_fd,
                follow_symlinks=True,
            )
        except FileExistsError as error:
            raise ScopeError(
                "scope union verification output already exists"
            ) from error
        except OSError as error:
            raise ScopeError(
                "scope union verification output could not be committed"
            ) from error
        while True:
            try:
                os.fsync(parent_fd)
                break
            except InterruptedError:
                continue
            except OSError as error:
                raise _ReceiptDurabilityIndeterminate(
                    "scope union preparation receipt was linked but "
                    "parent-directory durability is indeterminate; "
                    "manual reconciliation is required"
                ) from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.close(parent_fd)
        except OSError:
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    registry_guard: _VerificationGuard | None = None
    held_artifacts: list[_HeldDigest] = []
    mutation_watch: _MutationWatch | None = None
    snapshot_guard: _ArtifactSnapshotGuard | None = None
    preparation_written = False
    try:
        expected_version = decision_contract._token(
            args.expected_release_version,
            "expected release version",
        )
        if expected_version != args.expected_release_version:
            raise ScopeError("expected release version must be canonical")
        identities, policies, decision_rows = _load_decisions(args)

        manifest_raw = _stable_bytes(args.manifest, "global candidate manifest")
        promotion_raw = _stable_bytes(
            args.promotion_evidence,
            "global promotion evidence",
            private=True,
        )
        manifest = _strict_json(manifest_raw, "global candidate manifest")
        promotion = _strict_json(promotion_raw, "global promotion evidence")
        _manifest_identity(manifest, expected_version)
        _manifest_coverage(manifest)
        review_contexts, registry_commit = _verify_review_authorities(
            args,
            identities,
            decision_rows,
            manifest,
        )
        prepared_output_parent_fd, _prepared_output_parent = (
            _open_private_output_parent(args.output)
        )
        try:
            try:
                os.stat(
                    _safe_basename(
                        args.output.name,
                        "scope union output name",
                    ),
                    dir_fd=prepared_output_parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise ScopeError(
                    "scope union verification output already exists"
                )
        finally:
            _close_quietly(prepared_output_parent_fd)
        registry_guard = _verify_registry_checkout(
            args.registry_repository,
            registry_commit,
        )
        registry_guard.ignore_mutation_path(args.output)
        registry_guard.ignore_mutation_path(
            args.artifact_snapshot_root
        )
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        _verify_promotion_binding(
            promotion,
            manifest,
            manifest_sha,
            expected_version,
        )
        common_identity = identities["linux"]
        artifact_ids = decision_contract._verify_inventory(
            manifest,
            promotion,
            common_identity,
            policies,
        )
        mutation_watch = _MutationWatch(
            _candidate_artifact_paths(manifest, args.files_root),
            ignored_paths=[args.output],
        )
        mutation_watch.ignore_path(args.artifact_snapshot_root)
        _exact_string(
            promotion.get("contractName"),
            PROMOTION_CONTRACT,
            "promotion evidence contractName",
        )
        (
            verified_artifact_ids,
            files_inventory_sha,
            held_artifacts,
        ) = _verify_files(manifest, args.files_root)
        if artifact_ids != verified_artifact_ids:
            raise ScopeError("candidate artifact verification produced inconsistent identities")
        signing_rows = _verify_signing_receipts(args, manifest)
        presentation_rows = _verify_presentation(
            args,
            decision_rows,
            review_contexts,
        )
        mutation_watch.assert_quiet()
        snapshot_guard = _materialize_artifact_snapshot(
            root=args.artifact_snapshot_root,
            output=args.output,
            manifest=manifest,
            held_artifacts=held_artifacts,
            release_version=expected_version,
            manifest_sha256=manifest_sha,
            inventory_sha256=files_inventory_sha,
            registry_commit=registry_commit,
        )
        snapshot_guard.verify()
        mutation_watch.assert_quiet()
        mutation_watch.close()
        mutation_watch = None
        for held_artifact in reversed(held_artifacts):
            held_artifact.close()
        held_artifacts = []
        exact_tuples = sorted(
            f"avalonia:{platform}:{rid}" for platform, rid in PLATFORM_SPECS.items()
        )
        receipt = {
            "contractName": RECEIPT_CONTRACT,
            "contractVersion": 1,
            "status": "prepared",
            "authorizesCandidateProduction": False,
            "authorizationStatus": (
                "requires_publisher_consumption_receipt"
            ),
            "verificationPhase": "global_candidate_inventory_and_presentation",
            "releaseVersion": expected_version,
            "channel": "public_stable",
            "releaseTarget": "stable",
            "supportOwner": common_identity["supportOwner"],
            "approvedBy": common_identity["approvedBy"],
            "platforms": policies,
            "exactIncomingDesktopScope": ",".join(exact_tuples),
            "scopeDecisions": decision_rows,
            "artifactIds": artifact_ids,
            "manifestSha256": manifest_sha,
            "promotionEvidenceSha256": hashlib.sha256(promotion_raw).hexdigest(),
            "signingReceipts": signing_rows,
            "presentationReceipts": presentation_rows,
            "registryCommit": registry_commit,
            "reviewAuthorities": [
                {
                    "platform": platform,
                    **review_contexts[platform],
                }
                for platform in PLATFORM_SPECS
            ],
            "filesRootInventorySha256": files_inventory_sha,
            "artifactSnapshot": snapshot_guard.receipt_binding,
        }
        def final_held_check() -> None:
            if registry_guard is None:
                raise ScopeError("Registry verification guard is absent")
            if snapshot_guard is None:
                raise ScopeError("artifact snapshot guard is absent")
            snapshot_guard.verify()
            registry_guard.verify()
            snapshot_guard.verify()

        final_held_check()
        _write_new(
            args.output,
            receipt,
            post_write_check=final_held_check,
            mutation_watch=snapshot_guard.mutation_watch,
        )
        preparation_written = True
    except (ScopeError, OSError) as error:
        snapshot_disposition = ""
        if (
            snapshot_guard is not None
            and not preparation_written
            and not isinstance(error, _ReceiptDurabilityIndeterminate)
        ):
            snapshot_disposition = (
                "; uncommitted artifact snapshot retained for quarantine"
            )
        print(
            "release scope union verification failed: "
            f"{error}{snapshot_disposition}",
            file=sys.stderr,
        )
        return 1
    finally:
        if mutation_watch is not None:
            mutation_watch.close()
        for held_artifact in reversed(held_artifacts):
            held_artifact.close()
        if snapshot_guard is not None:
            snapshot_guard.close()
        if registry_guard is not None:
            registry_guard.close()
    try:
        print("release_scope_union_verification:prepared")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
