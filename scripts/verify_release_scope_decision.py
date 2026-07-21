#!/usr/bin/env python3
"""Verify one immutable, approved release scope and its exact candidate shelf."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit


CONTRACT = "chummer.release-scope-decision/v1"
RECEIPT_CONTRACT = "chummer.release-scope-verification/v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,127}$")
MAX_BYTES = 8 * 1024 * 1024
ROOT_FIELDS = {
    "contractName",
    "contractVersion",
    "decisionId",
    "status",
    "approvedAtUtc",
    "approvedBy",
    "releaseVersion",
    "channel",
    "releaseTarget",
    "supportOwner",
    "platforms",
}
PLATFORM_FIELDS = {
    "platform",
    "rid",
    "primaryHead",
    "fallbackHeads",
    "artifactAccessClass",
    "signingRequirement",
}
PLATFORM_ALIASES = {
    "darwin": "macos",
    "mac": "macos",
    "macos": "macos",
    "osx": "macos",
    "win": "windows",
    "windows": "windows",
    "linux": "linux",
}
ACCESS_CLASSES = {"open_public", "account_required", "support_directed"}
SIGNING_REQUIREMENTS = {"signed", "preview_unsigned_allowed", "not_applicable"}
SUPPORTED_HEADS = {"avalonia", "blazor-desktop"}
INSTALLER_KINDS = {"installer", "dmg", "pkg", "msix"}
INVALID_TEXT = {"", "none", "null", "pending", "review_required", "tbd", "unknown"}


class ScopeError(ValueError):
    pass


def _args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an approved release-scope decision. Supplying both manifest and "
            "promotion evidence additionally proves exact candidate inventory."
        )
    )
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--promotion-evidence", type=Path)
    parser.add_argument("--expected-release-version")
    parser.add_argument("--expected-channel")
    parser.add_argument("--expected-platform")
    parser.add_argument("--expected-rid")
    parser.add_argument("--expected-heads")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _stable_bytes(path: Path, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ScopeError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_BYTES
        ):
            raise ScopeError(f"{label} must be a bounded single-link regular file")
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
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    raw = b"".join(chunks)
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise ScopeError(f"{label} changed during stable read")
    return raw


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise ScopeError(f"{label} contains duplicate or case-shadowed field {key}")
            folded.add(normalized)
            result[key] = value
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScopeError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ScopeError(f"{label} must be a JSON object")
    return payload


def _token(value: Any, label: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ScopeError(f"{label} must be a canonical token")
    normalized = value.lower()
    if value != normalized or SAFE_ID.fullmatch(normalized) is None or ".." in normalized:
        raise ScopeError(f"{label} must be a canonical lowercase safe token")
    return normalized


def _text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ScopeError(f"{label} must be bounded canonical text")
    if value.casefold() in INVALID_TEXT:
        raise ScopeError(f"{label} must identify a resolved release authority owner")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ScopeError(f"{label} must be a canonical UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ScopeError(f"{label} must be a canonical UTC timestamp") from error
    canonical = parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise ScopeError(f"{label} must use second-precision canonical UTC")
    return canonical


def _authority(value: str, decision_id: str, expected_sha256: str) -> str:
    if value != value.strip() or len(value) > 2048 or any(character.isspace() for character in value):
        raise ScopeError("scope authority must be a bounded immutable reference")
    expected = f"design://release-scope/{decision_id}/sha256/{expected_sha256}"
    parsed = urlsplit(value)
    if (
        value != expected
        or parsed.scheme != "design"
        or parsed.netloc != "release-scope"
        or parsed.path != f"/{decision_id}/sha256/{expected_sha256}"
        or parsed.query
        or parsed.fragment
    ):
        raise ScopeError(
            "scope authority must exactly equal "
            "design://release-scope/<decisionId>/sha256/<decisionSha256>"
        )
    return value


def _platform(value: Any, label: str) -> str:
    token = _token(value, label)
    if token not in {"linux", "windows", "macos"}:
        raise ScopeError(f"{label} is not a canonical supported desktop platform")
    return token


def _parse_decision(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if set(payload) != ROOT_FIELDS:
        raise ScopeError("release scope decision has an unexpected field set")
    if (
        payload.get("contractName") != CONTRACT
        or payload.get("contractVersion") != 1
        or payload.get("status") != "approved"
    ):
        raise ScopeError("release scope decision is not an approved v1 decision")
    decision_id = _token(payload.get("decisionId"), "decisionId")
    approved_at = _timestamp(payload.get("approvedAtUtc"), "approvedAtUtc")
    approved_by = _text(payload.get("approvedBy"), "approvedBy")
    release_version = _token(payload.get("releaseVersion"), "releaseVersion")
    channel = _token(payload.get("channel"), "channel")
    target = _token(payload.get("releaseTarget"), "releaseTarget")
    if (channel, target) not in {("preview", "preview"), ("public_stable", "stable")}:
        raise ScopeError("release channel and target are not an allowed preview/stable pair")
    support_owner = _text(payload.get("supportOwner"), "supportOwner")
    rows = payload.get("platforms")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
        raise ScopeError("release scope decision must declare 1 through 16 platforms")
    normalized_rows: list[dict[str, Any]] = []
    seen_platforms: set[str] = set()
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, dict) or set(raw_row) != PLATFORM_FIELDS:
            raise ScopeError(f"release scope platform row {index} has an unexpected field set")
        platform = _platform(raw_row.get("platform"), f"platforms[{index}].platform")
        if platform in seen_platforms:
            raise ScopeError(f"release scope declares platform {platform} more than once")
        seen_platforms.add(platform)
        rid = _token(raw_row.get("rid"), f"platforms[{index}].rid")
        allowed_rids = {
            "linux": {"linux-x64", "linux-arm64"},
            "windows": {"win-x64", "win-arm64"},
            "macos": {"osx-x64", "osx-arm64"},
        }[platform]
        if rid not in allowed_rids:
            raise ScopeError(
                f"platforms[{index}].rid is incompatible with platform {platform}"
            )
        primary = _token(raw_row.get("primaryHead"), f"platforms[{index}].primaryHead")
        fallbacks = raw_row.get("fallbackHeads")
        if not isinstance(fallbacks, list) or len(fallbacks) > 15:
            raise ScopeError(f"platforms[{index}].fallbackHeads must be a bounded array")
        normalized_fallbacks = [
            _token(value, f"platforms[{index}].fallbackHeads") for value in fallbacks
        ]
        if (
            normalized_fallbacks != sorted(normalized_fallbacks)
            or len(set(normalized_fallbacks)) != len(normalized_fallbacks)
            or primary in normalized_fallbacks
        ):
            raise ScopeError(
                f"platforms[{index}].fallbackHeads must be sorted, unique, and exclude the primary head"
            )
        unsupported_heads = sorted(
            set([primary, *normalized_fallbacks]) - SUPPORTED_HEADS
        )
        if unsupported_heads:
            raise ScopeError(
                "approved release scope contains unsupported product head(s): "
                + ", ".join(unsupported_heads)
            )
        access = _token(
            raw_row.get("artifactAccessClass"),
            f"platforms[{index}].artifactAccessClass",
        )
        if access not in ACCESS_CLASSES:
            raise ScopeError(f"platforms[{index}].artifactAccessClass is unsupported")
        signing = _token(
            raw_row.get("signingRequirement"),
            f"platforms[{index}].signingRequirement",
        )
        if signing not in SIGNING_REQUIREMENTS:
            raise ScopeError(f"platforms[{index}].signingRequirement is unsupported")
        if signing == "preview_unsigned_allowed" and target != "preview":
            raise ScopeError("unsigned artifacts may only be approved for a preview target")
        if signing == "not_applicable" and platform in {"windows", "macos"}:
            raise ScopeError(f"{platform} cannot use signingRequirement=not_applicable")
        normalized_rows.append(
            {
                "platform": platform,
                "rid": rid,
                "primaryHead": primary,
                "fallbackHeads": normalized_fallbacks,
                "artifactAccessClass": access,
                "signingRequirement": signing,
            }
        )
    if normalized_rows != sorted(normalized_rows, key=lambda row: row["platform"]):
        raise ScopeError("release scope platform rows must be sorted by platform")
    identity = {
        "decisionId": decision_id,
        "approvedAtUtc": approved_at,
        "approvedBy": approved_by,
        "releaseVersion": release_version,
        "channel": channel,
        "releaseTarget": target,
        "supportOwner": support_owner,
    }
    return identity, normalized_rows


def _manifest_platform(row: dict[str, Any]) -> str:
    raw = row.get("platformId") or row.get("platform")
    if not isinstance(raw, str):
        raise ScopeError("candidate artifact is missing platform")
    token = raw.strip().lower()
    if token not in PLATFORM_ALIASES:
        token = re.split(r"[-_/ ]", token, maxsplit=1)[0]
    return PLATFORM_ALIASES.get(token, token)


def _manifest_rid(row: dict[str, Any], platform: str) -> str:
    raw = row.get("rid")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    arch = str(row.get("arch") or "").strip().lower()
    if platform == "windows":
        return f"win-{arch or 'x64'}"
    if platform == "macos":
        return f"osx-{arch or 'arm64'}"
    if platform == "linux":
        return f"linux-{arch or 'x64'}"
    return ""


def _installer(row: dict[str, Any]) -> bool:
    kind = str(row.get("kind") or "").strip().lower()
    if kind:
        return kind in INSTALLER_KINDS
    name = str(row.get("fileName") or "").strip().lower()
    return name.endswith((".exe", ".deb", ".dmg", ".pkg", ".msix"))


def _verify_inventory(
    manifest: dict[str, Any],
    promotion: dict[str, Any],
    identity: dict[str, Any],
    platforms: list[dict[str, Any]],
) -> list[str]:
    if (
        (manifest.get("version") or manifest.get("releaseVersion")) != identity["releaseVersion"]
        or (manifest.get("channel") or manifest.get("channelId")) != identity["channel"]
    ):
        raise ScopeError("candidate manifest identity disagrees with the approved scope")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ScopeError("candidate manifest contains no artifacts")
    platform_index = {row["platform"]: row for row in platforms}
    ids: set[str] = set()
    installed: set[tuple[str, str, str]] = set()
    artifact_platform: dict[str, str] = {}
    for raw_artifact in artifacts:
        if not isinstance(raw_artifact, dict):
            raise ScopeError("candidate manifest contains a malformed artifact row")
        artifact_id = str(
            raw_artifact.get("artifactId") or raw_artifact.get("id") or ""
        ).strip()
        if not artifact_id or artifact_id in ids:
            raise ScopeError("candidate manifest contains a missing or duplicate artifact id")
        ids.add(artifact_id)
        platform = _manifest_platform(raw_artifact)
        policy = platform_index.get(platform)
        if policy is None:
            raise ScopeError(f"candidate artifact {artifact_id} is outside approved platform scope")
        head = str(raw_artifact.get("head") or "").strip().lower()
        rid = _manifest_rid(raw_artifact, platform)
        allowed_heads = [policy["primaryHead"], *policy["fallbackHeads"]]
        if head not in allowed_heads or rid != policy["rid"]:
            raise ScopeError(f"candidate artifact {artifact_id} is outside approved head/RID scope")
        access = str(raw_artifact.get("installAccessClass") or "").strip().lower()
        if access != policy["artifactAccessClass"]:
            raise ScopeError(f"candidate artifact {artifact_id} has an unapproved access class")
        if _installer(raw_artifact):
            installed.add((platform, head, rid))
        artifact_platform[artifact_id] = platform
    expected_installed = {
        (row["platform"], head, row["rid"])
        for row in platforms
        for head in [row["primaryHead"], *row["fallbackHeads"]]
    }
    if installed != expected_installed:
        missing = sorted(expected_installed - installed)
        extra = sorted(installed - expected_installed)
        raise ScopeError(f"candidate installer inventory does not exactly match scope; missing={missing}, extra={extra}")

    if promotion.get("contractName") != "chummer.run.desktop_release_publication":
        raise ScopeError("promotion evidence has an unexpected contract")
    evidence_rows = promotion.get("artifacts")
    if not isinstance(evidence_rows, list):
        raise ScopeError("promotion evidence artifacts must be an array")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for row in evidence_rows:
        if not isinstance(row, dict):
            raise ScopeError("promotion evidence contains a malformed artifact row")
        artifact_id = str(row.get("artifactId") or "").strip()
        if not artifact_id or artifact_id in evidence_by_id:
            raise ScopeError("promotion evidence contains a missing or duplicate artifact id")
        evidence_by_id[artifact_id] = row
    if set(evidence_by_id) != ids:
        raise ScopeError("promotion evidence artifact ids do not exactly match the candidate manifest")
    for artifact_id, row in evidence_by_id.items():
        if str(row.get("promotionStatus") or "").strip().lower() != "pass":
            raise ScopeError(f"candidate artifact {artifact_id} did not pass promotion evidence")
        platform = artifact_platform[artifact_id]
        policy = platform_index[platform]
        signing = str(row.get("signingStatus") or "").strip().lower()
        notarization = str(row.get("notarizationStatus") or "").strip().lower()
        requirement = policy["signingRequirement"]
        if requirement == "signed":
            if signing != "pass" or (platform == "macos" and notarization != "pass"):
                raise ScopeError(f"candidate artifact {artifact_id} lacks required signing proof")
        elif requirement == "preview_unsigned_allowed":
            if signing not in {"pass", "skipped_preview"} or (
                platform == "macos" and notarization not in {"pass", "skipped_preview"}
            ):
                raise ScopeError(f"candidate artifact {artifact_id} has signing proof outside preview policy")
        elif signing or notarization:
            raise ScopeError(f"candidate artifact {artifact_id} unexpectedly carries signing posture")
    return sorted(ids)


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError as error:
        raise ScopeError("scope verification output already exists") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _args(argv)
    try:
        expected_sha = args.expected_sha256.strip().lower()
        if SHA256.fullmatch(expected_sha) is None:
            raise ScopeError("expected scope decision SHA-256 is not canonical")
        decision_raw = _stable_bytes(args.decision, "release scope decision")
        observed_sha = hashlib.sha256(decision_raw).hexdigest()
        if not hmac.compare_digest(observed_sha, expected_sha):
            raise ScopeError("release scope decision SHA-256 does not match")
        decision_payload = _strict_json(decision_raw, "release scope decision")
        canonical_decision_raw = (
            json.dumps(
                decision_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        if not hmac.compare_digest(decision_raw, canonical_decision_raw):
            raise ScopeError(
                "release scope decision bytes are not canonical compact sorted UTF-8 JSON plus LF"
            )
        identity, platforms = _parse_decision(decision_payload)
        authority = _authority(
            args.authority, identity["decisionId"], expected_sha
        )
        for expected, observed, label in (
            (args.expected_release_version, identity["releaseVersion"], "release version"),
            (args.expected_channel, identity["channel"], "release channel"),
        ):
            if expected is not None and expected.strip().lower() != observed:
                raise ScopeError(f"approved scope {label} disagrees with the requested candidate")
        if args.expected_platform is not None:
            expected_platform = _platform(args.expected_platform.strip().lower(), "expected platform")
            if len(platforms) != 1 or platforms[0]["platform"] != expected_platform:
                raise ScopeError(
                    "this platform-specific builder requires an approved scope containing exactly "
                    f"{expected_platform}"
                )
        if args.expected_rid is not None and (
            len(platforms) != 1 or platforms[0]["rid"] != args.expected_rid.strip().lower()
        ):
            raise ScopeError("approved scope RID disagrees with the requested candidate")
        if args.expected_heads is not None:
            requested_heads = [
                value.strip().lower()
                for value in args.expected_heads.replace(" ", ",").split(",")
                if value.strip()
            ]
            approved_heads = [platforms[0]["primaryHead"], *platforms[0]["fallbackHeads"]]
            if len(platforms) != 1 or requested_heads != approved_heads:
                raise ScopeError("requested app-head order disagrees with primary/fallback scope")
        if (args.manifest is None) != (args.promotion_evidence is None):
            raise ScopeError("manifest and promotion evidence must be supplied together")
        artifact_ids: list[str] = []
        manifest_sha: Optional[str] = None
        promotion_sha: Optional[str] = None
        phase = "scope_approval"
        if args.manifest is not None and args.promotion_evidence is not None:
            manifest_raw = _stable_bytes(args.manifest, "candidate manifest")
            promotion_raw = _stable_bytes(args.promotion_evidence, "promotion evidence")
            artifact_ids = _verify_inventory(
                _strict_json(manifest_raw, "candidate manifest"),
                _strict_json(promotion_raw, "promotion evidence"),
                identity,
                platforms,
            )
            manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
            promotion_sha = hashlib.sha256(promotion_raw).hexdigest()
            phase = "candidate_inventory"
        exact_tuples = sorted(
            f"{head}:{row['platform']}:{row['rid']}"
            for row in platforms
            for head in [row["primaryHead"], *row["fallbackHeads"]]
        )
        receipt = {
            "contractName": RECEIPT_CONTRACT,
            "contractVersion": 1,
            "status": "pass",
            "verificationPhase": phase,
            "decisionId": identity["decisionId"],
            "decisionSha256": observed_sha,
            "decisionAuthority": authority,
            **identity,
            "platforms": platforms,
            "exactIncomingDesktopScope": ",".join(exact_tuples),
            "artifactIds": artifact_ids,
            "manifestSha256": manifest_sha,
            "promotionEvidenceSha256": promotion_sha,
        }
        _write_new(args.output, receipt)
    except (ScopeError, OSError) as error:
        print(f"release scope verification failed: {error}", file=sys.stderr)
        return 1
    print("release_scope_verification:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
