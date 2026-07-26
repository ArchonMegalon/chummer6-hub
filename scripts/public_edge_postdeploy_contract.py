from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.strict_json_contract import (
        StrictJsonContractError,
        canonical_json_bytes,
        strict_json_object,
    )
except ModuleNotFoundError:
    from strict_json_contract import (
        StrictJsonContractError,
        canonical_json_bytes,
        strict_json_object,
    )

PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME = (
    "chummer.public_edge_postdeploy_gate.v1"
)
PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME = (
    "chummer.public_edge_postdeploy_gate.v2"
)
PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME = PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME
PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME = (
    "chummer.public_edge_postdeploy_gate.schema.v1"
)
PUBLIC_EDGE_POSTDEPLOY_BOUND_SCHEMA_CONTRACT_NAME = (
    "chummer.public_edge_postdeploy_gate.schema.v2"
)
PUBLIC_EDGE_POSTDEPLOY_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "public_edge_postdeploy_gate.v1.schema.json"
)
PUBLIC_EDGE_POSTDEPLOY_BOUND_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "public_edge_postdeploy_gate.v2.schema.json"
)
PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME = (
    "chummer.downloads_version_marker.bound.v1"
)
PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_CONTRACT_NAME = (
    "chummer.public_edge_downloads_authority_binding.v1"
)
PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS = frozenset(
    {
        "bindingSha256",
        "contractName",
        "downloadsReceiptContractName",
        "downloadsReceiptSha256",
        "releaseChannel",
        "releaseChannelReceiptSha256",
        "releaseManifestChannel",
        "releaseManifestGeneration",
        "releaseManifestSchema",
        "releaseManifestVersion",
        "releaseVersion",
    }
)
PUBLIC_EDGE_DOWNLOADS_AUTHORITY_IDENTITY_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}"
)
PUBLIC_EDGE_OFFLINE_STATIC_PATHS = {
    "/manifest.player.webmanifest",
    "/manifest.gm.webmanifest",
    "/mobile.css",
    "/mobile-turn-companion.js",
}
PUBLIC_EDGE_LEGACY_PRIVATE_CACHE_PREFIXES = {
    "chummer-shell-play-shell-",
    "chummer-media-play-shell-",
    "chummer-media-meta-play-shell-",
}
PUBLIC_EDGE_V2_ARTIFACT_CONTRACTS = {
    "pwaOfflineCacheArtifactContract": "chummer.pwa_offline_cache.v2",
    "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_install_boundary.v2",
    "frontdoorNavigationAnchorArtifactContract": "chummer.frontdoor_mobile_anchor_redirect.v2",
}
PUBLIC_EDGE_SECRET_KEY_STEMS = (
    "accesskey",
    "accountkey",
    "apikey",
    "authorization",
    "bearertoken",
    "clientsecret",
    "connstr",
    "connectionstring",
    "connectionuri",
    "connectionurl",
    "credential",
    "databaseurl",
    "dsn",
    "password",
    "passwd",
    "privatekey",
    "pwd",
    "secret",
    "sharedaccesssignature",
    "token",
)
PUBLIC_EDGE_SECRET_KEY_SHORT_WORDS = frozenset(
    {
        "connstr",
        "dsn",
        "dsns",
        "pwd",
        "pwds",
        "sas",
    }
)
PUBLIC_EDGE_SAFE_SECRET_BOOLEAN_SUFFIXES = frozenset(
    {
        "absent",
        "configured",
        "exposed",
        "leaked",
        "matches",
        "performed",
        "present",
        "redacted",
        "required",
        "stored",
        "valid",
    }
)
PUBLIC_EDGE_SAFE_SECRET_INTEGER_SUFFIXES = frozenset(
    {
        "count",
        "device",
        "inode",
        "mtimens",
    }
)
PUBLIC_EDGE_SAFE_SECRET_DIGEST_SUFFIXES = frozenset(
    {
        "digest",
        "hash",
        "sha256",
    }
)
_PRIVATE_IDENTITY_KEYS = {"sessionid", "deviceid"}
_PRIVATE_IDENTITY_ASSIGNMENT = re.compile(
    r"(?i)((?:[?&]|\b)(?:sessionId|deviceId)[\"']?\s*[:=]\s*[\"']?)([^&#,}\s\"']*)"
)
PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS = {
    "coreChildContracts",
    "preflightStatus",
    "preflightBlockingLockCount",
    "preflightStaleForeignLockCount",
    "preflightStaleForeignLocksIgnored",
    "preflightOverlayRoot",
    "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource",
    "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256",
    "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256",
    "preflightOverlayBuildInfoSourceFingerprintMissingKeys",
    "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys",
    "downloadsStatus",
    "downloadsHasMarker",
    "statusRedirectHasMarker",
    "statusRedirectHeading",
    "statusRedirectHeadingRecognized",
    "statusRedirectHeadingExpected",
    "statusRedirectHeadingMatchesReleaseChannel",
    "statusRedirectHeadingUsesGenericUpdatedCopy",
    "visibleVersion",
    "statusRedirectVersion",
    "expectedReleaseVersion",
    "visibleVersionMatchesReleaseChannel",
    "statusRedirectVersionMatchesReleaseChannel",
    "expectedReleaseStatus",
    "expectedReleaseChannel",
    "expectedReleaseSupportabilityState",
    "expectedReleaseRolloutState",
    "releaseManifestHttpStatus",
    "releaseManifestStatus",
    "releaseManifestStatusMatchesReleaseChannel",
    "releaseManifestChannel",
    "releaseManifestChannelMatchesReleaseChannel",
    "releaseManifestVersion",
    "releaseManifestVersionMatchesReleaseChannel",
    "releaseManifestSupportabilityState",
    "releaseManifestSupportabilityMatchesReleaseChannel",
    "releaseManifestRolloutState",
    "releaseManifestRolloutMatchesReleaseChannel",
    "pwaStaticStatus",
    "pwaManifestCount",
    "rolePwaManifestCount",
    "rolePwaManifests",
    "pwaAssetCount",
    "ledgerStreamNonCacheable",
    "ledgerStreamPrecached",
    "mobileLedgerStatus",
    "mobileLedgerPayloadStatus",
    "mobileLedgerCacheControl",
    "mobileLedgerVary",
    "readyMobileHandoffStatus",
    "readyMobileHandoffToolIds",
    "readyMobileHandoffPacketRoles",
    "readyMobileHandoffFrontdoorLaunchRoute",
    "readyMobileHandoffRoleRoutes",
    "downloadsStatusBrowserStatus",
    "downloadsStatusBrowserArtifactContract",
    "mobilePwaViewportStatus",
    "mobilePwaViewportArtifactContract",
    "mobilePwaViewportRouteCount",
    "mobilePwaViewportViewportCount",
    "mobilePwaViewportRoutes",
    "mobilePwaViewportMissingRoutes",
    "pwaOfflineCacheStatus",
    "pwaOfflineCacheArtifactContract",
    "pwaOfflineCacheCacheVersion",
    "pwaOfflineCacheNavigationPolicy",
    "pwaOfflineCachePrivateStateScope",
    "pwaOfflineCacheStaticPaths",
    "pwaOfflineCacheOfflineRoleFallbacks",
    "pwaOfflineCacheQueryBearingRequestsCached",
    "pwaOfflineCachePrivateNavigationCached",
    "pwaOfflineCachePrivateApiCached",
    "pwaOfflineCachePersonalizedLedgerCached",
    "pwaOfflineCacheLegacyPrivateCachePrefixesPurged",
    "pwaOfflineCacheUnrelatedCachePreserved",
    "roleAliasRouteStatus",
    "roleAliasRouteContract",
    "roleAliasRouteResults",
    "roleAliasRouteDrift",
    "participateIframeShellStatus",
    "participateIframeRouteCount",
    "participateIframeRouteIframeCount",
    "participateIframeRouteOfflineFallbackCount",
    "frontdoorNavigationStatus",
    "frontdoorNavigationMobileArtifactContract",
    "frontdoorNavigationLedgerArtifactContract",
    "frontdoorNavigationAnchorArtifactContract",
    "frontdoorNavigationGatedTargets",
    "frontdoorNavigationPublicTargets",
    "frontdoorNavigationPlayRoute",
    "frontdoorNavigationDirectPlayerRoute",
    "frontdoorNavigationDirectPlayerHttpStatus",
    "frontdoorNavigationFinalUrl",
    "frontdoorNavigationPrivateIdentityRedacted",
    "frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent",
    "frontdoorNavigationPlayerSessionContextPresent",
    "frontdoorNavigationPlayerDeviceContextPresent",
    "frontdoorNavigationLiveTurnCompanionShell",
    "frontdoorNavigationPwaManifestPath",
    "frontdoorNavigationPwaRole",
    "frontdoorNavigationBlazorShell",
    "frontdoorNavigationRybbitConfigured",
    "frontdoorNavigationRybbitTag",
    "frontdoorNavigationRybbitRoute",
    "frontdoorNavigationRybbitMode",
    "frontdoorNavigationRybbitRole",
    "frontdoorNavigationRybbitSiteIdPresent",
    "frontdoorNavigationRybbitScriptUrlPresent",
    "frontdoorNavigationRybbitScriptUrlAllowed",
    "frontdoorNavigationRybbitSkipPatterns",
    "frontdoorNavigationRybbitMaskPatterns",
    "frontdoorNavigationRybbitSkipMobilePaths",
    "frontdoorNavigationRybbitMaskMobilePaths",
    "frontdoorNavigationRybbitMasksPrivatePlayRoutes",
    "frontdoorNavigationRybbitReplayBlockSelector",
    "frontdoorNavigationRybbitReplayBlocksTurnRoot",
    "frontdoorNavigationPlayerSessionHandoffUrl",
    "frontdoorNavigationPlayerSessionHandoffStatus",
    "frontdoorNavigationPlayerSessionHandoffLinkText",
    "frontdoorNavigationPlayerSessionHandoffPreservesSession",
    "frontdoorNavigationPlayerSessionHandoffPreservesRole",
    "frontdoorNavigationPlayerSessionHandoffStripsDevice",
    "frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent",
    "frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted",
    "frontdoorNavigationGmRoute",
    "frontdoorNavigationGmRouteSessionIdPresent",
    "frontdoorNavigationGmRoutePrivateIdentityRedacted",
    "frontdoorNavigationGmHttpStatus",
    "frontdoorNavigationGmFinalUrl",
    "frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent",
    "frontdoorNavigationGmSessionContextPresent",
    "frontdoorNavigationGmDeviceContextPresent",
    "frontdoorNavigationGmLiveTurnCompanionShell",
    "frontdoorNavigationGmPwaManifestPath",
    "frontdoorNavigationGmPwaRole",
    "frontdoorNavigationGmBlazorShell",
    "frontdoorNavigationGmRybbitConfigured",
    "frontdoorNavigationGmRybbitTag",
    "frontdoorNavigationGmRybbitRoute",
    "frontdoorNavigationGmRybbitMode",
    "frontdoorNavigationGmRybbitRole",
    "frontdoorNavigationGmRybbitSiteIdPresent",
    "frontdoorNavigationGmRybbitScriptUrlPresent",
    "frontdoorNavigationGmRybbitScriptUrlAllowed",
    "frontdoorNavigationGmRybbitSkipPatterns",
    "frontdoorNavigationGmRybbitMaskPatterns",
    "frontdoorNavigationGmRybbitSkipMobilePaths",
    "frontdoorNavigationGmRybbitMaskMobilePaths",
    "frontdoorNavigationGmRybbitMasksPrivatePlayRoutes",
    "frontdoorNavigationGmRybbitReplayBlockSelector",
    "frontdoorNavigationGmRybbitReplayBlocksTurnRoot",
    "frontdoorNavigationGmSessionHandoffUrl",
    "frontdoorNavigationGmSessionHandoffStatus",
    "frontdoorNavigationGmSessionHandoffLinkText",
    "frontdoorNavigationGmSessionHandoffPreservesSession",
    "frontdoorNavigationGmSessionHandoffPreservesRole",
    "frontdoorNavigationGmSessionHandoffStripsDevice",
    "frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent",
    "frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted",
    "frontdoorNavigationLedgerPrimary",
    "frontdoorNavigationAnchorEntryUrl",
    "frontdoorNavigationAnchorFinalUrl",
    "frontdoorNavigationAnchorFinalPath",
    "frontdoorNavigationAnchorFinalHash",
    "frontdoorNavigationAnchorPwaManifestPath",
    "frontdoorNavigationAnchorPwaRole",
    "frontdoorNavigationAnchorBlazorShell",
    "frontdoorNavigationAnchorPrivateIdentityRedacted",
    "frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent",
    "frontdoorNavigationAnchorSessionContextPresent",
    "frontdoorNavigationAnchorDeviceContextPresent",
    "frontdoorNavigationAnchorFailure",
}


