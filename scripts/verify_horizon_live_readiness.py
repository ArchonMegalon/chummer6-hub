#!/usr/bin/env python3
"""Offline verifier for the generation-bound Horizon live-readiness receipt."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import verify_horizon_readiness as source_verifier
import verify_live_release_convergence as convergence


CONTRACT_NAME = "chummer.horizon_live_readiness/v1"
CONTRACT_VERSION = 1
EVIDENCE_CONTRACT_NAME = "chummer.post-activation-evidence/v1"
EVIDENCE_CONTRACT_VERSION = 1
EVIDENCE_KIND = "horizon_live_readiness"
EVIDENCE_CLAIM_ID = "horizon_live_readiness_v1"
PRODUCTION_ORIGIN = "https://chummer.run"
SOURCE_CONTRACT = "chummer.horizon_readiness.v1"
CONVERGENCE_CONTRACT = "chummer.live-release-convergence/v1"
EXPECTED_HORIZON_COUNT = 15
EXPECTED_CAPABILITY_COUNT = 20
INTERNAL_CAPABILITY_ROUTE = "/api/internal/horizons/capabilities?publicSafe=true"
PUBLIC_CAPABILITY_ROUTE = "/api/v1/public/horizons/capabilities"
DEFAULT_MAX_AGE_SECONDS = 86_400
DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS = 300

HORIZON_ROUTES: dict[str, str] = {
    "alice": "/alice",
    "origin-dossier": "/origin-dossier",
    "karma-forge": "/participate/karma-forge",
    "knowledge-fabric": "/rules",
    "jackpoint": "/jackpoint",
    "black-ledger": "/ledger",
    "runsite": "/runsites",
    "runbook-press": "/runbook",
    "table-pulse": "/table-pulse",
    "propertyquarry": "/propertyquarry",
    "runner_passport": "/passport",
    "signal_deck": "/signal-deck",
    "living_world": "/living-world",
    "community_hub": "/community",
    "creator_os": "/creator",
}

TOP_LEVEL_FIELDS = {
    "contractName", "contractVersion", "generatedAtUtc", "status",
    "operationalReadinessClaimAllowed", "releaseBinding", "inputBindings",
    "probePolicy", "currentFence", "catalogObservations", "summary",
    "horizons", "capabilities",
}
RELEASE_FIELDS = {
    "releaseVersion", "generationId", "manifestSha256",
    "releaseDecisionStatus", "releaseDecisionSha256", "authoritySnapshotSha256",
}
INPUT_FIELDS = {
    "sourceReadinessSha256",
    "committedPublicConvergenceSha256",
    "generationManifestFileSha256",
}
POLICY_FIELDS = {
    "baseOrigin", "methods", "sameOriginOnly", "redirectsFollowed",
    "runtimeRequestsPerformed", "providerCallsPerformed", "quotaConsumed",
    "mutationsPerformed", "secretRedacted",
}
FENCE_FIELDS = {"preCurrent", "postCurrent", "stable"}
FENCE_SNAPSHOT_FIELDS = {
    "route", "releaseVersion", "manifestSha256", "releaseDecisionSha256",
    "releaseDecisionStatus", "authoritySnapshotSha256", "releaseTruthSha256",
    "responseSha256",
}
SUMMARY_FIELDS = {
    "horizonCount", "capabilityCount", "deploymentReachableCount",
    "configurationConfiguredCount", "configurationDisabledCount",
    "operationalReadyCount", "governanceClearedCount", "publicCapabilityCount",
}
HORIZON_FIELDS = {
    "horizonId", "route", "sourceStatus", "deploymentStatus",
    "configurationStatus", "operationalStatus", "governanceStatus",
    "httpStatus", "contentType", "responseSha256", "identityBindingStatus",
}
CAPABILITY_FIELDS = {
    "horizonId", "capabilityId", "sourceStatus", "deploymentStatus",
    "configurationStatus", "operationalStatus", "governanceStatus",
    "httpStatus", "responseSha256", "identityBindingStatus",
    "publicCatalogObserved",
}
CATALOG_OBSERVATIONS_FIELDS = {"internalPublicSafe", "public"}
CATALOG_OBSERVATION_FIELDS = {
    "route", "httpStatus", "contentType", "responseSha256",
    "identityBindingStatus", "rowCount",
}
CONVERGENCE_FIELDS = {
    "contractName", "contractVersion", "generatedAtUtc", "status",
    "mismatchCount", "failureCount", "mismatches", "failures",
    "authorityRoute", "checkedRouteCount", "checkedRoutes", "comparedFields",
    "releaseTruth", "releaseVersion", "manifestSha256",
    "releaseDecisionStatus", "releaseDecisionSha256",
    "authoritySnapshotSha256", "verificationMode",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GENERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


class VerificationError(ValueError):
    pass


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_opaque_id(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or GENERATION_RE.fullmatch(value) is None
        or ".." in value
    ):
        raise VerificationError(f"{label}:invalid")
    return value


def _canonical_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise VerificationError(f"{label}:invalid")
    return value


def validate_public_https_origin(value: str) -> str:
    """Return one canonical public HTTPS origin or fail without DNS resolution."""

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise VerificationError("base_origin:invalid") from error
    if (
        not isinstance(value, str)
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port == 443
    ):
        raise VerificationError("base_origin:invalid")
    raw_host = parsed.hostname
    try:
        host = raw_host.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise VerificationError("base_origin:invalid") from error
    if host != raw_host or host.endswith(".") or any(character.isspace() for character in host):
        raise VerificationError("base_origin:noncanonical")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_global:
            raise VerificationError("base_origin:private_host")
        authority = f"[{host}]" if address.version == 6 else host
    else:
        lowered = host.casefold()
        if (
            "." not in host
            or lowered == "localhost"
            or lowered.endswith((".localhost", ".local", ".internal", ".home.arpa"))
        ):
            raise VerificationError("base_origin:private_host")
        authority = host
    if port is not None:
        authority += f":{port}"
    canonical = f"https://{authority}"
    if value.rstrip("/") != canonical:
        raise VerificationError("base_origin:noncanonical")
    if canonical != PRODUCTION_ORIGIN:
        raise VerificationError("base_origin:not_production")
    return canonical


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    folded: dict[str, str] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("duplicate_json_key")
        old = folded.get(key.casefold())
        if old is not None and old != key:
            raise VerificationError("case_shadowed_json_key")
        result[key] = value
        folded[key.casefold()] = key
    return result


def _reject_json_constant(_: str) -> Any:
    raise VerificationError("nonfinite_json_number")


def parse_json_object(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, VerificationError) as error:
        raise VerificationError(f"{label}:invalid_json") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{label}:not_object")
    return value


def read_stable_bytes(path: Path, *, label: str, max_bytes: int = 16 * 1024 * 1024) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise VerificationError(f"{label}:unsafe_or_unreadable_file") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) & 0o022
        ):
            raise VerificationError(f"{label}:unsafe_file_metadata")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise VerificationError(f"{label}:file_too_large")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise VerificationError(f"{label}:changed_while_reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_json_object(path: Path, *, label: str, require_canonical: bool = False) -> tuple[dict[str, Any], bytes]:
    data = read_stable_bytes(path, label=label)
    payload = parse_json_object(data, label=label)
    if require_canonical and data != canonical_json_bytes(payload):
        raise VerificationError(f"{label}:noncanonical_json")
    return payload, data


def _exact_keys(value: Any, expected: set[str], location: str, issues: list[str]) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{location}:not_object")
        return False
    actual = set(value)
    issues.extend(f"{location}:missing:{key}" for key in sorted(expected - actual))
    issues.extend(f"{location}:unknown:{key}" for key in sorted(actual - expected))
    return actual == expected


def _timestamp_issues(value: Any, now: datetime, max_age: int, future_skew: int, location: str) -> list[str]:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        return [f"{location}:malformed"]
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return [f"{location}:malformed"]
    result: list[str] = []
    if (parsed - now).total_seconds() > future_skew:
        result.append(f"{location}:future")
    if (now - parsed).total_seconds() > max_age:
        result.append(f"{location}:stale")
    return result


def expected_binding(
    release_version: str,
    generation_id: str,
    manifest_sha256: str,
    release_decision_sha256: str,
    authority_snapshot_sha256: str,
) -> dict[str, str]:
    if not isinstance(release_version, str) or not release_version or release_version != release_version.strip() or len(release_version) > 128:
        raise VerificationError("expected_release_version:invalid")
    if GENERATION_RE.fullmatch(generation_id or "") is None:
        raise VerificationError("expected_generation_id:invalid")
    for name, value in (
        ("manifest_sha256", manifest_sha256),
        ("release_decision_sha256", release_decision_sha256),
        ("authority_snapshot_sha256", authority_snapshot_sha256),
    ):
        if SHA256_RE.fullmatch(value or "") is None:
            raise VerificationError(f"expected_{name}:invalid")
    return {
        "releaseVersion": release_version,
        "generationId": generation_id,
        "manifestSha256": manifest_sha256,
        "releaseDecisionSha256": release_decision_sha256,
        "authoritySnapshotSha256": authority_snapshot_sha256,
    }


def validate_convergence(
    payload: dict[str, Any],
    expected: Mapping[str, str],
    *,
    generation_manifest_bytes: bytes,
) -> tuple[list[str], str | None]:
    issues: list[str] = []
    _exact_keys(payload, CONVERGENCE_FIELDS, "convergence", issues)
    for field, wanted in (
        ("contractName", CONVERGENCE_CONTRACT), ("contractVersion", 1),
        ("status", "pass"), ("mismatchCount", 0), ("failureCount", 0),
        ("verificationMode", "committed_public"),
        ("releaseVersion", expected["releaseVersion"]),
        ("manifestSha256", expected["manifestSha256"]),
        ("releaseDecisionSha256", expected["releaseDecisionSha256"]),
        ("authoritySnapshotSha256", expected["authoritySnapshotSha256"]),
    ):
        if payload.get(field) != wanted:
            issues.append(f"convergence:{field}:mismatch")
    if isinstance(payload.get("contractVersion"), bool) or not isinstance(payload.get("contractVersion"), int):
        issues.append("convergence:contractVersion:invalid_type")
    for count_field in ("mismatchCount", "failureCount", "checkedRouteCount"):
        value = payload.get(count_field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            issues.append(f"convergence:{count_field}:invalid_type")
    if payload.get("mismatches") != [] or payload.get("failures") != []:
        issues.append("convergence:nonempty_failures")
    route = f"/api/v1/public/release-truth/g/{expected['generationId']}"
    if payload.get("authorityRoute") != route:
        issues.append("convergence:generation_route_mismatch")
    truth = payload.get("releaseTruth")
    try:
        canonical = convergence.canonicalize_projection(truth, source="convergence receipt")
    except Exception:
        canonical = None
        issues.append("convergence:releaseTruth:invalid")
    if canonical is not None:
        for field in ("releaseVersion", "manifestSha256", "releaseDecisionSha256"):
            if canonical.get(field) != expected[field]:
                issues.append(f"convergence:releaseTruth:{field}:mismatch")
        if canonical.get("releaseDecisionStatus") != payload.get("releaseDecisionStatus"):
            issues.append("convergence:releaseDecisionStatus:mismatch")
        if canonical.get("releaseDecisionStatus") not in {"preview_ready", "stable_ready"}:
            issues.append("convergence:releaseDecisionStatus:not_release_ready")
        elif not convergence._availability_claims_allowed(canonical):
            issues.append("convergence:releaseTruth:not_publishable")
    if payload.get("comparedFields") != list(convergence.REQUIRED_FIELDS):
        issues.append("convergence:comparedFields:mismatch")
    checked = payload.get("checkedRoutes")
    generation = expected["generationId"]
    try:
        required_routes = set(convergence.generation_routes(generation))
        manifest_payload = parse_json_object(
            generation_manifest_bytes,
            label="generation_manifest",
        )
        if canonical is None:
            raise VerificationError("generation_manifest:no_release_truth")
        convergence._validate_native_manifest_claims(
            manifest_payload,
            canonical,
            source="generation manifest",
        )
        install_route = convergence.discover_install_route(
            generation_manifest_bytes,
            generation_id=generation,
        )
        if install_route is None:
            raise VerificationError("generation_manifest:no_install_handoff")
        required_routes.add(install_route)
    except Exception:
        required_routes = set()
        issues.append("convergence:checked_routes:invalid_generation_manifest")
    if (
        not isinstance(checked, list)
        or not checked
        or not all(isinstance(item, str) for item in checked)
        or checked != sorted(set(checked))
        or payload.get("checkedRouteCount") != len(checked)
    ):
        issues.append("convergence:checked_routes:invalid")
    else:
        actual_routes = set(checked)
        if not required_routes.issubset(actual_routes):
            issues.append("convergence:checked_routes:missing_generation_denominator")
        if actual_routes != required_routes:
            issues.append("convergence:checked_routes:generation_mismatch")
    decision = payload.get("releaseDecisionStatus")
    return issues, decision if isinstance(decision, str) else None


def _records_by_id(records: Any, field: str, location: str, issues: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        issues.append(f"{location}:not_array")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            issues.append(f"{location}:{index}:not_object")
            continue
        key = row.get(field)
        if not isinstance(key, str) or not key:
            issues.append(f"{location}:{index}:invalid_id")
        elif key in result:
            issues.append(f"{location}:duplicate:{key}")
        else:
            result[key] = row
    return result


def verify_receipt(
    receipt: dict[str, Any],
    source: dict[str, Any],
    convergence_receipt: dict[str, Any],
    *,
    source_sha256: str,
    convergence_sha256: str,
    generation_manifest_sha256: str,
    generation_manifest_bytes: bytes,
    expected: Mapping[str, str],
    repo_root: Path,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    allowed_future_skew_seconds: int = DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS,
    now_utc: datetime | None = None,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    supplied_now = now_utc or datetime.now(UTC)
    if supplied_now.tzinfo is None or supplied_now.utcoffset() is None:
        return False, ["freshness_policy:naive_now"]
    now = supplied_now.astimezone(UTC)
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, int)
        or max_age_seconds <= 0
        or isinstance(allowed_future_skew_seconds, bool)
        or not isinstance(allowed_future_skew_seconds, int)
        or allowed_future_skew_seconds < 0
    ):
        return False, ["freshness_policy:invalid"]
    if SHA256_RE.fullmatch(source_sha256 or "") is None:
        issues.append("source:sha256:invalid")
    if SHA256_RE.fullmatch(convergence_sha256 or "") is None:
        issues.append("convergence:sha256:invalid")
    if SHA256_RE.fullmatch(generation_manifest_sha256 or "") is None:
        issues.append("generation_manifest:sha256:invalid")
    elif sha256_bytes(generation_manifest_bytes) != generation_manifest_sha256:
        issues.append("generation_manifest:sha256:content_mismatch")

    source_ok, source_issues = source_verifier.verify_payload(
        source,
        repo_root.resolve(),
        repo_root / ".codex-design/product/HORIZON_REGISTRY.yaml",
        repo_root / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs",
        max_age_seconds=max_age_seconds,
        allowed_future_skew_seconds=allowed_future_skew_seconds,
        now_utc=now,
    )
    if not source_ok:
        issues.extend(f"source:{item}" for item in source_issues)
    if source.get("contract_name") != SOURCE_CONTRACT:
        issues.append("source:contract_mismatch")
    if not source_verifier.source_working_claim_allowed(source):
        issues.append("source:working_claim_not_allowed")
    convergence_issues, decision_status = validate_convergence(
        convergence_receipt,
        expected,
        generation_manifest_bytes=generation_manifest_bytes,
    )
    issues.extend(convergence_issues)
    issues.extend(
        _timestamp_issues(
            convergence_receipt.get("generatedAtUtc"),
            now,
            max_age_seconds,
            allowed_future_skew_seconds,
            "convergence:generatedAtUtc",
        )
    )

    _exact_keys(receipt, TOP_LEVEL_FIELDS, "receipt", issues)
    if receipt.get("contractName") != CONTRACT_NAME:
        issues.append("receipt:contractName:mismatch")
    if (
        isinstance(receipt.get("contractVersion"), bool)
        or not isinstance(receipt.get("contractVersion"), int)
        or receipt.get("contractVersion") != CONTRACT_VERSION
    ):
        issues.append("receipt:contractVersion:mismatch")
    issues.extend(_timestamp_issues(receipt.get("generatedAtUtc"), now, max_age_seconds, allowed_future_skew_seconds, "receipt:generatedAtUtc"))

    binding = receipt.get("releaseBinding")
    if _exact_keys(binding, RELEASE_FIELDS, "releaseBinding", issues):
        wanted_binding = {**expected, "releaseDecisionStatus": decision_status}
        for field, wanted in wanted_binding.items():
            if binding.get(field) != wanted:
                issues.append(f"releaseBinding:{field}:mismatch")

    inputs = receipt.get("inputBindings")
    if _exact_keys(inputs, INPUT_FIELDS, "inputBindings", issues):
        if inputs.get("sourceReadinessSha256") != source_sha256:
            issues.append("inputBindings:sourceReadinessSha256:mismatch")
        if inputs.get("committedPublicConvergenceSha256") != convergence_sha256:
            issues.append("inputBindings:committedPublicConvergenceSha256:mismatch")
        if inputs.get("generationManifestFileSha256") != generation_manifest_sha256:
            issues.append("inputBindings:generationManifestFileSha256:mismatch")

    policy = receipt.get("probePolicy")
    if _exact_keys(policy, POLICY_FIELDS, "probePolicy", issues):
        required_policy = {
            "methods": ["GET"], "sameOriginOnly": True, "redirectsFollowed": False,
            "runtimeRequestsPerformed": True, "providerCallsPerformed": False,
            "quotaConsumed": False, "mutationsPerformed": False, "secretRedacted": True,
        }
        for field, wanted in required_policy.items():
            if policy.get(field) != wanted:
                issues.append(f"probePolicy:{field}:unsafe")
        origin = policy.get("baseOrigin")
        try:
            canonical_origin = validate_public_https_origin(origin)
        except VerificationError:
            issues.append("probePolicy:baseOrigin:unsafe")
        else:
            if canonical_origin != origin:
                issues.append("probePolicy:baseOrigin:noncanonical")

    fence = receipt.get("currentFence")
    if _exact_keys(fence, FENCE_FIELDS, "currentFence", issues):
        try:
            convergence_truth = convergence.canonicalize_projection(
                convergence_receipt.get("releaseTruth"),
                source="convergence receipt",
            )
            expected_truth_sha256 = sha256_bytes(canonical_json_bytes(convergence_truth))
        except Exception:
            expected_truth_sha256 = None
        snapshots: list[dict[str, Any]] = []
        for name in ("preCurrent", "postCurrent"):
            value = fence.get(name)
            if _exact_keys(value, FENCE_SNAPSHOT_FIELDS, f"currentFence:{name}", issues):
                snapshots.append(value)
                if value.get("route") != "/api/v1/public/release-truth":
                    issues.append(f"currentFence:{name}:route:mismatch")
                for field in ("releaseVersion", "manifestSha256", "releaseDecisionSha256", "authoritySnapshotSha256"):
                    if value.get(field) != expected[field]:
                        issues.append(f"currentFence:{name}:{field}:mismatch")
                if value.get("releaseDecisionStatus") != decision_status:
                    issues.append(f"currentFence:{name}:releaseDecisionStatus:mismatch")
                if value.get("releaseTruthSha256") != expected_truth_sha256:
                    issues.append(f"currentFence:{name}:releaseTruthSha256:mismatch")
                if SHA256_RE.fullmatch(str(value.get("responseSha256", ""))) is None:
                    issues.append(f"currentFence:{name}:responseSha256:invalid")
        if fence.get("stable") is not True:
            issues.append("currentFence:unstable")
        if len(snapshots) == 2 and snapshots[0] != snapshots[1]:
            issues.append("currentFence:pre_post_drift")

    source_capability_list = source.get("capabilities")
    expected_public_count = (
        sum(
            isinstance(row, dict) and row.get("public_visible") is True
            for row in source_capability_list
        )
        if isinstance(source_capability_list, list)
        else 0
    )
    catalog_observations = receipt.get("catalogObservations")
    if _exact_keys(
        catalog_observations,
        CATALOG_OBSERVATIONS_FIELDS,
        "catalogObservations",
        issues,
    ):
        expected_catalogs = {
            "internalPublicSafe": (INTERNAL_CAPABILITY_ROUTE, EXPECTED_CAPABILITY_COUNT),
            "public": (PUBLIC_CAPABILITY_ROUTE, expected_public_count),
        }
        for name, (route, row_count) in expected_catalogs.items():
            observation = catalog_observations.get(name)
            location = f"catalogObservations:{name}"
            if not _exact_keys(
                observation,
                CATALOG_OBSERVATION_FIELDS,
                location,
                issues,
            ):
                continue
            expected_fields = {
                "route": route,
                "httpStatus": 200,
                "contentType": "application/json",
                "rowCount": row_count,
            }
            for field, wanted in expected_fields.items():
                value = observation.get(field)
                if value != wanted or (
                    field in {"httpStatus", "rowCount"}
                    and (isinstance(value, bool) or not isinstance(value, int))
                ):
                    issues.append(f"{location}:{field}:mismatch")
            if observation.get("identityBindingStatus") not in {"exact", "not_exposed"}:
                issues.append(f"{location}:identityBindingStatus:invalid")
            if SHA256_RE.fullmatch(str(observation.get("responseSha256", ""))) is None:
                issues.append(f"{location}:responseSha256:invalid")

    source_horizons = _records_by_id(source.get("horizons"), "horizon_id", "source:horizons", issues)
    source_capabilities = _records_by_id(source.get("capabilities"), "capability_id", "source:capabilities", issues)
    horizon_rows = _records_by_id(receipt.get("horizons"), "horizonId", "receipt:horizons", issues)
    capability_rows = _records_by_id(receipt.get("capabilities"), "capabilityId", "receipt:capabilities", issues)
    if len(source_horizons) != EXPECTED_HORIZON_COUNT or set(source_horizons) != set(HORIZON_ROUTES):
        issues.append("source:horizons:denominator_not_15")
    if len(source_capabilities) != EXPECTED_CAPABILITY_COUNT:
        issues.append("source:capabilities:denominator_not_20")
    if set(horizon_rows) != set(source_horizons):
        issues.append("receipt:horizons:id_set_mismatch")
    if set(capability_rows) != set(source_capabilities):
        issues.append("receipt:capabilities:id_set_mismatch")

    for horizon_id, row in horizon_rows.items():
        _exact_keys(row, HORIZON_FIELDS, f"horizon:{horizon_id}", issues)
        source_row = source_horizons.get(horizon_id, {})
        identity_status = row.get("identityBindingStatus")
        if identity_status not in {"exact", "not_exposed"}:
            issues.append(f"horizon:{horizon_id}:identityBindingStatus:invalid")
        checks = {
            "route": HORIZON_ROUTES.get(horizon_id),
            "sourceStatus": source_row.get("source_status"),
            "configurationStatus": "not_applicable",
            "operationalStatus": source_row.get("runtime_status"),
            "governanceStatus": source_row.get("governance_status"),
            "deploymentStatus": (
                "release_bound_reachable"
                if identity_status == "exact"
                else "raw_http_reachable"
            ),
            "httpStatus": 200,
        }
        for field, wanted in checks.items():
            if row.get(field) != wanted:
                issues.append(f"horizon:{horizon_id}:{field}:mismatch")
        if isinstance(row.get("httpStatus"), bool) or not isinstance(row.get("httpStatus"), int):
            issues.append(f"horizon:{horizon_id}:httpStatus:invalid_type")
        if not isinstance(row.get("contentType"), str) or not row.get("contentType"):
            issues.append(f"horizon:{horizon_id}:contentType:invalid")
        if SHA256_RE.fullmatch(str(row.get("responseSha256", ""))) is None:
            issues.append(f"horizon:{horizon_id}:responseSha256:invalid")

    for capability_id, row in capability_rows.items():
        _exact_keys(row, CAPABILITY_FIELDS, f"capability:{capability_id}", issues)
        source_row = source_capabilities.get(capability_id, {})
        identity_status = row.get("identityBindingStatus")
        if identity_status not in {"exact", "not_exposed"}:
            issues.append(f"capability:{capability_id}:identityBindingStatus:invalid")
        checks = {
            "horizonId": source_row.get("horizon_id"),
            "sourceStatus": source_row.get("source_status"),
            "deploymentStatus": (
                "release_bound_observed"
                if identity_status == "exact"
                else "raw_http_observed"
            ),
            "publicCatalogObserved": source_row.get("public_visible"),
            "httpStatus": 200,
            "governanceStatus": source_row.get("governance_status"),
        }
        for field, wanted in checks.items():
            if row.get(field) != wanted:
                issues.append(f"capability:{capability_id}:{field}:mismatch")
        if isinstance(row.get("httpStatus"), bool) or not isinstance(row.get("httpStatus"), int):
            issues.append(f"capability:{capability_id}:httpStatus:invalid_type")
        if row.get("configurationStatus") not in {"configured", "disabled"}:
            issues.append(f"capability:{capability_id}:configurationStatus:invalid")
        if row.get("operationalStatus") not in {"unverified", "verified"}:
            issues.append(f"capability:{capability_id}:operationalStatus:invalid")
        if SHA256_RE.fullmatch(str(row.get("responseSha256", ""))) is None:
            issues.append(f"capability:{capability_id}:responseSha256:invalid")

    summary = receipt.get("summary")
    if _exact_keys(summary, SUMMARY_FIELDS, "summary", issues):
        rows = list(capability_rows.values())
        expected_summary = {
            "horizonCount": len(horizon_rows), "capabilityCount": len(rows),
            "deploymentReachableCount": sum(
                row.get("deploymentStatus") in {"raw_http_reachable", "release_bound_reachable"}
                for row in horizon_rows.values()
            ),
            "configurationConfiguredCount": sum(row.get("configurationStatus") == "configured" for row in rows),
            "configurationDisabledCount": sum(row.get("configurationStatus") == "disabled" for row in rows),
            "operationalReadyCount": sum(row.get("operationalStatus") == "verified" for row in rows),
            "governanceClearedCount": sum(row.get("governanceStatus") in {"cleared", "not_required"} for row in rows),
            "publicCapabilityCount": sum(row.get("publicCatalogObserved") is True for row in rows),
        }
        for field, wanted in expected_summary.items():
            value = summary.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value != wanted:
                issues.append(f"summary:{field}:mismatch")

    # v1 carries observations, but no digest-bound operational/governance
    # evidence authority. It therefore cannot honestly authorize a ready claim.
    operational_allowed = False
    if receipt.get("operationalReadinessClaimAllowed") is not False:
        issues.append("receipt:operationalReadinessClaimAllowed:mismatch")
    if receipt.get("status") != "attention_required":
        issues.append("receipt:status:mismatch")
    return not issues, sorted(set(issues))


def build_post_activation_evidence(
    receipt: dict[str, Any],
    receipt_bytes: bytes,
    *,
    evidence_id: str,
    target_pointer_sha256: str,
) -> dict[str, Any]:
    """Adapt one verified detailed receipt into the bounded v1 evidence envelope."""

    safe_evidence_id = _safe_opaque_id(evidence_id, label="evidence_id")
    target_pointer = _canonical_sha256(
        target_pointer_sha256,
        label="expected_target_pointer_sha256",
    )
    if receipt_bytes != canonical_json_bytes(receipt):
        raise VerificationError("evidence:receipt_bytes:not_canonical")
    if (
        receipt.get("contractName") != CONTRACT_NAME
        or type(receipt.get("contractVersion")) is not int
        or receipt.get("contractVersion") != CONTRACT_VERSION
        or receipt.get("status") != "attention_required"
        or receipt.get("operationalReadinessClaimAllowed") is not False
    ):
        raise VerificationError("evidence:receipt:not_attention_required")
    generated_at = receipt.get("generatedAtUtc")
    if not isinstance(generated_at, str) or UTC_RE.fullmatch(generated_at) is None:
        raise VerificationError("evidence:generatedAtUtc:invalid")
    binding = receipt.get("releaseBinding")
    if not isinstance(binding, dict) or set(binding) != RELEASE_FIELDS:
        raise VerificationError("evidence:releaseBinding:not_exact")
    release_version = _safe_opaque_id(
        binding.get("releaseVersion"),
        label="evidence:releaseVersion",
    )
    generation_id = _safe_opaque_id(
        binding.get("generationId"),
        label="evidence:generationId",
    )
    manifest_sha256 = _canonical_sha256(
        binding.get("manifestSha256"),
        label="evidence:manifestSha256",
    )
    decision_sha256 = _canonical_sha256(
        binding.get("releaseDecisionSha256"),
        label="evidence:decisionSha256",
    )
    snapshot_sha256 = _canonical_sha256(
        binding.get("authoritySnapshotSha256"),
        label="evidence:snapshotSha256",
    )

    # v1 is intentionally observation-only. No caller input can widen either
    # the envelope or its sole claim to accepted/ready/pass.
    return {
        "contractName": EVIDENCE_CONTRACT_NAME,
        "contractVersion": EVIDENCE_CONTRACT_VERSION,
        "evidenceKind": EVIDENCE_KIND,
        "evidenceId": safe_evidence_id,
        "generatedAtUtc": generated_at,
        "status": "attention_required",
        "secretRedacted": True,
        "operationalReadinessClaimAllowed": False,
        "releaseBinding": {
            "releaseVersion": release_version,
            "generationId": generation_id,
            "manifestSha256": manifest_sha256,
            "decisionSha256": decision_sha256,
            "snapshotSha256": snapshot_sha256,
            "targetPointerSha256": target_pointer,
        },
        "claims": [
            {
                "claimId": EVIDENCE_CLAIM_ID,
                "status": "attention_required",
                "evidenceSha256": sha256_bytes(receipt_bytes),
            }
        ],
    }


def write_new_evidence(path: Path, payload: dict[str, Any]) -> None:
    """Durably create one canonical mode-0600 envelope without replacement."""

    parent = path.parent.resolve()
    if path.parent.absolute() != parent or path.name in {"", ".", ".."}:
        raise VerificationError("evidence_output:unsafe_parent")
    try:
        parent_metadata = parent.stat()
    except OSError as error:
        raise VerificationError("evidence_output:missing_parent") from error
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise VerificationError("evidence_output:unsafe_parent")
    target = parent / path.name
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    data = canonical_json_bytes(payload)
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError as error:
        raise VerificationError("evidence_output:must_be_new") from error
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise OSError("short write")
            written += count
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != len(data)
        ):
            raise OSError("unsafe output metadata")
    except OSError as error:
        os.close(descriptor)
        try:
            os.unlink(target)
        except OSError:
            pass
        raise VerificationError("evidence_output:write_failed") from error
    else:
        os.close(descriptor)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_descriptor = os.open(parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise VerificationError("evidence_output:directory_sync_failed") from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Horizon live-readiness receipt without network access.")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source-readiness", type=Path, required=True)
    parser.add_argument("--committed-public-convergence", type=Path, required=True)
    parser.add_argument("--generation-manifest", type=Path, required=True)
    parser.add_argument("--expected-source-readiness-sha256", required=True)
    parser.add_argument("--expected-committed-public-convergence-sha256", required=True)
    parser.add_argument("--expected-generation-manifest-file-sha256", required=True)
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--expected-generation-id", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-release-decision-sha256", required=True)
    parser.add_argument("--expected-authority-snapshot-sha256", required=True)
    parser.add_argument(
        "--evidence-output",
        type=Path,
        help=(
            "Optional new-file destination for a canonical post-activation "
            "evidence envelope; requires both other evidence arguments."
        ),
    )
    parser.add_argument(
        "--evidence-id",
        help="Secret-safe opaque evidence identifier; requires both other evidence arguments.",
    )
    parser.add_argument(
        "--expected-target-pointer-sha256",
        help="Finalized target-pointer digest; requires both other evidence arguments.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    parser.add_argument("--allowed-future-skew-seconds", type=int, default=DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS)
    parser.add_argument(
        "--allow-attention-required",
        action="store_true",
        help=(
            "Observation-only mode: exit zero for a valid attention_required receipt. "
            "Without this flag, attention_required is a non-zero release gate."
        ),
    )
    parser.add_argument("--require-operational-ready", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    issues: list[str] = []
    attention_blocked = False
    try:
        evidence_options = (
            args.evidence_output,
            args.evidence_id,
            args.expected_target_pointer_sha256,
        )
        if any(value is not None for value in evidence_options) and not all(
            value is not None for value in evidence_options
        ):
            raise VerificationError("evidence_export:all_options_required")
        evidence_requested = all(value is not None for value in evidence_options)
        expected = expected_binding(
            args.expected_release_version, args.expected_generation_id,
            args.expected_manifest_sha256, args.expected_release_decision_sha256,
            args.expected_authority_snapshot_sha256,
        )
        source, source_bytes = read_json_object(args.source_readiness, label="source")
        convergence_receipt, convergence_bytes = read_json_object(args.committed_public_convergence, label="convergence")
        generation_manifest_bytes = read_stable_bytes(
            args.generation_manifest,
            label="generation_manifest",
        )
        receipt, receipt_bytes = read_json_object(
            args.receipt,
            label="receipt",
            require_canonical=True,
        )
        source_sha = sha256_bytes(source_bytes)
        convergence_sha = sha256_bytes(convergence_bytes)
        generation_manifest_sha = sha256_bytes(generation_manifest_bytes)
        if source_sha != args.expected_source_readiness_sha256:
            issues.append("source:sha256:mismatch")
        if convergence_sha != args.expected_committed_public_convergence_sha256:
            issues.append("convergence:sha256:mismatch")
        if generation_manifest_sha != args.expected_generation_manifest_file_sha256:
            issues.append("generation_manifest:sha256:mismatch")
        ok, found = verify_receipt(
            receipt, source, convergence_receipt,
            source_sha256=source_sha, convergence_sha256=convergence_sha,
            generation_manifest_sha256=generation_manifest_sha,
            generation_manifest_bytes=generation_manifest_bytes,
            expected=expected, repo_root=args.repo_root,
            max_age_seconds=args.max_age_seconds,
            allowed_future_skew_seconds=args.allowed_future_skew_seconds,
        )
        issues.extend(found)
        structurally_valid = ok and not issues
        if structurally_valid and evidence_requested:
            evidence = build_post_activation_evidence(
                receipt,
                receipt_bytes,
                evidence_id=args.evidence_id,
                target_pointer_sha256=args.expected_target_pointer_sha256,
            )
            write_new_evidence(args.evidence_output, evidence)
        attention_blocked = (
            structurally_valid
            and receipt.get("status") == "attention_required"
            and not args.allow_attention_required
        )
        if attention_blocked:
            issues.append("attention_required_not_allowed")
        if args.require_operational_ready and receipt.get("operationalReadinessClaimAllowed") is not True:
            issues.append("operational_readiness_not_allowed")
        ok = ok and not issues
    except VerificationError as error:
        ok = False
        issues.append(str(error))
    report_status = (
        "pass"
        if ok
        else "attention_required"
        if attention_blocked and not args.require_operational_ready
        else "fail"
    )
    print(json.dumps({"status": report_status, "issues": sorted(set(issues))}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
