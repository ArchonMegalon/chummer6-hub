from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse


PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME = "chummer.public_edge_postdeploy_gate.v1"
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
