#!/usr/bin/env python3
"""Materialize one complete, secret-safe Tough Tongue read-only runtime config.

This tool performs local validation only. It never contacts Tough Tongue,
enables a provider gate, creates a provider resource, or claims live readback.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping


CONFIG_SCHEMA = "chummer.build_ghost.tough_tongue.runtime_config.v1"
RECEIPT_SCHEMA = "chummer.build_ghost.tough_tongue.runtime_config_receipt.v1"
CONTRACT_SCHEMA = "chummer.build_ghost.tough_tongue.read_only_binding_contract.v3"
STOCK_AVATAR_READBACK_RECEIPT_SCHEMA = (
    "chummer.tough_tongue.stock_avatar_readback_receipt.v1"
)
STOCK_AVATAR_READBACK_SOURCE = "tough_tongue_api_public_scenario_get"
STATUS = "ready-for-read-only-probe"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVIDER_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+~-]{0,511}$")
UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
CREDENTIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~+/@:=-]{15,511}$")
SAFE_ABSOLUTE_PATH = re.compile(r"^/(?:[A-Za-z0-9._@:+~-]+/?)+$")
SAFE_LOWER_VALUE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERIFIED_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
MAX_CONFIG_BYTES = 256 * 1024
MAX_ENVIRONMENT_BYTES = 256 * 1024
MAX_CONTRACT_BYTES = 512 * 1024
MAX_ACCOUNT_SELECTION_POLICY_BYTES = 512 * 1024
MAX_STOCK_AVATAR_READBACK_RECEIPT_BYTES = 64 * 1024
CANDIDATE_KINDS = ("agent", "voice", "function", "scenario", "live_avatar")
STOCK_AVATAR_MIGRATION_KINDS = frozenset(("voice", "scenario", "live_avatar"))
ALLOWED_LIVE_AVATAR_PROVIDERS = frozenset(
    ("anam", "avatario", "heygen", "liveavatar")
)
EXPECTED_SLOT_COUNT = 6
ACCOUNT_SELECTION_POLICY_SCHEMA = "ea.tough_tongue.operator_premium_grants.v1"
PREMIUM_BASIS = "operator_policy_available_minutes_gt_threshold"
PREMIUM_THRESHOLD_MINUTES = 1100.0
PREMIUM_VALIDITY_CALENDAR_MONTHS = 11
DOCUMENTED_GET_ROUTES = {
    "balance": "balance",
    "subscriptions": "subscriptions",
    "organizations": "v2/organizations",
    "scenario": "scenarios/{resource_ref}",
}
NORMALIZATION = {
    "plan": "subscriptions.active.product_name",
    "remaining_minutes": "balance.available_minutes",
    "refresh_at": "balance.last_updated",
    "organization": "organizations.id",
    "resource_ownership": "organization_scoped_scenario_readback",
}
UNSUPPORTED_DIRECT_RESOURCES = ["agent", "voice", "function", "avatar"]
ENVIRONMENT_NAMES = {
    "agent": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID",
    "voice": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID",
    "function": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID",
    "scenario": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID",
    "live_avatar": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID",
}
STOCK_AVATAR_ENVIRONMENT_NAMES = {
    "provider": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_PROVIDER",
    "name": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_NAME",
    "asset_path": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_ASSET_PATH",
    "readback_digest": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_DIGEST",
    "model_provider": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_PROVIDER",
    "model_id": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_ID",
    "allow_legacy_cascade": "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ALLOW_LEGACY_CASCADE",
}
STOCK_AVATAR_READBACK_JSON_ENV = (
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_RECEIPT_JSON"
)
STOCK_AVATAR_READBACK_FIELDS = {
    "Schema", "HttpStatus", "CanonicalWhitelistedResponseDigest",
    "ObservedProvider", "ObservedAvatarName", "ObservedAvatarAssetPath",
    "ObservedLiveAvatarId", "ObservedModelProvider", "ObservedModelId",
    "LegacyCascadePolicyOptIn", "ScenarioRefDigest", "Source",
    "ObservedAtUtc", "MaximumAgeSeconds", "ReceiptDigest",
}


class ConfigError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
    )


def _validated_absolute_path(path: Path, label: str) -> tuple[str, ...]:
    if (
        not path.is_absolute()
        or Path(os.path.normpath(path)) != path
        or SAFE_ABSOLUTE_PATH.fullmatch(str(path)) is None
    ):
        raise ConfigError(f"{label}-path-invalid")
    parts = path.parts[1:]
    if not parts:
        raise ConfigError(f"{label}-path-invalid")
    return parts


def _open_directory_chain(path: Path, label: str) -> int:
    """Open an absolute directory without following any path-component link."""

    parts = () if path == Path("/") else _validated_absolute_path(path, label)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open("/", flags)
    except OSError as error:
        raise ConfigError(f"{label}-unavailable") from error
    try:
        for part in parts:
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                raise ConfigError(f"{label}-authority-invalid") from error
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_owned_file(path: Path, label: str, maximum: int) -> tuple[int, os.stat_result]:
    parts = _validated_absolute_path(path, label)
    parent = Path("/").joinpath(*parts[:-1]) if len(parts) > 1 else Path("/")
    parent_fd = _open_directory_chain(parent, label)
    try:
        try:
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(linked.st_mode):
                raise ConfigError(f"{label}-authority-invalid")
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except ConfigError:
            raise
        except OSError as error:
            raise ConfigError(f"{label}-unavailable") from error
        try:
            opened = os.fstat(descriptor)
            if (
                _identity(opened) != _identity(linked)
                or stat.S_ISLNK(opened.st_mode)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) not in {0o400, 0o600}
                or not 1 <= opened.st_size <= maximum
            ):
                raise ConfigError(f"{label}-authority-invalid")
            return descriptor, opened
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(parent_fd)


def _capture_owned_file(path: Path, label: str, maximum: int) -> bytes:
    descriptor, before = _open_owned_file(path, label, maximum)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise ConfigError(f"{label}-too-large")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _identity(before) != _identity(after):
        raise ConfigError(f"{label}-changed")
    return b"".join(chunks)


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ConfigError(f"{label}-duplicate-key")
            result[key] = value
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"{label}-json-invalid") from error
    if not isinstance(payload, dict):
        raise ConfigError(f"{label}-not-object")
    return payload


def _candidate_digest(value: str) -> str:
    return _digest(value.encode("utf-8"))


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utc_timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or VERIFIED_AT.fullmatch(value) is None:
        raise ConfigError(f"{label}-invalid")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError as error:
        raise ConfigError(f"{label}-invalid") from error


def _add_calendar_months(value: dt.datetime, months: int) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0) or months < 0:
        raise ConfigError("account-selection-policy-calendar-invalid")
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _validated_account_selection_policy(
    payload: dict[str, Any],
    expected_digest: str,
    account_refs: list[str],
    preferred_account_ref: str,
) -> dict[str, Any]:
    required = {
        "schema", "generatedAt", "status", "sourceType", "decisionSequence",
        "decisionEvidenceDigest", "supersededDecisionEvidenceDigest",
        "premiumBasis", "thresholdComparison", "thresholdMinutes",
        "validityCalendarMonths", "identityBasis", "providerPlanLabelBasis",
        "inputAuditEvidenceDigest", "qualificationObservedAt", "premiumValidUntil",
        "grants", "unqualifiedAccountRefs", "preferredAccountRef",
        "preferredOrganizationMembershipVerified", "readyForAccountSelection",
        "readyForResourceBinding", "resourceOwnershipVerified",
        "laterBalanceDropRevokesBeforeExpiry", "identityMismatchRequiresRequalification",
        "expiryRequiresRequalification", "runtimeGatesChanged",
        "providerActivationPerformed", "rawCredentialsPersisted",
        "rawIdentifiersPersisted", "evidenceDigest",
    }
    if set(payload) != required:
        raise ConfigError("account-selection-policy-schema-invalid")
    if not isinstance(expected_digest, str) or SHA256.fullmatch(expected_digest) is None:
        raise ConfigError("account-selection-policy-digest-invalid")
    if _digest(_canonical(payload)) != expected_digest:
        raise ConfigError("account-selection-policy-digest-mismatch")
    internal_digest = payload.get("evidenceDigest")
    if not isinstance(internal_digest, str) or SHA256.fullmatch(internal_digest) is None:
        raise ConfigError("account-selection-policy-evidence-invalid")
    without_evidence = {key: value for key, value in payload.items() if key != "evidenceDigest"}
    if _digest(_canonical(without_evidence)) != internal_digest:
        raise ConfigError("account-selection-policy-evidence-mismatch")
    if (
        payload.get("schema") != ACCOUNT_SELECTION_POLICY_SCHEMA
        or payload.get("status") != "active"
        or payload.get("sourceType") != "user_authority"
        or payload.get("decisionSequence") != 2
        or payload.get("premiumBasis") != PREMIUM_BASIS
        or payload.get("thresholdComparison") != "strictly_greater_than"
        or payload.get("thresholdMinutes") != PREMIUM_THRESHOLD_MINUTES
        or payload.get("validityCalendarMonths") != PREMIUM_VALIDITY_CALENDAR_MONTHS
        or payload.get("identityBasis") != "stable_account_ref_sha256"
        or payload.get("providerPlanLabelBasis") != "unproven_by_documented_api"
    ):
        raise ConfigError("account-selection-policy-authority-invalid")
    for field in (
        "decisionEvidenceDigest", "supersededDecisionEvidenceDigest",
        "inputAuditEvidenceDigest",
    ):
        if not isinstance(payload.get(field), str) or SHA256.fullmatch(payload[field]) is None:
            raise ConfigError("account-selection-policy-authority-invalid")
    if payload["decisionEvidenceDigest"] == payload["supersededDecisionEvidenceDigest"]:
        raise ConfigError("account-selection-policy-supersession-invalid")
    generated_at = _utc_timestamp(payload.get("generatedAt"), "account-selection-policy-generated-at")
    observed_at = _utc_timestamp(
        payload.get("qualificationObservedAt"),
        "account-selection-policy-observed-at",
    )
    valid_until = _utc_timestamp(
        payload.get("premiumValidUntil"),
        "account-selection-policy-valid-until",
    )
    if generated_at < observed_at or valid_until != _add_calendar_months(
        observed_at, PREMIUM_VALIDITY_CALENDAR_MONTHS
    ):
        raise ConfigError("account-selection-policy-calendar-invalid")
    now = _utc_now().astimezone(dt.timezone.utc)
    if now < observed_at or now >= valid_until:
        raise ConfigError("account-selection-policy-expired")

    grants = payload.get("grants")
    if not isinstance(grants, list) or not grants:
        raise ConfigError("account-selection-policy-grants-invalid")
    grant_refs: list[str] = []
    for grant in grants:
        if not isinstance(grant, dict) or set(grant) != {
            "accountRefSha256", "qualificationRemainingMinutes",
            "qualificationObservedAt", "premiumValidUntil",
        }:
            raise ConfigError("account-selection-policy-grants-invalid")
        account_ref = grant.get("accountRefSha256")
        remaining = grant.get("qualificationRemainingMinutes")
        if (
            not isinstance(account_ref, str)
            or SHA256.fullmatch(account_ref) is None
            or isinstance(remaining, bool)
            or not isinstance(remaining, (int, float))
            or float(remaining) <= PREMIUM_THRESHOLD_MINUTES
            or grant.get("qualificationObservedAt") != payload["qualificationObservedAt"]
            or grant.get("premiumValidUntil") != payload["premiumValidUntil"]
        ):
            raise ConfigError("account-selection-policy-grants-invalid")
        grant_refs.append(account_ref)
    if len(set(grant_refs)) != len(grant_refs):
        raise ConfigError("account-selection-policy-grants-invalid")
    unqualified = payload.get("unqualifiedAccountRefs")
    if (
        not isinstance(unqualified, list)
        or any(not isinstance(value, str) or SHA256.fullmatch(value) is None for value in unqualified)
        or len(set(unqualified)) != len(unqualified)
        or set(grant_refs) & set(unqualified)
        or set(grant_refs) | set(unqualified) != set(account_refs)
    ):
        raise ConfigError("account-selection-policy-identity-mismatch")
    if payload.get("preferredAccountRef") != preferred_account_ref or preferred_account_ref not in grant_refs:
        raise ConfigError("account-selection-policy-preferred-account-invalid")
    expected_booleans = {
        "preferredOrganizationMembershipVerified": True,
        "readyForAccountSelection": True,
        "readyForResourceBinding": False,
        "resourceOwnershipVerified": False,
        "laterBalanceDropRevokesBeforeExpiry": False,
        "identityMismatchRequiresRequalification": True,
        "expiryRequiresRequalification": True,
        "runtimeGatesChanged": False,
        "providerActivationPerformed": False,
        "rawCredentialsPersisted": False,
        "rawIdentifiersPersisted": False,
    }
    if any(payload.get(key) is not value for key, value in expected_booleans.items()):
        raise ConfigError("account-selection-policy-posture-invalid")
    return {
        "digest": expected_digest,
        "evidence_digest": internal_digest,
        "grant_refs_digest": _digest(_canonical({"account_refs": sorted(grant_refs)})),
        "grant_count": len(grant_refs),
        "valid_until": payload["premiumValidUntil"],
    }


def _validated_stock_avatar_readback_receipt(
    payload: dict[str, Any],
    expected_file_digest: str,
    expected_contract_digest: str,
    scenario_ref: str,
    live_avatar_ref: str,
    contract_maximum_age_seconds: int,
) -> dict[str, Any]:
    if set(payload) != STOCK_AVATAR_READBACK_FIELDS:
        raise ConfigError("stock-avatar-readback-receipt-schema-invalid")
    if (
        payload.get("Schema") != STOCK_AVATAR_READBACK_RECEIPT_SCHEMA
        or payload.get("HttpStatus") != 200
        or payload.get("ObservedProvider") != "avatario"
        or payload.get("ObservedAvatarName") != "Amelia"
        or payload.get("ObservedAvatarAssetPath")
        != "/live-avatars/avatars/Amelia.jpg"
        or payload.get("ObservedModelProvider") != "Landmass"
        or payload.get("Source") != STOCK_AVATAR_READBACK_SOURCE
    ):
        raise ConfigError("stock-avatar-readback-receipt-authority-invalid")
    live_avatar_id = payload.get("ObservedLiveAvatarId")
    if (
        not isinstance(live_avatar_id, str)
        or live_avatar_id != live_avatar_ref
        or UUID.fullmatch(live_avatar_id) is None
    ):
        raise ConfigError("stock-avatar-readback-receipt-live-avatar-invalid")
    scenario_digest = payload.get("ScenarioRefDigest")
    if scenario_digest != _candidate_digest(scenario_ref):
        raise ConfigError("stock-avatar-readback-receipt-scenario-invalid")
    legacy_opt_in = payload.get("LegacyCascadePolicyOptIn")
    model_id = payload.get("ObservedModelId")
    if type(legacy_opt_in) is not bool or not (
        (model_id == "gemini" and legacy_opt_in is False)
        or (model_id == "cascade" and legacy_opt_in is True)
    ):
        raise ConfigError("stock-avatar-readback-receipt-model-invalid")
    maximum_age = payload.get("MaximumAgeSeconds")
    if (
        type(maximum_age) is not int
        or not 60 <= maximum_age <= contract_maximum_age_seconds
        or maximum_age > 900
    ):
        raise ConfigError("stock-avatar-readback-receipt-freshness-invalid")
    observed_at = _utc_timestamp(
        payload.get("ObservedAtUtc"), "stock-avatar-readback-receipt-observed-at"
    )
    now = _utc_now().astimezone(dt.timezone.utc)
    if observed_at > now or now - observed_at > dt.timedelta(seconds=maximum_age):
        raise ConfigError("stock-avatar-readback-receipt-stale")

    response_authority = {
        "ObservedAvatarAssetPath": payload["ObservedAvatarAssetPath"],
        "ObservedAvatarName": payload["ObservedAvatarName"],
        "ObservedLiveAvatarId": payload["ObservedLiveAvatarId"],
        "ObservedModelId": payload["ObservedModelId"],
        "ObservedModelProvider": payload["ObservedModelProvider"],
        "ObservedProvider": payload["ObservedProvider"],
        "ScenarioRefDigest": payload["ScenarioRefDigest"],
    }
    if payload.get("CanonicalWhitelistedResponseDigest") != _digest(
        _canonical(response_authority)
    ):
        raise ConfigError("stock-avatar-readback-receipt-response-digest-invalid")
    receipt_authority = {
        key: value for key, value in payload.items() if key != "ReceiptDigest"
    }
    if payload.get("ReceiptDigest") != _digest(_canonical(receipt_authority)):
        raise ConfigError("stock-avatar-readback-receipt-digest-invalid")
    file_digest = _digest(_canonical(payload))
    if (
        not isinstance(expected_file_digest, str)
        or SHA256.fullmatch(expected_file_digest) is None
        or file_digest != expected_file_digest
        or file_digest != expected_contract_digest
    ):
        raise ConfigError("stock-avatar-readback-receipt-file-digest-mismatch")
    return {
        "file_digest": file_digest,
        "receipt_digest": payload["ReceiptDigest"],
        "readback_digest": payload["ReceiptDigest"],
        "response_digest": payload["CanonicalWhitelistedResponseDigest"],
        "provider": payload["ObservedProvider"],
        "name": payload["ObservedAvatarName"],
        "asset_path": payload["ObservedAvatarAssetPath"],
        "model_provider": payload["ObservedModelProvider"],
        "model_id": payload["ObservedModelId"],
        "allow_legacy_cascade": legacy_opt_in,
        "observed_at": payload["ObservedAtUtc"],
        "scenario_ref_digest": payload["ScenarioRefDigest"],
        "canonical_json": _canonical(payload).decode("utf-8"),
    }


def _validated_contract(payload: dict[str, Any], expected_digest: str) -> None:
    required = {
        "schema", "provider_key", "base_url", "source_type", "verified_at",
        "authority", "slot_cardinality", "maximum_snapshot_age_seconds",
        "premium_plan_values", "live_avatar_providers",
        "documented_get_allowlist", "normalization",
        "unsupported_direct_resources", "stock_avatar_readback_receipt_digest",
    }
    if set(payload) != required:
        raise ConfigError("read-only-contract-schema-invalid")
    if (
        payload.get("schema") != CONTRACT_SCHEMA
        or payload.get("provider_key") != "tough_tongue"
        or payload.get("base_url") != "https://api.toughtongueai.com/api/public"
        or payload.get("source_type") != "provider_documentation"
    ):
        raise ConfigError("read-only-contract-schema-invalid")
    verified_at = payload.get("verified_at")
    if not isinstance(verified_at, str) or VERIFIED_AT.fullmatch(verified_at) is None:
        raise ConfigError("read-only-contract-authority-invalid")
    try:
        dt.datetime.strptime(verified_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ConfigError("read-only-contract-authority-invalid") from error

    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or set(authority) != {"operator_verified", "source_ref_sha256"}
        or authority.get("operator_verified") is not True
        or not isinstance(authority.get("source_ref_sha256"), str)
        or SHA256.fullmatch(authority["source_ref_sha256"]) is None
    ):
        raise ConfigError("read-only-contract-authority-invalid")

    for field in ("premium_plan_values", "live_avatar_providers"):
        values = payload.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(
                not isinstance(value, str)
                or SAFE_LOWER_VALUE.fullmatch(value) is None
                for value in values
            )
            or len(set(values)) != len(values)
        ):
            raise ConfigError("read-only-contract-entitlements-invalid")
    if any(
        provider not in ALLOWED_LIVE_AVATAR_PROVIDERS
        for provider in payload["live_avatar_providers"]
    ):
        raise ConfigError("read-only-contract-live-avatar-provider-invalid")

    if payload.get("slot_cardinality") != EXPECTED_SLOT_COUNT:
        raise ConfigError("read-only-contract-cardinality-invalid")
    maximum_age = payload.get("maximum_snapshot_age_seconds")
    if not isinstance(maximum_age, int) or not 60 <= maximum_age <= 86400:
        raise ConfigError("read-only-contract-freshness-invalid")
    routes = payload.get("documented_get_allowlist")
    if not isinstance(routes, dict) or set(routes) != set(DOCUMENTED_GET_ROUTES):
        raise ConfigError("read-only-contract-routes-invalid")
    for name, expected_path in DOCUMENTED_GET_ROUTES.items():
        route = routes.get(name)
        if not isinstance(route, dict) or set(route) != {"method", "path"}:
            raise ConfigError(f"read-only-contract-route-{name}-invalid")
        if route.get("method") != "GET" or route.get("path") != expected_path:
            raise ConfigError(f"read-only-contract-route-{name}-invalid")
    if payload.get("normalization") != NORMALIZATION:
        raise ConfigError("read-only-contract-normalization-invalid")
    if payload.get("unsupported_direct_resources") != UNSUPPORTED_DIRECT_RESOURCES:
        raise ConfigError("read-only-contract-unsupported-resources-invalid")
    stock_receipt_digest = payload.get("stock_avatar_readback_receipt_digest")
    if stock_receipt_digest != "" and (
        not isinstance(stock_receipt_digest, str)
        or SHA256.fullmatch(stock_receipt_digest) is None
    ):
        raise ConfigError("read-only-contract-stock-avatar-receipt-invalid")

    if _digest(_canonical(payload)) != expected_digest:
        raise ConfigError("read-only-contract-digest-mismatch")


def _validated_config(
    config_path: Path, contract_snapshot_path: Path
) -> tuple[dict[str, str], dict[str, Any], bytes]:
    payload = _json_object(
        _capture_owned_file(config_path, "operator-config", MAX_CONFIG_BYTES),
        "operator-config",
    )
    required_config_keys = {
        "schema", "account_slots", "preferred_account_ref", "candidate_refs",
        "read_only_contract",
    }
    if (
        not required_config_keys.issubset(payload)
        or not set(payload).issubset(
            required_config_keys
            | {"account_selection_policy", "stock_avatar_readback_receipt"}
        )
        or payload.get("schema") != CONFIG_SCHEMA
    ):
        raise ConfigError("operator-config-schema-invalid")

    slots = payload.get("account_slots")
    if not isinstance(slots, list) or len(slots) != EXPECTED_SLOT_COUNT:
        raise ConfigError("account-slots-invalid")
    account_refs: list[str] = []
    credentials: list[str] = []
    organization_refs: list[str] = []
    for slot in slots:
        if (
            not isinstance(slot, dict)
            or set(slot) not in (
                {"account_ref", "api_key"},
                {"account_ref", "api_key", "organization_ref"},
            )
        ):
            raise ConfigError("account-slot-schema-invalid")
        account_ref = slot.get("account_ref")
        api_key = slot.get("api_key")
        organization_ref = slot.get("organization_ref", "")
        if not isinstance(account_ref, str) or SHA256.fullmatch(account_ref) is None:
            raise ConfigError("account-ref-invalid")
        if not isinstance(api_key, str) or CREDENTIAL.fullmatch(api_key) is None:
            raise ConfigError("account-credential-invalid")
        if (
            not isinstance(organization_ref, str)
            or organization_ref != organization_ref.strip()
            or (organization_ref and PROVIDER_REF.fullmatch(organization_ref) is None)
        ):
            raise ConfigError("organization-ref-invalid")
        account_refs.append(account_ref)
        credentials.append(api_key)
        organization_refs.append(organization_ref)
    if len(set(account_refs)) != len(account_refs):
        raise ConfigError("account-refs-not-distinct")
    if len(set(credentials)) != len(credentials):
        raise ConfigError("account-credentials-not-distinct")
    if any(organization_refs) and not all(organization_refs):
        raise ConfigError("organization-refs-partial")

    preferred = payload.get("preferred_account_ref")
    if not isinstance(preferred, str) or SHA256.fullmatch(preferred) is None:
        raise ConfigError("preferred-account-ref-invalid")
    if account_refs.count(preferred) != 1:
        raise ConfigError("preferred-account-ref-not-exactly-one")

    candidates = payload.get("candidate_refs")
    if not isinstance(candidates, dict) or set(candidates) != set(CANDIDATE_KINDS):
        raise ConfigError("candidate-refs-schema-invalid")
    if any(not isinstance(candidates.get(kind), str) for kind in CANDIDATE_KINDS):
        raise ConfigError("candidate-refs-schema-invalid")
    configured_candidate_kinds = {
        kind for kind in CANDIDATE_KINDS if bool(candidates[kind])
    }
    binding_candidates_configured = configured_candidate_kinds == set(CANDIDATE_KINDS)
    stock_avatar_migration_configured = (
        configured_candidate_kinds == STOCK_AVATAR_MIGRATION_KINDS
    )
    if configured_candidate_kinds and not (
        binding_candidates_configured or stock_avatar_migration_configured
    ):
        raise ConfigError("candidate-refs-partial")
    candidate_digests: dict[str, str] = {}
    for kind in CANDIDATE_KINDS:
        value = candidates.get(kind)
        if not binding_candidates_configured and value == "":
            continue
        if (
            not isinstance(value, str)
            or value != value.strip()
            or PROVIDER_REF.fullmatch(value) is None
            or SHA256.fullmatch(value.lower()) is not None
        ):
            raise ConfigError(f"candidate-{kind.replace('_', '-')}-ref-invalid")
        candidate_digests[kind] = _candidate_digest(value)

    policy_config = payload.get("account_selection_policy")
    account_selection_policy: dict[str, Any] | None = None
    if policy_config is not None:
        if not isinstance(policy_config, dict) or set(policy_config) != {"path", "digest"}:
            raise ConfigError("account-selection-policy-config-invalid")
        policy_path_value = policy_config.get("path")
        policy_digest = policy_config.get("digest")
        if (
            not isinstance(policy_path_value, str)
            or SAFE_ABSOLUTE_PATH.fullmatch(policy_path_value) is None
        ):
            raise ConfigError("account-selection-policy-path-invalid")
        policy_payload = _json_object(
            _capture_owned_file(
                Path(policy_path_value),
                "account-selection-policy",
                MAX_ACCOUNT_SELECTION_POLICY_BYTES,
            ),
            "account-selection-policy",
        )
        account_selection_policy = _validated_account_selection_policy(
            policy_payload,
            policy_digest,
            account_refs,
            preferred,
        )
    if not binding_candidates_configured and account_selection_policy is None:
        raise ConfigError("account-selection-policy-required")

    contract = payload.get("read_only_contract")
    if not isinstance(contract, dict) or set(contract) != {"path", "digest"}:
        raise ConfigError("read-only-contract-config-invalid")
    path_value = contract.get("path")
    contract_digest = contract.get("digest")
    if (
        not isinstance(path_value, str)
        or SAFE_ABSOLUTE_PATH.fullmatch(path_value) is None
    ):
        raise ConfigError("read-only-contract-path-invalid")
    contract_path = Path(path_value)
    if not isinstance(contract_digest, str) or SHA256.fullmatch(contract_digest) is None:
        raise ConfigError("read-only-contract-digest-invalid")
    contract_payload = _json_object(
        _capture_owned_file(contract_path, "read-only-contract", MAX_CONTRACT_BYTES),
        "read-only-contract",
    )
    _validated_contract(contract_payload, contract_digest)

    stock_avatar_receipt_config = payload.get("stock_avatar_readback_receipt")
    stock_avatar_receipt: dict[str, Any] | None = None
    if stock_avatar_receipt_config is not None:
        if (
            not isinstance(stock_avatar_receipt_config, dict)
            or set(stock_avatar_receipt_config) != {"path", "digest"}
        ):
            raise ConfigError("stock-avatar-readback-receipt-config-invalid")
        receipt_path_value = stock_avatar_receipt_config.get("path")
        receipt_file_digest = stock_avatar_receipt_config.get("digest")
        if (
            not isinstance(receipt_path_value, str)
            or SAFE_ABSOLUTE_PATH.fullmatch(receipt_path_value) is None
        ):
            raise ConfigError("stock-avatar-readback-receipt-path-invalid")
        receipt_payload = _json_object(
            _capture_owned_file(
                Path(receipt_path_value),
                "stock-avatar-readback-receipt",
                MAX_STOCK_AVATAR_READBACK_RECEIPT_BYTES,
            ),
            "stock-avatar-readback-receipt",
        )
        stock_avatar_receipt = _validated_stock_avatar_readback_receipt(
            receipt_payload,
            receipt_file_digest,
            contract_payload["stock_avatar_readback_receipt_digest"],
            candidates["scenario"],
            candidates["live_avatar"],
            contract_payload["maximum_snapshot_age_seconds"],
        )
    if bool(candidates["live_avatar"]) != (stock_avatar_receipt is not None):
        raise ConfigError("stock-avatar-readback-receipt-required-or-unexpected")
    if stock_avatar_receipt is None \
            and contract_payload["stock_avatar_readback_receipt_digest"] != "":
        raise ConfigError("read-only-contract-stock-avatar-receipt-unexpected")

    environment = {
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS": ";".join(credentials),
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS": ";".join(account_refs),
        "TOUGH_TONGUE_ORGANIZATION_IDS": ";".join(organization_refs),
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF": preferred,
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE": str(
            contract_snapshot_path
        ),
        "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST": contract_digest,
    }
    environment.update(
        {ENVIRONMENT_NAMES[kind]: candidates[kind] for kind in CANDIDATE_KINDS}
    )
    stock_avatar_environment = {
        STOCK_AVATAR_ENVIRONMENT_NAMES["provider"]: "",
        STOCK_AVATAR_ENVIRONMENT_NAMES["name"]: "",
        STOCK_AVATAR_ENVIRONMENT_NAMES["asset_path"]: "",
        STOCK_AVATAR_ENVIRONMENT_NAMES["readback_digest"]: "",
        STOCK_AVATAR_ENVIRONMENT_NAMES["model_provider"]: "",
        STOCK_AVATAR_ENVIRONMENT_NAMES["model_id"]: "",
        STOCK_AVATAR_ENVIRONMENT_NAMES["allow_legacy_cascade"]: "false",
        STOCK_AVATAR_READBACK_JSON_ENV: "",
    }
    if stock_avatar_receipt is not None:
        for key in (
            "provider", "name", "asset_path", "readback_digest",
            "model_provider", "model_id",
        ):
            stock_avatar_environment[STOCK_AVATAR_ENVIRONMENT_NAMES[key]] = str(
                stock_avatar_receipt[key]
            )
        stock_avatar_environment[
            STOCK_AVATAR_ENVIRONMENT_NAMES["allow_legacy_cascade"]
        ] = str(stock_avatar_receipt["allow_legacy_cascade"]).lower()
        stock_avatar_environment[STOCK_AVATAR_READBACK_JSON_ENV] = str(
            stock_avatar_receipt["canonical_json"]
        )
    environment.update(stock_avatar_environment)
    expectation_digest = _digest(
        _canonical(
            {
                "preferred_account_ref": preferred,
                "candidate_refs": dict(sorted(candidate_digests.items())),
                "account_selection_policy_digest": (
                    account_selection_policy["digest"]
                    if account_selection_policy is not None
                    else ""
                ),
            }
        )
    )
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "generatedAt": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "status": STATUS,
        "providerKey": "tough_tongue",
        "accountRefCount": len(account_refs),
        "accountRefsDigest": _digest(
            _canonical({"account_refs": sorted(account_refs)})
        ),
        "organizationContextCount": sum(1 for value in organization_refs if value),
        "organizationRefsDigest": (
            _digest(_canonical({"organization_refs": sorted(organization_refs)}))
            if any(organization_refs)
            else ""
        ),
        "preferredAccountRef": preferred,
        "candidateRefDigests": dict(sorted(candidate_digests.items())),
        "candidateRefCount": len(candidate_digests),
        "bindingCandidatesConfigured": binding_candidates_configured,
        "stockAvatarMigrationConfigured": stock_avatar_migration_configured,
        "stockAvatarReadbackReceiptFileDigest": (
            stock_avatar_receipt["file_digest"]
            if stock_avatar_receipt is not None else ""
        ),
        "stockAvatarReadbackReceiptDigest": (
            stock_avatar_receipt["receipt_digest"]
            if stock_avatar_receipt is not None else ""
        ),
        "stockAvatarCanonicalResponseDigest": (
            stock_avatar_receipt["response_digest"]
            if stock_avatar_receipt is not None else ""
        ),
        "stockAvatarReadbackObservedAtUtc": (
            stock_avatar_receipt["observed_at"]
            if stock_avatar_receipt is not None else ""
        ),
        "stockAvatarReadbackScenarioRefDigest": (
            stock_avatar_receipt["scenario_ref_digest"]
            if stock_avatar_receipt is not None else ""
        ),
        "stockAvatarLegacyCascadePolicyOptIn": (
            stock_avatar_receipt["allow_legacy_cascade"]
            if stock_avatar_receipt is not None else False
        ),
        "expectationDigest": expectation_digest,
        "readOnlyContractDigest": contract_digest,
        "accountSelectionPolicyDigest": (
            account_selection_policy["digest"]
            if account_selection_policy is not None
            else ""
        ),
        "accountSelectionPolicyEvidenceDigest": (
            account_selection_policy["evidence_digest"]
            if account_selection_policy is not None
            else ""
        ),
        "accountSelectionPolicySource": (
            "user_authority" if account_selection_policy is not None else ""
        ),
        "premiumBasis": PREMIUM_BASIS if account_selection_policy is not None else "",
        "premiumThresholdMinutes": (
            PREMIUM_THRESHOLD_MINUTES if account_selection_policy is not None else None
        ),
        "premiumValidityCalendarMonths": (
            PREMIUM_VALIDITY_CALENDAR_MONTHS if account_selection_policy is not None else None
        ),
        "premiumValidUntil": (
            account_selection_policy["valid_until"]
            if account_selection_policy is not None
            else ""
        ),
        "premiumGrantCount": (
            account_selection_policy["grant_count"]
            if account_selection_policy is not None
            else 0
        ),
        "premiumGrantAccountRefsDigest": (
            account_selection_policy["grant_refs_digest"]
            if account_selection_policy is not None
            else ""
        ),
        "readyForAccountSelection": account_selection_policy is not None,
        "readyForResourceBinding": False,
        "providerPlanLabelReadbackVerified": False,
        "providerReadbackVerified": False,
        "providerActivationAuthorized": False,
        "providerMutationPerformed": False,
        "rawCredentialsInReceipt": False,
        "rawCandidateRefsInReceipt": False,
        "environmentContainsCredentials": True,
        "environmentMode": "0600",
        "nextAction": (
            "attach-read-verified-grounded-custom-function-before-any-remote-execution"
            if stock_avatar_migration_configured
            else "deploy-private-account-audit-only-runtime-with-all-gates-false"
            if not binding_candidates_configured
            else "run-fresh-ea-live-ops-read-only-binding-probe"
        ),
        "evidenceDigestContract": "sha256-canonical-json-without-evidenceDigest",
    }
    receipt["evidenceDigest"] = _digest(_canonical(receipt))
    # The mounted snapshot is itself the canonical authority. Keeping the exact
    # file bytes canonical makes its full-file SHA-256 identical to the operator
    # contract digest consumed by both the runtime and the attester.
    return environment, receipt, _canonical(contract_payload)


def _open_private_output_parent(path: Path) -> int:
    _validated_absolute_path(path, "output")
    try:
        descriptor = _open_directory_chain(path.parent, "output-parent")
    except ConfigError as error:
        if str(error) == "output-parent-path-invalid":
            raise ConfigError("output-path-invalid") from error
        raise
    parent = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        os.close(descriptor)
        raise ConfigError("output-parent-authority-invalid")
    return descriptor


def _assert_output_parent_binding(path: Path, expected_fd: int) -> None:
    rebound_fd = _open_private_output_parent(path)
    try:
        expected = os.fstat(expected_fd)
        rebound = os.fstat(rebound_fd)
        if (expected.st_dev, expected.st_ino) != (rebound.st_dev, rebound.st_ino):
            raise ConfigError("output-parent-changed")
    finally:
        os.close(rebound_fd)


def _publish_new(parent_fd: int, name: str, raw: bytes, mode: int) -> None:
    if not name or "/" in name or name in {".", ".."}:
        raise ConfigError("output-name-invalid")
    temporary_flag = getattr(os, "O_TMPFILE", 0)
    if not temporary_flag:
        raise ConfigError("output-atomic-publication-unavailable")
    try:
        descriptor = os.open(
            ".",
            os.O_WRONLY
            | temporary_flag
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
    except OSError as error:
        raise ConfigError("output-atomic-publication-unavailable") from error
    try:
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise ConfigError("output-short-write")
            offset += written
        os.fsync(descriptor)
        _link_staged_file(parent_fd, descriptor, name)
        os.fsync(parent_fd)
    finally:
        os.close(descriptor)


def _link_staged_file(parent_fd: int, descriptor: int, name: str) -> None:
    """Atomically give an unnamed staged inode one non-replacing output name."""

    os.link(
        f"/proc/self/fd/{descriptor}",
        name,
        dst_dir_fd=parent_fd,
        follow_symlinks=True,
    )


def destroy_environment(
    path: Path,
    *,
    expected_parent_device: int,
    expected_parent_inode: int,
    expected_environment_digest: str | None = None,
) -> bool:
    """Zero and unlink one owned runtime env without following path links."""

    if (
        expected_parent_device < 0
        or expected_parent_inode <= 0
    ):
        raise ConfigError("environment-destroy-binding-invalid")
    if (
        expected_environment_digest is not None
        and (
            not isinstance(expected_environment_digest, str)
            or SHA256.fullmatch(expected_environment_digest) is None
        )
    ):
        raise ConfigError("environment-destroy-binding-invalid")

    parts = _validated_absolute_path(path, "environment-destroy")
    parent = Path("/").joinpath(*parts[:-1]) if len(parts) > 1 else Path("/")
    parent_fd = _open_directory_chain(parent, "environment-destroy-parent")
    descriptor = -1
    try:
        parent_metadata = os.fstat(parent_fd)
        if (
            parent_metadata.st_dev != expected_parent_device
            or parent_metadata.st_ino != expected_parent_inode
        ):
            raise ConfigError("environment-destroy-parent-changed")
        try:
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(linked.st_mode):
            raise ConfigError("environment-destroy-authority-invalid")
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDWR
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise ConfigError("environment-destroy-unavailable") from error
        opened = os.fstat(descriptor)
        if (
            _identity(opened) != _identity(linked)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or not 0 <= opened.st_size <= MAX_ENVIRONMENT_BYTES
        ):
            raise ConfigError("environment-destroy-authority-invalid")
        if expected_environment_digest is not None:
            hasher = hashlib.sha256()
            os.lseek(descriptor, 0, os.SEEK_SET)
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
            if f"sha256:{hasher.hexdigest()}" != expected_environment_digest:
                raise ConfigError("environment-destroy-digest-mismatch")
        remaining = opened.st_size
        os.lseek(descriptor, 0, os.SEEK_SET)
        zeroes = b"\0" * min(64 * 1024, max(1, remaining))
        while remaining:
            written = os.write(descriptor, zeroes[: min(len(zeroes), remaining)])
            if written <= 0:
                raise ConfigError("environment-destroy-short-write")
            remaining -= written
        os.fsync(descriptor)
        os.ftruncate(descriptor, 0)
        os.fsync(descriptor)
        rebound = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (rebound.st_dev, rebound.st_ino):
            raise ConfigError("environment-destroy-changed")
        os.unlink(parts[-1], dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def materialize(
    config_path: Path,
    environment_path: Path,
    contract_snapshot_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    output_paths = (environment_path, contract_snapshot_path, receipt_path)
    if len(set(output_paths)) != len(output_paths):
        raise ConfigError("output-paths-not-distinct")
    if len({path.parent for path in output_paths}) != 1:
        raise ConfigError("output-paths-not-same-private-directory")
    environment, receipt, contract_raw = _validated_config(
        config_path, contract_snapshot_path
    )
    environment_raw = (
        "".join(f"{name}={value}\n" for name, value in sorted(environment.items()))
    ).encode("utf-8")
    receipt["environmentFileDigest"] = _digest(environment_raw)
    receipt["readOnlyContractFileDigest"] = _digest(contract_raw)
    receipt["contractSnapshotMode"] = "0400"
    receipt["publicationOrder"] = ["contract-snapshot", "receipt", "environment"]
    parent_fd = _open_private_output_parent(environment_path)
    try:
        parent_metadata = os.fstat(parent_fd)
        receipt["outputDirectoryDevice"] = parent_metadata.st_dev
        receipt["outputDirectoryInode"] = parent_metadata.st_ino
        receipt["evidenceDigest"] = _digest(_canonical({
            key: value for key, value in receipt.items() if key != "evidenceDigest"
        }))
        receipt_raw = json.dumps(
            receipt, indent=2, ensure_ascii=True, sort_keys=True
        ).encode("utf-8") + b"\n"
        _assert_output_parent_binding(contract_snapshot_path, parent_fd)
        _publish_new(parent_fd, contract_snapshot_path.name, contract_raw, 0o400)
        _assert_output_parent_binding(receipt_path, parent_fd)
        _publish_new(parent_fd, receipt_path.name, receipt_raw, 0o600)
        # The credential-bearing file is the commit marker and is published last.
        # A killed process can leave harmless contract/receipt evidence, but never a
        # usable env file without the already-durable matching receipt.
        _assert_output_parent_binding(environment_path, parent_fd)
        _publish_new(parent_fd, environment_path.name, environment_raw, 0o600)
        _assert_output_parent_binding(environment_path, parent_fd)
    finally:
        os.close(parent_fd)
    return receipt


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a complete read-only Tough Tongue runtime config.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-env", type=Path)
    parser.add_argument("--output-contract", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--destroy-environment", type=Path)
    parser.add_argument("--expected-parent-device", type=int)
    parser.add_argument("--expected-parent-inode", type=int)
    parser.add_argument("--expected-environment-digest")
    args = parser.parse_args()
    materialize_values = (
        args.config, args.output_env, args.output_contract, args.receipt
    )
    if args.destroy_environment is not None:
        if any(value is not None for value in materialize_values):
            parser.error("--destroy-environment cannot be combined with materialization")
        if args.expected_parent_device is None or args.expected_parent_inode is None:
            parser.error(
                "--destroy-environment requires --expected-parent-device "
                "and --expected-parent-inode"
            )
    elif any(value is None for value in materialize_values):
        parser.error(
            "--config, --output-env, --output-contract, and --receipt are required"
        )
    elif any(
        value is not None
        for value in (
            args.expected_parent_device,
            args.expected_parent_inode,
            args.expected_environment_digest,
        )
    ):
        parser.error("expected cleanup bindings require --destroy-environment")
    return args


def main() -> int:
    args = _arguments()
    try:
        if args.destroy_environment is not None:
            removed = destroy_environment(
                args.destroy_environment,
                expected_parent_device=args.expected_parent_device,
                expected_parent_inode=args.expected_parent_inode,
                expected_environment_digest=args.expected_environment_digest,
            )
            print(f"tough_tongue_runtime_environment_destroyed={str(removed).lower()}")
            return 0
        receipt = materialize(
            args.config, args.output_env, args.output_contract, args.receipt
        )
    except (OSError, ConfigError) as error:
        stage = str(error) if isinstance(error, ConfigError) else "io-failed"
        print(f"tough_tongue_runtime_config=failed stage={stage}", file=sys.stderr)
        return 1
    print(
        "tough_tongue_runtime_config=materialized "
        f"status={receipt['status']} evidence_digest={receipt['evidenceDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