def load_exact_public_edge_postdeploy_schema(
    path: Path | None = None,
    *,
    receipt_contract_name: str = PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME,
) -> dict[str, Any]:
    if receipt_contract_name == PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME:
        expected_schema_contract_name = (
            PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME
        )
        expected_schema_path = PUBLIC_EDGE_POSTDEPLOY_SCHEMA_PATH
        expected_schema_id = (
            "urn:chummer:public-edge-postdeploy-gate:schema:v1"
        )
    elif receipt_contract_name == PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME:
        expected_schema_contract_name = (
            PUBLIC_EDGE_POSTDEPLOY_BOUND_SCHEMA_CONTRACT_NAME
        )
        expected_schema_path = PUBLIC_EDGE_POSTDEPLOY_BOUND_SCHEMA_PATH
        expected_schema_id = (
            "urn:chummer:public-edge-postdeploy-gate:schema:v2"
        )
    else:
        raise RuntimeError(
            "public-edge postdeploy receipt contract is unsupported"
        )
    if path is None:
        path = expected_schema_path
    normalized = Path(os.path.abspath(path))
    if path != normalized or not path.is_absolute():
        raise RuntimeError(
            "public-edge postdeploy schema path is not exact and absolute"
        )
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > 1024 * 1024
    ):
        raise RuntimeError(
            "public-edge postdeploy schema is not a safe regular file"
        )
    descriptor = os.open(
        normalized,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 1024 * 1024:
                raise RuntimeError(
                    "public-edge postdeploy schema is oversized"
                )
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = normalized.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        or identity
        != (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
            path_after.st_mtime_ns,
            path_after.st_ctime_ns,
            path_after.st_nlink,
        )
        or total != before.st_size
    ):
        raise RuntimeError(
            "public-edge postdeploy schema changed while being read"
        )
    raw = b"".join(chunks)
    try:
        schema = strict_json_object(
            raw,
            label="public-edge postdeploy schema",
        )
        canonical = canonical_json_bytes(
            schema,
            label="public-edge postdeploy schema",
        )
    except StrictJsonContractError as exc:
        raise RuntimeError(
            "public-edge postdeploy schema is not strict canonical JSON"
        ) from exc
    if raw != canonical:
        raise RuntimeError(
            "public-edge postdeploy schema is not strict canonical JSON"
        )
    expected_top_level_keys = {
        "$id",
        "$schema",
        "additionalProperties",
        "maxProperties",
        "minProperties",
        "patternProperties",
        "properties",
        "propertyNames",
        "type",
        "x-chummer-receipt-contract",
        "x-chummer-schema-contract",
    }
    property_names = schema.get("propertyNames")
    fields = (
        property_names.get("enum")
        if isinstance(property_names, dict)
        else None
    )
    expected_properties = {
        "childReceipts": {
            "additionalProperties": False,
            "maxProperties": 0,
            "type": "object",
        },
        "contractName": {
            "const": receipt_contract_name,
        },
        "schemaContractName": {
            "const": expected_schema_contract_name,
        },
        "schemaSha256": {
            "pattern": "^[0-9a-f]{64}$",
            "type": "string",
        },
        "status": {"enum": ["fail", "pass"]},
    }
    if receipt_contract_name == PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME:
        expected_properties.update(
            {
                "downloadsAuthorityBinding": {
                    "additionalProperties": False,
                    "maxProperties": len(
                        PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS
                    ),
                    "minProperties": len(
                        PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS
                    ),
                    "propertyNames": {
                        "enum": sorted(
                            PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS
                        )
                    },
                    "type": "object",
                },
                "releaseChannelAuthorizationCapable": {"const": True},
                "releaseChannelReceiptBindingRequired": {"const": True},
            }
        )
    if (
        set(schema) != expected_top_level_keys
        or schema.get("$id")
        != expected_schema_id
        or schema.get("$schema")
        != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or schema.get("patternProperties")
        != {"^[A-Za-z][A-Za-z0-9]*$": {}}
        or schema.get("properties") != expected_properties
        or schema.get("x-chummer-receipt-contract")
        != receipt_contract_name
        or schema.get("x-chummer-schema-contract")
        != expected_schema_contract_name
        or not isinstance(fields, list)
        or not fields
        or fields != sorted(fields)
        or len(fields) != len(set(fields))
        or any(
            not isinstance(field, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", field) is None
            for field in fields
        )
        or schema.get("minProperties") != len(fields)
        or schema.get("maxProperties") != len(fields)
        or not {
            "contractName",
            "failures",
            "generatedAtUtc",
            "schemaContractName",
            "schemaSha256",
            "status",
        }.issubset(fields)
    ):
        raise RuntimeError(
            "public-edge postdeploy schema contract is invalid"
        )
    return {
        "contractName": expected_schema_contract_name,
        "fields": frozenset(fields),
        "path": normalized,
        "receiptContractName": receipt_contract_name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _lower_sha256(value: Any) -> str:
    normalized = str(value or "").strip()
    return (
        normalized
        if re.fullmatch(r"[0-9a-f]{64}", normalized) is not None
        else ""
    )


def _required_binding_text(
    payload: dict[str, Any],
    field: str,
) -> str:
    value = str(payload.get(field) or "").strip()
    if (
        not value
        or PUBLIC_EDGE_DOWNLOADS_AUTHORITY_IDENTITY_PATTERN.fullmatch(
            value
        )
        is None
    ):
        raise ValueError(
            f"downloads authority binding {field} is not a safe release identity"
        )
    return value


def build_public_edge_downloads_authority_binding(
    downloads_receipt: dict[str, Any],
    *,
    downloads_receipt_sha256: str,
    release_channel_receipt_sha256: str,
) -> dict[str, str]:
    """Build the only public child-authority summary.

    The raw child receipt stays private. The public receipt carries only exact
    receipt digests plus the non-secret release identity needed to validate
    that the selected channel and served manifest are the same authority.
    """

    if (
        str(downloads_receipt.get("contractName") or "").strip()
        != PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME
    ):
        raise ValueError(
            "downloads authority binding requires the bound downloads contract"
        )
    if str(downloads_receipt.get("status") or "").strip().lower() != "pass":
        raise ValueError(
            "downloads authority binding requires a passing downloads receipt"
        )
    child_digest = _lower_sha256(downloads_receipt_sha256)
    channel_digest = _lower_sha256(release_channel_receipt_sha256)
    if not child_digest:
        raise ValueError(
            "downloads authority binding receipt digest is invalid"
        )
    if not channel_digest:
        raise ValueError(
            "downloads authority binding release-channel digest is invalid"
        )
    if (
        _lower_sha256(
            downloads_receipt.get(
                "release_channel_receipt_sha256_expected"
            )
        )
        != channel_digest
        or _lower_sha256(
            downloads_receipt.get(
                "release_channel_receipt_sha256_actual"
            )
        )
        != channel_digest
        or downloads_receipt.get(
            "release_channel_receipt_sha256_matches"
        )
        is not True
        or str(
            downloads_receipt.get(
                "release_channel_receipt_binding_status"
            )
            or ""
        ).strip()
        != "pass"
    ):
        raise ValueError(
            "downloads authority binding does not match the selected release channel"
        )
    release_version = _required_binding_text(
        downloads_receipt,
        "release_channel_version",
    )
    release_channel = _required_binding_text(
        downloads_receipt,
        "expected_release_channel",
    )
    release_manifest_schema = _required_binding_text(
        downloads_receipt,
        "release_manifest_schema",
    )
    release_manifest_version = _required_binding_text(
        downloads_receipt,
        "release_manifest_version",
    )
    release_manifest_channel = _required_binding_text(
        downloads_receipt,
        "release_manifest_channel",
    )
    release_manifest_generation = _required_binding_text(
        downloads_receipt,
        "release_manifest_generation",
    )
    if (
        downloads_receipt.get(
            "release_manifest_version_matches_release_channel"
        )
        is not True
        or downloads_receipt.get(
            "release_manifest_channel_matches_release_channel"
        )
        is not True
        or downloads_receipt.get(
            "downloads_generation_matches_served_manifest"
        )
        is not True
        or downloads_receipt.get(
            "status_redirect_generation_matches_served_manifest"
        )
        is not True
        or release_manifest_version != release_version
        or release_manifest_channel != release_channel
    ):
        raise ValueError(
            "downloads authority binding release identity is inconsistent"
        )
    body = {
        "contractName": (
            PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_CONTRACT_NAME
        ),
        "downloadsReceiptContractName": (
            PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME
        ),
        "downloadsReceiptSha256": child_digest,
        "releaseChannel": release_channel,
        "releaseChannelReceiptSha256": channel_digest,
        "releaseManifestChannel": release_manifest_channel,
        "releaseManifestGeneration": release_manifest_generation,
        "releaseManifestSchema": release_manifest_schema,
        "releaseManifestVersion": release_manifest_version,
        "releaseVersion": release_version,
    }
    body["bindingSha256"] = hashlib.sha256(
        canonical_json_bytes(
            body,
            label="public-edge downloads authority binding",
        )
    ).hexdigest()
    return body


def public_edge_postdeploy_schema_failures(
    payload: dict[str, Any],
    *,
    receipt_contract_name: str,
) -> list[str]:
    failures: list[str] = []
    try:
        schema = load_exact_public_edge_postdeploy_schema(
            receipt_contract_name=receipt_contract_name,
        )
    except (OSError, RuntimeError):
        return [
            "public-edge postdeploy local schema authority is invalid"
        ]
    if str(payload.get("contractName") or "").strip() != receipt_contract_name:
        failures.append(
            "public-edge postdeploy receipt contract does not match schema authority"
        )
    if (
        str(payload.get("schemaContractName") or "").strip()
        != schema["contractName"]
    ):
        failures.append(
            "public-edge postdeploy schema contract does not match local authority"
        )
    if _lower_sha256(payload.get("schemaSha256")) != schema["sha256"]:
        failures.append(
            "public-edge postdeploy schema digest does not match local authority"
        )
    actual_fields = set(payload)
    expected_fields = set(schema["fields"])
    if actual_fields != expected_fields:
        if expected_fields - actual_fields:
            failures.append(
                "public-edge postdeploy receipt is missing schema fields"
            )
        if actual_fields - expected_fields:
            failures.append(
                "public-edge postdeploy receipt contains fields outside the schema"
            )
    if payload.get("childReceipts") != {}:
        failures.append(
            "public-edge postdeploy public childReceipts must be empty"
        )
    return failures


def public_edge_authorizing_binding_failures(
    payload: dict[str, Any],
    *,
    expected_release_channel_sha256: str = "",
    current_release_channel_sha256: str = "",
) -> list[str]:
    """Validate the shared fail-closed v2 authority contract."""

    failures = public_edge_postdeploy_schema_failures(
        payload,
        receipt_contract_name=PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME,
    )
    if payload.get("releaseChannelAuthorizationCapable") is not True:
        failures.append(
            "public-edge postdeploy receipt is not release-channel authorization capable"
        )
    if payload.get("releaseChannelReceiptBindingRequired") is not True:
        failures.append(
            "public-edge postdeploy receipt does not require channel binding"
        )
    core_contracts = (
        payload.get("coreChildContracts")
        if isinstance(payload.get("coreChildContracts"), dict)
        else {}
    )
    if (
        str(core_contracts.get("downloads") or "").strip()
        != PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME
    ):
        failures.append(
            "public-edge postdeploy downloads child is not the bound contract"
        )
    binding = (
        payload.get("downloadsAuthorityBinding")
        if isinstance(payload.get("downloadsAuthorityBinding"), dict)
        else {}
    )
    if set(binding) != PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS:
        failures.append(
            "public-edge postdeploy downloads authority binding schema is invalid"
        )
        return list(dict.fromkeys(failures))
    if (
        str(binding.get("contractName") or "").strip()
        != PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_CONTRACT_NAME
        or str(binding.get("downloadsReceiptContractName") or "").strip()
        != PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME
    ):
        failures.append(
            "public-edge postdeploy downloads authority binding contract is invalid"
        )
    for field in (
        "bindingSha256",
        "downloadsReceiptSha256",
        "releaseChannelReceiptSha256",
    ):
        if not _lower_sha256(binding.get(field)):
            failures.append(
                "public-edge postdeploy downloads authority binding digest is invalid"
            )
            break
    for field in (
        "releaseChannel",
        "releaseManifestChannel",
        "releaseManifestGeneration",
        "releaseManifestSchema",
        "releaseManifestVersion",
        "releaseVersion",
    ):
        if (
            PUBLIC_EDGE_DOWNLOADS_AUTHORITY_IDENTITY_PATTERN.fullmatch(
                str(binding.get(field) or "").strip()
            )
            is None
        ):
            failures.append(
                "public-edge postdeploy downloads authority binding release identity is unsafe"
            )
            break
    binding_body = {
        key: value
        for key, value in binding.items()
        if key != "bindingSha256"
    }
    try:
        expected_binding_digest = hashlib.sha256(
            canonical_json_bytes(
                binding_body,
                label="public-edge downloads authority binding",
            )
        ).hexdigest()
    except StrictJsonContractError:
        expected_binding_digest = ""
        failures.append(
            "public-edge postdeploy downloads authority binding encoding is invalid"
        )
    if (
        not expected_binding_digest
        or _lower_sha256(binding.get("bindingSha256"))
        != expected_binding_digest
    ):
        failures.append(
            "public-edge postdeploy downloads authority binding digest mismatches"
        )
    expected_digest = _lower_sha256(expected_release_channel_sha256)
    current_digest = _lower_sha256(current_release_channel_sha256)
    bound_digest = _lower_sha256(
        binding.get("releaseChannelReceiptSha256")
    )
    if expected_release_channel_sha256 and not expected_digest:
        failures.append(
            "public-edge postdeploy expected release-channel digest is invalid"
        )
    if current_release_channel_sha256 and not current_digest:
        failures.append(
            "public-edge postdeploy current release-channel digest is invalid"
        )
    if expected_digest and bound_digest != expected_digest:
        failures.append(
            "public-edge postdeploy release-channel binding mismatches expected authority"
        )
    if current_digest and bound_digest != current_digest:
        failures.append(
            "public-edge postdeploy release-channel binding is stale"
        )
    identity_fields = (
        ("releaseVersion", "expectedReleaseVersion"),
        ("releaseChannel", "expectedReleaseChannel"),
        ("releaseManifestSchema", "releaseManifestSchema"),
        ("releaseManifestVersion", "releaseManifestVersion"),
        ("releaseManifestChannel", "releaseManifestChannel"),
        ("releaseManifestGeneration", "releaseManifestGeneration"),
    )
    for binding_field, payload_field in identity_fields:
        binding_value = str(binding.get(binding_field) or "").strip()
        payload_value = str(payload.get(payload_field) or "").strip()
        if not binding_value or binding_value != payload_value:
            failures.append(
                "public-edge postdeploy release identity does not match its authority binding"
            )
            break
    if (
        str(binding.get("releaseManifestVersion") or "").strip()
        != str(binding.get("releaseVersion") or "").strip()
        or str(binding.get("releaseManifestChannel") or "").strip()
        != str(binding.get("releaseChannel") or "").strip()
    ):
        failures.append(
            "public-edge postdeploy manifest identity contradicts the selected release"
        )
    return list(dict.fromkeys(failures))


def public_edge_receipt_key_parts(value: Any) -> tuple[str, ...]:
    words = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        str(value),
    )
    words = re.sub(r"[^A-Za-z0-9]+", "_", words).strip("_").lower()
    return tuple(part for part in words.split("_") if part)


def public_edge_secret_like_key(value: Any) -> bool:
    parts = public_edge_receipt_key_parts(value)
    if not parts:
        return False
    collapsed = "".join(parts)
    return bool(
        any(stem in collapsed for stem in PUBLIC_EDGE_SECRET_KEY_STEMS)
        or any(part in PUBLIC_EDGE_SECRET_KEY_SHORT_WORDS for part in parts)
    )


def public_edge_safe_secret_metadata_value(key: Any, value: Any) -> bool:
    parts = public_edge_receipt_key_parts(key)
    if not parts or not public_edge_secret_like_key(key):
        return False
    suffix = parts[-1]
    if suffix in PUBLIC_EDGE_SAFE_SECRET_BOOLEAN_SUFFIXES:
        return type(value) is bool
    if suffix in PUBLIC_EDGE_SAFE_SECRET_INTEGER_SUFFIXES:
        return type(value) is int and value >= 0
    if suffix in PUBLIC_EDGE_SAFE_SECRET_DIGEST_SUFFIXES:
        return bool(
            isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        )
    if str(key).startswith("/run/chummer-secrets/"):
        return bool(
            isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        )
    return False


def public_edge_forbidden_secret_key(key: Any, value: Any) -> bool:
    return bool(
        public_edge_secret_like_key(key)
        and not public_edge_safe_secret_metadata_value(key, value)
    )


def receipt_contract(payload: dict[str, Any]) -> str:
    return str(payload.get("contractName") or payload.get("contract_name") or "").strip()


def release_channel_trust_invariant_failures(payload: dict[str, Any]) -> list[str]:
    """Validate canonical supportability, proof freshness, and public posture as one truth."""

    def token(value: Any) -> str:
        return str(value or "").strip().lower()

    public_trust = (
        payload.get("publicTrustMetrics")
        if isinstance(payload.get("publicTrustMetrics"), dict)
        else {}
    )
    public_release = (
        public_trust.get("releaseChannel")
        if isinstance(public_trust.get("releaseChannel"), dict)
        else {}
    )
    proof_freshness = (
        public_trust.get("proofFreshness")
        if isinstance(public_trust.get("proofFreshness"), dict)
        else {}
    )
    registry_coverage = (
        payload.get("registryBoundaryCoverage")
        if isinstance(payload.get("registryBoundaryCoverage"), dict)
        else {}
    )
    registry_release = (
        registry_coverage.get("releaseChannel")
        if isinstance(registry_coverage.get("releaseChannel"), dict)
        else {}
    )
    status = token(payload.get("status"))
    rollout = token(payload.get("rolloutState"))
    top_supportability = token(payload.get("supportabilityState"))
    trust_contract_required = bool(
        top_supportability == "gold_supported"
        or rollout == "public_stable"
        or public_trust
        or registry_coverage
    )
    if not trust_contract_required:
        return []

    failures: list[str] = []
    freshness = token(proof_freshness.get("status"))
    if freshness not in {"fresh", "stale", "missing"}:
        failures.append(
            "release channel proof freshness is missing or unrecognized"
        )

    public_supportability = token(public_release.get("supportabilityState"))
    registry_supportability = token(registry_release.get("supportabilityState"))
    for label, value in (
        ("public trust", public_supportability),
        ("registry boundary", registry_supportability),
    ):
        if not value:
            failures.append(f"release channel {label} supportability is missing")
        elif value != top_supportability:
            failures.append(
                "release channel supportability contradicts "
                f"{label} supportability ({top_supportability or 'missing'} != {value})"
            )

    if freshness in {"stale", "missing"}:
        for label, value in (
            ("top-level", top_supportability),
            ("public trust", public_supportability),
            ("registry boundary", registry_supportability),
        ):
            if value != "review_required":
                failures.append(
                    f"release channel {label} supportability must be review_required when proof freshness is {freshness}"
                )

    expected_posture = "blocked"
    if freshness == "fresh" and status == "published":
        expected_posture = "live" if rollout == "public_stable" else "preview"
    if status == "revoked" or rollout == "revoked":
        expected_posture = "revoked"
    public_posture = token(public_release.get("posture"))
    registry_posture = token(registry_release.get("publicTrustPosture"))
    for label, value in (
        ("public trust", public_posture),
        ("registry boundary", registry_posture),
    ):
        if not value:
            failures.append(f"release channel {label} posture is missing")
        elif value != expected_posture:
            failures.append(
                f"release channel {label} posture is {value}, expected {expected_posture}"
            )
    if public_posture and registry_posture and public_posture != registry_posture:
        failures.append("release channel public trust posture contradicts registry boundary posture")

    if (top_supportability == "gold_supported" or rollout == "public_stable") and freshness != "fresh":
        failures.append("release channel flagship stable posture requires fresh proof receipts")

    return list(dict.fromkeys(failures))


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _redact_private_identity(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            redacted[key] = "[redacted]" if normalized_key in _PRIVATE_IDENTITY_KEYS and item not in (None, "") else _redact_private_identity(item)
        return redacted
    if isinstance(value, list):
        return [_redact_private_identity(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_private_identity(item) for item in value)
    if isinstance(value, str):
        def replacement(match: re.Match[str]) -> str:
            private_value = match.group(2).strip().lower()
            if private_value in {"[redacted]", "%5bredacted%5d"} or private_value.startswith(("{sessionid", "{deviceid")):
                return match.group(0)
            return match.group(1) + "[redacted]"

        return _PRIVATE_IDENTITY_ASSIGNMENT.sub(replacement, value)
    return value


def _private_value_is_safe(value: Any) -> bool:
    text = unquote(str(value or "")).strip().lower()
    return text in {"", "[redacted]"} or text.startswith(("{sessionid", "{deviceid"))


def _contains_raw_private_identity(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized_key in _PRIVATE_IDENTITY_KEYS and not _private_value_is_safe(item):
                return True
            if _contains_raw_private_identity(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_raw_private_identity(item) for item in value)
    if not isinstance(value, str):
        return False
    return any(not _private_value_is_safe(match.group(2)) for match in _PRIVATE_IDENTITY_ASSIGNMENT.finditer(value))


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _safe_visible_url(value: Any, expected_path: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    decoded = unquote(text).lower()
    parsed = urlparse(text)
    return (
        parsed.path == expected_path
        and not parsed.query
        and "sessionid" not in decoded
        and "deviceid" not in decoded
    )


def _safe_redacted_handoff(value: Any, expected_path: str, expected_role: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    query_items = [(key.lower(), item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)]
    query = dict(query_items)
    decoded_fragment = unquote(parsed.fragment).lower()
    return (
        parsed.path == expected_path
        and len(query_items) == 2
        and set(query) == {"sessionid", "role"}
        and query.get("sessionid") == "[redacted]"
        and query.get("role") == expected_role
        and "deviceid" not in unquote(text).lower()
        and "sessionid" not in decoded_fragment
        and "deviceid" not in decoded_fragment
    )


def public_edge_v2_offline_failures(payload: dict[str, Any]) -> list[str]:
    """Validate the v2 offline proof without treating missing/not-run evidence as a pass."""
    if str(payload.get("pwaOfflineCacheStatus") or "").strip().lower() != "pass":
        return []

    failures: list[str] = []
    if str(payload.get("pwaOfflineCacheCacheVersion") or "").strip() != "v17":
        failures.append("public-edge postdeploy PWA offline cache version is not v17")
    if str(payload.get("pwaOfflineCacheNavigationPolicy") or "").strip() != "network_only":
        failures.append("public-edge postdeploy PWA offline navigation policy is not network_only")
    if str(payload.get("pwaOfflineCachePrivateStateScope") or "").strip() != "open_tab_only":
        failures.append("public-edge postdeploy PWA private state scope is not open_tab_only")

    static_paths = _string_set(payload.get("pwaOfflineCacheStaticPaths"))
    for path in sorted(PUBLIC_EDGE_OFFLINE_STATIC_PATHS - static_paths):
        failures.append(f"public-edge postdeploy PWA offline static cache is missing {path}")
    for path in sorted(static_paths):
        parsed = urlparse(path)
        if (
            parsed.scheme
            or parsed.netloc
            or not parsed.path.startswith("/")
            or parsed.query
            or parsed.fragment
            or parsed.path in {"/mobile/player", "/mobile/gm"}
            or parsed.path.startswith("/api/")
            or "ledger" in parsed.path.lower()
        ):
            failures.append("public-edge postdeploy PWA offline static cache contains a private or query-bearing route")
            break

    for field, label in (
        ("pwaOfflineCacheQueryBearingRequestsCached", "query-bearing requests"),
        ("pwaOfflineCachePrivateNavigationCached", "private navigation"),
        ("pwaOfflineCachePrivateApiCached", "private API responses"),
        ("pwaOfflineCachePersonalizedLedgerCached", "the personalized ledger stream"),
    ):
        if payload.get(field) is not False:
            failures.append(f"public-edge postdeploy PWA offline cache did not prove {label} remain uncached")

    purged = _string_set(payload.get("pwaOfflineCacheLegacyPrivateCachePrefixesPurged"))
    if not PUBLIC_EDGE_LEGACY_PRIVATE_CACHE_PREFIXES.issubset(purged):
        failures.append("public-edge postdeploy PWA offline cache did not prove all legacy private cache prefixes were purged")
    if payload.get("pwaOfflineCacheUnrelatedCachePreserved") is not True:
        failures.append("public-edge postdeploy PWA offline cache did not prove unrelated caches were preserved")

    fallbacks = payload.get("pwaOfflineCacheOfflineRoleFallbacks")
    fallbacks_by_role = {
        str(item.get("role") or "").strip(): item
        for item in fallbacks
        if isinstance(item, dict)
    } if isinstance(fallbacks, list) else {}
    if set(fallbacks_by_role) != {"Player", "GameMaster"}:
        failures.append("public-edge postdeploy PWA offline cache role fallback set is not exactly Player and GameMaster")
    for role, path in (("Player", "/mobile/player"), ("GameMaster", "/mobile/gm")):
        fallback = fallbacks_by_role.get(role)
        if not fallback:
            failures.append(f"public-edge postdeploy PWA offline cache is missing the {role} no-store fallback")
            continue
        cache_control = {
            token.strip().lower()
            for token in str(fallback.get("cache_control") or "").split(",")
            if token.strip()
        }
        if (
            str(fallback.get("path") or "").strip() != path
            or fallback.get("status") != 503
            or not {"private", "no-store"}.issubset(cache_control)
            or fallback.get("private_projection_restored") is not False
        ):
            failures.append(f"public-edge postdeploy PWA offline {role} fallback is not an HTTP 503 private no-store shell")
    return failures


def public_edge_v2_private_identity_failures(payload: dict[str, Any]) -> list[str]:
    """Validate that v2 frontdoor evidence proves context without serializing identity."""
    if str(payload.get("frontdoorNavigationStatus") or "").strip().lower() != "pass":
        return []

    failures: list[str] = []
    if payload.get("privateIdentityWasRaw") is True or _contains_raw_private_identity(payload):
        failures.append("public-edge postdeploy front-door evidence contains raw private identity")
    if not _safe_visible_url(payload.get("frontdoorNavigationFinalUrl"), "/mobile/player"):
        failures.append("public-edge postdeploy front-door visible Player URL is not query-free /mobile/player")
    if not _safe_visible_url(payload.get("frontdoorNavigationGmFinalUrl"), "/mobile/gm"):
        failures.append("public-edge postdeploy front-door visible GM URL is not query-free /mobile/gm")
    if not _safe_visible_url(payload.get("frontdoorNavigationGmRoute"), "/mobile/gm"):
        failures.append("public-edge postdeploy front-door GM switch route is not query-free /mobile/gm")
    if not _safe_visible_url(payload.get("frontdoorNavigationAnchorEntryUrl"), "/"):
        failures.append("public-edge postdeploy front-door anchor entry URL contains private identity")
    if not _safe_visible_url(payload.get("frontdoorNavigationAnchorFinalUrl"), "/mobile/player"):
        failures.append("public-edge postdeploy front-door anchor final URL is not query-free /mobile/player")
    elif urlparse(str(payload.get("frontdoorNavigationAnchorFinalUrl") or "")).fragment != "turn-runsite-card":
        failures.append("public-edge postdeploy front-door anchor final URL did not preserve #turn-runsite-card")
    if str(payload.get("frontdoorNavigationAnchorFinalPath") or "").strip() != "/mobile/player":
        failures.append("public-edge postdeploy front-door anchor final path is not /mobile/player")
    if str(payload.get("frontdoorNavigationAnchorFinalHash") or "").strip() != "#turn-runsite-card":
        failures.append("public-edge postdeploy front-door anchor final hash is not #turn-runsite-card")
    if str(payload.get("frontdoorNavigationAnchorFailure") or "").strip():
        failures.append("public-edge postdeploy front-door anchor proof reports a failure")

    for field, label in (
        ("frontdoorNavigationPrivateIdentityRedacted", "Player artifact private identity redaction"),
        ("frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent", "visible Player URL identity absence"),
        ("frontdoorNavigationPlayerSessionContextPresent", "Player session context"),
        ("frontdoorNavigationPlayerDeviceContextPresent", "Player device context"),
        ("frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted", "Player handoff private identity redaction"),
        ("frontdoorNavigationGmRouteSessionIdPresent", "GM route session context"),
        ("frontdoorNavigationGmRoutePrivateIdentityRedacted", "GM route private identity redaction"),
        ("frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent", "visible GM URL identity absence"),
        ("frontdoorNavigationGmSessionContextPresent", "GM session context"),
        ("frontdoorNavigationGmDeviceContextPresent", "GM device context"),
        ("frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted", "GM handoff private identity redaction"),
        ("frontdoorNavigationAnchorPrivateIdentityRedacted", "anchor private identity redaction"),
        ("frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent", "visible anchor URL identity absence"),
        ("frontdoorNavigationAnchorSessionContextPresent", "anchor session context"),
        ("frontdoorNavigationAnchorDeviceContextPresent", "anchor device context"),
    ):
        if payload.get(field) is not True:
            failures.append(f"public-edge postdeploy front-door did not prove {label}")

    if not _safe_redacted_handoff(
        payload.get("frontdoorNavigationPlayerSessionHandoffUrl"), "/mobile/player", "Player"
    ):
        failures.append("public-edge postdeploy front-door Player handoff is not a redacted player route")
    if not _safe_redacted_handoff(
        payload.get("frontdoorNavigationGmSessionHandoffUrl"), "/mobile/gm", "GameMaster"
    ):
        failures.append("public-edge postdeploy front-door GM handoff is not a redacted GM route")
    return failures


def public_edge_v2_artifact_contract_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    status_by_field = {
        "pwaOfflineCacheArtifactContract": "pwaOfflineCacheStatus",
        "frontdoorNavigationMobileArtifactContract": "frontdoorNavigationStatus",
        "frontdoorNavigationAnchorArtifactContract": "frontdoorNavigationStatus",
    }
    for field, expected in PUBLIC_EDGE_V2_ARTIFACT_CONTRACTS.items():
        if str(payload.get(status_by_field[field]) or "").strip().lower() != "pass":
            continue
        if str(payload.get(field) or "").strip() != expected:
            failures.append(f"public_edge_postdeploy_gate {field} is not {expected}")
    return failures


def normalize_public_edge_postdeploy_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    private_identity_was_raw = _contains_raw_private_identity(payload)
    normalized = _redact_private_identity(payload)
    if not isinstance(normalized, dict):
        return {}
    if private_identity_was_raw:
        normalized["privateIdentityWasRaw"] = True
    child_receipts = normalized.get("childReceipts")
    if (
        receipt_contract(normalized)
        == PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME
    ):
        # V2 is exact and authorizing: preserve any invalid public child
        # content so every consumer can reject it. Only legacy receipts are
        # flattened and scrubbed for non-authorizing compatibility views.
        return normalized
    normalized["childReceipts"] = {}
    if not isinstance(child_receipts, dict):
        return normalized

    preflight_receipt = child_receipts.get("preflight")
    if isinstance(preflight_receipt, dict):
        overlay_fingerprint = (
            preflight_receipt.get("overlayBuildInfoSourceFingerprint")
            if isinstance(preflight_receipt.get("overlayBuildInfoSourceFingerprint"), dict)
            else {}
        )
        legacy_preflight_fields = {
            "preflightOverlayRoot": preflight_receipt.get("overlayRoot"),
            "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource": overlay_fingerprint.get("aggregateMatchesCurrentSource"),
            "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256": overlay_fingerprint.get("recordedAggregateSha256"),
            "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256": overlay_fingerprint.get("expectedAggregateSha256"),
            "preflightOverlayBuildInfoSourceFingerprintMissingKeys": overlay_fingerprint.get("missingKeys"),
            "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys": overlay_fingerprint.get("mismatchedKeys"),
        }
        for key, value in legacy_preflight_fields.items():
            if key in normalized or not _present(value):
                continue
            normalized[key] = value

    frontdoor_navigation = child_receipts.get("frontdoorNavigation")
    if not isinstance(frontdoor_navigation, dict):
        return normalized

    anchor_artifact = frontdoor_navigation.get("anchorArtifact")
    if not isinstance(anchor_artifact, dict):
        return normalized

    current_anchor_fields = {
        "frontdoorNavigationAnchorArtifactContract": receipt_contract(anchor_artifact),
        "frontdoorNavigationAnchorEntryUrl": anchor_artifact.get("entry_url"),
        "frontdoorNavigationAnchorFinalUrl": anchor_artifact.get("final_url"),
        "frontdoorNavigationAnchorFinalPath": anchor_artifact.get("final_pathname"),
        "frontdoorNavigationAnchorFinalHash": anchor_artifact.get("final_hash"),
        "frontdoorNavigationAnchorPwaManifestPath": anchor_artifact.get("pwa_manifest_path"),
        "frontdoorNavigationAnchorPwaRole": anchor_artifact.get("pwa_role"),
        "frontdoorNavigationAnchorBlazorShell": anchor_artifact.get("blazor_shell"),
        "frontdoorNavigationAnchorPrivateIdentityRedacted": anchor_artifact.get("private_identity_redacted"),
        "frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent": anchor_artifact.get("visible_url_private_identity_absent"),
        "frontdoorNavigationAnchorSessionContextPresent": anchor_artifact.get("session_context_present"),
        "frontdoorNavigationAnchorDeviceContextPresent": anchor_artifact.get("device_context_present"),
        "frontdoorNavigationAnchorFailure": anchor_artifact.get("failure"),
    }

    for key, value in current_anchor_fields.items():
        if key in normalized or (key != "frontdoorNavigationAnchorFailure" and not _present(value)):
            continue
        normalized[key] = value

    return normalized
