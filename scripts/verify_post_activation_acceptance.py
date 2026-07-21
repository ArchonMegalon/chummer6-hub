#!/usr/bin/env python3
"""Pure, offline aggregation of post-activation acceptance evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Sequence


AGGREGATE_CONTRACT = "chummer.post-activation-acceptance/v1"
EVIDENCE_CONTRACT = "chummer.post-activation-evidence/v1"
FINALIZATION_CONTRACT = "chummer.staged-release-owner-finalization/v1"
CONVERGENCE_CONTRACT = "chummer.live-release-convergence/v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_REVISION = re.compile(r"^auth-[0-9a-f]{64}$")
SAFE_KIND = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_STATUS = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAFE_SCOPE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_EVIDENCE_AGE_SECONDS = 24 * 60 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60
RELEASE_BINDING_FIELDS = (
    "releaseVersion",
    "generationId",
    "manifestSha256",
    "decisionSha256",
    "snapshotSha256",
    "targetPointerSha256",
)
FINALIZATION_FIELDS = {
    "contractName",
    "contractVersion",
    "status",
    "releaseVersion",
    "generationId",
    "stageReceiptId",
    "manifestSha256",
    "releaseScopeDecisionSha256",
    "releaseScopeVerificationSha256",
    "exactIncomingDesktopScope",
    "snapshotSha256",
    "decisionSha256",
    "authorityRevisionId",
    "targetPointerSha256",
    "completedAtUtc",
}
EVIDENCE_REQUIRED_FIELDS = {
    "contractName",
    "contractVersion",
    "status",
    "secretRedacted",
    "evidenceId",
    "evidenceKind",
    "generatedAtUtc",
    "releaseBinding",
    "claims",
    "operationalReadinessClaimAllowed",
}
EVIDENCE_OPTIONAL_FIELDS: set[str] = set()
REQUIRED_EVIDENCE_KINDS = frozenset(
    {"horizon_live_readiness", "multi_account_live_journey"}
)
CLAIM_FIELDS = {"claimId", "status", "evidenceSha256"}
CONVERGENCE_FIELDS = {
    "contractName",
    "contractVersion",
    "generatedAtUtc",
    "status",
    "mismatchCount",
    "failureCount",
    "mismatches",
    "failures",
    "authorityRoute",
    "checkedRouteCount",
    "checkedRoutes",
    "comparedFields",
    "releaseTruth",
    "releaseVersion",
    "manifestSha256",
    "releaseDecisionStatus",
    "releaseDecisionSha256",
    "authoritySnapshotSha256",
    "verificationMode",
}
FORBIDDEN_FIELD_MARKERS = (
    "authorization",
    "bearer",
    "credential",
    "password",
    "secret",
    "token",
    "header",
    "email",
    "accountid",
    "accountidentifier",
)


class AcceptanceError(RuntimeError):
    pass


def _convergence_helpers():
    path = Path(__file__).with_name("verify_live_release_convergence.py")
    spec = importlib.util.spec_from_file_location("_chummer_live_convergence", path)
    if spec is None or spec.loader is None:
        raise AcceptanceError("live convergence verifier helpers are unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError) as error:
        raise AcceptanceError("live convergence verifier helpers are unavailable") from error
    return module


CONVERGENCE_HELPERS = _convergence_helpers()


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate digest-pinned post-activation evidence without network access."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--finalization-receipt", type=Path, required=True)
    parser.add_argument("--expected-finalization-sha256", required=True)
    parser.add_argument("--generation-convergence", type=Path, required=True)
    parser.add_argument("--expected-generation-convergence-sha256", required=True)
    parser.add_argument("--current-convergence", type=Path, required=True)
    parser.add_argument("--expected-current-convergence-sha256", required=True)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--expected-release-manifest-file-sha256", required=True)
    parser.add_argument(
        "--require-evidence",
        action="append",
        default=[],
        metavar="KIND=PATH",
        help="Require exactly one evidence envelope for KIND; repeat for the explicit denominator.",
    )
    parser.add_argument(
        "--evidence-sha256",
        action="append",
        default=[],
        metavar="KIND=SHA256",
        help="Digest pin corresponding to one --require-evidence entry.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise AcceptanceError(f"{label} must be canonical SHA-256")
    return value


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _strict_json(raw: bytes, label: str, *, require_canonical: bool = False) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise AcceptanceError(f"{label} contains a duplicate or case-shadowed field")
            folded.add(normalized)
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                AcceptanceError(f"{label} contains a non-finite number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AcceptanceError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise AcceptanceError(f"{label} must be a JSON object")
    if require_canonical and raw != _canonical_bytes(payload):
        raise AcceptanceError(f"{label} is not canonical JSON")
    return payload


def _workspace(path: Path) -> Path:
    if not path.is_absolute():
        raise AcceptanceError("workspace must be absolute")
    try:
        lexical = os.lstat(path)
        root = path.resolve(strict=True)
        metadata = root.stat()
    except OSError as error:
        raise AcceptanceError("workspace is unavailable") from error
    if (
        stat.S_ISLNK(lexical.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise AcceptanceError("workspace must be a caller-owned, non-symlink mode-0700 directory")
    return root


def _confined(path: Path, root: Path, label: str, *, must_exist: bool = True) -> Path:
    if not path.is_absolute():
        raise AcceptanceError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise AcceptanceError(f"{label} must remain beneath the workspace") from error
    return resolved


def _stable_file(path: Path, root: Path, label: str) -> tuple[Path, bytes]:
    try:
        lexical = path.absolute()
        canonical = path.resolve(strict=True)
    except OSError as error:
        raise AcceptanceError(f"{label} is unavailable") from error
    if lexical != canonical:
        raise AcceptanceError(f"{label} must not use symlinks or non-canonical path components")
    resolved = _confined(path, root, label)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise AcceptanceError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 1 <= before.st_size <= MAX_INPUT_BYTES
        ):
            raise AcceptanceError(
                f"{label} must be a caller-owned, single-link mode-0600 regular file"
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
    )
    try:
        final = os.lstat(resolved)
    except OSError as error:
        raise AcceptanceError(f"{label} changed during stable read") from error
    if (
        identity(before) != identity(after)
        or len(raw) != before.st_size
        or stat.S_ISLNK(final.st_mode)
        or identity(final) != identity(after)
    ):
        raise AcceptanceError(f"{label} changed during stable read")
    return resolved, raw


def _pinned_json(
    path: Path,
    expected_sha256: str,
    root: Path,
    label: str,
    *,
    require_canonical: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    _, raw = _stable_file(path, root, label)
    expected = _require_sha(expected_sha256, f"{label} expected digest")
    if not hmac.compare_digest(_sha(raw), expected):
        raise AcceptanceError(f"{label} SHA-256 mismatch")
    return raw, _strict_json(raw, label, require_canonical=require_canonical)


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise AcceptanceError(f"{label} must be a canonical UTC timestamp")
    normalized = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise AcceptanceError(f"{label} must be a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise AcceptanceError(f"{label} must be a canonical UTC timestamp")
    return parsed.astimezone(dt.timezone.utc)


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None or ".." in value:
        raise AcceptanceError(f"{label} must be a secret-safe opaque identifier")
    return value


def _desktop_scope(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise AcceptanceError("owner finalization exactIncomingDesktopScope is invalid")
    entries = value.split(",")
    if len(entries) > 64 or entries != sorted(set(entries)):
        raise AcceptanceError("owner finalization exactIncomingDesktopScope is not canonical")
    for entry in entries:
        components = entry.split(":")
        if len(components) != 3 or any(
            SAFE_SCOPE_COMPONENT.fullmatch(component) is None
            for component in components
        ):
            raise AcceptanceError("owner finalization exactIncomingDesktopScope is invalid")
    return value


def _target_from_finalization(payload: dict[str, Any]) -> dict[str, str]:
    if set(payload) != FINALIZATION_FIELDS:
        raise AcceptanceError("owner finalization receipt has an unexpected field set")
    if (
        payload.get("contractName") != FINALIZATION_CONTRACT
        or type(payload.get("contractVersion")) is not int
        or payload.get("contractVersion") != 1
        or payload.get("status") != "preview_ready"
    ):
        raise AcceptanceError("owner finalization receipt is not preview_ready")
    target = {
        "releaseVersion": _safe_id(payload.get("releaseVersion"), "releaseVersion"),
        "generationId": _safe_id(payload.get("generationId"), "generationId"),
        "manifestSha256": _require_sha(payload.get("manifestSha256"), "manifestSha256"),
        "decisionSha256": _require_sha(payload.get("decisionSha256"), "decisionSha256"),
        "snapshotSha256": _require_sha(payload.get("snapshotSha256"), "snapshotSha256"),
        "targetPointerSha256": _require_sha(
            payload.get("targetPointerSha256"), "targetPointerSha256"
        ),
    }
    _safe_id(payload.get("stageReceiptId"), "stageReceiptId")
    _require_sha(payload.get("releaseScopeDecisionSha256"), "releaseScopeDecisionSha256")
    _require_sha(
        payload.get("releaseScopeVerificationSha256"),
        "releaseScopeVerificationSha256",
    )
    _desktop_scope(payload.get("exactIncomingDesktopScope"))
    revision = payload.get("authorityRevisionId")
    if not isinstance(revision, str) or AUTHORITY_REVISION.fullmatch(revision) is None:
        raise AcceptanceError("owner finalization authorityRevisionId is invalid")
    _timestamp(payload.get("completedAtUtc"), "owner finalization completedAtUtc")
    return target


def _validate_convergence(
    payload: dict[str, Any],
    target: dict[str, str],
    finalization: dict[str, Any],
    *,
    role: str,
    completed_at: dt.datetime,
    observed_at: dt.datetime,
    expected_install_route: str | None,
) -> tuple[dt.datetime, dict[str, Any]]:
    if set(payload) != CONVERGENCE_FIELDS:
        raise AcceptanceError(f"{role} convergence has an unexpected field set")
    if (
        payload.get("contractName") != CONVERGENCE_CONTRACT
        or type(payload.get("contractVersion")) is not int
        or payload.get("contractVersion") != 1
        or payload.get("verificationMode") != "committed_public"
        or payload.get("status") != "pass"
        or type(payload.get("mismatchCount")) is not int
        or payload.get("mismatchCount") != 0
        or type(payload.get("failureCount")) is not int
        or payload.get("failureCount") != 0
        or payload.get("mismatches") != []
        or payload.get("failures") != []
        or payload.get("releaseVersion") != target["releaseVersion"]
        or payload.get("manifestSha256") != target["manifestSha256"]
        or payload.get("releaseDecisionStatus") != finalization.get("status")
        or payload.get("authoritySnapshotSha256") != target["snapshotSha256"]
        or payload.get("releaseDecisionSha256") != target["decisionSha256"]
    ):
        raise AcceptanceError(f"{role} convergence does not bind the finalized release")
    checked_routes = payload.get("checkedRoutes")
    checked_count = payload.get("checkedRouteCount")
    if (
        not isinstance(checked_routes, list)
        or not checked_routes
        or len(checked_routes) > 512
        or any(
            not isinstance(route, str)
            or not route.startswith("/")
            or route != route.strip()
            or len(route) > 1024
            for route in checked_routes
        )
        or checked_routes != sorted(set(checked_routes))
        or type(checked_count) is not int
        or checked_count != len(checked_routes)
        or payload.get("comparedFields") != list(CONVERGENCE_HELPERS.REQUIRED_FIELDS)
    ):
        raise AcceptanceError(f"{role} convergence checked-route denominator is invalid")
    try:
        release_truth = CONVERGENCE_HELPERS.canonicalize_projection(
            payload.get("releaseTruth"), source=f"{role} convergence releaseTruth"
        )
    except CONVERGENCE_HELPERS.ConvergenceError as error:
        raise AcceptanceError(f"{role} convergence releaseTruth is invalid") from error
    if release_truth != payload["releaseTruth"]:
        raise AcceptanceError(f"{role} convergence releaseTruth is not canonical")
    if (
        release_truth["releaseVersion"] != target["releaseVersion"]
        or release_truth["manifestSha256"] != target["manifestSha256"]
        or release_truth["releaseDecisionStatus"] != finalization["status"]
        or release_truth["releaseDecisionSha256"] != target["decisionSha256"]
        or release_truth["releaseVersion"] != payload["releaseVersion"]
        or release_truth["manifestSha256"] != payload["manifestSha256"]
        or release_truth["releaseDecisionStatus"] != payload["releaseDecisionStatus"]
        or release_truth["releaseDecisionSha256"] != payload["releaseDecisionSha256"]
        or not CONVERGENCE_HELPERS._availability_claims_allowed(release_truth)
    ):
        raise AcceptanceError(f"{role} convergence releaseTruth is not publishable or bound")
    checked_route_set = set(checked_routes)
    if role == "generation":
        base_routes = set(CONVERGENCE_HELPERS.generation_routes(target["generationId"]))
    else:
        base_routes = set(CONVERGENCE_HELPERS.DEFAULT_ROUTES)
    expected_routes = set(base_routes)
    expected_install_count = 1 if release_truth["artifactCount"] > 0 else 0
    if expected_install_count:
        if expected_install_route is None:
            raise AcceptanceError(f"{role} convergence release manifest has no install route")
        expected_routes.add(expected_install_route)
    if (
        (expected_install_route is not None) != bool(expected_install_count)
        or checked_route_set != expected_routes
    ):
        raise AcceptanceError(f"{role} convergence checked-route denominator is invalid")
    authority_route = payload.get("authorityRoute")
    if role == "generation":
        expected = f"/api/v1/public/release-truth/g/{target['generationId']}"
        if authority_route != expected:
            raise AcceptanceError("generation convergence names the wrong generation authority route")
    elif authority_route != "/api/v1/public/release-truth":
        raise AcceptanceError("CURRENT convergence is not canonical CURRENT authority")
    generated_at = _timestamp(
        payload.get("generatedAtUtc"), f"{role} convergence generatedAtUtc"
    )
    if generated_at > observed_at + dt.timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise AcceptanceError(f"{role} convergence is unreasonably in the future")
    if generated_at < completed_at:
        raise AcceptanceError(f"{role} convergence predates owner finalization")
    if observed_at - generated_at > dt.timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS):
        raise AcceptanceError(f"{role} convergence is stale")
    return generated_at, release_truth


def _parse_kind_map(values: Sequence[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if value.count("=") != 1:
            raise AcceptanceError(f"{label} must use KIND=VALUE")
        kind, item = value.split("=", 1)
        if SAFE_KIND.fullmatch(kind) is None or not item:
            raise AcceptanceError(f"{label} contains an invalid kind or empty value")
        if kind in result:
            raise AcceptanceError(f"{label} contains a duplicate kind")
        result[kind] = item
    if not result:
        raise AcceptanceError("at least one --require-evidence entry is required")
    return result


def _validate_evidence(
    payload: dict[str, Any],
    target: dict[str, str],
    expected_kind: str,
    *,
    completed_at: dt.datetime,
    observed_at: dt.datetime,
) -> tuple[dict[str, Any], bool, dt.datetime]:
    fields = set(payload)
    if not EVIDENCE_REQUIRED_FIELDS.issubset(fields) or not fields.issubset(
        EVIDENCE_REQUIRED_FIELDS | EVIDENCE_OPTIONAL_FIELDS
    ):
        raise AcceptanceError("evidence envelope has an unexpected field set")
    if (
        payload.get("contractName") != EVIDENCE_CONTRACT
        or type(payload.get("contractVersion")) is not int
        or payload.get("contractVersion") != 1
        or payload.get("secretRedacted") is not True
        or payload.get("evidenceKind") != expected_kind
    ):
        raise AcceptanceError(f"evidence envelope for {expected_kind} has invalid identity")
    evidence_id = _safe_id(payload.get("evidenceId"), f"{expected_kind} evidenceId")
    if any(
        key != "secretRedacted" and marker in key.casefold()
        for key in payload
        for marker in FORBIDDEN_FIELD_MARKERS
    ):
        raise AcceptanceError("evidence envelope contains a forbidden sensitive field")
    binding = payload.get("releaseBinding")
    if not isinstance(binding, dict) or set(binding) != set(RELEASE_BINDING_FIELDS):
        raise AcceptanceError(f"{expected_kind} evidence releaseBinding is not exact")
    for field in RELEASE_BINDING_FIELDS:
        if binding.get(field) != target[field]:
            raise AcceptanceError(f"{expected_kind} evidence target drifted at {field}")
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims or len(claims) > 256:
        raise AcceptanceError(f"{expected_kind} evidence claims must be a non-empty array")
    claim_ids: set[str] = set()
    normalized_claims: list[dict[str, str]] = []
    all_claims_pass = True
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != CLAIM_FIELDS:
            raise AcceptanceError(f"{expected_kind} evidence claim schema is not exact")
        claim_id = _safe_id(claim.get("claimId"), f"{expected_kind} claimId")
        if claim_id in claim_ids:
            raise AcceptanceError(f"{expected_kind} evidence has a duplicate claimId")
        claim_ids.add(claim_id)
        claim_status = claim.get("status")
        if claim_status not in {"pass", "attention_required"}:
            raise AcceptanceError(f"{expected_kind} evidence claim status is invalid")
        evidence_sha256 = _require_sha(
            claim.get("evidenceSha256"), f"{expected_kind} claim evidenceSha256"
        )
        normalized_claims.append(
            {
                "claimId": claim_id,
                "status": claim_status,
                "evidenceSha256": evidence_sha256,
            }
        )
        all_claims_pass = all_claims_pass and claim_status == "pass"
    generated_at = _timestamp(payload.get("generatedAtUtc"), "evidence generatedAtUtc")
    if generated_at < completed_at:
        raise AcceptanceError(f"{expected_kind} evidence predates owner finalization")
    if generated_at > observed_at + dt.timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise AcceptanceError(f"{expected_kind} evidence is unreasonably in the future")
    if observed_at - generated_at > dt.timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS):
        raise AcceptanceError(f"{expected_kind} evidence is stale")
    status = payload.get("status")
    if not isinstance(status, str) or SAFE_STATUS.fullmatch(status) is None:
        raise AcceptanceError(f"{expected_kind} evidence status is invalid")
    ready = status in {"accepted", "ready"} and all_claims_pass
    readiness = payload.get("operationalReadinessClaimAllowed")
    if not isinstance(readiness, bool):
        raise AcceptanceError("operationalReadinessClaimAllowed must be boolean")
    ready = ready and readiness
    return {
        "evidenceId": evidence_id,
        "evidenceKind": expected_kind,
        "status": status,
        "generatedAtUtc": payload["generatedAtUtc"],
        "claimCount": len(normalized_claims),
        "claimSetSha256": _sha(
            _canonical_bytes(sorted(normalized_claims, key=lambda claim: claim["claimId"]))
        ),
    }, ready, generated_at


def verify(
    *,
    workspace: Path,
    finalization_receipt: Path,
    finalization_sha256: str,
    generation_convergence: Path,
    generation_convergence_sha256: str,
    current_convergence: Path,
    current_convergence_sha256: str,
    release_manifest: Path,
    release_manifest_file_sha256: str,
    required_evidence: dict[str, tuple[Path, str]],
    output: Path,
    observed_at: dt.datetime | None = None,
) -> dict[str, Any]:
    root = _workspace(workspace)
    final_raw, finalization = _pinned_json(
        finalization_receipt,
        finalization_sha256,
        root,
        "owner finalization receipt",
        require_canonical=True,
    )
    generation_raw, generation_payload = _pinned_json(
        generation_convergence,
        generation_convergence_sha256,
        root,
        "generation convergence receipt",
    )
    current_raw, current_payload = _pinned_json(
        current_convergence,
        current_convergence_sha256,
        root,
        "CURRENT convergence receipt",
    )
    manifest_raw, manifest_payload = _pinned_json(
        release_manifest,
        release_manifest_file_sha256,
        root,
        "release manifest",
    )
    if set(required_evidence) != REQUIRED_EVIDENCE_KINDS:
        raise AcceptanceError(
            "required evidence kinds must exactly match the flagship v1 denominator"
        )
    now = observed_at or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise AcceptanceError("observed_at must be timezone-aware UTC")
    target = _target_from_finalization(finalization)
    completed_at = _timestamp(finalization.get("completedAtUtc"), "completedAtUtc")
    try:
        generation_install_route = CONVERGENCE_HELPERS.discover_install_route(
            manifest_raw, generation_id=target["generationId"]
        )
        current_install_route = CONVERGENCE_HELPERS.discover_install_route(manifest_raw)
    except CONVERGENCE_HELPERS.ConvergenceError as error:
        raise AcceptanceError("release manifest install route is invalid") from error
    generation_generated_at, generation_release_truth = _validate_convergence(
        generation_payload,
        target,
        finalization,
        role="generation",
        completed_at=completed_at,
        observed_at=now,
        expected_install_route=generation_install_route,
    )
    current_generated_at, current_release_truth = _validate_convergence(
        current_payload,
        target,
        finalization,
        role="CURRENT",
        completed_at=completed_at,
        observed_at=now,
        expected_install_route=current_install_route,
    )
    if generation_release_truth != current_release_truth:
        raise AcceptanceError("generation and CURRENT releaseTruth do not converge exactly")
    try:
        manifest_release_truth = CONVERGENCE_HELPERS.canonicalize_projection(
            manifest_payload.get("releaseTruth"), source="release manifest releaseTruth"
        )
        CONVERGENCE_HELPERS._validate_native_manifest_claims(
            manifest_payload,
            generation_release_truth,
            source="release manifest",
        )
    except CONVERGENCE_HELPERS.ConvergenceError as error:
        raise AcceptanceError("release manifest claims do not bind releaseTruth") from error
    if (
        manifest_release_truth != manifest_payload.get("releaseTruth")
        or manifest_release_truth != generation_release_truth
    ):
        raise AcceptanceError("release manifest releaseTruth does not converge exactly")
    evidence_rows: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    all_ready = True
    for kind in sorted(required_evidence):
        if SAFE_KIND.fullmatch(kind) is None:
            raise AcceptanceError("required evidence kind is invalid")
        path, expected_digest = required_evidence[kind]
        raw, payload = _pinned_json(
            path,
            expected_digest,
            root,
            f"{kind} evidence",
            require_canonical=True,
        )
        row, ready, evidence_generated_at = _validate_evidence(
            payload,
            target,
            kind,
            completed_at=completed_at,
            observed_at=now,
        )
        if current_generated_at < evidence_generated_at:
            raise AcceptanceError(
                f"CURRENT convergence predates {kind} post-activation evidence"
            )
        if generation_generated_at > evidence_generated_at:
            raise AcceptanceError(
                f"generation convergence postdates {kind} post-activation evidence"
            )
        if row["evidenceId"] in evidence_ids:
            raise AcceptanceError("duplicate evidenceId")
        evidence_ids.add(row["evidenceId"])
        evidence_rows.append(
            {
                **row,
                "accepted": ready,
                "ref": f"{kind}:{row['evidenceId']}",
                "sha256": _sha(raw),
            }
        )
        all_ready = all_ready and ready
    receipt = {
        "contractName": AGGREGATE_CONTRACT,
        "contractVersion": 1,
        "generatedAtUtc": now.astimezone(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "status": "accepted" if all_ready else "attention_required",
        "secretRedacted": True,
        "ownerFinalizationStatus": finalization["status"],
        "releaseBinding": target,
        "authorityRevisionId": finalization["authorityRevisionId"],
        "inputDigests": {
            "ownerFinalization": _sha(final_raw),
            "generationConvergence": _sha(generation_raw),
            "currentConvergence": _sha(current_raw),
            "releaseManifest": _sha(manifest_raw),
        },
        "requiredEvidenceKinds": sorted(required_evidence),
        "evidenceCount": len(evidence_rows),
        "evidence": evidence_rows,
    }
    _write_new(output, root, _canonical_bytes(receipt))
    return receipt


def _write_new(path: Path, root: Path, raw: bytes) -> None:
    if not path.is_absolute():
        raise AcceptanceError("acceptance output must be absolute")
    try:
        path.relative_to(root)
        parent = path.parent.resolve(strict=True)
        parent.relative_to(root)
    except (OSError, ValueError) as error:
        raise AcceptanceError("acceptance output must remain beneath the workspace") from error
    if path.parent.absolute() != parent:
        raise AcceptanceError("acceptance output must not use symlinked path components")
    resolved = parent / path.name
    metadata = parent.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise AcceptanceError("acceptance output parent is unsafe")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    temporary: Path | None = None
    descriptor: int | None = None
    created_identity: tuple[int, int] | None = None
    for _attempt in range(32):
        candidate = parent / (
            ".post-activation-acceptance.tmp-" + secrets.token_hex(16)
        )
        try:
            descriptor = os.open(candidate, flags, 0o600)
        except FileExistsError:
            continue
        temporary = candidate
        created = os.fstat(descriptor)
        created_identity = (created.st_dev, created.st_ino)
        break
    if temporary is None or descriptor is None or created_identity is None:
        raise AcceptanceError("acceptance temporary output could not be allocated")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o600)
            os.fsync(stream.fileno())
            written = os.fstat(stream.fileno())
        final = os.lstat(temporary)
        if (
            not stat.S_ISREG(final.st_mode)
            or final.st_uid != os.geteuid()
            or final.st_nlink != 1
            or stat.S_IMODE(final.st_mode) != 0o600
            or (final.st_dev, final.st_ino) != (written.st_dev, written.st_ino)
        ):
            raise AcceptanceError("acceptance temporary output changed during write")
        try:
            os.link(temporary, resolved, follow_symlinks=False)
        except FileExistsError as error:
            raise AcceptanceError("acceptance output already exists") from error
        published = os.lstat(resolved)
        if (
            not stat.S_ISREG(published.st_mode)
            or published.st_uid != os.geteuid()
            or published.st_nlink != 2
            or stat.S_IMODE(published.st_mode) != 0o600
            or (published.st_dev, published.st_ino) != created_identity
        ):
            raise AcceptanceError("acceptance output changed during publication")
        temporary_state = os.lstat(temporary)
        if (temporary_state.st_dev, temporary_state.st_ino) != created_identity:
            raise AcceptanceError("acceptance temporary output changed during publication")
        os.unlink(temporary)
        temporary = None
        published = os.lstat(resolved)
        if (
            published.st_nlink != 1
            or (published.st_dev, published.st_ino) != created_identity
        ):
            raise AcceptanceError("acceptance output changed after publication")
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if temporary is not None:
            try:
                temporary_state = os.lstat(temporary)
                if (temporary_state.st_dev, temporary_state.st_ino) == created_identity:
                    os.unlink(temporary)
            except OSError:
                pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        paths = _parse_kind_map(args.require_evidence, "--require-evidence")
        digests = _parse_kind_map(args.evidence_sha256, "--evidence-sha256")
        if set(paths) != set(digests):
            raise AcceptanceError("evidence path and digest kinds must match exactly")
        evidence = {
            kind: (Path(paths[kind]), _require_sha(digests[kind], f"{kind} evidence digest"))
            for kind in paths
        }
        receipt = verify(
            workspace=args.workspace,
            finalization_receipt=args.finalization_receipt,
            finalization_sha256=args.expected_finalization_sha256,
            generation_convergence=args.generation_convergence,
            generation_convergence_sha256=args.expected_generation_convergence_sha256,
            current_convergence=args.current_convergence,
            current_convergence_sha256=args.expected_current_convergence_sha256,
            release_manifest=args.release_manifest,
            release_manifest_file_sha256=args.expected_release_manifest_file_sha256,
            required_evidence=evidence,
            output=args.output,
        )
    except AcceptanceError as error:
        print(f"post_activation_acceptance:fail: {error}", file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, ValueError):
        print(
            "post_activation_acceptance:fail: bounded local validation failed",
            file=sys.stderr,
        )
        return 1
    print(f"post_activation_acceptance:{receipt['status']}")
    return 0 if receipt["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
