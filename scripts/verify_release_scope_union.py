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
import sys
from typing import Any, Optional, Sequence

import verify_release_scope_decision as decision_contract


RECEIPT_CONTRACT = "chummer.release-scope-union-verification/v1"
BINDING_CONTRACT = "chummer6-ui.campaign_operability_candidate_binding"
PROMOTION_CONTRACT = "chummer.run.desktop_release_publication"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
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
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--expected-registry-commit", required=True)
    parser.add_argument("--expected-authority-snapshot-sha256", required=True)
    parser.add_argument("--expected-release-decision-sha256", required=True)
    for platform in PLATFORM_SPECS:
        parser.add_argument(f"--{platform}-decision", type=Path, required=True)
        parser.add_argument(f"--{platform}-decision-sha256", required=True)
        parser.add_argument(f"--{platform}-decision-authority", required=True)
        parser.add_argument(f"--{platform}-signing-receipt", type=Path, required=True)
        parser.add_argument(f"--{platform}-signing-receipt-sha256", required=True)
        for gate in GATE_SPECS:
            parser.add_argument(
                f"--{platform}-{gate}-receipt",
                type=Path,
                required=True,
            )
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


def _open_stable(path: Path, label: str, *, private: bool, bounded: bool) -> tuple[int, os.stat_result]:
    _path_without_symlinks(path, label)
    try:
        before_path = path.lstat()
    except OSError as error:
        raise ScopeError(f"{label} could not be inspected safely") from error
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
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
        return descriptor, before
    except BaseException:
        os.close(descriptor)
        raise


def _stable_bytes(path: Path, label: str, *, private: bool = False) -> bytes:
    descriptor, before = _open_stable(path, label, private=private, bounded=True)
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
    finally:
        os.close(descriptor)
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
    descriptor, before = _open_stable(path, label, private=False, bounded=False)
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
    finally:
        os.close(descriptor)
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


def _verify_presentation(
    args: argparse.Namespace,
    manifest_sha: str,
    decision_rows: list[dict[str, str]],
    registry_commit: str,
    authority_snapshot_sha: str,
    release_decision_sha: str,
) -> list[dict[str, str]]:
    decision_sha_by_platform = {
        row["platform"]: row["decisionSha256"] for row in decision_rows
    }
    output: list[dict[str, str]] = []
    observed_hashes: set[str] = set()
    for platform, rid in PLATFORM_SPECS.items():
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
                "authority_snapshot_sha256": authority_snapshot_sha,
                "contract_name": BINDING_CONTRACT,
                "contract_version": 1,
                "manifest_sha256": manifest_sha,
                "platform": platform,
                "primary_head": "avalonia",
                "registry_commit": registry_commit,
                "release_decision_sha256": release_decision_sha,
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


def _verify_signing_receipts(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ScopeError("candidate manifest artifacts must be an array")
    expected_by_platform: dict[str, list[dict[str, str]]] = {
        platform: [] for platform in PLATFORM_SPECS
    }
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ScopeError(f"candidate artifact row {index} must be an object")
        platform = decision_contract._platform(
            artifact.get("platform"),
            f"artifacts[{index}].platform",
        )
        expected_by_platform[platform].append(
            {
                "fileName": _safe_basename(
                    artifact.get("fileName"),
                    f"artifacts[{index}].fileName",
                ),
                "sha256": _canonical_sha(
                    artifact.get("sha256"),
                    f"artifacts[{index}].sha256",
                )
                if isinstance(artifact.get("sha256"), str)
                else "",
                "kind": decision_contract._token(
                    artifact.get("kind"),
                    f"artifacts[{index}].kind",
                ),
            }
        )
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
        _exact_string(payload.get("platform"), platform, f"{platform} signing receipt platform")
        _exact_string(payload.get("app"), "avalonia", f"{platform} signing receipt app")
        _exact_string(payload.get("rid"), rid, f"{platform} signing receipt rid")
        _exact_string(
            payload.get("releaseChannel"),
            "stable",
            f"{platform} signing receipt releaseChannel",
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
        expected = sorted(
            expected_by_platform[platform],
            key=lambda row: (row["fileName"], row["kind"], row["sha256"]),
        )
        observed.sort(key=lambda row: (row["fileName"], row["kind"], row["sha256"]))
        if observed != expected:
            raise ScopeError(
                f"{platform} signing receipt artifacts do not exactly bind manifest artifacts"
            )
        output.append(
            {
                "platform": platform,
                "contractName": "chummer6-ui.desktop_artifact_signing",
                "sha256": receipt_sha,
            }
        )
    return output


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    _path_without_symlinks(path.parent, "scope union output parent", allow_missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    _path_without_symlinks(path.parent, "scope union output parent")
    raw = _canonical_json(payload)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError as error:
        raise ScopeError("scope union verification output already exists") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        expected_version = decision_contract._token(
            args.expected_release_version,
            "expected release version",
        )
        if expected_version != args.expected_release_version:
            raise ScopeError("expected release version must be canonical")
        registry_commit = _canonical_commit(args.expected_registry_commit)
        authority_snapshot_sha = _canonical_sha(
            args.expected_authority_snapshot_sha256,
            "expected authority snapshot SHA-256",
        )
        release_decision_sha = _canonical_sha(
            args.expected_release_decision_sha256,
            "expected release decision SHA-256",
        )
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
        promotion_version = _alias(
            promotion,
            ("releaseVersion", "version"),
            "promotion evidence release version",
            required=False,
        )
        if promotion_version is not None and promotion_version != expected_version:
            raise ScopeError("promotion evidence release version disagrees with candidate")
        verified_artifact_ids, files_inventory_sha = _verify_files(
            manifest,
            args.files_root,
        )
        if artifact_ids != verified_artifact_ids:
            raise ScopeError("candidate artifact verification produced inconsistent identities")
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        signing_rows = _verify_signing_receipts(args, manifest)
        presentation_rows = _verify_presentation(
            args,
            manifest_sha,
            decision_rows,
            registry_commit,
            authority_snapshot_sha,
            release_decision_sha,
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
            "authoritySnapshotSha256": authority_snapshot_sha,
            "releaseDecisionSha256": release_decision_sha,
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
