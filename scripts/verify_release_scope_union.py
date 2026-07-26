#!/usr/bin/env python3
"""Verify the exact global stable desktop release-scope union and candidate bytes."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Optional, Sequence

import verify_release_scope_decision as decision_contract


RECEIPT_CONTRACT = "chummer.release-scope-union-verification/v1"
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


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify three immutable per-platform stable scope decisions, the exact "
            "global candidate shelf, and all nine candidate-bound Presentation gates."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--promotion-evidence", type=Path, required=True)
    parser.add_argument("--files-root", type=Path, required=True)
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
        except OSError as error:
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
            if component in {"", ".", ".."}:
                raise ScopeError(f"{label} parent contains an unsafe component")
            try:
                before = os.stat(
                    component,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ScopeError(f"{label} parent could not be inspected safely") from error
            if not stat.S_ISDIR(before.st_mode):
                raise ScopeError(f"{label} must not traverse a symlink")
            try:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except OSError as error:
                raise ScopeError(f"{label} parent could not be opened safely") from error
            opened = os.fstat(next_fd)
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
    except OSError as error:
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
    except OSError as error:
        os.close(parent_fd)
        raise ScopeError(f"{label} could not be inspected safely") from error
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
    except OSError as error:
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
                raise ScopeError(f"{label} contains duplicate or case-shadowed field {key}")
            folded.add(normalized)
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ScopeError(f"{label} contains non-finite number {value}")

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


def _verify_registry_checkout(path: Path, expected_commit: str) -> None:
    _path_without_symlinks(path, "Registry repository")
    absolute = path.absolute()
    git_binary = Path("/usr/bin/git")
    try:
        git_stat = git_binary.lstat()
        repository_stat = os.stat(absolute, follow_symlinks=False)
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
    if (
        not stat.S_ISDIR(repository_stat.st_mode)
        or repository_stat.st_uid != os.geteuid()
    ):
        raise ScopeError("Registry repository must be a caller-owned directory")

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        repository_fd = os.open(absolute, directory_flags)
    except OSError as error:
        raise ScopeError("Registry repository could not be held safely") from error
    held_stat = os.fstat(repository_fd)
    if _identity(held_stat) != _identity(repository_stat):
        os.close(repository_fd)
        raise ScopeError("Registry repository changed while it was opened")
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
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    }

    def repository_still_bound() -> None:
        try:
            current = os.stat(absolute, follow_symlinks=False)
            opened = os.fstat(repository_fd)
        except OSError as error:
            raise ScopeError(
                "Registry repository changed during Git inspection"
            ) from error
        if (
            _identity(current) != _identity(repository_stat)
            or _identity(opened) != _identity(repository_stat)
        ):
            raise ScopeError("Registry repository changed during Git inspection")

    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        repository_still_bound()
        try:
            result = subprocess.run(
                [*command_prefix, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
                env=git_environment,
                close_fds=True,
                pass_fds=(repository_fd,),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ScopeError("Registry Git authority could not be inspected") from error
        repository_still_bound()
        return result

    try:
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
        head = run("rev-parse", "--verify", "HEAD^{commit}")
        if (
            head.returncode != 0
            or head.stdout.strip() != expected_commit
            or GIT_COMMIT.fullmatch(head.stdout.strip()) is None
        ):
            raise ScopeError(
                "review authority Registry commit does not equal the checked-out HEAD"
            )
        protected_paths = (
            "scripts/release/promote_public_stable_release_channel.sh",
            "scripts/materialize_public_release_channel.py",
            "scripts/verify_public_release_channel.py",
        )
        status_result = run(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *protected_paths,
        )
        if status_result.returncode != 0 or status_result.stdout:
            raise ScopeError(
                "Registry release producer paths must be clean at the reviewed HEAD"
            )
        for source_path in protected_paths:
            exists = run("cat-file", "-e", f"HEAD:{source_path}")
            if exists.returncode != 0:
                raise ScopeError(
                    f"Registry reviewed HEAD is missing required source path {source_path}"
                )
    finally:
        os.close(repository_fd)


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
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise ScopeError(f"{label} must be a safe basename")
    return value


def _stable_file_digest(path: Path, label: str) -> tuple[str, int]:
    descriptor, before, parent_fd, absolute_parent = _open_stable(
        path,
        label,
        private=False,
        bounded=False,
    )
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        _parent_still_bound(parent_fd, absolute_parent, label)
    finally:
        os.close(descriptor)
        os.close(parent_fd)
    if _identity(before) != _identity(after) or size != before.st_size:
        raise ScopeError(f"{label} changed during stable hash")
    return digest.hexdigest(), size


def _verify_files(
    manifest: dict[str, Any],
    files_root: Path,
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
            observed_sha, observed_size = _stable_file_digest(
                files_root / file_name,
                f"candidate artifact {artifact_id} {role} bytes",
            )
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
    if absolute.name in {"", ".", ".."}:
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
            if component in {"", ".", ".."}:
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
                except OSError as error:
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
            opened = os.fstat(next_fd)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                os.close(next_fd)
                raise ScopeError("scope union output parent changed while it was opened")
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


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    raw = _canonical_json(payload)
    parent_fd, absolute_parent = _open_private_output_parent(path)
    descriptor: Optional[int] = None
    created = False
    try:
        try:
            descriptor = os.open(
                path.name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            created = True
        except FileExistsError as error:
            raise ScopeError("scope union verification output already exists") from error
        except OSError as error:
            raise ScopeError("scope union verification output could not be created") from error
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
        ):
            raise ScopeError("scope union verification output identity is unsafe")
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        after = os.fstat(descriptor)
        if (
            after.st_size != len(raw)
            or stat.S_IMODE(after.st_mode) != 0o600
            or after.st_nlink != 1
        ):
            raise ScopeError("scope union verification output changed during write")
        try:
            observed_parent = os.stat(absolute_parent, follow_symlinks=False)
        except OSError as error:
            raise ScopeError(
                "scope union output parent became unreachable during write"
            ) from error
        opened_parent = os.fstat(parent_fd)
        if (
            observed_parent.st_dev,
            observed_parent.st_ino,
        ) != (
            opened_parent.st_dev,
            opened_parent.st_ino,
        ):
            raise ScopeError("scope union output parent changed during write")
        os.fsync(parent_fd)
    except BaseException:
        if created:
            try:
                os.unlink(path.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
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
        _verify_registry_checkout(args.registry_repository, registry_commit)
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
        _exact_string(
            promotion.get("contractName"),
            PROMOTION_CONTRACT,
            "promotion evidence contractName",
        )
        verified_artifact_ids, files_inventory_sha = _verify_files(
            manifest,
            args.files_root,
        )
        if artifact_ids != verified_artifact_ids:
            raise ScopeError("candidate artifact verification produced inconsistent identities")
        signing_rows = _verify_signing_receipts(args, manifest)
        presentation_rows = _verify_presentation(
            args,
            decision_rows,
            review_contexts,
        )
        exact_tuples = sorted(
            f"avalonia:{platform}:{rid}" for platform, rid in PLATFORM_SPECS.items()
        )
        receipt = {
            "contractName": RECEIPT_CONTRACT,
            "contractVersion": 1,
            "status": "pass",
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
        }
        _write_new(args.output, receipt)
    except (ScopeError, OSError) as error:
        print(f"release scope union verification failed: {error}", file=sys.stderr)
        return 1
    print("release_scope_union_verification:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
