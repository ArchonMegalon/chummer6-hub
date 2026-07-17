from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_operator_release_dashboard.py"
WINDOWS_INTAKE_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "materialize_windows_installer_visual_audit_intake_request.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_operator_release_dashboard", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES = ()
    module.WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES = ()
    module.supply_chain_release_gate_path = (
        lambda: module.PUBLISHED_ROOT / "SUPPLY_CHAIN_RELEASE_GATE.generated.json"
    )
    return module


def load_windows_intake_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_windows_installer_visual_audit_intake_request",
        WINDOWS_INTAKE_SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stale_timestamp() -> str:
    return (datetime.now(UTC) - timedelta(hours=49)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def with_fresh_timestamp(path: Path, payload: dict[str, object]) -> dict[str, object]:
    stamped = dict(payload)
    if path.name == "RELEASE_CHANNEL.generated.json":
        stamped.setdefault("supportabilityState", "gold_supported")
        stamped.setdefault("rolloutState", "public_stable")
        return stamped
    if "generatedAtUtc" in stamped:
        stamped["generatedAtUtc"] = fresh_timestamp()
    elif "generated_at" in stamped:
        stamped["generated_at"] = fresh_timestamp()
    else:
        stamped.setdefault("generated_at_utc", fresh_timestamp())
    return stamped


def passing_portable_receipts_audit_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.run.portable_receipts_audit",
        "generated_at": fresh_timestamp(),
        "status": "pass",
        "summary": "Published proof artifacts are portable.",
        "scanned_artifact_count": 12,
        "machine_specific_hits": [],
        "machine_specific_path_hits": [],
        "artifact_integrity_hits": [],
        "failure_counts": {
            "machine_specific_paths": 0,
            "artifact_integrity": 0,
        },
        "machine_specific_hit_details": [],
        "unreadable_artifacts": [],
        "scan_roots": ["scan-root-1"],
        "policy": {
            "use_repo_relative_paths": True,
            "allow_local_only_hostnames": True,
            "forbid_machine_specific_paths": True,
            "redact_failure_samples": True,
            "scan_nested_json_artifacts": True,
            "fail_on_artifact_integrity_errors": True,
        },
        "abs_ids": ["ABS-012"],
    }


def passing_supply_chain_release_gate_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer6.supply_chain_release_gate.v1",
        "generated_at_utc": fresh_timestamp(),
        "status": "pass",
        "verdict": "SUPPLY_CHAIN_READY",
        "pass": True,
        "blockers": [],
        "checks": {
            check_id: {"status": "pass"}
            for check_id in (
                "container_vulnerability_audit",
                "dependency_vulnerability_audit",
                "provenance",
                "sbom",
                "secret_scan",
            )
        },
        "next_actions": [],
    }


def passing_public_edge_observability_release_gate_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.public_edge_observability_release_gate.v1",
        "generated_at_utc": fresh_timestamp(),
        "status": "pass",
        "verdict": "OBSERVABILITY_RELEASE_READY",
        "failure_count": 0,
        "failures": [],
        "checks": [
            {"id": check_id, "status": "pass", "detail": "ready"}
            for check_id in (
                "runtime:program",
                "runtime:readiness",
                "runtime:instruments",
                "runtime:middleware",
                "runtime:compose",
                "release_candidate",
                "policy",
                "operator_proof",
                "operator_intake_request",
                "operator_attestation",
            )
        ],
        "release_candidate": {
            "version": "run-test",
            "channel": "public_stable",
            "status": "published",
        },
        "operator_intake": {
            "state": "complete",
            "external_evidence_required": False,
        },
        "operator_dependencies": [],
    }


def write_receipts(receipts: dict[Path, dict[str, object]]) -> None:
    receipts_to_write = dict(receipts)
    published_root = next(
        (path.parent for path in receipts_to_write if path.parent.name == "published"),
        None,
    )
    if published_root is not None:
        receipts_to_write.setdefault(
            published_root / "PORTABLE_RECEIPTS_AUDIT.generated.json",
            passing_portable_receipts_audit_payload(),
        )
        receipts_to_write.setdefault(
            published_root / "SUPPLY_CHAIN_RELEASE_GATE.generated.json",
            passing_supply_chain_release_gate_payload(),
        )
        receipts_to_write.setdefault(
            published_root / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json",
            passing_public_edge_observability_release_gate_payload(),
        )
    for path, payload in receipts_to_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(with_fresh_timestamp(path, payload)) + "\n", encoding="utf-8")


def test_windows_visual_audit_is_release_blocking_by_default_but_explicit_dev_override_remains(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CHUMMER_IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING", raising=False)
    assert load_module().IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING is False

    monkeypatch.setenv("CHUMMER_IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING", "1")
    assert load_module().IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING is True


def test_normalized_release_ready_snapshot_truth_audit_rejects_pass_shaped_failures() -> None:
    module = load_module()

    normalized = module.normalized_release_ready_snapshot_truth_audit(
        {
            "status": "pass",
            "verdict": "SNAPSHOT_CONSISTENT_LAUNCH_READY",
            "failures": ["snapshot audit contradicted by nested release truth failures"],
        },
        Path("/tmp/PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"),
    )

    assert normalized["pass"] is False
    assert normalized["status"] == "fail"
    assert normalized["raw_status"] == "pass"


def test_expected_visible_version_candidates_allow_blank_status_for_stable_lane() -> None:
    module = load_module()

    assert module.expected_visible_version_candidates(
        "run-20260630",
        "",
        "public_stable",
        "gold_supported",
        "public_stable",
    ) == ["Version 2026.06.30", "Version run-20260630"]


def passing_public_edge_postdeploy_payload() -> dict[str, object]:
    return {
        "contractName": "chummer.public_edge_postdeploy_gate.v1",
        "status": "pass",
        "generatedAtUtc": fresh_timestamp(),
        "coreChildContracts": {
            "preflight": "chummer.public_edge_deploy_preflight.v1",
            "downloads": "chummer.downloads_version_marker.v1",
            "pwaStatic": "chummer.public_pwa_static_assets.v1",
            "mobileLedger": "chummer.mobile_pwa_ledger_boundary.v1",
            "readyMobileHandoff": "chummer.ready_mobile_handoff_contract.v1",
            "participateIframeShell": "chummer.participate_iframe_shell.v1",
        },
        "preflightStatus": "pass",
        "preflightActiveLockCount": 0,
        "preflightBlockingLockCount": 0,
        "preflightForeignLockCount": 0,
        "preflightIgnoredForeignLockCount": 0,
        "preflightForeignLocksIgnored": False,
        "preflightAllowForeignBuildLocks": False,
        "preflightStaleLookingLockCount": 0,
        "preflightStaleForeignLockCount": 0,
        "preflightStaleForeignLocksIgnored": False,
        "preflightAllowStaleForeignBuildLocks": False,
        "preflightOverlayRoot": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
        "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource": True,
        "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256": "a" * 64,
        "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256": "a" * 64,
        "preflightOverlayBuildInfoSourceFingerprintMissingKeys": [],
        "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys": [],
        "downloadsStatus": "pass",
        "downloadsHasMarker": True,
        "statusRedirectHasMarker": True,
        "statusRedirectHeading": "Stable downloads",
        "statusRedirectHeadingRecognized": True,
        "statusRedirectHeadingExpected": "Stable downloads",
        "statusRedirectHeadingMatchesReleaseChannel": True,
        "statusRedirectHeadingUsesGenericUpdatedCopy": False,
        "visibleVersion": "Version run-test",
        "statusRedirectVersion": "Version run-test",
        "expectedReleaseVersion": "run-test",
        "visibleVersionMatchesReleaseChannel": True,
        "statusRedirectVersionMatchesReleaseChannel": True,
        "expectedReleaseStatus": "published",
        "expectedReleaseChannel": "public_stable",
        "expectedReleaseSupportabilityState": "gold_supported",
        "expectedReleaseRolloutState": "public_stable",
        "releaseManifestHttpStatus": 200,
        "releaseManifestStatus": "published",
        "releaseManifestStatusMatchesReleaseChannel": True,
        "releaseManifestChannel": "public_stable",
        "releaseManifestChannelMatchesReleaseChannel": True,
        "releaseManifestVersion": "run-test",
        "releaseManifestVersionMatchesReleaseChannel": True,
        "releaseManifestSupportabilityState": "gold_supported",
        "releaseManifestSupportabilityMatchesReleaseChannel": True,
        "releaseManifestRolloutState": "public_stable",
        "releaseManifestRolloutMatchesReleaseChannel": True,
        "pwaStaticStatus": "pass",
        "pwaManifestCount": 3,
        "rolePwaManifestCount": 2,
        "rolePwaManifests": [
            {
                "path": "/manifest.player.webmanifest",
                "role": "Player",
                "id": "/mobile/player",
                "start_url": "/mobile/player?role=Player",
                "display": "standalone",
            },
            {
                "path": "/manifest.gm.webmanifest",
                "role": "GameMaster",
                "id": "/mobile/gm",
                "start_url": "/mobile/gm?role=GameMaster",
                "display": "standalone",
            },
        ],
        "pwaAssetCount": 11,
        "ledgerStreamNonCacheable": True,
        "ledgerStreamPrecached": False,
        "mobileLedgerStatus": "pass",
        "mobileLedgerPayloadStatus": "opt_in_required",
        "mobileLedgerCacheControl": "private, no-store, no-cache, max-age=0",
        "mobileLedgerVary": "Cookie, Authorization",
        "readyMobileHandoffStatus": "pass",
        "readyMobileHandoffToolIds": ["inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"],
        "readyMobileHandoffPacketRoles": ["player", "gm", "organizer"],
        "readyMobileHandoffFrontdoorLaunchRoute": "/mobile/player",
        "readyMobileHandoffRoleRoutes": [
            {
                "role": "Player",
                "mode": "player",
                "route": "/mobile/player",
                "manifest_path": "/manifest.player.webmanifest",
                "manifest_id": "/mobile/player",
                "manifest_start_url": "/mobile/player?role=Player",
                "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
                "frontdoor_default": True,
            },
            {
                "role": "GameMaster",
                "mode": "gm",
                "route": "/mobile/gm",
                "manifest_path": "/manifest.gm.webmanifest",
                "manifest_id": "/mobile/gm",
                "manifest_start_url": "/mobile/gm?role=GameMaster",
                "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
                "frontdoor_default": False,
            },
        ],
        "downloadsStatusBrowserStatus": "pass",
        "downloadsStatusBrowserArtifactContract": "chummer.downloads_status_e2e.v1",
        "mobilePwaViewportStatus": "pass",
        "mobilePwaViewportArtifactContract": "chummer.mobile_pwa_viewport_smoke.v1",
        "mobilePwaViewportRouteCount": 6,
        "mobilePwaViewportViewportCount": 3,
        "mobilePwaViewportRoutes": ["/mobile", "/mobile/player", "/mobile/gm", "/mobile/observer", "/play", "/play/continuity"],
        "mobilePwaViewportMissingRoutes": [],
        "pwaOfflineCacheStatus": "pass",
        "pwaOfflineCacheArtifactContract": "chummer.pwa_offline_cache.v2",
        "pwaOfflineCacheCacheVersion": "v17",
        "pwaOfflineCacheNavigationPolicy": "network_only",
        "pwaOfflineCachePrivateStateScope": "open_tab_only",
        "pwaOfflineCacheStaticPaths": [
            "/manifest.player.webmanifest",
            "/manifest.gm.webmanifest",
            "/mobile.css",
            "/mobile-turn-companion.js",
        ],
        "pwaOfflineCacheOfflineRoleFallbacks": [
            {
                "role": "Player",
                "path": "/mobile/player",
                "status": 503,
                "cache_control": "private, no-store",
                "private_projection_restored": False,
            },
            {
                "role": "GameMaster",
                "path": "/mobile/gm",
                "status": 503,
                "cache_control": "private, no-store",
                "private_projection_restored": False,
            },
        ],
        "pwaOfflineCacheQueryBearingRequestsCached": False,
        "pwaOfflineCachePrivateNavigationCached": False,
        "pwaOfflineCachePrivateApiCached": False,
        "pwaOfflineCachePersonalizedLedgerCached": False,
        "pwaOfflineCacheLegacyPrivateCachePrefixesPurged": [
            "chummer-shell-play-shell-",
            "chummer-media-play-shell-",
            "chummer-media-meta-play-shell-",
        ],
        "pwaOfflineCacheUnrelatedCachePreserved": True,
        "roleAliasRouteStatus": "pass",
        "roleAliasRouteContract": "chummer.public_role_alias_routes.v1",
        "roleAliasRouteResults": [
            {
                "aliasPath": "/player",
                "requestedUrl": "https://chummer.run/player",
                "httpStatus": 200,
                "finalUrl": "https://chummer.run/mobile/player",
                "finalRoute": "/mobile/player",
                "expectedFinalRoute": "/mobile/player",
                "pass": True,
                "error": "",
            },
            {
                "aliasPath": "/gm",
                "requestedUrl": "https://chummer.run/gm",
                "httpStatus": 200,
                "finalUrl": "https://chummer.run/mobile/gm",
                "finalRoute": "/mobile/gm",
                "expectedFinalRoute": "/mobile/gm",
                "pass": True,
                "error": "",
            },
            {
                "aliasPath": "/observer",
                "requestedUrl": "https://chummer.run/observer",
                "httpStatus": 200,
                "finalUrl": "https://chummer.run/mobile/observer",
                "finalRoute": "/mobile/observer",
                "expectedFinalRoute": "/mobile/observer",
                "pass": True,
                "error": "",
            },
        ],
        "roleAliasRouteDrift": [],
        "participateIframeShellStatus": "pass",
        "participateIframeRouteCount": 2,
        "participateIframeRouteIframeCount": 2,
        "participateIframeRouteOfflineFallbackCount": 0,
        "frontdoorNavigationStatus": "pass",
        "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_launch.v2",
        "frontdoorNavigationLedgerArtifactContract": "chummer.black_ledger_globe_frontdoor.v1",
        "frontdoorNavigationAnchorArtifactContract": "chummer.frontdoor_mobile_anchor_redirect.v2",
        "frontdoorNavigationGatedTargets": ["Build", "Play"],
        "frontdoorNavigationPublicTargets": [],
        "frontdoorNavigationPlayRoute": "/mobile/player",
        "frontdoorNavigationPlaySignInRoute": "/login?next=%2Fmobile%2Fplayer",
        "frontdoorNavigationDirectPlayerRoute": "/mobile/player",
        "frontdoorNavigationDirectPlayerHttpStatus": 200,
        "frontdoorNavigationFinalUrl": "https://chummer.run/mobile/player",
        "frontdoorNavigationPrivateIdentityRedacted": True,
        "frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent": True,
        "frontdoorNavigationPlayerSessionContextPresent": True,
        "frontdoorNavigationPlayerDeviceContextPresent": True,
        "frontdoorNavigationLiveTurnCompanionShell": True,
        "frontdoorNavigationPwaManifestPath": "/manifest.player.webmanifest",
        "frontdoorNavigationPwaRole": "Player",
        "frontdoorNavigationBlazorShell": "interactive-server",
        "frontdoorNavigationRybbitConfigured": True,
        "frontdoorNavigationRybbitTag": "mobile_play_shell",
        "frontdoorNavigationRybbitRoute": "/mobile/player",
        "frontdoorNavigationRybbitMode": "player",
        "frontdoorNavigationRybbitRole": "Player",
        "frontdoorNavigationRybbitSiteIdPresent": True,
        "frontdoorNavigationRybbitScriptUrlPresent": True,
        "frontdoorNavigationRybbitScriptUrlAllowed": True,
        "frontdoorNavigationRybbitSkipPatterns": ["/mobile/**"],
        "frontdoorNavigationRybbitMaskPatterns": ["/api/play/**", "/mobile/**"],
        "frontdoorNavigationRybbitSkipMobilePaths": True,
        "frontdoorNavigationRybbitMaskMobilePaths": True,
        "frontdoorNavigationRybbitMasksPrivatePlayRoutes": True,
        "frontdoorNavigationRybbitReplayBlockSelector": "[data-turn-root]",
        "frontdoorNavigationRybbitReplayBlocksTurnRoot": True,
        "frontdoorNavigationPlayerSessionHandoffUrl": "https://chummer.run/mobile/player?sessionId=[redacted]&role=Player",
        "frontdoorNavigationPlayerSessionHandoffStatus": "Session handoff is ready in the link above.",
        "frontdoorNavigationPlayerSessionHandoffLinkText": "Open session handoff link",
        "frontdoorNavigationPlayerSessionHandoffPreservesSession": True,
        "frontdoorNavigationPlayerSessionHandoffPreservesRole": True,
        "frontdoorNavigationPlayerSessionHandoffStripsDevice": True,
        "frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent": True,
        "frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted": True,
        "frontdoorNavigationGmRoute": "/mobile/gm",
        "frontdoorNavigationGmRouteSessionIdPresent": True,
        "frontdoorNavigationGmRoutePrivateIdentityRedacted": True,
        "frontdoorNavigationGmHttpStatus": 200,
        "frontdoorNavigationGmFinalUrl": "https://chummer.run/mobile/gm",
        "frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent": True,
        "frontdoorNavigationGmSessionContextPresent": True,
        "frontdoorNavigationGmDeviceContextPresent": True,
        "frontdoorNavigationGmLiveTurnCompanionShell": True,
        "frontdoorNavigationGmPwaManifestPath": "/manifest.gm.webmanifest",
        "frontdoorNavigationGmPwaRole": "GameMaster",
        "frontdoorNavigationGmBlazorShell": "interactive-server",
        "frontdoorNavigationGmRybbitConfigured": True,
        "frontdoorNavigationGmRybbitTag": "mobile_play_shell",
        "frontdoorNavigationGmRybbitRoute": "/mobile/gm",
        "frontdoorNavigationGmRybbitMode": "gm",
        "frontdoorNavigationGmRybbitRole": "GameMaster",
        "frontdoorNavigationGmRybbitSiteIdPresent": True,
        "frontdoorNavigationGmRybbitScriptUrlPresent": True,
        "frontdoorNavigationGmRybbitScriptUrlAllowed": True,
        "frontdoorNavigationGmRybbitSkipPatterns": ["/mobile/**"],
        "frontdoorNavigationGmRybbitMaskPatterns": ["/api/play/**", "/mobile/**"],
        "frontdoorNavigationGmRybbitSkipMobilePaths": True,
        "frontdoorNavigationGmRybbitMaskMobilePaths": True,
        "frontdoorNavigationGmRybbitMasksPrivatePlayRoutes": True,
        "frontdoorNavigationGmRybbitReplayBlockSelector": "[data-turn-root]",
        "frontdoorNavigationGmRybbitReplayBlocksTurnRoot": True,
        "frontdoorNavigationGmSessionHandoffUrl": "https://chummer.run/mobile/gm?sessionId=[redacted]&role=GameMaster",
        "frontdoorNavigationGmSessionHandoffStatus": "Session handoff is ready in the link above.",
        "frontdoorNavigationGmSessionHandoffLinkText": "Open session handoff link",
        "frontdoorNavigationGmSessionHandoffPreservesSession": True,
        "frontdoorNavigationGmSessionHandoffPreservesRole": True,
        "frontdoorNavigationGmSessionHandoffStripsDevice": True,
        "frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent": True,
        "frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted": True,
        "frontdoorNavigationLedgerPrimary": False,
        "frontdoorNavigationAnchorEntryUrl": "https://chummer.run/#turn-runsite-card",
        "frontdoorNavigationAnchorFinalUrl": "https://chummer.run/mobile/player#turn-runsite-card",
        "frontdoorNavigationAnchorFinalPath": "/mobile/player",
        "frontdoorNavigationAnchorFinalHash": "#turn-runsite-card",
        "frontdoorNavigationAnchorPwaManifestPath": "/manifest.player.webmanifest",
        "frontdoorNavigationAnchorPwaRole": "Player",
        "frontdoorNavigationAnchorBlazorShell": "interactive-server",
        "frontdoorNavigationAnchorPrivateIdentityRedacted": True,
        "frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent": True,
        "frontdoorNavigationAnchorSessionContextPresent": True,
        "frontdoorNavigationAnchorDeviceContextPresent": True,
        "frontdoorNavigationAnchorFailure": "",
    }


def passing_teable_important_work_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.teable_important_work.v1",
        "generated_at_utc": fresh_timestamp(),
        "status": "ready",
        "table_name": "Chummer Important Work",
        "row_count": 2,
        "rows": [
            {"item_id": "public-edge-postdeploy", "title": "Public edge postdeploy"},
            {"item_id": "native-windows-proof", "title": "Native Windows proof"},
        ],
        "sync": {
            "state": "passed",
            "attempted": True,
            "synced_count": 2,
            "created_count": 0,
            "updated_count": 2,
            "failed_count": 0,
            "errors": [],
        },
    }


def nested_public_edge_postdeploy_anchor_payload() -> dict[str, object]:
    payload = passing_public_edge_postdeploy_payload()
    anchor_artifact = {
        "contractName": payload.pop("frontdoorNavigationAnchorArtifactContract"),
        "entry_url": payload.pop("frontdoorNavigationAnchorEntryUrl"),
        "final_url": payload.pop("frontdoorNavigationAnchorFinalUrl"),
        "final_pathname": payload.pop("frontdoorNavigationAnchorFinalPath"),
        "final_hash": payload.pop("frontdoorNavigationAnchorFinalHash"),
        "pwa_manifest_path": payload.pop("frontdoorNavigationAnchorPwaManifestPath"),
        "pwa_role": payload.pop("frontdoorNavigationAnchorPwaRole"),
        "blazor_shell": payload.pop("frontdoorNavigationAnchorBlazorShell"),
        "private_identity_redacted": payload.pop("frontdoorNavigationAnchorPrivateIdentityRedacted"),
        "visible_url_private_identity_absent": payload.pop("frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent"),
        "session_context_present": payload.pop("frontdoorNavigationAnchorSessionContextPresent"),
        "device_context_present": payload.pop("frontdoorNavigationAnchorDeviceContextPresent"),
    }
    payload["childReceipts"] = {
        "frontdoorNavigation": {
            "status": "pass",
            "anchorArtifact": anchor_artifact,
        }
    }
    return payload


def passing_flagship_product_readiness_payload() -> dict[str, object]:
    return {
        "contract_name": "fleet.flagship_product_readiness",
        "generated_at": fresh_timestamp(),
        "status": "pass",
        "completion_audit": {
            "status": "pass",
            "reason": "Flagship product readiness planes are green.",
        },
        "flagship_readiness_audit": {
            "status": "pass",
            "reason": "Flagship product readiness proof is green.",
            "coverage_gap_keys": [],
            "scoped_coverage_gap_keys": [],
        },
        "summary": {
            "ready_count": 8,
            "warning_count": 0,
            "missing_count": 0,
            "scoped_missing_count": 0,
        },
    }


def failing_flagship_product_readiness_gate_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.flagship_product_readiness_gate.v1",
        "generated_at_utc": fresh_timestamp(),
        "status": "fail",
        "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
        "readiness_path": ".codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json",
        "readiness_load_status": "loaded",
        "summary": {
            "contract_name": "fleet.flagship_product_readiness",
            "status": "pass",
            "generated_at": fresh_timestamp(),
            "readiness_load_status": "loaded",
            "completion_audit_status": "pass",
            "flagship_readiness_audit_status": "pass",
            "reason": "Launch-critical nested blockers or coverage gaps remain; raw materializer status is not sufficient for a flagship launch claim. Launch blockers: final gold janitor state is 'fail', final gold janitor verdict is 'NOT_GOLD', live-backed gold claim is not allowed.",
            "ready_count": 8,
            "missing_count": 0,
            "scoped_missing_count": 0,
            "warning_count": 0,
            "coverage_gap_keys": [],
            "scoped_coverage_gap_keys": [],
            "launch_critical_nested_blockers": [
                "final gold janitor state is 'fail'",
                "final gold janitor verdict is 'NOT_GOLD'",
                "live-backed gold claim is not allowed",
            ],
            "launch_critical_nested_blocker_count": 3,
            "pass": False,
        },
    }


def failing_flagship_product_readiness_gate_payload_with_failed_nested_audits() -> dict[str, object]:
    payload = failing_flagship_product_readiness_gate_payload()
    payload["summary"]["completion_audit_status"] = "fail"
    payload["summary"]["flagship_readiness_audit_status"] = "fail"
    return payload


def preview_release_channel_payload() -> dict[str, object]:
    return {
        "status": "published",
        "version": "run-test",
        "publishedAt": "2026-06-24T08:00:00Z",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
    }


def passing_windows_installer_visual_audit_payload() -> dict[str, object]:
    sha = "a" * 64
    return {
        "contract_name": "chummer.windows_installer_visual_audit",
        "generated_at_utc": fresh_timestamp(),
        "status": "pass",
        "artifact": {
            "sha256": sha,
            "actualSha256": sha,
        },
        "startupReceipt": {
            "status": "pass",
            "artifactDigest": f"sha256:{sha}",
        },
        "visualAuditSource": {
            "exists": True,
            "status": "pass",
            "platform": "windows",
            "hostClass": "native-windows-11",
            "artifactSha256": sha,
            "screenshotCount": 4,
            "defaultDpiScreenshotCount": 2,
            "scaledDpiScreenshotCount": 2,
            "requiredSurfaces": ["install-progress", "completion"],
        },
        "failures": [],
        "nextActions": [],
    }


def passing_release_ready_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.release_ready",
        "generated_at_utc": fresh_timestamp(),
        "status": "pass",
        "verdict": "RELEASE_READY",
        "returncode": 0,
        "timed_out": False,
        "saw_release_ready_marker": True,
        "not_release_ready_markers": [],
        "failures": [],
        "failed_gates": [],
    }


def passing_blazor_execution_horizon_bridge_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.blazor_execution_horizon_bridge",
        "generated_at_utc": fresh_timestamp(),
        "status": "pass",
        "verdict": "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven",
        "proofs": {
            "hub_mobile_pwa_public_projection": {
                "status": "pass",
                "pass": True,
            },
            "blazor_hosted_pwa_public_edge": {
                "status": "passed",
                "pass": True,
            },
            "blazor_hosted_execution_horizon": {
                "status": "passed",
                "pass": True,
                "near_term_smoke_status": "proven",
                "mid_term_full_matrix_status": "not_proven",
                "mid_term_full_required_workflow_family_count": 49,
                "mid_term_full_covered_workflow_family_count": 9,
                "long_term_full_browser_parity_status": "not_proven",
            },
        },
        "notes": [
            "This Hub bridge keeps mobile/PWA readiness, Blazor PWA installability, and Blazor hosted execution horizons visible together.",
        ],
        "failures": [],
    }


def passing_blazor_play_surface_horizon_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer6-ui.blazor_play_surface_horizon",
        "generated_at_utc": fresh_timestamp(),
        "status": "passed",
        "horizons": [
            {
                "id": "near_term_stabilization",
                "title": "Near-term stabilization",
                "status": "proven",
                "evidence_tier": "runtime_proven",
            },
            {
                "id": "mid_term_pwa_session_utility",
                "title": "Mid-term PWA and session utility",
                "status": "mixed",
                "evidence_tier": "runtime_pwa_plus_source_staged_session_utility",
                "server_bound_boundaries": [
                    "runner data",
                    "workspace data",
                    "API traffic",
                    "Black Ledger state",
                    "heat state",
                    "session state",
                ],
            },
            {
                "id": "long_term_living_world_expansion",
                "title": "Long-term living-world expansion",
                "status": "staged",
                "evidence_tier": "source_staged_and_docs_only",
                "unproven_claims": [
                    "live Black Ledger mutation",
                    "heat propagation runtime",
                ],
            },
        ],
    }


def passing_google_oauth_linking_proof_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.run.google_oauth_linking_proof",
        "proof_contract_version": 3,
        "generated_at_utc": fresh_timestamp(),
        "status": "pass",
        "base_url": "https://chummer.run",
        "bindings": {
            "release": {},
            "request": {},
            "evidence": {},
            "programs": {},
        },
        "quick_handoff_probe": {"pass": True},
        "signed_in_link_handoff": {"status": "pass", "pass": True},
        "operator_end_to_end_evidence": {"pass": True, "exists": True, "failures": []},
        "operator_request_artifacts": {"pass": True, "failures": []},
        "failures": [],
    }


def passing_ea_operator_readiness_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.ea_operator_readiness.v1",
        "generated_at_utc": fresh_timestamp(),
        "updated_at": fresh_timestamp(),
        "observed_at": fresh_timestamp(),
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready_with_actions",
        "runtime_status": "degraded",
        "runtime_ready": False,
        "source": "script:ea_live_ops.py",
        "source_runtime": "ea_live_ops.bridge",
        "probe_ok": True,
        "secret_leak_detected": False,
        "operator_ready": False,
        "operator_status": "ready_with_actions",
        "blocking_count": 0,
        "advisory_count": 1,
        "attention_required_count": 1,
        "blocked_count": 0,
        "probe_failed_count": 0,
        "component_count": 7,
        "component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "effective_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "pushbullet",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "ready_component_keys": [
            "telegram",
            "google_workspace_oauth",
            "whatsapp",
            "whatsapp_pairing",
            "teable_recovery",
            "mymedia_alexa",
        ],
        "attention_component_keys": ["pushbullet"],
        "blocked_component_keys": [],
        "probe_failed_component_keys": [],
        "blocking_findings": [],
        "advisory_findings": ["attention:pushbullet:blocked_setup_required"],
        "next_action_component_keys": ["pushbullet"],
        "advisory_action_component_keys": ["mymedia_alexa"],
        "components": [
            {
                "key": "telegram",
                "label": "Telegram operator delivery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "google_workspace_oauth",
                "label": "Google Workspace OAuth",
                "probe_ok": True,
                "ready": True,
                "status": "pass",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "pushbullet",
                "label": "Pushbullet operator delivery",
                "probe_ok": True,
                "ready": False,
                "status": "blocked_setup_required",
                "reason": "pushbullet_token_missing:elisabeth",
                "next_action": "create_missing_pushbullet_access_tokens",
                "next_action_href": "https://www.pushbullet.com/#settings/account",
                "next_action_label": "Open Pushbullet account settings",
                "next_action_method": "get",
                "details": {},
            },
            {
                "key": "whatsapp",
                "label": "WhatsApp Web action processor",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "whatsapp_pairing",
                "label": "WhatsApp Web pairing recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "teable_recovery",
                "label": "Teable env recovery",
                "probe_ok": True,
                "ready": True,
                "status": "ready",
                "reason": "",
                "next_action": "",
                "next_action_href": "",
                "next_action_label": "",
                "next_action_method": "",
                "details": {},
            },
            {
                "key": "mymedia_alexa",
                "label": "My Media for Alexa",
                "probe_ok": True,
                "ready": True,
                "status": "ready_library_scan_in_progress",
                "reason": "mymedia_library_scan_in_progress",
                "next_action": "wait_for_mymedia_library_scan",
                "next_action_href": "host-local:///index.html#!/tables",
                "next_action_label": "Open Watch Folders",
                "next_action_method": "get",
                "details": {},
            },
        ],
        "next_actions": [
            {
                "component_key": "pushbullet",
                "component_label": "Pushbullet operator delivery",
                "action": "create_missing_pushbullet_access_tokens",
                "reason": "pushbullet_token_missing",
                "href": "https://www.pushbullet.com/#settings/account",
                "label": "Open Pushbullet account settings",
                "method": "get",
            }
        ],
        "advisory_actions": [
            {
                "component_key": "mymedia_alexa",
                "component_label": "My Media for Alexa",
                "action": "wait_for_mymedia_library_scan",
                "reason": "mymedia_library_scan_in_progress",
                "href": "host-local:///index.html#!/tables",
                "label": "Open Watch Folders",
                "method": "get",
            }
        ],
    }


def passing_mymedia_public_surface_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.ea_mymedia_public_surface.v1",
        "generated_at_utc": fresh_timestamp(),
        "updated_at": fresh_timestamp(),
        "observed_at": fresh_timestamp(),
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "access_protected",
        "runtime_status": "ready",
        "runtime_ready": True,
        "source": "script:ea_live_ops.py",
        "probe_payload_present": True,
        "probe_ok": True,
        "secret_leak_detected": False,
        "blocking_count": 0,
        "advisory_count": 0,
        "blocking_findings": [],
        "advisory_findings": [],
        "public_surface_configured": True,
        "public_surface_ready": True,
        "public_surface_status": "access_protected",
        "public_surface_reason": "",
        "public_surface_url": "https://mymedia.girschele.com",
        "public_surface_scope": "public",
        "public_surface_http_status_code": 302,
        "public_surface_access_protected": True,
        "public_surface_cloudflare_blocked": False,
        "public_surface_redirect_host": "girschele.cloudflareaccess.com",
        "next_action": "",
        "next_action_href": "https://mymedia.girschele.com",
        "next_action_label": "Open public My Media URL",
        "next_action_method": "get",
        "nextActions": [],
        "mymedia_status": "ready_library_scan_in_progress",
        "mymedia_reason": "mymedia_library_scan_in_progress",
        "connection_status": "connected",
        "container_running": True,
        "library_scan_pending": True,
        "watch_folder_states": ["indexing"],
        "tracks": 12453,
        "failures": [],
        "source_runtime": "ea_live_ops.bridge",
    }


def passing_qbittorrent_staging_hygiene_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.qbittorrent_staging_hygiene.v1",
        "generated_at_utc": fresh_timestamp(),
        "updated_at": fresh_timestamp(),
        "observed_at": fresh_timestamp(),
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready",
        "runtime_status": "ready",
        "runtime_ready": True,
        "source": "script:materialize_qbittorrent_staging_hygiene.py",
        "source_runtime": "qbittorrent.staging_hygiene",
        "blocking_count": 0,
        "advisory_count": 0,
        "blocking_findings": [],
        "advisory_findings": [],
        "next_action_component_keys": [],
        "advisory_action_component_keys": [],
        "next_actions": [],
        "advisory_actions": [],
        "runtime_observation": {
            "qbittorrent_api_ok": True,
            "staging_root_ok": True,
            "orphan_partial_file_count": 0,
            "orphan_partial_gib": 0.0,
            "dead_meta_candidate_count": 0,
            "dead_stalled_candidate_count": 0,
            "dead_checking_candidate_count": 0,
            "dead_meta_requeue_count": 1,
            "dead_stalled_requeue_count": 2,
            "dead_checking_requeue_count": 3,
        },
        "failures": [],
        "secret_leak_detected": False,
        "stdout_tail": "observed_at=2026-07-06T00:50:16Z source=script:materialize_qbittorrent_staging_hygiene.py runtime_status=ready orphan_partials=0",
        "stderr_tail": "",
    }


def passing_host_workload_runtime_health_payload() -> dict[str, object]:
    return {
        "contract_name": "chummer.host_workload_runtime_health.v1",
        "generated_at_utc": fresh_timestamp(),
        "updated_at": fresh_timestamp(),
        "observed_at": fresh_timestamp(),
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "degraded",
        "runtime_status": "degraded",
        "runtime_ready": False,
        "source": "script:materialize_host_workload_runtime_health.py",
        "source_runtime": "host_workload.runtime_health",
        "blocking_count": 0,
        "advisory_count": 1,
        "blocking_findings": [],
        "advisory_findings": ["plex_internxt_mirror_failed"],
        "next_action_component_keys": [],
        "advisory_action_component_keys": ["internxt_mirror"],
        "next_actions": [],
        "advisory_actions": [
            {
                "component_key": "internxt_mirror",
                "component_label": "Internxt mirror lane",
                "action": "inspect_plex_internxt_mirror_failure",
                "reason": "plex_internxt_mirror_failed",
                "href": "",
                "label": "Inspect Internxt mirror failure",
                "method": "manual",
            }
        ],
        "runtime_observation": {
            "qbittorrent_write_probe_ok": True,
            "qbittorrent_fast_resume_rejected_count": 0,
            "pcloud_cache_mode": "writes",
            "internxt_cache_bytes_used": 6654089437,
            "plex_internxt_mirror": {
                "status": "running",
                "phase": "movies",
                "overall_current": 325,
                "overall_total": 2235,
                "eta_seconds": 1800,
            },
        },
        "secret_leak_detected": False,
        "failures": [],
        "stdout_tail": "runtime_status=degraded mirror_status=running mirror_phase=movies mirror_progress=325/2235 mirror_eta_seconds=1800",
        "stderr_tail": "",
    }


def passing_dashboard_receipts(
    published: Path,
    completion: Path,
    registry: Path,
) -> dict[Path, dict[str, object]]:
    return {
        published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
        published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
        published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
        published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
            "status": "pass",
            "base_url": "https://chummer.run",
            "summary": {
                "route_count": 12,
                "failed_count": 0,
                "negative_path_failed_count": 0,
            },
        },
        published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
        published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
        published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
        completion / "UI_FRAME_INTEGRITY.generated.json": {
            "status": "pass",
            "verdict": "READY",
            "base_url": "https://chummer.run",
            "summary": {"checked_pages": 1, "failure_count": 0},
        },
        published / "DESIGN_QUALITY_GATE.generated.json": {
            "status": "pass",
            "verdict": "DESIGN_READY",
        },
        published / "PUBLIC_COPY_LEAK_GATE.generated.json": {
            "status": "pass",
            "verdict": "READY",
        },
        published / "PARTICIPATE_BILLING_HONESTY.generated.json": {
            "status": "pass",
            "verdict": "READY",
        },
        published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
            "status": "pass",
            "verdict": "READY",
        },
        published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
        published / "FINAL_GOLD_JANITOR.generated.json": {
            "status": "pass",
            "verdict": "GOLD_READY",
        },
        published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
        published / "PORTABLE_RECEIPTS_AUDIT.generated.json": passing_portable_receipts_audit_payload(),
        published / "SUPPLY_CHAIN_RELEASE_GATE.generated.json": passing_supply_chain_release_gate_payload(),
        published / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json": passing_public_edge_observability_release_gate_payload(),
        registry / "RELEASE_CHANNEL.generated.json": {
            "status": "published",
            "version": "run-test",
            "channel": "public_stable",
            "supportabilityState": "gold_supported",
            "rolloutState": "public_stable",
        },
    }


def test_dashboard_direct_release_evidence_checks_pass_on_authoritative_green_receipts() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="operator-dashboard-direct-release-evidence-pass-") as temp_dir:
        root = Path(temp_dir)
        published = root / "published"
        completion = root / "completion"
        registry = root / "registry"
        receipts = passing_dashboard_receipts(published, completion, registry)
        write_receipts(receipts)

        with mock.patch.object(module, "PUBLISHED_ROOT", published), \
            mock.patch.object(module, "COMPLETION_ROOT", completion), \
            mock.patch.object(module, "REGISTRY_ROOT", registry), \
            mock.patch.object(module, "ROOT_RELEASE_BLOCKERS_PATH", root / "RELEASE_BLOCKERS.generated.json"):
            payload = module.build_payload(refresh_windows_runtime_receipts=False)
            markdown = module.build_markdown(payload)

    for check_id in (
        "portable_receipts_audit",
        "supply_chain_release_gate",
        "public_edge_observability_release_gate",
    ):
        assert payload["checks"][check_id]["pass"] is True
        assert check_id in payload["release_blocking_checks"]
        assert check_id not in payload["failed_release_blocking_checks"]
    assert payload["status"] == "pass"
    assert "- PASS `portable_receipts_audit`: `pass`" in markdown
    assert "- PASS `supply_chain_release_gate`: `pass`" in markdown
    assert "- PASS `public_edge_observability_release_gate`: `pass`" in markdown


def test_dashboard_fails_closed_on_pass_shaped_portability_supply_chain_and_observability_drift() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="operator-dashboard-direct-release-evidence-fail-") as temp_dir:
        root = Path(temp_dir)
        published = root / "published"
        completion = root / "completion"
        registry = root / "registry"
        receipts = passing_dashboard_receipts(published, completion, registry)

        portable = passing_portable_receipts_audit_payload()
        portable["machine_specific_hits"] = [
            "scan-root-1/native-startup.receipt.json",
            "scan-root-1/unstable.json",
        ]
        portable["machine_specific_path_hits"] = ["scan-root-1/native-startup.receipt.json"]
        portable["artifact_integrity_hits"] = ["scan-root-1/unstable.json"]
        portable["unreadable_artifacts"] = ["scan-root-1/unstable.json"]
        portable["failure_counts"] = {
            "machine_specific_paths": 1,
            "artifact_integrity": 1,
        }
        receipts[published / "PORTABLE_RECEIPTS_AUDIT.generated.json"] = portable

        supply_chain = passing_supply_chain_release_gate_payload()
        supply_chain["blockers"] = ["provenance:fail"]
        supply_chain["checks"]["provenance"] = {"status": "fail"}
        receipts[published / "SUPPLY_CHAIN_RELEASE_GATE.generated.json"] = supply_chain

        observability = passing_public_edge_observability_release_gate_payload()
        observability["failure_count"] = 2
        observability["failures"] = [
            "operator_proof: operator proof is missing",
            "operator_attestation: detached attestation is missing",
        ]
        for check in observability["checks"]:
            if check["id"] in {"operator_proof", "operator_attestation"}:
                check["status"] = "fail"
        observability["operator_intake"] = {
            "state": "waiting_for_external_proof",
            "external_evidence_required": True,
        }
        receipts[
            published / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json"
        ] = observability
        write_receipts(receipts)

        with mock.patch.object(module, "PUBLISHED_ROOT", published), \
            mock.patch.object(module, "COMPLETION_ROOT", completion), \
            mock.patch.object(module, "REGISTRY_ROOT", registry), \
            mock.patch.object(module, "ROOT_RELEASE_BLOCKERS_PATH", root / "RELEASE_BLOCKERS.generated.json"):
            payload = module.build_payload(refresh_windows_runtime_receipts=False)
            markdown = module.build_markdown(payload)

    failed_checks = payload["failed_release_blocking_checks"]
    assert payload["status"] == "fail"
    assert failed_checks == [
        "portable_receipts_audit",
        "public_edge_observability_release_gate",
        "supply_chain_release_gate",
    ]
    for check_id in failed_checks:
        check = payload["checks"][check_id]
        assert check["raw_status"] == "pass"
        assert check["status"] == "fail"
        assert check["pass"] is False
        assert check["semanticFailures"]

    portable_summary = payload["checks"]["portable_receipts_audit"]["summary"]
    assert portable_summary["machine_specific_path_failure_count"] == 1
    assert portable_summary["artifact_integrity_failure_count"] == 1
    assert payload["checks"]["supply_chain_release_gate"]["summary"]["blockers"] == [
        "provenance:fail"
    ]
    assert payload["checks"]["public_edge_observability_release_gate"]["summary"][
        "failed_check_ids"
    ] == ["operator_proof", "operator_attestation"]

    root_ids = [entry["id"] for entry in payload["root_blockers"]]
    assert root_ids.count("portable_receipt_integrity") == 1
    assert root_ids.count("supply_chain_evidence") == 1
    assert root_ids.count("public_edge_observability") == 1
    assert "- FAIL `portable_receipts_audit`: `fail`" in markdown
    assert "machine_specific_paths=1 artifact_integrity=1" in markdown
    assert "- FAIL `supply_chain_release_gate`: `fail`" in markdown
    assert "- FAIL `public_edge_observability_release_gate`: `fail`" in markdown


class OperatorReleaseDashboardParticipateBillingTests(unittest.TestCase):
    def test_dashboard_materializes_into_current_repo_published_root(self) -> None:
        module = load_module()

        self.assertEqual(SCRIPT_PATH.parents[1], module.RUN_SERVICES_ROOT)
        self.assertEqual(SCRIPT_PATH.parents[1] / ".codex-studio" / "published", module.PUBLISHED_ROOT)

    def test_dashboard_release_channel_path_falls_back_to_shared_workspace_when_local_registry_is_missing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-channel-") as temp_dir:
            shared_workspace = Path(temp_dir) / "shared"
            shared_run_services = shared_workspace / "chummer.run-services"
            shared_release_channel = shared_run_services / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
            shared_release_channel.parent.mkdir(parents=True, exist_ok=True)
            shared_release_channel.write_text(
                json.dumps({"status": "published", "version": "run-20260705-040324"}) + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "SHARED_WORKSPACE_ROOT", shared_workspace), \
                mock.patch.object(module, "SHARED_REGISTRY_ROOT", shared_workspace / "chummer-hub-registry" / ".codex-studio" / "published"), \
                mock.patch.object(module, "SHARED_RUN_SERVICES_ROOT", shared_run_services), \
                mock.patch.object(module, "REGISTRY_ROOT", Path(temp_dir) / "missing-registry"):
                self.assertEqual(shared_release_channel, module.resolve_release_channel_path())

    def test_parse_args_enables_release_ready_self_check_by_default(self) -> None:
        module = load_module()

        with mock.patch("sys.argv", ["materialize_operator_release_dashboard.py"]):
            args = module.parse_args()

        self.assertTrue(args.release_ready_self_check)

    def test_parse_args_can_disable_release_ready_self_check(self) -> None:
        module = load_module()

        with mock.patch(
            "sys.argv",
            ["materialize_operator_release_dashboard.py", "--no-release-ready-self-check"],
        ):
            args = module.parse_args()

        self.assertFalse(args.release_ready_self_check)

    def test_dashboard_surfaces_participate_billing_honesty_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {
                    "status": "pass",
                    "generatedAtUtc": "2026-06-24T08:05:00Z",
                    "releaseManifestVersion": "run-20260624-080000",
                    "visibleVersion": "Version run-20260624-080000",
                    "navigationStatus": "pass",
                    "pwaStaticStatus": "pass",
                    "mobileLedgerStatus": "pass",
                    "mobileLedgerPayloadStatus": "opt_in_required",
                    "readyMobileHandoffStatus": "pass",
                    "participateIframeShellStatus": "pass",
                    "flagshipHorizonsStatus": "pass",
                },
                published / "RELEASE_READY.generated.json": {"status": "pass", "verdict": "RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {
                    "status": "fail",
                    "artifact": {
                        "fileName": "chummer-avalonia-win-x64-installer.exe",
                        "sha256": "promoted-sha",
                    },
                    "visualAuditSource": {
                        "status": "pass",
                        "artifactSha256": "stale-sha",
                    },
                    "failures": ["Windows installer visual audit source digest does not match promoted installer"],
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {
                    "status": "external_artifact_required",
                    "promoted_installer": {
                        "file_name": "chummer-avalonia-win-x64-installer.exe",
                        "sha256": "promoted-sha",
                    },
                    "operator_request": {
                        "summary": "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle."
                    },
                    "last_discovery": {
                        "gold_proof_zip": {"status": "not_found"},
                        "visual_sources": {"matching_promoted_count": 0},
                    },
                    "import_command": "python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify",
                },
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertEqual("pass", payload["status"])
        self.assertEqual("NIGHTLY_HANDOFF_READY", payload["verdict"])
        self.assertFalse(payload["release_readiness"]["full_release_ready"])
        self.assertTrue(payload["release_readiness"]["nightly_handoff_ready"])
        self.assertEqual(
            ["windows_installer_visual_audit"],
            payload["release_readiness"]["full_release_blockers"],
        )
        self.assertEqual([], payload["release_readiness"]["release_ready_truth_blockers"])
        self.assertIn("participate_billing_honesty", payload["checks"])
        self.assertTrue(payload["checks"]["participate_billing_honesty"]["pass"])
        self.assertIn("account_handoff_runtime_config", payload["checks"])
        self.assertTrue(payload["checks"]["account_handoff_runtime_config"]["pass"])
        self.assertEqual(payload["account_handoffs"]["billing_mode"], "external_handoff_configured")
        self.assertIn("public_edge_postdeploy_gate", payload["checks"])
        self.assertTrue(payload["checks"]["public_edge_postdeploy_gate"]["pass"])
        self.assertEqual("2026-06-24T08:05:00Z", payload["checks"]["public_edge_postdeploy_gate"]["generated_at_utc"])
        self.assertEqual(payload["public_edge"]["mobile_ledger_payload_status"], "opt_in_required")
        self.assertIn("google_oauth_linking_proof", payload["checks"])
        self.assertFalse(payload["checks"]["google_oauth_linking_proof"]["release_blocking"])
        self.assertEqual("pass", payload["google_oauth_linking"]["status"])
        self.assertIn("windows_installer_visual_audit", payload["checks"])
        self.assertFalse(payload["checks"]["windows_installer_visual_audit"]["release_blocking"])
        self.assertIn("windows_installer_visual_audit_intake_request", payload["checks"])
        self.assertFalse(payload["checks"]["windows_installer_visual_audit_intake_request"]["release_blocking"])
        self.assertTrue(payload["checks"]["windows_installer_visual_audit_intake_request"]["pass"])
        self.assertEqual(payload["windows_installer_visual_audit"]["artifact_sha256"], "promoted-sha")
        self.assertEqual(payload["windows_installer_visual_audit"]["visual_source_artifact_sha256"], "stale-sha")
        self.assertEqual(payload["windows_installer_visual_audit"]["matching_promoted_visual_source_count"], 0)
        self.assertEqual(
            payload["windows_installer_visual_audit"]["import_command"],
            "python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify",
        )

    def test_dashboard_surfaces_google_oauth_operator_handoff_context(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-google-oauth-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {"status": "pass"},
                published / "RELEASE_READY.generated.json": {"status": "fail", "verdict": "NOT_RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {
                    "status": "fail",
                    "failures": [
                        "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                        "operator_request_artifacts: operator ask delivery is stale; resend current ask: python3 resend-google",
                    ],
                    "operator_end_to_end_evidence": {
                        "pass": False,
                        "exists": False,
                        "path": "/tmp/operator-evidence.json",
                    },
                    "operator_request_artifacts": {
                        "pass": True,
                        "request_status": "operator_action_required",
                        "request_receipt_path": "/tmp/operator-request.generated.json",
                        "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
                        "operator_ask_metadata_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json",
                        "operator_evidence_template_path": "/tmp/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
                        "operator_ask_receipt_name": "google-oauth-linking-operator-ask.receipt.json",
                        "operator_ask_send_command": "python3 send-google",
                        "operator_ask_resend_command": "python3 resend-google",
                        "operator_ask_delivery_status": "sent",
                        "operator_ask_delivery_generated_at_utc": "2026-07-05T09:35:52Z",
                        "operator_ask_delivery_receipt_path": "/tmp/google-ask.receipt.json",
                        "operator_ask_delivery_matches_current_text": False,
                        "operator_ask_delivery_needs_resend": True,
                        "preferred_drop_path": "/tmp/google-proof.zip",
                        "import_command": "python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py /tmp/google-proof.zip --verify",
                        "auto_import_watch_command": "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --wait-seconds 900",
                        "post_import_verify_command": "python3 scripts/verify_google_oauth_linking_proof.py --require-pass",
                    },
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {"status": "fail"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {"status": "external_artifact_required"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260705-040324",
                    "publishedAt": "2026-07-05T04:05:30Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        self.assertEqual("fail", payload["checks"]["google_oauth_linking_proof"]["status"])
        self.assertFalse(payload["checks"]["google_oauth_linking_proof"]["release_blocking"])
        self.assertEqual("operator_action_required", payload["google_oauth_linking"]["request_status"])
        self.assertEqual("/tmp/operator-request.generated.json", payload["google_oauth_linking"]["request_receipt_path"])
        self.assertEqual("/tmp/operator-evidence.json", payload["google_oauth_linking"]["operator_evidence_path"])
        self.assertEqual("python3 send-google", payload["google_oauth_linking"]["operator_ask_send_command"])
        self.assertEqual("python3 resend-google", payload["google_oauth_linking"]["operator_ask_resend_command"])
        self.assertEqual("sent", payload["google_oauth_linking"]["operator_ask_delivery_status"])
        self.assertFalse(payload["google_oauth_linking"]["operator_ask_delivery_matches_current_text"])
        self.assertTrue(payload["google_oauth_linking"]["operator_ask_delivery_needs_resend"])
        self.assertEqual("/tmp/google-proof.zip", payload["google_oauth_linking"]["preferred_drop_path"])
        self.assertIn("import_google_oauth_linking_operator_evidence_artifact.py", payload["google_oauth_linking"]["import_command"])
        self.assertIn("auto_import_google_oauth_linking_operator_evidence.py", payload["google_oauth_linking"]["auto_import_watch_command"])
        self.assertIn("## Google OAuth Handoff", markdown)
        self.assertIn("`python3 resend-google`", markdown)

    def test_dashboard_full_release_blockers_include_release_ready_when_release_gate_fails(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-ready-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {"status": "pass"},
                published / "RELEASE_READY.generated.json": {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failed_gates": ["verify_release_channel", "verify_google_oauth_linking_proof"],
                    "release_truth_blockers": [
                        "release channel channel is preview, not a flagship stable lane",
                        "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
                    ],
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {"status": "fail"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {"status": "external_artifact_required"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertEqual("pass", payload["status"])
        self.assertEqual("NIGHTLY_HANDOFF_READY", payload["verdict"])
        self.assertEqual(
            ["release_ready", "windows_installer_visual_audit"],
            payload["release_readiness"]["full_release_blockers"],
        )
        self.assertEqual(
            [
                "verify_release_channel",
                "verify_google_oauth_linking_proof",
            ],
            payload["release_readiness"]["release_ready_failed_gates"],
        )
        self.assertEqual(
            [
                "release channel channel is preview, not a flagship stable lane",
                "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
            ],
            payload["release_readiness"]["release_ready_truth_blockers"],
        )
        self.assertEqual(
            [
                "release channel channel is preview, not a flagship stable lane",
                "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
                "windows_installer_visual_audit",
            ],
            payload["release_readiness"]["full_release_blocker_details"],
        )

    def test_dashboard_release_ready_self_check_recovers_current_truth_when_receipt_is_stale(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-ready-self-check-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {"status": "pass"},
                published / "RELEASE_READY.generated.json": {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failures": ["FAIL verify_windows_installer_visual_audit"],
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {"status": "fail"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {"status": "external_artifact_required"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(
                    module,
                    "current_release_truth_launch_blockers",
                    return_value=[
                        "release channel channel is preview, not a flagship stable lane",
                        "release channel supportability is not gold_supported",
                    ],
                ):
                payload = module.build_payload(release_ready_self_check=True)

        self.assertTrue(payload["release_readiness"]["release_ready_self_check"])
        self.assertEqual(
            [
                "release channel channel is preview, not a flagship stable lane",
                "release channel supportability is not gold_supported",
            ],
            payload["release_readiness"]["release_ready_truth_blockers"],
        )
        self.assertEqual(
            [
                "release channel channel is preview, not a flagship stable lane",
                "release channel supportability is not gold_supported",
                "windows_installer_visual_audit",
            ],
            payload["release_readiness"]["full_release_blocker_details"],
        )

    def test_dashboard_requires_public_edge_postdeploy_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-edge-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": {"status": "pass", "verdict": "RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertFalse(payload["checks"]["public_edge_postdeploy_gate"]["pass"])

    def test_dashboard_blocks_participate_billing_honesty_unexpected_verdict(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-participate-verdict-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {
                    "status": "pass",
                    "verdict": "READY_BUT_NOT_READY",
                },
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        participate = payload["checks"]["participate_billing_honesty"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertIn("participate_billing_honesty", payload["failures"])
        self.assertFalse(participate["pass"])
        self.assertEqual("fail", participate["status"])
        self.assertEqual(
            ["participate_billing_honesty receipt has unexpected verdict"],
            participate["semanticFailures"],
        )
        self.assertIn("participate_billing_honesty semantic proof failed", participate["failures"])
        self.assertIn("participate_billing_honesty receipt has unexpected verdict", markdown)

    def test_dashboard_blocks_account_handoff_runtime_config_unexpected_verdict(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-account-handoff-verdict-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "NOT_READY_BUT_PASS_SHAPED",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        account_handoff = payload["checks"]["account_handoff_runtime_config"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertIn("account_handoff_runtime_config", payload["failures"])
        self.assertFalse(account_handoff["pass"])
        self.assertEqual("fail", account_handoff["status"])
        self.assertEqual(
            ["account_handoff_runtime_config receipt has unexpected verdict"],
            account_handoff["semanticFailures"],
        )
        self.assertIn("account_handoff_runtime_config semantic proof failed", account_handoff["failures"])
        self.assertIn("account_handoff_runtime_config receipt has unexpected verdict", markdown)

    def test_dashboard_blocks_design_quality_gate_unexpected_verdict(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-design-verdict-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {
                    "status": "pass",
                    "verdict": "READY_BUT_NOT_DESIGN_READY",
                },
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        design = payload["checks"]["design_quality_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertIn("design_quality_gate", payload["failures"])
        self.assertFalse(design["pass"])
        self.assertEqual("fail", design["status"])
        self.assertEqual(
            ["design_quality_gate receipt has unexpected verdict"],
            design["semanticFailures"],
        )
        self.assertIn("design_quality_gate semantic proof failed", design["failures"])
        self.assertIn("design_quality_gate receipt has unexpected verdict", markdown)

    def test_dashboard_blocks_ui_frame_integrity_unexpected_verdict(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-ui-frame-verdict-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY_BUT_NOT_FRAME_READY",
                    "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        ui_frame = payload["checks"]["ui_frame_integrity"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertIn("ui_frame_integrity", payload["failures"])
        self.assertFalse(ui_frame["pass"])
        self.assertEqual("fail", ui_frame["status"])
        self.assertEqual(
            ["ui_frame_integrity receipt has unexpected verdict"],
            ui_frame["semanticFailures"],
        )
        self.assertIn("ui_frame_integrity semantic proof failed", ui_frame["failures"])
        self.assertIn("ui_frame_integrity receipt has unexpected verdict", markdown)

    def test_dashboard_blocks_release_channel_until_gold_supported_and_unblocked(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-channel-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = root / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = root / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    **passing_release_ready_payload(),
                    "blocking_gate_artifacts": {
                        "windows_installer_visual_audit": {
                            "stage_release_build_handoff_path": "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
                            "stage_release_build_handoff_status": "fail",
                            "stage_windows_visual_proof_handoff_path": "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
                            "stage_windows_visual_proof_handoff_status": "ready_for_windows_host",
                            "stage_windows_visual_proof_handoff_summary": "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
                        },
                    },
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": fresh_timestamp(),
                    "channel": "stable",
                    "supportabilityState": "review_required",
                    "rolloutState": "coverage_incomplete",
                },
            }
            write_receipts(receipts)
            root_release_blockers = root / "RELEASE_BLOCKERS.generated.json"
            root_blockers_generated_at = fresh_timestamp()
            root_release_blockers.write_text(
                json.dumps(
                    {
                        "generated_at": root_blockers_generated_at,
                        "blockers": [
                            {
                                "blocker_id": "release_posture:non_flagship_channel",
                                "stable_promotion_command": (
                                    "RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260624-080000 "
                                    "bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh "
                                    "/tmp/downloads /tmp/downloads"
                                ),
                                "post_promotion_verify_command": (
                                    "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && "
                                    "python3 scripts/materialize_operator_release_dashboard.py && "
                                    "python3 scripts/final_gold_janitor.py && "
                                    "python3 ../scripts/release/_release_gate_common.py && "
                                    "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\""
                                ),
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "ROOT_RELEASE_BLOCKERS_PATH", root_release_blockers), \
                mock.patch.object(
                    module,
                    "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH",
                    root / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json",
                ):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        release_channel = payload["checks"]["release_channel"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertFalse(release_channel["pass"])
        self.assertEqual("review_required", release_channel["supportability_state"])
        self.assertEqual("coverage_incomplete", release_channel["rollout_state"])
        self.assertIn("release_channel", payload["release_blocking_checks"])
        self.assertIn("release_channel", payload["failed_release_blocking_checks"])
        self.assertEqual(payload["failures"], payload["release_blocking_failures"])
        self.assertEqual(
            len(payload["failed_release_blocking_checks"]),
            payload["summary"]["failed_release_blocking_check_count"],
        )
        self.assertIn("release_channel", payload["summary"]["failed_release_blocking_checks"])
        self.assertEqual(len(payload["release_blocking_checks"]), payload["summary"]["release_blocking_check_count"])
        self.assertEqual(len(payload["failures"]), payload["summary"]["failure_count"])
        self.assertIn("release_channel", payload["failures"])
        self.assertEqual(1, payload["summary"]["root_blocker_count"])
        self.assertIn("release_lane_posture", payload["summary"]["root_blocker_ids"])
        self.assertEqual(["release_posture:non_flagship_channel"], payload["root_blocker_ids"])
        self.assertEqual(root_blockers_generated_at, payload["root_blockers_generated_at"])
        self.assertEqual(str(root_release_blockers), payload["root_release_truth_source"])
        self.assertTrue(payload["local_surface_status"]["all_passing"])
        self.assertIn("release channel supportability is not gold_supported", release_channel["failures"])
        self.assertIn("release channel rollout is blocking: coverage_incomplete", release_channel["failures"])
        posture = next(item for item in payload["root_blockers"] if item["id"] == "release_lane_posture")
        self.assertEqual(
            "RELEASE_CHANNEL=public_stable RELEASE_VERSION=run-20260624-080000 "
            "bash /docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh "
            "/tmp/downloads /tmp/downloads",
            posture["stable_promotion_command"],
        )
        self.assertEqual(
            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && "
            "python3 scripts/materialize_operator_release_dashboard.py && "
            "python3 scripts/final_gold_janitor.py && "
            "python3 ../scripts/release/_release_gate_common.py && "
            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
            posture["post_promotion_verify_command"],
        )
        self.assertEqual(posture["stable_promotion_command"], payload["stable_promotion_command"])
        self.assertEqual(posture["post_promotion_verify_command"], payload["post_promotion_verify_command"])
        self.assertIn("- FAIL `release_channel`: `fail`", markdown)
        self.assertIn("`release_lane_posture`: Live release channel is not yet on a flagship stable lane.", markdown)
        self.assertIn("stable promotion command:", markdown)
        self.assertIn("post-promotion verify command:", markdown)
        self.assertIn("- local flagship surfaces: all_passing=True", markdown)
        self.assertIn("supportability=review_required rollout=coverage_incomplete", markdown)

    def test_dashboard_blocks_release_channel_when_workspace_portal_manifest_drifts_from_registry(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(
            prefix="operator-dashboard-release-channel-drift-",
            dir=module.ROOT / ".tmp",
        ) as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            completion = root / "completion"
            registry = root / "registry"
            portal = root / "workspace-portal"
            published.mkdir(parents=True, exist_ok=True)
            completion.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)
            portal.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": fresh_timestamp(),
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)

            drift_path = portal / "RELEASE_CHANNEL.generated.json"
            drift_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-old",
                        "publishedAt": fresh_timestamp(),
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            portable_drift_path = module.display_path(drift_path.resolve())

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "COMPLETION_ROOT", completion),
                mock.patch.object(module, "REGISTRY_ROOT", registry),
                mock.patch.object(module, "WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES", (drift_path,)),
            ):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        release_channel = payload["checks"]["release_channel"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(release_channel["pass"])
        self.assertEqual(1, len(release_channel["workspace_portal_release_channels_checked"]))
        self.assertEqual(1, len(release_channel["workspace_portal_release_channel_mismatches"]))
        self.assertTrue(portable_drift_path.startswith(".tmp/"))
        self.assertEqual(
            portable_drift_path,
            release_channel["workspace_portal_release_channels_checked"][0]["path"],
        )
        self.assertTrue(
            any(
                item.startswith(
                    f"workspace portal release channel artifact {portable_drift_path} disagrees with authoritative registry receipt"
                )
                for item in release_channel["failures"]
            )
        )
        self.assertNotIn(str(module.ROOT.resolve()), release_channel["failures"][0])
        drift_markdown_lines = [
            line
            for line in markdown.splitlines()
            if "workspace portal release channel artifact" in line
        ]
        self.assertTrue(drift_markdown_lines)
        self.assertTrue(
            all(str(module.ROOT.resolve()) not in line for line in drift_markdown_lines)
        )
        self.assertIn("local channel=stable, version=run-old", release_channel["failures"][0])
        self.assertIn("authoritative channel=stable, version=run-test", release_channel["failures"][0])
        self.assertIn("workspace portal release channel artifact", markdown)
        self.assertEqual(1, markdown.count("workspace portal release channel artifact"))

    def test_dashboard_dedupes_workspace_portal_release_channel_alias_paths(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(
            prefix="operator-dashboard-release-channel-alias-",
            dir=module.ROOT / ".tmp",
        ) as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            completion = root / "completion"
            registry = root / "registry"
            portal = root / "workspace-portal"
            published.mkdir(parents=True, exist_ok=True)
            completion.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)
            portal.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": fresh_timestamp(),
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)

            drift_path = portal / "RELEASE_CHANNEL.generated.json"
            drift_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-old",
                        "publishedAt": fresh_timestamp(),
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            alias_path = portal / "RELEASE_CHANNEL.alias.generated.json"
            alias_path.symlink_to(drift_path)
            portable_drift_path = module.display_path(drift_path.resolve())

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "COMPLETION_ROOT", completion),
                mock.patch.object(module, "REGISTRY_ROOT", registry),
                mock.patch.object(module, "WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES", (drift_path, alias_path)),
            ):
                payload = module.build_payload()

        release_channel = payload["checks"]["release_channel"]
        self.assertEqual(1, len(release_channel["workspace_portal_release_channels_checked"]))
        self.assertEqual(1, len(release_channel["workspace_portal_release_channel_mismatches"]))
        self.assertEqual(1, len(release_channel["failures"]))
        self.assertTrue(portable_drift_path.startswith(".tmp/"))
        self.assertEqual(
            portable_drift_path,
            release_channel["workspace_portal_release_channels_checked"][0]["path"],
        )
        self.assertIn(portable_drift_path, release_channel["failures"][0])
        self.assertNotIn(str(module.ROOT.resolve()), release_channel["failures"][0])

    def test_dashboard_blocks_release_ready_failed_gates(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-ready-") as temp_dir:
            root = Path(temp_dir)
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failed_gates": ["verify_public_release_snapshot_truth"],
                    "blocking_gate_artifacts": {
                        "public_release_snapshot_readonly_audit": {
                            "path": str(root / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"),
                            "exists": True,
                            "load_status": "loaded",
                            "status": "pass",
                            "verdict": "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                            "summary": "Snapshot is internally consistent with current launch truth, but the release is not launch-ready.",
                            "expected_top_level_blocker_ids": [
                                "release_posture:non_flagship_channel",
                                "release_truth:windows_installer_visual_audit",
                            ],
                            "expected_release_truth_blockers": ["windows_installer_visual_audit"],
                        },
                    },
                },
                root / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json": {
                    "status": "fail",
                    "verdict": "FALLBACK_SHOULD_NOT_WIN",
                    "summary": "This fallback receipt should not override the embedded release_ready audit.",
                    "expected_top_level_blocker_ids": ["fallback:stale"],
                    "expected_release_truth_blockers": ["fallback"],
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(
                    module,
                    "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH",
                    root / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json",
                ):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        release_ready = payload["checks"]["release_ready"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertFalse(release_ready["pass"])
        self.assertTrue(release_ready.get("release_blocking", True))
        self.assertIn("release_ready", payload["failures"])
        self.assertEqual(["verify_public_release_snapshot_truth"], release_ready["failed_gates"])
        snapshot_audit = release_ready["public_release_snapshot_readonly_audit"]
        self.assertEqual("fail", snapshot_audit["status"])
        self.assertEqual("pass", snapshot_audit["raw_status"])
        self.assertFalse(snapshot_audit["pass"])
        self.assertEqual("SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY", snapshot_audit["verdict"])
        self.assertEqual(
            ["release_posture:non_flagship_channel", "release_truth:windows_installer_visual_audit"],
            snapshot_audit["expected_top_level_blocker_ids"],
        )
        self.assertEqual("loaded", snapshot_audit["load_status"])
        self.assertIn("- FAIL `release_ready`: `fail`", markdown)
        self.assertIn("failed gates: verify_public_release_snapshot_truth", markdown)
        self.assertIn("snapshot truth audit: status=fail verdict=SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY", markdown)
        self.assertIn("snapshot truth audit raw status: pass", markdown)

    def test_dashboard_blocks_pass_shaped_public_copy_leak_gate_with_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-copy-leak-failures-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "failures": ["copied public copy leak detected on /downloads"],
                    "failed_gates": ["verify_public_copy"],
                },
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        copy_gate = payload["checks"]["public_copy_leak_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertFalse(copy_gate["pass"])
        self.assertEqual("fail", copy_gate["status"])
        self.assertIn("public_copy_leak_gate", payload["failures"])
        self.assertEqual(
            ["copied public copy leak detected on /downloads"],
            copy_gate["failures"],
        )
        self.assertEqual(["verify_public_copy"], copy_gate["failed_gates"])
        self.assertIn("- FAIL `public_copy_leak_gate`: `fail`", markdown)
        self.assertIn("failed gates: verify_public_copy", markdown)

    def test_release_ready_self_check_skips_only_previous_release_ready_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-ready-self-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failed_gates": ["verify_previous_run"],
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload(release_ready_self_check=True)
                markdown = module.build_markdown(payload)

        release_ready = payload["checks"]["release_ready"]
        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertEqual("OPERABLE_RELEASE_READY", payload["verdict"])
        self.assertTrue(release_ready["pass"])
        self.assertFalse(release_ready["release_blocking"])
        self.assertTrue(release_ready["self_check_skipped"])
        self.assertEqual("self_check_skipped", release_ready["status"])
        self.assertNotIn("release_ready", payload["failures"])
        self.assertIn("- PASS `release_ready`: `self_check_skipped` (operator context, not release-blocking)", markdown)
        self.assertIn(
            "mobile PWA offline cache: status=pass version=v17 navigation=network_only private_state=open_tab_only",
            markdown,
        )
        self.assertIn("role PWA manifests: count=2", markdown)
        self.assertIn("/manifest.player.webmanifest", markdown)
        self.assertIn("/mobile/player?role=Player", markdown)
        self.assertIn("/manifest.gm.webmanifest", markdown)
        self.assertIn("/mobile/gm?role=GameMaster", markdown)
        self.assertIn("static_paths=['/manifest.player.webmanifest', '/manifest.gm.webmanifest', '/mobile.css', '/mobile-turn-companion.js']", markdown)
        self.assertIn("personalized_ledger_cached=False", markdown)
        self.assertIn(
            "front-door mobile launch: player_http=200 player_role=Player "
            "player_manifest=/manifest.player.webmanifest player_blazor=interactive-server "
            "player_rybbit=True player_rybbit_skip_mobile=True player_rybbit_mask_api=True "
            "player_rybbit_replay_block=True gm_http=200 gm_role=GameMaster "
            "gm_manifest=/manifest.gm.webmanifest gm_blazor=interactive-server gm_rybbit=True "
            "gm_rybbit_skip_mobile=True gm_rybbit_mask_api=True gm_rybbit_replay_block=True",
            markdown,
        )
        self.assertIn(
            "front-door session handoff: player_preserves_session=True player_preserves_role=True "
            "player_strips_device=True player_identity_redacted=True gm_preserves_session=True "
            "gm_preserves_role=True gm_strips_device=True gm_identity_redacted=True",
            markdown,
        )

    def test_release_ready_self_check_still_blocks_real_dependency_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-self-real-fail-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            windows = passing_windows_installer_visual_audit_payload()
            windows.update(
                {
                    "status": "fail",
                    "failures": ["Windows installer visual audit source digest does not match promoted installer"],
                }
            )
            windows["visualAuditSource"]["artifactDigestMatchesPromoted"] = False
            windows["visualAuditSource"]["requiresRecapture"] = True
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": windows,
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failed_gates": ["verify_previous_run"],
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload(release_ready_self_check=True)

        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertTrue(payload["failures"])
        self.assertNotIn("release_ready", payload["failures"])
        self.assertFalse(payload["checks"]["windows_installer_visual_audit"]["pass"])
        self.assertFalse(payload["checks"]["release_ready"]["release_blocking"])

    def test_release_ready_self_check_recovers_wrapper_only_flagship_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-self-wrapper-flagship-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json": (
                    failing_flagship_product_readiness_gate_payload_with_failed_nested_audits()
                ),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failed_gates": ["verify_previous_run"],
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload(release_ready_self_check=True)

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertEqual("OPERABLE_RELEASE_READY", payload["verdict"])
        self.assertTrue(payload["checks"]["flagship_product_readiness"]["pass"])
        self.assertTrue(payload["checks"]["flagship_product_readiness"]["release_blocking_recovered"])
        self.assertEqual(
            ["release_ready:self_check_skipped"],
            payload["checks"]["flagship_product_readiness"]["recovered_because_of_checks"],
        )
        self.assertNotIn("flagship_product_readiness", payload["failures"])

    def test_dashboard_blocks_release_ready_semantic_contradictions(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-ready-semantics-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            release_ready_payload = passing_release_ready_payload()
            release_ready_payload.update(
                {
                    "contract_name": "wrong.release.ready",
                    "returncode": 1,
                    "timed_out": True,
                    "saw_release_ready_marker": False,
                    "not_release_ready_markers": ["NOT_RELEASE_READY"],
                    "failed_gates": ["verify_desktop_release_matrix"],
                }
            )
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": release_ready_payload,
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        release_ready = payload["checks"]["release_ready"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertFalse(release_ready["pass"])
        self.assertEqual("fail", release_ready["status"])
        self.assertIn("release_ready", payload["failures"])
        self.assertIn("release_ready semantic proof failed", release_ready["failures"])
        self.assertIn("release_ready receipt has unexpected contract", release_ready["semanticFailures"])
        self.assertIn("release_ready verifier returncode is not zero", release_ready["semanticFailures"])
        self.assertIn("release_ready verifier timed_out is not false", release_ready["semanticFailures"])
        self.assertIn("release_ready receipt did not record RELEASE_READY marker", release_ready["semanticFailures"])
        self.assertIn("release_ready receipt contains NOT_RELEASE_READY markers", release_ready["semanticFailures"])
        self.assertIn("release_ready receipt contains failed gates", release_ready["semanticFailures"])
        self.assertIn("release_ready semantic proof failed", markdown)
        self.assertIn("release_ready verifier returncode is not zero", markdown)
        self.assertIn("failed gates: verify_desktop_release_matrix", markdown)

    def test_dashboard_blocks_failed_public_edge_postdeploy_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {
                    "status": "fail",
                    "generatedAtUtc": "2026-06-30T08:00:00Z",
                    "failures": [
                        "public-edge deploy preflight is not pass",
                        "downloads version marker proof is not pass",
                        "Participate iframe shell proof is not pass",
                    ],
                    "preflightStatus": "fail",
                    "preflightActiveLockCount": 4,
                    "preflightBlockingLockCount": 1,
                    "preflightStaleLookingLockCount": 4,
                    "preflightStaleForeignLockCount": 3,
                    "preflightStaleForeignLocksIgnored": True,
                    "preflightOverlayRoot": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
                    "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource": False,
                    "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256": "a" * 64,
                    "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256": "b" * 64,
                    "preflightOverlayBuildInfoSourceFingerprintMissingKeys": [],
                    "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys": ["landing"],
                    "downloadsStatus": "fail",
                    "downloadsHasMarker": False,
                    "statusRedirectHasMarker": False,
                    "visibleVersion": "Version run-20260627-005402",
                    "statusRedirectVersion": "Version run-20260627-005402",
                    "expectedReleaseVersion": "run-20260624-080000",
                    "visibleVersionMatchesReleaseChannel": False,
                    "statusRedirectVersionMatchesReleaseChannel": False,
                    "pwaStaticStatus": "pass",
                    "mobileLedgerStatus": "pass",
                    "readyMobileHandoffStatus": "pass",
                    "downloadsStatusBrowserStatus": "fail",
                    "mobilePwaViewportStatus": "fail",
                    "mobilePwaViewportRouteCount": 6,
                    "mobilePwaViewportViewportCount": 3,
                    "mobilePwaViewportRoutes": ["/mobile", "/mobile/player", "/mobile/gm", "/mobile/observer", "/play", "/play/continuity"],
                    "mobilePwaViewportMissingRoutes": [],
                    "participateIframeShellStatus": "fail",
                    "participateIframeRouteCount": 2,
                    "participateIframeRouteIframeCount": 2,
                    "participateIframeRouteOfflineFallbackCount": 0,
                    "frontdoorNavigationStatus": "fail",
                    "frontdoorNavigationGatedTargets": ["Build", "Play"],
                    "frontdoorNavigationPublicTargets": [],
                    "frontdoorNavigationPlayRoute": "/mobile/player",
                    "frontdoorNavigationPlaySignInRoute": "/login?next=%2Fmobile%2Fplayer",
                    "frontdoorNavigationDirectPlayerRoute": "/mobile/player",
                    "frontdoorNavigationLedgerPrimary": False,
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_edge = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge["pass"])
        self.assertTrue(public_edge.get("release_blocking", True))
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertIn("downloads version marker proof is not pass", public_edge["failures"])
        self.assertEqual(
            "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
            public_edge["summary"]["preflight_overlay_root"],
        )
        self.assertFalse(public_edge["summary"]["preflight_overlay_source_fingerprint_matches_current_source"])
        self.assertEqual(["landing"], public_edge["summary"]["preflight_overlay_source_fingerprint_mismatched_keys"])
        self.assertEqual("fail", public_edge["summary"]["participate_iframe_shell_status"])
        self.assertEqual(2, public_edge["summary"]["participate_iframe_route_iframe_count"])
        self.assertEqual("fail", public_edge["summary"]["mobile_pwa_viewport_status"])
        self.assertEqual(3, public_edge["summary"]["mobile_pwa_viewport_viewport_count"])
        self.assertEqual("fail", public_edge["summary"]["frontdoor_navigation_status"])
        self.assertEqual(["Build", "Play"], public_edge["summary"]["frontdoor_navigation_gated_targets"])
        self.assertEqual([], public_edge["summary"]["frontdoor_navigation_public_targets"])
        self.assertEqual("/mobile/player", public_edge["summary"]["frontdoor_navigation_play_route"])
        self.assertEqual("/login?next=%2Fmobile%2Fplayer", public_edge["summary"]["frontdoor_navigation_play_sign_in_route"])
        self.assertIn(
            "overlay_root=/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app overlay_source_match=False overlay_missing=[] overlay_mismatched=['landing'] downloads=fail downloads_marker=False status_marker=False visible_version=Version run-20260627-005402 status_version=Version run-20260627-005402 expected_version=run-20260624-080000 version_match=False status_version_match=False",
            markdown,
        )
        self.assertIn("participate iframe shell: status=fail routes=2 iframe_routes=2 fallback_routes=0", markdown)
        self.assertIn("mobile PWA viewport: status=fail routes=6 viewports=3 missing_routes=[]", markdown)
        self.assertIn("front-door navigation: status=fail gated_targets=['Build', 'Play'] public_targets=[] play_route=/mobile/player play_sign_in_route=/login?next=%2Fmobile%2Fplayer direct_player_route=/mobile/player ledger_primary=False", markdown)
        self.assertIn("failures: public-edge deploy preflight is not pass, downloads version marker proof is not pass, Participate iframe shell proof is not pass", markdown)

    def test_dashboard_surfaces_public_release_snapshot_runtime_override_for_public_edge(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-runtime-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            snapshot = Path(temp_dir) / "PUBLIC_RELEASE_SNAPSHOT.generated.json"

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)
            snapshot.write_text(
                json.dumps(
                    {
                        "release_truth": {
                            "public_edge_postdeploy_gate": {
                                "status": "fail",
                                "verdict": "RUNTIME_PREFLIGHT_FAIL",
                                "generated_at": fresh_timestamp(),
                                "runtime_override_applied": True,
                                "runtime_override_reason": "Current mounted public-edge preflight status=fail. activeLockCount=2 foreignLockCount=2 staleForeignLockCount=2.",
                                "runtime_observation": {
                                    "status": "fail",
                                    "overlay_root": "/tmp/public-edge-overlay/app",
                                    "active_lock_count": 2,
                                    "foreign_lock_count": 2,
                                    "stale_foreign_lock_count": 2,
                                    "blocking_findings": [
                                        "active_build_lane: bash pid 191868 matches build-chummer6-linux",
                                        "public_edge_overlay_marker_missing: overlay .codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json missing markers",
                                    ],
                                },
                            }
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "COMPLETION_ROOT", completion),
                mock.patch.object(module, "REGISTRY_ROOT", registry),
                mock.patch.object(module, "PUBLIC_RELEASE_SNAPSHOT_PATH", snapshot),
            ):
                payload = module.build_payload()

        public_edge = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge["pass"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertIn(
            "public_edge_postdeploy_gate release truth verdict is RUNTIME_PREFLIGHT_FAIL",
            public_edge["failures"],
        )
        self.assertEqual("RUNTIME_PREFLIGHT_FAIL", public_edge["summary"]["release_truth_verdict"])
        self.assertTrue(public_edge["summary"]["release_truth_runtime_override_applied"])
        self.assertEqual("fail", public_edge["summary"]["release_truth_runtime_observation_status"])
        self.assertEqual("/tmp/public-edge-overlay/app", public_edge["summary"]["release_truth_runtime_overlay_root"])
        self.assertIn(
            "public_edge_overlay_marker_missing: overlay .codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json missing markers",
            public_edge["summary"]["release_truth_runtime_blocking_findings"],
        )
        markdown = module.build_markdown(payload)
        self.assertIn(
            "live release truth: verdict=RUNTIME_PREFLIGHT_FAIL status=fail runtime_override=True runtime_status=fail runtime_active_locks=2 runtime_foreign_locks=2 runtime_stale_foreign_locks=2",
            markdown,
        )

    def test_dashboard_surfaces_local_overlay_and_preflight_context_for_public_edge(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-overlay-context-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "PUBLIC_EDGE_DEPLOY_PREFLIGHT.generated.json": {
                    "status": "pass",
                    "activeLockCount": 2,
                    "blockingLockCount": 0,
                    "foreignLockCount": 2,
                    "ignoredForeignLockCount": 2,
                    "foreignLocksIgnored": True,
                    "allowForeignBuildLocks": False,
                    "staleLookingLockCount": 2,
                    "staleForeignLockCount": 2,
                    "staleForeignLocksIgnored": True,
                    "allowStaleForeignBuildLocks": False,
                    "autoIgnoredStaleForeignLockCount": 2,
                    "autoIgnoreStaleForeignLockSeconds": 86400,
                    "overlayRoot": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
                    "overlayBuildInfoSourceFingerprint": {
                        "aggregateMatchesCurrentSource": True,
                        "recordedAggregateSha256": "a" * 64,
                        "expectedAggregateSha256": "a" * 64,
                        "missingKeys": [],
                        "mismatchedKeys": [],
                    },
                    "findings": [],
                },
                published / "PUBLIC_EDGE_PORTAL_OVERLAY_PUBLISH.generated.json": {
                    "status": "pass",
                    "activationStatus": "staged_only",
                    "reuseStaging": True,
                    "verification": {
                        "receiptStatus": "pass",
                        "receiptPath": str(published / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json"),
                        "landingMarkerStatus": "pass",
                        "landingMissingMarkers": [],
                        "landingBrowserRedirect": {
                            "status": "pass",
                            "pathMatches": True,
                            "hashMatches": True,
                            "finalUrl": "http://127.0.0.1:40607/mobile/player#turn-runsite-card",
                        },
                        "localLiveSurfaceParity": {
                            "status": "pass",
                            "failureCount": 0,
                            "failures": [],
                            "verdict": "LIVE_SURFACE_PARITY_READY",
                            "receiptPath": str(published / "LIVE_SURFACE_PARITY.local-overlay.generated.json"),
                        },
                    },
                },
                published / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json": {"status": "pass"},
                published / "LIVE_SURFACE_PARITY.local-overlay.generated.json": {
                    "status": "pass",
                    "verdict": "LIVE_SURFACE_PARITY_READY",
                    "failures": [],
                },
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "COMPLETION_ROOT", completion),
                mock.patch.object(module, "REGISTRY_ROOT", registry),
            ):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_edge = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual(2, public_edge["summary"]["preflight_foreign_lock_count"])
        self.assertEqual(2, public_edge["summary"]["preflight_ignored_foreign_lock_count"])
        self.assertTrue(public_edge["summary"]["preflight_foreign_locks_ignored"])
        self.assertFalse(public_edge["summary"]["preflight_allow_foreign_build_locks"])
        self.assertEqual(2, public_edge["summary"]["preflight_auto_ignored_stale_foreign_lock_count"])
        self.assertEqual(86400, public_edge["summary"]["preflight_auto_ignore_stale_foreign_lock_seconds"])
        self.assertEqual("pass", public_edge["summary"]["local_overlay_publish_status"])
        self.assertEqual("staged_only", public_edge["summary"]["local_overlay_activation_status"])
        self.assertTrue(public_edge["summary"]["local_overlay_reuse_staging"])
        self.assertEqual("pass", public_edge["summary"]["local_overlay_verify_receipt_status"])
        self.assertEqual("pass", public_edge["summary"]["local_overlay_landing_marker_status"])
        self.assertEqual("pass", public_edge["summary"]["local_overlay_landing_browser_redirect_status"])
        self.assertTrue(public_edge["summary"]["local_overlay_landing_browser_redirect_path_matches"])
        self.assertTrue(public_edge["summary"]["local_overlay_landing_browser_redirect_hash_matches"])
        self.assertEqual("pass", public_edge["summary"]["local_overlay_local_live_surface_parity_status"])
        self.assertEqual(0, public_edge["summary"]["local_overlay_local_live_surface_parity_failure_count"])
        self.assertIn(
            "preflight lock policy: foreign_locks=2 ignored_foreign_locks=2 foreign_locks_ignored=True allow_foreign_build_locks=False allow_stale_foreign_build_locks=False auto_ignored_stale_foreign_locks=2 auto_ignore_stale_foreign_lock_seconds=86400",
            markdown,
        )
        self.assertIn(
            "local overlay staging: publish_status=pass activation_status=staged_only reuse_staging=True verify_receipt_status=pass landing_marker_status=pass landing_redirect_status=pass path_match=True hash_match=True local_live_surface_parity=pass local_live_surface_parity_failures=0",
            markdown,
        )

    def test_dashboard_blocks_public_edge_postdeploy_unexpected_contract(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-contract-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            public_edge = passing_public_edge_postdeploy_payload()
            public_edge["contractName"] = "chummer.public_edge_postdeploy_gate.preview"

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": public_edge,
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    **passing_release_ready_payload(),
                    "blocking_gate_artifacts": {
                        "windows_installer_visual_audit": {
                            "stage_release_build_handoff_path": "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
                            "stage_release_build_handoff_status": "fail",
                            "stage_windows_visual_proof_handoff_path": "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
                            "stage_windows_visual_proof_handoff_status": "ready_for_windows_host",
                            "stage_windows_visual_proof_handoff_summary": "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
                        },
                    },
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json": {
                    "status": "waiting_for_artifact",
                    "generated_at_utc": fresh_timestamp(),
                    "actionable_candidate_count": 0,
                    "matching_promoted_directory_candidate_count": 0,
                    "matching_promoted_zip_candidate_count": 0,
                    "stale_directory_candidate_count": 11,
                    "directory_candidate_note": (
                        "Complete extracted proof directories were found, but none match the promoted installer digest. "
                        "Digest-mismatched directories were summarized separately."
                    ),
                },
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": fresh_timestamp(),
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge_check["pass"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertEqual("chummer.public_edge_postdeploy_gate.preview", public_edge_check["summary"]["contract_name"])
        self.assertIn("unexpected public-edge postdeploy contract", public_edge_check["failures"])
        self.assertIn("failures: unexpected public-edge postdeploy contract", markdown)

    def test_dashboard_blocks_public_edge_postdeploy_semantic_contradictions(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-semantics-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            public_edge = passing_public_edge_postdeploy_payload()
            public_edge.update(
                {
                    "downloadsHasMarker": False,
                    "statusRedirectHasMarker": False,
                    "visibleVersion": "",
                    "statusRedirectVersion": "",
                    "expectedReleaseVersion": "run-test",
                    "visibleVersionMatchesReleaseChannel": False,
                    "statusRedirectVersionMatchesReleaseChannel": False,
                    "expectedReleaseStatus": "draft",
                    "expectedReleaseChannel": "",
                    "expectedReleaseSupportabilityState": "review_required",
                    "expectedReleaseRolloutState": "coverage_incomplete",
                    "releaseManifestStatus": "draft",
                    "releaseManifestStatusMatchesReleaseChannel": False,
                    "releaseManifestChannel": "preview",
                    "releaseManifestChannelMatchesReleaseChannel": False,
                    "releaseManifestSupportabilityState": "review_required",
                    "releaseManifestSupportabilityMatchesReleaseChannel": False,
                    "releaseManifestRolloutState": "coverage_incomplete",
                    "releaseManifestRolloutMatchesReleaseChannel": False,
                    "pwaManifestCount": 1,
                    "ledgerStreamPrecached": True,
                    "mobileLedgerPayloadStatus": "live",
                    "readyMobileHandoffToolIds": ["inventory"],
                    "readyMobileHandoffFrontdoorLaunchRoute": "/mobile",
                    "readyMobileHandoffRoleRoutes": [
                        {
                            "role": "Player",
                            "mode": "player",
                            "route": "/mobile/player",
                        }
                    ],
                    "mobilePwaViewportRoutes": ["/mobile", "/mobile/player", "/mobile/observer", "/play", "/play/continuity"],
                    "mobilePwaViewportMissingRoutes": ["/mobile/gm"],
                    "mobilePwaViewportViewportCount": 1,
                    "participateIframeRouteOfflineFallbackCount": 1,
                    "frontdoorNavigationGatedTargets": ["Open"],
                    "frontdoorNavigationPublicTargets": [],
                    "frontdoorNavigationPlayRoute": "/play",
                    "frontdoorNavigationPlaySignInRoute": "",
                }
            )
            public_edge["roleAliasRouteStatus"] = "fail"
            public_edge["roleAliasRouteResults"][0].update(
                {
                    "finalUrl": "https://chummer.run/play?role=player",
                    "finalRoute": "/play?role=player",
                    "pass": False,
                }
            )
            public_edge["roleAliasRouteDrift"] = [public_edge["roleAliasRouteResults"][0]]

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": public_edge,
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    **passing_release_ready_payload(),
                    "blocking_gate_artifacts": {
                        "windows_installer_visual_audit": {
                            "stage_release_build_handoff_path": "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
                            "stage_release_build_handoff_status": "fail",
                            "stage_windows_visual_proof_handoff_path": "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
                            "stage_windows_visual_proof_handoff_status": "ready_for_windows_host",
                            "stage_windows_visual_proof_handoff_summary": "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
                        },
                    },
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json": {
                    "status": "waiting_for_artifact",
                    "generated_at_utc": fresh_timestamp(),
                    "actionable_candidate_count": 0,
                    "matching_promoted_directory_candidate_count": 0,
                    "matching_promoted_zip_candidate_count": 0,
                    "stale_directory_candidate_count": 11,
                    "directory_candidate_note": (
                        "Complete extracted proof directories were found, but none match the promoted installer digest. "
                        "Digest-mismatched directories were summarized separately."
                    ),
                },
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": fresh_timestamp(),
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge_check["pass"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertIn("public-edge postdeploy downloads marker is not proven", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy visible Version text does not match release channel", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy status redirect Version text does not match release channel", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy expected release status is not published", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy expected release channel is missing", public_edge_check["failures"])
        self.assertNotIn("public-edge postdeploy expected release supportability is not gold_supported", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy live release manifest status does not match release channel", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy live release manifest channel does not match release channel", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy live release manifest supportability does not match release channel", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy live release manifest rollout does not match release channel", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy PWA manifest count is below required count", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy mobile ledger payload is not opt_in_required", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy Ready mobile handoff frontdoor launch route is not /mobile/player", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy Ready mobile handoff Player manifest path is not /manifest.player.webmanifest", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy Ready mobile handoff is missing the GameMaster role route", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy mobile PWA viewport is missing required routes: /mobile/gm", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy roleAliasRouteStatus is not pass", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy role alias routes drifted", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy /player resolved to /play?role=player instead of /mobile/player", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy front-door navigation does not gate Build", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy front-door navigation does not gate Play", public_edge_check["failures"])
        self.assertIn("public-edge postdeploy front-door navigation Play route is not /mobile/player", public_edge_check["failures"])
        self.assertIn("failures:", markdown)
        self.assertIn("public-edge postdeploy downloads marker is not proven", markdown)

    def test_dashboard_allows_truthful_review_required_public_edge_postdeploy_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-review-required-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            public_edge = passing_public_edge_postdeploy_payload()
            public_edge.update(
                {
                    "statusRedirectHeading": "Preview downloads",
                    "statusRedirectHeadingExpected": "Preview downloads",
                    "visibleVersion": "Version 2026.07.04 (Preview)",
                    "statusRedirectVersion": "Version 2026.07.04 (Preview)",
                    "expectedReleaseVersion": "run-20260704-170602",
                    "releaseManifestVersion": "run-20260704-170602",
                    "expectedReleaseSupportabilityState": "review_required",
                    "expectedReleaseRolloutState": "coverage_incomplete",
                    "releaseManifestSupportabilityState": "review_required",
                    "releaseManifestRolloutState": "coverage_incomplete",
                }
            )

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": public_edge,
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260704-170602",
                    "publishedAt": fresh_timestamp(),
                    "channel": "public_stable",
                    "supportabilityState": "review_required",
                    "rolloutState": "coverage_incomplete",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("pass", public_edge_check["status"])
        self.assertTrue(public_edge_check["pass"])
        self.assertNotIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertNotIn(
            "public-edge postdeploy expected release rollout is blocking: coverage_incomplete",
            public_edge_check.get("failures", []),
        )

    def test_dashboard_blocks_public_edge_live_alias_drift_after_green_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-live-drift-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json": {
                    "status": "waiting_for_artifact",
                    "generated_at_utc": fresh_timestamp(),
                    "actionable_candidate_count": 0,
                    "matching_promoted_directory_candidate_count": 0,
                    "matching_promoted_zip_candidate_count": 0,
                    "stale_directory_candidate_count": 11,
                    "directory_candidate_note": (
                        "Complete extracted proof directories were found, but none match the promoted installer digest. "
                        "Digest-mismatched directories were summarized separately."
                    ),
                },
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": fresh_timestamp(),
                    "channel": "public_stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)
            live_alias_routes = {
                "status": "fail",
                "checkedAtUtc": fresh_timestamp(),
                "baseUrl": "https://chummer.run",
                "results": [
                    {
                        "aliasPath": "/player",
                        "requestedUrl": "https://chummer.run/player",
                        "httpStatus": 200,
                        "finalUrl": "https://chummer.run/play?role=player",
                        "finalRoute": "/play?role=player",
                        "expectedFinalRoute": "/mobile/player",
                        "pass": False,
                        "error": "",
                    },
                    {
                        "aliasPath": "/gm",
                        "requestedUrl": "https://chummer.run/gm",
                        "httpStatus": 200,
                        "finalUrl": "https://chummer.run/play?role=gm",
                        "finalRoute": "/play?role=gm",
                        "expectedFinalRoute": "/mobile/gm",
                        "pass": False,
                        "error": "",
                    },
                    {
                        "aliasPath": "/observer",
                        "requestedUrl": "https://chummer.run/observer",
                        "httpStatus": 200,
                        "finalUrl": "https://chummer.run/play?role=observer",
                        "finalRoute": "/play?role=observer",
                        "expectedFinalRoute": "/mobile/observer",
                        "pass": False,
                        "error": "",
                    },
                ],
            }
            live_alias_routes["drift"] = list(live_alias_routes["results"])

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload(public_edge_live_role_alias_routes=live_alias_routes)
                markdown = module.build_markdown(payload)

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge_check["pass"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertEqual("pass", public_edge_check["summary"]["role_alias_route_status"])
        self.assertEqual("fail", public_edge_check["summary"]["live_role_alias_route_status"])
        self.assertIn("public-edge live role alias routes are not pass", public_edge_check["failures"])
        self.assertIn("public-edge live /player resolved to /play?role=player instead of /mobile/player", public_edge_check["failures"])
        self.assertIn("live public role aliases: status=fail", markdown)

    def test_dashboard_recovers_timeout_only_public_edge_live_alias_probe_from_green_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-live-timeout-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json": {
                    "status": "waiting_for_artifact",
                    "generated_at_utc": fresh_timestamp(),
                    "actionable_candidate_count": 0,
                    "matching_promoted_directory_candidate_count": 0,
                    "matching_promoted_zip_candidate_count": 0,
                    "stale_directory_candidate_count": 11,
                    "directory_candidate_note": (
                        "Complete extracted proof directories were found, but none match the promoted installer digest. "
                        "Digest-mismatched directories were summarized separately."
                    ),
                },
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": fresh_timestamp(),
                    "channel": "public_stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)
            live_alias_routes = {
                "status": "fail",
                "checkedAtUtc": fresh_timestamp(),
                "baseUrl": "https://chummer.run",
                "results": [
                    {
                        "aliasPath": "/player",
                        "requestedUrl": "https://chummer.run/player",
                        "httpStatus": 200,
                        "finalUrl": "https://chummer.run/mobile/player",
                        "finalRoute": "/mobile/player",
                        "expectedFinalRoute": "/mobile/player",
                        "pass": True,
                        "error": "",
                    },
                    {
                        "aliasPath": "/gm",
                        "requestedUrl": "https://chummer.run/gm",
                        "httpStatus": None,
                        "finalUrl": "",
                        "finalRoute": "",
                        "expectedFinalRoute": "/mobile/gm",
                        "pass": False,
                        "error": "TimeoutError: The read operation timed out",
                    },
                    {
                        "aliasPath": "/observer",
                        "requestedUrl": "https://chummer.run/observer",
                        "httpStatus": 200,
                        "finalUrl": "https://chummer.run/mobile/observer",
                        "finalRoute": "/mobile/observer",
                        "expectedFinalRoute": "/mobile/observer",
                        "pass": True,
                        "error": "",
                    },
                ],
            }
            live_alias_routes["drift"] = [live_alias_routes["results"][1]]

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload(public_edge_live_role_alias_routes=live_alias_routes)

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(public_edge_check["pass"])
        self.assertNotIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertEqual("fail", public_edge_check["summary"]["live_role_alias_route_status"])
        self.assertTrue(public_edge_check["summary"]["live_role_alias_timeout_recovered"])
        self.assertNotIn("public-edge live role alias routes are not pass", public_edge_check.get("failures", []))

    def test_dashboard_rejects_stale_public_edge_postdeploy_schema(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-stale-public-edge-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {
                    "status": "pass",
                    "generatedAtUtc": "2026-06-30T08:00:00Z",
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_edge = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge["pass"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertIn("missing postdeploy fields", public_edge["failures"][0])
        self.assertIn("preflightOverlayRoot", public_edge["failures"][0])
        self.assertIn("preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource", public_edge["failures"][0])
        self.assertIn("participateIframeShellStatus", public_edge["failures"][0])
        self.assertIn("mobilePwaViewportStatus", public_edge["failures"][0])
        self.assertIn("mobilePwaViewportRoutes", public_edge["failures"][0])
        self.assertIn("mobilePwaViewportMissingRoutes", public_edge["failures"][0])
        self.assertIn("roleAliasRouteStatus", public_edge["failures"][0])
        self.assertIn("frontdoorNavigationStatus", public_edge["failures"][0])
        self.assertIn("frontdoorNavigationAnchorArtifactContract", public_edge["failures"][0])
        self.assertIn("frontdoorNavigationAnchorFinalPath", public_edge["failures"][0])
        self.assertIn("missing postdeploy fields:", markdown)

    def test_dashboard_rejects_public_edge_receipt_when_release_channel_version_advances(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-version-drift-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            stale_public_edge = passing_public_edge_postdeploy_payload()
            stale_public_edge["expectedReleaseVersion"] = "run-old"
            stale_public_edge["visibleVersion"] = "Version run-old"
            stale_public_edge["statusRedirectVersion"] = "Version run-old"
            stale_public_edge["releaseManifestVersion"] = "run-old"

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": stale_public_edge,
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json": {
                    "status": "waiting_for_artifact",
                    "generated_at_utc": fresh_timestamp(),
                    "actionable_candidate_count": 0,
                    "matching_promoted_directory_candidate_count": 0,
                    "matching_promoted_zip_candidate_count": 0,
                    "stale_directory_candidate_count": 11,
                    "directory_candidate_note": (
                        "Complete extracted proof directories were found, but none match the promoted installer digest. "
                        "Digest-mismatched directories were summarized separately."
                    ),
                },
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-new",
                    "publishedAt": fresh_timestamp(),
                    "channel": "public_stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_edge_check["pass"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertEqual("run-new", public_edge_check["summary"]["current_release_channel_version"])
        self.assertIn(
            "public-edge postdeploy expected release version does not match current release channel version",
            public_edge_check["failures"],
        )
        self.assertIn(
            "public-edge postdeploy release manifest version does not match current release channel version",
            public_edge_check["failures"],
        )
        self.assertIn(
            "public-edge postdeploy expected release version does not match current release channel version",
            public_edge_check["summary"]["release_channel_alignment_failures"],
        )

    def test_dashboard_blocks_teable_important_work_without_passed_sync(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-teable-sync-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": {
                    "contract_name": "chummer.teable_important_work.v1",
                    "status": "ready",
                    "generated_at_utc": "2026-06-30T08:00:00Z",
                    "table_name": "Chummer Important Work",
                    "row_count": 1,
                    "rows": [{"item_id": "teable-important-work-sync"}],
                    "sync": {
                        "state": "not_requested",
                        "attempted": False,
                        "synced_count": 0,
                        "failed_count": 0,
                    },
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        teable = payload["checks"]["teable_important_work"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("teable_important_work", payload["failures"])
        self.assertEqual("fail", teable["status"])
        self.assertIn("Teable important work sync is not pass", teable["failures"])
        self.assertIn("teable: state=not_requested", markdown)

    def test_dashboard_accepts_teable_important_work_ready_projection_after_passed_sync(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-teable-ready-pass-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        teable = payload["checks"]["teable_important_work"]
        self.assertTrue(teable["pass"])
        self.assertEqual("pass", teable["status"])
        self.assertNotIn("teable_important_work", payload["failures"])

    def test_dashboard_blocks_failed_flagship_product_readiness(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-readiness-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            failed_flagship = passing_flagship_product_readiness_payload()
            failed_flagship["status"] = "fail"
            failed_flagship["completion_audit"] = {"status": "fail"}
            failed_flagship["flagship_readiness_audit"] = {
                "status": "fail",
                "reason": "missing coverage: desktop_client",
                "coverage_gap_keys": ["desktop_client"],
                "scoped_coverage_gap_keys": ["desktop_client"],
            }
            failed_flagship["summary"] = {"ready_count": 7, "missing_count": 1, "scoped_missing_count": 1}
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": failed_flagship,
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        flagship = payload["checks"]["flagship_product_readiness"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("flagship_product_readiness", payload["failures"])
        self.assertEqual("fail", flagship["status"])
        self.assertIn("Flagship product readiness is not pass", flagship["failures"])
        self.assertIn("coverage_gaps=['desktop_client']", markdown)

    def test_dashboard_prefers_fail_closed_flagship_product_readiness_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-gate-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                gate_path: failing_flagship_product_readiness_gate_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        flagship = payload["checks"]["flagship_product_readiness"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("flagship_product_readiness", payload["failures"])
        self.assertEqual(str(gate_path), flagship["path"])
        self.assertEqual("gate", flagship["source_receipt"])
        self.assertEqual("loaded", flagship["load_status"])
        self.assertEqual("NOT_FLAGSHIP_PRODUCT_READY", flagship["verdict"])
        self.assertFalse(flagship["pass"])
        self.assertIn("Flagship product readiness is not pass", flagship["failures"])
        self.assertIn("final gold janitor verdict is 'NOT_GOLD'", flagship["failures"])
        self.assertEqual("NOT_FLAGSHIP_PRODUCT_READY", flagship["summary"]["verdict"])
        self.assertEqual("loaded", flagship["summary"]["readiness_load_status"])
        self.assertEqual("loaded", flagship["summary"]["source_receipt_load_status"])
        self.assertEqual(
            [
                "final gold janitor state is 'fail'",
                "final gold janitor verdict is 'NOT_GOLD'",
                "live-backed gold claim is not allowed",
            ],
            flagship["summary"]["launch_critical_nested_blockers"],
        )
        self.assertIn("Launch-critical nested blockers or coverage gaps remain", flagship["summary"]["reason"])
        self.assertIn("final gold janitor verdict is 'NOT_GOLD'", flagship["summary"]["reason"])
        self.assertIn("flagship readiness: source=gate verdict=NOT_FLAGSHIP_PRODUCT_READY", markdown)

    def test_dashboard_rejects_flagship_gate_unexpected_ready_verdict(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-gate-verdict-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                gate_path: {
                    "contract_name": "chummer.flagship_product_readiness_gate.v1",
                    "generated_at_utc": fresh_timestamp(),
                    "status": "pass",
                    "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                    "readiness_path": ".codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json",
                    "readiness_load_status": "loaded",
                    "summary": {
                        "contract_name": "fleet.flagship_product_readiness",
                        "status": "pass",
                        "generated_at": fresh_timestamp(),
                        "readiness_load_status": "loaded",
                        "completion_audit_status": "pass",
                        "flagship_readiness_audit_status": "pass",
                        "reason": "Flagship product readiness proof is green.",
                        "ready_count": 8,
                        "missing_count": 0,
                        "scoped_missing_count": 0,
                        "warning_count": 0,
                        "coverage_gap_keys": [],
                        "scoped_coverage_gap_keys": [],
                        "launch_critical_nested_blockers": [],
                        "launch_critical_nested_blocker_count": 0,
                        "pass": True,
                    },
                },
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        flagship = payload["checks"]["flagship_product_readiness"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("flagship_product_readiness", payload["failures"])
        self.assertFalse(flagship["pass"])
        self.assertFalse(flagship["summary"]["structural_pass"])
        self.assertEqual(
            ["flagship_product_readiness gate has unexpected verdict (expected FLAGSHIP_PRODUCT_READY)"],
            flagship["semanticFailures"],
        )
        self.assertIn(
            "flagship_product_readiness gate has unexpected verdict (expected FLAGSHIP_PRODUCT_READY)",
            flagship["failures"],
        )
        self.assertIn("flagship readiness: source=gate verdict=NOT_FLAGSHIP_PRODUCT_READY", markdown)

    def test_dashboard_refreshes_default_flagship_gate_before_loading(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-gate-refresh-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                gate_path: {
                    **failing_flagship_product_readiness_gate_payload(),
                    "generated_at_utc": "2026-07-06T05:00:00Z",
                },
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            def fake_run(args, **_kwargs):
                if args[:2] == ["python3", "scripts/verify_flagship_product_readiness_gate.py"]:
                    refreshed = failing_flagship_product_readiness_gate_payload()
                    refreshed["generated_at_utc"] = "2026-07-06T05:35:00Z"
                    gate_path.write_text(
                        json.dumps(refreshed) + "\n",
                        encoding="utf-8",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "COMPLETION_ROOT", completion),
                mock.patch.object(module, "REGISTRY_ROOT", registry),
                mock.patch.object(module, "DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH", gate_path),
                mock.patch.object(
                    module,
                    "DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND",
                    [
                        "python3",
                        "scripts/verify_flagship_product_readiness_gate.py",
                        "--summary-output",
                        str(gate_path),
                    ],
                ),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run) as run,
            ):
                payload = module.build_payload()

        run.assert_called_once()
        flagship = payload["checks"]["flagship_product_readiness"]
        self.assertEqual("2026-07-06T05:35:00Z", flagship["generated_at_utc"])
        self.assertEqual(3, flagship["summary"]["launch_critical_nested_blocker_count"])
        self.assertEqual([], flagship["summary"]["coverage_gap_keys"])

    def test_dashboard_recovers_flagship_gate_when_other_release_blockers_exist(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-gate-recovered-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                gate_path: failing_flagship_product_readiness_gate_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": preview_release_channel_payload(),
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        flagship = payload["checks"]["flagship_product_readiness"]
        release_channel = payload["checks"]["release_channel"]
        self.assertEqual("fail", payload["status"])
        self.assertNotIn("flagship_product_readiness", payload["failures"])
        self.assertEqual(str(gate_path), flagship["path"])
        self.assertEqual("gate", flagship["source_receipt"])
        self.assertTrue(flagship["pass"])
        self.assertTrue(flagship["release_blocking_recovered"])
        self.assertEqual(["public_edge_postdeploy_gate", "release_channel"], flagship["recovered_because_of_checks"])
        self.assertTrue(flagship["summary"]["recovered_for_release_blocking"])
        self.assertIn("release channel channel is preview, not a flagship stable lane", release_channel["failures"])
        self.assertIn("release channel supportability is not gold_supported", release_channel["failures"])
        self.assertIn("release channel rollout is promoted_preview, not public_stable", release_channel["failures"])
        self.assertIn("release-blocking recovered via: public_edge_postdeploy_gate, release_channel", markdown)
        self.assertIn("source=gate", markdown)
        self.assertIn("launch blockers: final gold janitor state is 'fail'", markdown)

    def test_dashboard_recovers_flagship_gate_with_failed_nested_audits_when_only_wrapper_echo_remains(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-gate-nested-audits-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                gate_path: failing_flagship_product_readiness_gate_payload_with_failed_nested_audits(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": preview_release_channel_payload(),
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        flagship = payload["checks"]["flagship_product_readiness"]
        self.assertEqual("fail", payload["status"])
        self.assertNotIn("flagship_product_readiness", payload["failures"])
        self.assertEqual(str(gate_path), flagship["path"])
        self.assertTrue(flagship["pass"])
        self.assertTrue(flagship["release_blocking_recovered"])
        self.assertTrue(flagship["summary"]["structural_pass"])
        self.assertTrue(flagship["summary"]["recovered_for_release_blocking"])
        self.assertEqual(["public_edge_postdeploy_gate", "release_channel"], flagship["recovered_because_of_checks"])

    def test_dashboard_surfaces_malformed_flagship_gate_receipt_structurally(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-flagship-gate-invalid-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)
            gate_path.write_text("{not json}\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        flagship = payload["checks"]["flagship_product_readiness"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual(str(gate_path), flagship["path"])
        self.assertEqual("gate", flagship["source_receipt"])
        self.assertEqual("invalid", flagship["load_status"])
        self.assertIn(
            f"flagship_product_readiness receipt is malformed: {gate_path}",
            flagship["failures"],
        )

    def test_dashboard_recovers_public_edge_gate_when_only_preflight_failed(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-edge-preflight-recovered-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            public_edge = passing_public_edge_postdeploy_payload()
            public_edge.update(
                {
                    "status": "fail",
                    "preflightStatus": "fail",
                    "preflightActiveLockCount": 4,
                    "preflightBlockingLockCount": 1,
                    "preflightStaleLookingLockCount": 4,
                    "preflightStaleForeignLockCount": 3,
                    "preflightStaleForeignLocksIgnored": True,
                    "failures": ["public-edge deploy preflight is not pass"],
                }
            )
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": public_edge,
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                    "rolloutState": "public_stable",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        public_edge_check = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("pass", payload["status"])
        self.assertNotIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertTrue(public_edge_check["pass"])
        self.assertEqual("pass", public_edge_check["status"])
        self.assertTrue(public_edge_check["release_blocking_recovered_from_preflight"])
        self.assertEqual(["public-edge deploy preflight is not pass"], public_edge_check["summary"]["receipt_failures"])
        self.assertEqual([], public_edge_check["summary"]["non_preflight_receipt_failures"])

    def test_dashboard_blocks_failed_public_route_proof_summary(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-public-route-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 1, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_route = payload["checks"]["public_route_proof"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(public_route["pass"])
        self.assertIn("public_route_proof", payload["failures"])
        self.assertEqual(1, public_route["summary"]["failed_count"])
        self.assertIn("routes: count=12 failed=1 negative_path_failed=0", markdown)

    def test_dashboard_blocks_failed_windows_installer_visual_audit(self) -> None:
        module = load_module()
        module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = False
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-windows-visual-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {
                    "status": "fail",
                    "generated_at_utc": "2026-06-30T08:00:00Z",
                    "failures": ["native Windows startup-smoke receipt is missing"],
                    "nextActions": ["Run the promoted Windows installer on a native Windows host."],
                    "startupReceipt": {
                        "status": "fail",
                        "verificationDisposition": "incompatible_host",
                    },
                    "visualAuditSource": {
                        "exists": False,
                        "screenshotCount": 0,
                    },
                },
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        visual_audit = payload["checks"]["windows_installer_visual_audit"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(visual_audit["pass"])
        self.assertTrue(visual_audit.get("release_blocking", True))
        self.assertIn("windows_installer_visual_audit", payload["failures"])
        self.assertIn("native Windows startup-smoke receipt is missing", visual_audit["failures"])
        self.assertEqual(["Run the promoted Windows installer on a native Windows host."], visual_audit["nextActions"])
        self.assertEqual("incompatible_host", visual_audit["startupReceipt"]["verificationDisposition"])
        self.assertFalse(visual_audit["visualAuditSource"]["exists"])
        self.assertIn("native Windows startup-smoke receipt is missing", markdown)
        self.assertIn("Run the promoted Windows installer on a native Windows host.", markdown)

    def test_windows_visual_root_blocker_summary_acknowledges_confirmed_startup(self) -> None:
        module = load_module()
        summary = module.windows_visual_root_blocker_summary(
            {
                "artifact": {"sha256": "a" * 64},
                "startupReceipt": {
                    "status": "pass",
                    "artifactDigest": "sha256:" + ("a" * 64),
                },
                "visualAuditSource": {
                    "artifactSha256": "b" * 64,
                },
            }
        )

        self.assertEqual(
            "Native Windows installer execution is confirmed, but the matching visual proof is still missing or mismatched for the promoted bytes.",
            summary,
        )

    def test_dashboard_blocks_windows_installer_visual_audit_semantic_contradictions(self) -> None:
        module = load_module()
        windows_intake = load_windows_intake_module()
        visual_audit_verifier_binding = windows_intake.visual_audit_verifier_binding()
        bound_visual_audit_verify_command = windows_intake.build_bound_visual_audit_verify_command(
            visual_audit_verifier_binding
        )
        module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = False
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-windows-visual-semantics-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            telegram = Path(temp_dir) / "telegram"
            telegram.mkdir(parents=True, exist_ok=True)
            windows_ask_text_path = Path(temp_dir) / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            windows_ask_metadata_path = Path(temp_dir) / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            windows_ask_text_path.write_text("windows operator ask\n", encoding="utf-8")
            source_windows_ask_text_path = Path(temp_dir) / "windows-ask.txt"
            source_windows_ask_metadata_path = Path(temp_dir) / "windows-ask.generated.json"
            source_windows_ask_text_path.write_text("windows operator ask\n", encoding="utf-8")
            windows_message_sha = hashlib.sha256("windows operator ask\n".encode("utf-8")).hexdigest()
            source_windows_ask_metadata_path.write_text(
                json.dumps(
                    {
                        "request_receipt_path": str(
                            Path(temp_dir) / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
                        ),
                        "message_sha256": windows_message_sha,
                        "receipt_name": "windows.receipt.json",
                        "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
                        "preferred_drop_path": "/tmp/windows-installer-gold-proof-a.zip",
                        "promoted_installer_sha256": "a" * 64,
                        "secrets_redacted": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            windows_ask_metadata_path.write_text(
                json.dumps(
                    {
                        "request_receipt_path": str(
                            Path(temp_dir) / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
                        ),
                        "current_message_path": str(windows_ask_text_path),
                        "message_sha256": windows_message_sha,
                        "receipt_name": "windows.receipt.json",
                        "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
                        "preferred_drop_path": "/tmp/windows-installer-gold-proof-a.zip",
                        "promoted_installer_sha256": "a" * 64,
                        "secrets_redacted": True,
                        "source_message_path": str(source_windows_ask_text_path),
                        "source_metadata_path": str(source_windows_ask_metadata_path),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (telegram / "windows.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": fresh_timestamp(),
                        "text_sha256": hashlib.sha256("stale windows operator ask\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            windows = passing_windows_installer_visual_audit_payload()
            windows.update(
                {
                    "artifact": {
                        "sha256": "a" * 64,
                        "actualSha256": "b" * 64,
                    },
                    "startupReceipt": {
                        "status": "pass",
                        "verificationDisposition": "incompatible_host",
                        "artifactDigest": "sha256:" + ("c" * 64),
                    },
                    "visualAuditSource": {
                        "exists": True,
                        "status": "pass",
                        "platform": "linux",
                        "hostClass": "container",
                        "artifactSha256": "d" * 64,
                        "path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                        "screenshotCount": 1,
                        "defaultDpiScreenshotCount": 1,
                        "scaledDpiScreenshotCount": 0,
                        "requiredSurfaces": ["completion"],
                    },
                }
            )

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": windows,
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {
                    "contract_name": "chummer.windows_installer_visual_audit_intake_request.v1",
                    "generated_at_utc": fresh_timestamp(),
                    "status": "external_artifact_required",
                    "provider": "native_windows_operator",
                    "release_channel_receipt_path": str(registry / "RELEASE_CHANNEL.generated.json"),
                    "release_version": "run-20260624-080000",
                    "release_channel": "stable",
                    "request_receipt_path": str(
                        published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
                    ),
                    "promoted_installer_sha256": "a" * 64,
                    "promoted_installer": {
                        "sha256": "a" * 64,
                        "file_name": "chummer6-win-x64-setup.exe",
                    },
                    "promoted_installer_binding_ready": True,
                    "visual_audit_verifier_binding": visual_audit_verifier_binding,
                    "preferred_drop_path": "/tmp/windows-installer-gold-proof-a.zip",
                    "preferred_zip_name": "windows-installer-gold-proof-a.zip",
                    "required_zip_filename": "windows-installer-gold-proof-a.zip",
                    "preferred_extracted_visual_dir": "/tmp/windows-installer",
                    "current_blocker": {
                        "receipt": str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"),
                    },
                    "operator_request": {
                        "actionable": True,
                        "summary": "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
                        "required_surfaces": ["install-progress", "completion"],
                        "required_dpi_scales": ["1.0", "1.5"],
                        "required_host_class_prefix": "native-windows",
                        "powershell_commands": ["one", "two"],
                    },
                    "operator_telegram_draft": {
                        "message_path": str(source_windows_ask_text_path),
                        "metadata_path": str(source_windows_ask_metadata_path),
                        "current_message_path": str(windows_ask_text_path),
                        "current_metadata_path": str(windows_ask_metadata_path),
                        "message_sha256": windows_message_sha,
                        "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
                        "receipt_name": "windows.receipt.json",
                        "message_preview": "Windows operator ask preview",
                        "preferred_extracted_visual_dir": "/tmp/windows-installer",
                        "discover_visual_source_command": "python3 discover-visual",
                    },
                    "artifact_intake": {
                        "discover_command": "python3 discover",
                        "discover_visual_source_command": "python3 discover-visual",
                        "preferred_extracted_visual_dir": "/tmp/windows-installer",
                        "watcher_launch_mode": "python_subprocess_start_new_session",
                        "watcher_state_path": str(Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.generated.json"),
                        "watcher_pid_file": str(Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.pid"),
                        "watcher_log_path": str(Path(temp_dir) / "state" / "windows_installer_gold_proof_auto_import_watch.log"),
                        "watcher_start_command": (
                            "python3 watcher-start "
                            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                        ),
                        "watcher_status_command": (
                            "python3 watcher-status "
                            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                        ),
                        "watcher_stop_command": (
                            "python3 watcher-stop "
                            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                        ),
                        "import_command": (
                            "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                            "bundle.zip "
                            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                            "--verify"
                        ),
                        "auto_import_command": (
                            "python3 scripts/auto_import_windows_installer_gold_proof.py "
                            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                        ),
                        "auto_import_watch_command": (
                            "python3 scripts/auto_import_windows_installer_gold_proof.py "
                            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                            "--wait-seconds 900"
                        ),
                        "auto_import_roots": [str(Path(temp_dir) / "drop")],
                        "post_import_verify_command": bound_visual_audit_verify_command,
                        "post_import_verify_note": "The --verify import reruns the full intake-request post-import gate chain, not just the first verifier.",
                    },
                    "expected_artifact_patterns": [
                        "*windows-installer-gold-proof*.zip",
                        "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                        "windows-installer-gold-proof-a.zip",
                    ],
                    "post_import_gates": [
                        bound_visual_audit_verify_command,
                        "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                        "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
                        "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
                        "python3 scripts/materialize_operator_release_dashboard.py",
                        "python3 scripts/final_gold_janitor.py --skip-materializers",
                        "python3 ../scripts/release/_release_gate_common.py",
                        "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json",
                        "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json",
                        "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass",
                        "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
                    ],
                    "secrets_redacted": True,
                    "direct_telegram_sent": False,
                },
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {
                    **passing_release_ready_payload(),
                    "blocking_gate_artifacts": {
                        "windows_installer_visual_audit": {
                            "stage_release_build_handoff_path": "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
                            "stage_release_build_handoff_status": "fail",
                            "stage_windows_visual_proof_handoff_path": "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
                            "stage_windows_visual_proof_handoff_status": "ready_for_windows_host",
                            "stage_windows_visual_proof_handoff_summary": "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
                        },
                    },
                },
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": fresh_timestamp(),
                    "channel": "stable",
                    "supportabilityState": "gold_supported",
                },
            }
            write_receipts(receipts)
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "generated_at_utc": fresh_timestamp(),
                        "artifact": "/tmp/windows-installer-gold-proof-a.zip",
                        "import_failure": {
                            "type": "BadZipFile",
                            "message": "File is not a zip file",
                            "code": None,
                        },
                        "summary": "Selected Windows installer gold-proof artifact failed import validation.",
                        "actionable_candidate_count": 0,
                        "matching_promoted_directory_candidate_count": 0,
                        "matching_promoted_zip_candidate_count": 0,
                        "stale_directory_candidate_count": 11,
                        "stage_like_stale_directory_candidate_count": 2,
                        "stage_visual_proof_receipt_count": 3,
                        "matching_promoted_stage_visual_proof_receipt_count": 0,
                        "stale_stage_visual_proof_receipt_count": 3,
                        "suppressed_stale_stage_visual_proof_receipt_count": 1,
                        "stage_startup_smoke_receipt_count": 2,
                        "matching_promoted_stage_startup_smoke_receipt_count": 1,
                        "stale_stage_startup_smoke_receipt_count": 1,
                        "suppressed_stale_stage_startup_smoke_receipt_count": 0,
                        "matching_promoted_stage_startup_smoke_receipts": [
                            {
                                "path": "/tmp/chummer6-ui-publishfix/Docker/Downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                                "matches_promoted_installer": True,
                            },
                        ],
                        "stale_stage_startup_smoke_receipts": [
                            {
                                "path": "/tmp/stale/startup-smoke-avalonia-win-x64.receipt.json",
                                "matches_promoted_installer": False,
                            },
                        ],
                        "stale_stage_visual_proof_receipts": [
                            {
                                "path": "/tmp/chummer6-ui-publishfix/Docker/Downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                                "matches_promoted_installer": False,
                            },
                            {
                                "path": "/tmp/chummer6-ui-publishfix/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                                "matches_promoted_installer": False,
                            },
                        ],
                        "stage_visual_proof_receipt_note": (
                            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest."
                        ),
                        "stage_startup_smoke_receipt_note": (
                            "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. Additional digest-mismatched startup-smoke receipts were summarized separately."
                        ),
                        "stale_directory_digest_summary": [
                            {
                                "artifact_sha256": "d" * 64,
                                "count": 2,
                                "stage_like_count": 2,
                                "sample_path": "/tmp/chummer-run-services-browserfix3",
                                "latest_source_updated_at_utc": "2026-06-21T17:44:15.3027652Z",
                            },
                            {
                                "artifact_sha256": "e" * 64,
                                "count": 9,
                                "stage_like_count": 0,
                                "sample_path": "/tmp/windows-installer-proof-27866529115",
                                "latest_source_updated_at_utc": "2026-06-20T09:21:23Z",
                            },
                        ],
                        "directory_candidate_note": (
                            "Complete extracted proof directories were found, but none match the promoted installer digest. "
                            "Digest-mismatched directories were summarized separately."
                        ),
                    }
                ),
                encoding="utf-8",
            )
            watcher_state_path = Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.generated.json"
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": fresh_timestamp(),
                        "status": "running",
                        "pid": 1866861,
                        "process_alive": True,
                        "matching_process_pids": [1866861],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "watcher discovered by pid file or process scan",
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "TELEGRAM_TEXT_DELIVERY_ROOT", telegram):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        visual_audit = payload["checks"]["windows_installer_visual_audit"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(visual_audit["pass"])
        self.assertEqual("pass", visual_audit["raw_status"])
        self.assertIn("windows_installer_visual_audit", payload["failures"])
        self.assertIn(
            "windows installer visual audit source still targets "
            f"{'d' * 64} instead of promoted digest {'a' * 64}: /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            payload["failures"],
        )
        self.assertIn("windows_installer_visual_audit artifact sha256 does not match actual artifact bytes", visual_audit["failures"])
        self.assertIn(
            "windows installer visual audit source still targets "
            f"{'d' * 64} instead of promoted digest {'a' * 64}: /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            visual_audit["failures"],
        )
        self.assertEqual(
            str(Path(temp_dir) / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
            visual_audit["operator_request_artifacts"]["request_receipt_path"],
        )
        self.assertEqual("/tmp/RELEASE_BUILD_HANDOFF.generated.json", visual_audit["stage_release_build_handoff_path"])
        self.assertEqual("fail", visual_audit["stage_release_build_handoff_status"])
        self.assertEqual(
            "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
            visual_audit["stage_windows_visual_proof_handoff_path"],
        )
        self.assertEqual("ready_for_windows_host", visual_audit["stage_windows_visual_proof_handoff_status"])
        self.assertEqual(
            "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
            visual_audit["stage_windows_visual_proof_handoff_summary"],
        )
        self.assertIn(
            "windows_native_visual_proof",
            [item["id"] for item in payload["root_blockers"]],
        )
        self.assertIn("windows_installer_visual_audit startup receipt is incompatible-host", visual_audit["semanticFailures"])
        self.assertIn("windows_installer_visual_audit visual source platform is not windows", visual_audit["semanticFailures"])
        self.assertIn("windows_installer_visual_audit scaled-DPI screenshot count is below required count", visual_audit["semanticFailures"])
        self.assertIn(
            "`windows_native_visual_proof`: Native Windows installer visual proof is still missing or mismatched for the promoted bytes.",
            markdown,
        )
        self.assertIn("raw status: `pass`", markdown)
        self.assertIn("windows_installer_visual_audit artifact sha256 does not match actual artifact bytes", markdown)
        self.assertIn(
            "visual audit source: promoted_digest="
            f"{'a' * 64} source_digest={'d' * 64} "
            "source_path=/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            markdown,
        )
        self.assertIn(
            "windows visual proof request: request_receipt="
            f"{Path(temp_dir) / 'published' / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            f"ask_text={windows_ask_text_path} ask_meta={windows_ask_metadata_path} "
            "preferred_drop=/tmp/windows-installer-gold-proof-a.zip fallback_dir=/tmp/windows-installer",
            markdown,
        )
        self.assertIn(
            "windows proof discovery: bundle=python3 discover visual_source=python3 discover-visual",
            markdown,
        )
        self.assertIn(
            "staged windows handoff: release_build=/tmp/RELEASE_BUILD_HANDOFF.generated.json "
            "release_status=fail visual_handoff=/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json "
            "visual_status=ready_for_windows_host",
            markdown,
        )
        self.assertIn(
            "staged windows handoff summary: Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
            markdown,
        )
        self.assertEqual("/tmp/windows-installer-gold-proof-a.zip", visual_audit["operator_request_artifacts"]["preferred_drop_path"])
        self.assertFalse(visual_audit["operator_request_artifacts"]["preferred_drop_path_exists"])
        self.assertEqual("windows-installer-gold-proof-a.zip", visual_audit["operator_request_artifacts"]["preferred_zip_name"])
        self.assertEqual("windows-installer-gold-proof-a.zip", visual_audit["operator_request_artifacts"]["required_zip_filename"])
        self.assertEqual(
            "/tmp/windows-installer",
            visual_audit["operator_request_artifacts"]["preferred_extracted_visual_dir"],
        )
        self.assertFalse(
            visual_audit["operator_request_artifacts"]["preferred_extracted_visual_dir_exists"]
        )
        self.assertEqual(
            "python3 discover-visual",
            visual_audit["operator_request_artifacts"]["discover_visual_source_command"],
        )
        self.assertEqual(
            str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"),
            visual_audit["operator_request_artifacts"]["auto_import_receipt_path"],
        )
        self.assertEqual(
            str(Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.generated.json"),
            visual_audit["operator_request_artifacts"]["watcher_state_receipt_path"],
        )
        self.assertEqual("running", visual_audit["operator_request_artifacts"]["watcher_status"])
        self.assertEqual(1866861, visual_audit["operator_request_artifacts"]["watcher_pid"])
        self.assertEqual(1, visual_audit["operator_request_artifacts"]["watcher_matching_process_count"])
        self.assertEqual(0, visual_audit["operator_request_artifacts"]["watcher_duplicate_process_count"])
        self.assertFalse(visual_audit["operator_request_artifacts"]["watcher_attention_required"])
        self.assertEqual(
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
            visual_audit["operator_ask_send_command"],
        )
        self.assertEqual(
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
            visual_audit["operator_ask_resend_command"],
        )
        self.assertEqual(1866861, visual_audit["watcher_pid"])
        self.assertEqual("running", visual_audit["watcher_status"])
        self.assertEqual(
            str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"),
            visual_audit["auto_import_receipt_path"],
        )
        self.assertEqual("fail", visual_audit["operator_request_artifacts"]["auto_import_receipt_status"])
        self.assertEqual("fail", visual_audit["auto_import_receipt_status"])
        self.assertEqual(
            "BadZipFile",
            visual_audit["operator_request_artifacts"]["auto_import_import_failure_type"],
        )
        self.assertEqual("BadZipFile", visual_audit["auto_import_import_failure_type"])
        self.assertEqual(
            "File is not a zip file",
            visual_audit["operator_request_artifacts"]["auto_import_import_failure_message"],
        )
        self.assertEqual(
            "Selected Windows installer gold-proof artifact failed import validation.",
            visual_audit["operator_request_artifacts"]["auto_import_import_failure_summary"],
        )
        self.assertEqual(11, visual_audit["operator_request_artifacts"]["auto_import_stale_directory_candidate_count"])
        self.assertEqual(11, visual_audit["auto_import_stale_directory_candidate_count"])
        self.assertEqual(
            "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof-a.zip",
            visual_audit["operatorArtifactMissingFailure"],
        )
        self.assertEqual(
            3,
            visual_audit["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            0,
            visual_audit["operator_request_artifacts"]["auto_import_matching_promoted_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            3,
            visual_audit["operator_request_artifacts"]["auto_import_stale_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            2,
            visual_audit["operator_request_artifacts"]["auto_import_stage_startup_smoke_receipt_count"],
        )
        self.assertEqual(
            1,
            visual_audit["operator_request_artifacts"]["auto_import_matching_promoted_stage_startup_smoke_receipt_count"],
        )
        self.assertEqual(
            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
            visual_audit["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_note"],
        )
        self.assertIn(
            "Startup is already proven",
            visual_audit["operator_request_artifacts"]["auto_import_stage_startup_smoke_receipt_note"],
        )
        self.assertIn(
            "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof-a.zip",
            payload["failures"],
        )
        self.assertNotIn(
            "windows installer operator ask delivery is stale; resend current ask: "
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} "
            "--receipt-name windows.receipt.json",
            payload["failures"],
        )
        self.assertNotIn(
            "windows installer operator ask delivery is stale; resend current ask: "
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} "
            "--receipt-name windows.receipt.json",
            visual_audit["failures"],
        )
        self.assertIn(
            "windows installer operator ask delivery is stale; resend current ask: "
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} "
            "--receipt-name windows.receipt.json",
            visual_audit["advisoryActions"],
        )
        self.assertIn(
            "windows stage/nightly proof hints are available: "
            f"{published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}; "
            "visual-proof receipts=3, startup-smoke receipts=2. "
            "Use them only to locate old Windows capture output for recapture or bundle packaging. "
            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest. "
            "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. "
            "Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. "
            "Additional digest-mismatched startup-smoke receipts were summarized separately.",
            visual_audit["advisoryActions"],
        )
        self.assertIn(
            "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof-a.zip",
            markdown,
        )
        self.assertIn(
            f"windows operator ask send: python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
            markdown,
        )
        self.assertIn(
            f"windows operator ask resend: python3 scripts/send_telegram_message_via_ea.py --text-file {windows_ask_text_path} --receipt-name windows.receipt.json",
            markdown,
        )
        self.assertIn("  - advisory actions:", markdown)
        self.assertIn(
            "windows proof intake: "
            "import=python3 scripts/import_windows_installer_gold_proof_artifact.py "
            "bundle.zip "
            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            "--verify "
            "auto=python3 scripts/auto_import_windows_installer_gold_proof.py "
            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            "watch=python3 scripts/auto_import_windows_installer_gold_proof.py "
            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} --wait-seconds 900",
            markdown,
        )
        self.assertIn(
            "windows watcher state: status=running pid=1866861 matches=1 duplicates=0 "
            f"attention=false state={Path(temp_dir) / 'state' / 'windows_installer_gold_proof_watcher.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows watcher control: "
            f"start=python3 watcher-start --intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            f"status=python3 watcher-status --intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            f"stop=python3 watcher-stop --intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows auto-import state: "
            "status=fail actionable=0 matching_dirs=0 matching_zips=0 stale_dirs=11 "
            f"artifact=/tmp/windows-installer-gold-proof-a.zip receipt={published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows auto-import failure: "
            "type=BadZipFile message=File is not a zip file "
            "summary=Selected Windows installer gold-proof artifact failed import validation.",
            markdown,
        )
        self.assertIn(
            "windows stage-proof hints: "
            f"total=3 matching_promoted=0 stale=3 receipt={published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows stage-proof hint paths: "
            "/tmp/chummer6-ui-publishfix/Docker/Downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; "
            "/tmp/chummer6-ui-publishfix/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            markdown,
        )
        self.assertIn(
            "windows stage-proof hint note: Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
            markdown,
        )
        self.assertIn(
            "windows startup-smoke hints: total=2 matching_promoted=1 stale=1 "
            f"receipt={published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows startup-smoke hint note: Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. "
            "Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. "
            "Additional digest-mismatched startup-smoke receipts were summarized separately.",
            markdown,
        )
        self.assertIn(
            "windows startup-smoke hint paths: "
            "/tmp/chummer6-ui-publishfix/Docker/Downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json; "
            "/tmp/stale/startup-smoke-avalonia-win-x64.receipt.json",
            markdown,
        )
        self.assertEqual(
            2,
            visual_audit["operator_request_artifacts"]["auto_import_stage_like_stale_directory_candidate_count"],
        )
        self.assertEqual(
            2,
            len(visual_audit["operator_request_artifacts"]["auto_import_stale_directory_digest_summary"]),
        )
        self.assertIn(
            "windows auto-import stale digests: "
            f"{'d' * 12} count=2 stage_like=2; {'e' * 12} count=9 stage_like=0 "
            "(stage_like_total=2)",
            markdown,
        )
        self.assertIn(
            "windows auto-import note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.",
            markdown,
        )
        self.assertEqual("pass", visual_audit["receipt_verifier"]["status"])
        self.assertTrue(visual_audit["operator_request_artifacts"]["pass"])
        self.assertIn("windows proof verifier: structural_status=pass", markdown)

    def test_dashboard_blocks_stale_release_blocking_receipt(self) -> None:
        module = load_module()
        module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = False
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-stale-receipt-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            windows_path = published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                windows_path: passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)
            stale_windows = passing_windows_installer_visual_audit_payload()
            stale_windows["generated_at_utc"] = stale_timestamp()
            windows_path.write_text(
                json.dumps(stale_windows) + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        visual_audit = payload["checks"]["windows_installer_visual_audit"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(visual_audit["pass"])
        self.assertFalse(visual_audit["fresh"])
        self.assertEqual(module.RELEASE_BLOCKING_MAX_AGE_HOURS, visual_audit["fresh_within_hours"])
        self.assertIn("windows_installer_visual_audit", payload["failures"])
        self.assertIn(
            "windows_installer_visual_audit generated_at is missing or stale for operator dashboard",
            visual_audit["failures"],
        )
        self.assertIn("fresh=False", markdown)

    def test_dashboard_blocks_stale_google_oauth_linking_proof(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-stale-oauth-receipt-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            oauth_path = published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                oauth_path: {"status": "pass", "generated_at": stale_timestamp()},
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)
            stale_oauth = json.loads(oauth_path.read_text(encoding="utf-8"))
            stale_oauth["generated_at"] = stale_timestamp()
            stale_oauth.pop("generated_at_utc", None)
            oauth_path.write_text(
                json.dumps(stale_oauth) + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        oauth = payload["checks"]["google_oauth_linking_proof"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(oauth["pass"])
        self.assertFalse(oauth["fresh"])
        self.assertEqual(module.RELEASE_BLOCKING_MAX_AGE_HOURS, oauth["fresh_within_hours"])
        self.assertIn("google_oauth_linking_proof", payload["failures"])
        self.assertIn(
            "google_oauth_linking_proof generated_at is missing or stale for operator dashboard",
            oauth["failures"],
        )
        self.assertIn("fresh=False", markdown)

    def test_dashboard_surfaces_google_oauth_missing_operator_evidence_path(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-google-oauth-failed-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            telegram = Path(temp_dir) / "telegram"
            telegram.mkdir(parents=True, exist_ok=True)
            google_ask_text_path = Path(temp_dir) / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
            google_ask_metadata_path = Path(temp_dir) / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
            google_ask_template_path = Path(temp_dir) / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
            google_ask_text_path.write_text("current operator ask\n", encoding="utf-8")
            google_ask_metadata_path.write_text("{}\n", encoding="utf-8")
            google_ask_template_path.write_text("{}\n", encoding="utf-8")
            (telegram / "google-oauth-linking-operator-ask.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": fresh_timestamp(),
                        "text_sha256": hashlib.sha256("stale operator ask\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {
                    "contract_name": "chummer.run.google_oauth_linking_proof",
                    "proof_contract_version": 3,
                    "status": "fail",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": fresh_timestamp(),
                    "bindings": {
                        "release": {},
                        "request": {},
                        "evidence": {},
                        "programs": {},
                    },
                    "quick_handoff_probe": {"pass": True},
                    "signed_in_link_handoff": {"status": "operator_required", "pass": False},
                    "failures": [
                        "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                    ],
                    "operator_end_to_end_evidence": {
                        "pass": False,
                        "exists": False,
                        "path": "/tmp/operator-evidence.json",
                        "failures": [
                            "missing operator evidence receipt: /tmp/operator-evidence.json",
                        ],
                    },
                    "operator_request_artifacts": {
                        "pass": True,
                        "request_receipt_path": "/tmp/operator-request.generated.json",
                        "required_operator_evidence_path": "/tmp/operator-evidence.json",
                        "operator_ask_text_path": str(google_ask_text_path),
                        "preferred_drop_path": "/tmp/google-oauth-linking-operator-evidence.zip",
                        "operator_ask_send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google-oauth-linking-operator-ask.receipt.json",
                        "operator_ask_metadata_path": str(google_ask_metadata_path),
                        "operator_evidence_template_path": str(google_ask_template_path),
                        "operator_ask_receipt_name": "google-oauth-linking-operator-ask.receipt.json",
                        "import_command": (
                            "python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py "
                            "/tmp/google-oauth-linking-operator-evidence.zip "
                            "--intake-request /tmp/operator-request.generated.json --verify"
                        ),
                        "auto_import_watch_command": (
                            "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py "
                            "--intake-request /tmp/operator-request.generated.json --wait-seconds 900 --poll-seconds 10"
                        ),
                        "failures": [],
                    },
                },
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "TELEGRAM_TEXT_DELIVERY_ROOT", telegram), \
                mock.patch.object(
                    module,
                    "google_oauth_linking_receipt_verifier",
                    return_value={
                        "contract_name": "chummer.run.google_oauth_linking_proof",
                        "status": "fail",
                        "proof_status": "fail",
                        "proof_contract_version": 3,
                        "release_authority_ready": True,
                        "issues": [
                            "evidence: missing regular file: /tmp/operator-evidence.json",
                        ],
                    },
                ):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        oauth = payload["checks"]["google_oauth_linking_proof"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(oauth["pass"])
        self.assertIn("google_oauth_linking_proof", payload["failures"])
        self.assertIn(
            "google_oauth_operator_evidence",
            [item["id"] for item in payload["root_blockers"]],
        )
        self.assertIn("google oauth operator evidence is still missing: /tmp/operator-evidence.json", payload["failures"])
        self.assertIn("google oauth operator evidence is still missing: /tmp/operator-evidence.json", oauth["failures"])
        self.assertNotIn(
            f"google oauth operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google-oauth-linking-operator-ask.receipt.json",
            payload["failures"],
        )
        self.assertNotIn(
            f"google oauth operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google-oauth-linking-operator-ask.receipt.json",
            oauth["failures"],
        )
        self.assertIn(
            f"google oauth operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google-oauth-linking-operator-ask.receipt.json",
            oauth["advisoryActions"],
        )
        self.assertIn(
            "`google_oauth_operator_evidence`: Browser-backed Google OAuth linking evidence is still missing.",
            markdown,
        )
        self.assertIn(
            f"google oauth operator evidence: required_path=/tmp/operator-evidence.json request_receipt=/tmp/operator-request.generated.json ask_text={google_ask_text_path} preferred_drop=/tmp/google-oauth-linking-operator-evidence.zip",
            markdown,
        )
        self.assertIn(
            f"google oauth operator packet: ask_meta={google_ask_metadata_path} template={google_ask_template_path}",
            markdown,
        )
        self.assertIn(
            f"google oauth operator ask send: python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google-oauth-linking-operator-ask.receipt.json",
            markdown,
        )
        self.assertIn(
            f"google oauth operator ask resend: python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google-oauth-linking-operator-ask.receipt.json",
            markdown,
        )
        self.assertIn(
            "google oauth operator intake: "
            "import=python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py "
            "/tmp/google-oauth-linking-operator-evidence.zip "
            "--intake-request /tmp/operator-request.generated.json --verify "
            "watch=python3 scripts/auto_import_google_oauth_linking_operator_evidence.py "
            "--intake-request /tmp/operator-request.generated.json --wait-seconds 900 --poll-seconds 10",
            markdown,
        )
        self.assertIn(
            "google oauth proof verifier: structural_status=fail operator_evidence_pass=false recovery_pack=false",
            markdown,
        )

    def test_dashboard_treats_google_signed_in_preflight_only_failure_as_nonblocking_context(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-google-signed-in-preflight-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            root_release_blockers = Path(temp_dir) / "RELEASE_BLOCKERS.generated.json"
            root_release_blockers.write_text(
                json.dumps({"generated_at": fresh_timestamp(), "root_blockers": []}) + "\n",
                encoding="utf-8",
            )

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {
                    "contract_name": "chummer.run.google_oauth_linking_proof",
                    "proof_contract_version": 2,
                    "status": "fail",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": fresh_timestamp(),
                    "quick_handoff_probe": {"pass": True},
                    "signed_in_link_handoff": {"status": "fail", "pass": False},
                    "operator_end_to_end_evidence": {"pass": True, "exists": True, "failures": []},
                    "operator_request_artifacts": {
                        "pass": True,
                        "request_status": "not_required",
                        "failures": [],
                    },
                    "failures": [
                        "signed_in_link_handoff: /home returned 302, expected 200",
                        "signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
                    ],
                },
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "channel": "stable",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "ROOT_RELEASE_BLOCKERS_PATH", root_release_blockers):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        oauth = payload["checks"]["google_oauth_linking_proof"]
        self.assertEqual("pass", payload["status"])
        self.assertFalse(oauth["pass"])
        self.assertTrue(oauth["release_truth_effective_pass"])
        self.assertFalse(oauth["release_blocking"])
        self.assertNotIn("google_oauth_linking_proof", payload["failed_release_blocking_checks"])
        self.assertNotIn("google_oauth_linking_proof", payload["summary"]["failed_release_blocking_checks"])
        self.assertNotIn("google_oauth_linking_proof", payload["failures"])
        self.assertIn("- INFO `google_oauth_linking_proof`:", markdown)

    def test_dashboard_treats_effectively_not_required_google_request_as_non_blocking(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-google-effective-request-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            root_release_blockers = Path(temp_dir) / "RELEASE_BLOCKERS.generated.json"
            root_release_blockers.write_text(json.dumps({"root_blockers": []}), encoding="utf-8")

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {
                    "contract_name": "chummer.run.google_oauth_linking_proof",
                    "proof_contract_version": 2,
                    "status": "fail",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": fresh_timestamp(),
                    "quick_handoff_probe": {"pass": True},
                    "signed_in_link_handoff": {"status": "fail", "pass": False},
                    "operator_end_to_end_evidence": {"pass": True, "exists": True, "failures": []},
                    "operator_request_artifacts": {
                        "pass": True,
                        "request_status": "operator_action_required",
                        "request_effective_status": "not_required",
                        "failures": [],
                    },
                    "failures": [
                        "signed_in_link_handoff: /home returned 302, expected 200",
                        "signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
                    ],
                },
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "channel": "stable",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "ROOT_RELEASE_BLOCKERS_PATH", root_release_blockers):
                payload = module.build_payload()

        oauth = payload["checks"]["google_oauth_linking_proof"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(oauth["release_truth_effective_pass"])
        self.assertFalse(oauth["release_blocking"])
        self.assertNotIn("google_oauth_linking_proof", payload["failed_release_blocking_checks"])

    def test_dashboard_treats_user_paused_google_signin_automation_as_non_blocking(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-google-paused-user-request-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            root_release_blockers = Path(temp_dir) / "RELEASE_BLOCKERS.generated.json"
            root_release_blockers.write_text(json.dumps({"root_blockers": []}), encoding="utf-8")

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {
                    "contract_name": "chummer.run.google_oauth_linking_proof",
                    "proof_contract_version": 2,
                    "status": "fail",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": fresh_timestamp(),
                    "operator_request_artifacts": {
                        "pass": True,
                        "request_status": "not_required",
                        "request_effective_status": "not_required",
                        "operator_action_still_required": False,
                        "failures": [],
                    },
                    "failures": [
                        "auth_signin_automation_paused: paused by user request on 2026-07-08",
                    ],
                },
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-test",
                    "channel": "stable",
                },
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "ROOT_RELEASE_BLOCKERS_PATH", root_release_blockers):
                payload = module.build_payload()

        oauth = payload["checks"]["google_oauth_linking_proof"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(oauth["release_truth_effective_pass"])
        self.assertEqual(
            "auth_signin_automation_paused_by_user_request",
            oauth["release_truth_effective_pass_reason"],
        )
        self.assertFalse(oauth["release_blocking"])
        self.assertNotIn("google_oauth_linking_proof", payload["failed_release_blocking_checks"])

    def test_dashboard_surfaces_blazor_execution_horizon_bridge_as_non_release_blocking_info(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-blazor-execution-horizon-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            play_surface_horizon_path = Path(temp_dir) / "play-surface" / "BLAZOR_PLAY_SURFACE_HORIZON.generated.json"
            play_surface_horizon_path.parent.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json": passing_blazor_execution_horizon_bridge_payload(),
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                play_surface_horizon_path: passing_blazor_play_surface_horizon_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry), \
                mock.patch.object(module, "WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES", (play_surface_horizon_path,)):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        bridge = payload["checks"]["blazor_execution_horizon_bridge"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(bridge["pass"])
        self.assertFalse(bridge["release_blocking"])
        self.assertEqual(
            "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven",
            bridge["summary"]["verdict"],
        )
        self.assertEqual("proven", bridge["summary"]["near_term_smoke_status"])
        self.assertEqual("not_proven", bridge["summary"]["mid_term_full_matrix_status"])
        self.assertEqual("not_proven", bridge["summary"]["long_term_full_browser_parity_status"])
        self.assertEqual(
            ["near_term_stabilization", "mid_term_pwa_session_utility", "long_term_living_world_expansion"],
            [item["id"] for item in bridge["summary"]["play_surface_horizon"]["horizons"]],
        )
        self.assertEqual(
            ["runner data", "workspace data", "API traffic", "Black Ledger state", "heat state", "session state"],
            bridge["summary"]["play_surface_horizon"]["mid_term_server_bound_boundaries"],
        )
        self.assertNotIn("blazor_execution_horizon_bridge", payload["failures"])
        self.assertIn(
            "- PASS `blazor_execution_horizon_bridge`: `pass` (operator context, not release-blocking)",
            markdown,
        )
        self.assertIn(
            "blazor bridge: verdict=mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven "
            "hub_mobile=pass blazor_pwa=passed near_term=proven mid_term=not_proven "
            "mid_term_workflows=9/49 long_term=not_proven",
            markdown,
        )
        self.assertIn(
            "play-surface horizons: near_term_stabilization=proven, "
            "mid_term_pwa_session_utility=mixed, long_term_living_world_expansion=staged",
            markdown,
        )
        self.assertIn(
            "mid-term server-bound boundaries: runner data, workspace data, API traffic, Black Ledger state, heat state, session state",
            markdown,
        )

    def test_dashboard_surfaces_ea_operator_readiness_as_non_release_blocking_info(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-ea-operator-readiness-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "EA_OPERATOR_READINESS.generated.json": passing_ea_operator_readiness_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        ea = payload["checks"]["ea_operator_readiness"]
        self.assertEqual("pass", payload["status"])
        self.assertFalse(ea["pass"])
        self.assertFalse(ea["release_blocking"])
        self.assertEqual("ready_with_actions", ea["status"])
        self.assertEqual(["pushbullet"], ea["next_action_component_keys"])
        self.assertEqual(["mymedia_alexa"], ea["advisory_action_component_keys"])
        self.assertEqual("pass", ea["receipt_verifier"]["status"])
        self.assertNotIn("ea_operator_readiness", payload["failures"])
        self.assertIn(
            "- INFO `ea_operator_readiness`: `ready_with_actions` (operator context, not release-blocking)",
            markdown,
        )
        self.assertIn(
            "ea operator readiness: ready=false runtime_status=degraded attention=1 blocked=0 next=pushbullet supplemental=none advisory=mymedia_alexa",
            markdown,
        )
        self.assertIn(
            "ea operator receipt verifier: structural_status=pass operator_status=ready_with_actions runtime_status=degraded",
            markdown,
        )
        self.assertIn(
            "pushbullet: create_missing_pushbullet_access_tokens",
            markdown,
        )
        self.assertIn(
            "mymedia_alexa: wait_for_mymedia_library_scan",
            markdown,
        )

    def test_dashboard_surfaces_operator_supplemental_actions_separately(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-ea-supplemental-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            ea_payload = passing_ea_operator_readiness_payload()
            for component in ea_payload["components"]:
                if component["key"] == "google_workspace_oauth":
                    component.update(
                        {
                            "ready": False,
                            "status": "ready_retry_required",
                            "reason": "oauth_retry_or_account_selection_required",
                            "next_action": "retry_full_workspace_auth_with_approved_account",
                            "next_action_href": "/integrations/google",
                            "next_action_label": "Retry Google auth",
                            "next_action_method": "get",
                        }
                    )
                elif component["key"] == "whatsapp_pairing":
                    component.update(
                        {
                            "ready": False,
                            "status": "available",
                            "reason": "",
                            "next_action": "scan_whatsapp_web_qr",
                            "next_action_href": "host-local:///sessions/redacted/pair",
                            "next_action_label": "Open WhatsApp pairing",
                            "next_action_method": "get",
                        }
                    )
            ea_payload.update(
                {
                    "runtime_status": "blocked",
                    "blocking_count": 1,
                    "advisory_count": 0,
                    "attention_required_count": 1,
                    "blocked_count": 1,
                    "ready_component_keys": [
                        "telegram",
                        "whatsapp",
                        "teable_recovery",
                        "mymedia_alexa",
                    ],
                    "attention_component_keys": ["google_workspace_oauth"],
                    "blocked_component_keys": ["google_workspace_oauth"],
                    "blocking_findings": ["blocked:google_workspace_oauth:ready_retry_required"],
                    "advisory_findings": [],
                    "steering_component_keys": [
                        "telegram",
                        "google_workspace_oauth",
                        "teable_recovery",
                        "mymedia_alexa",
                    ],
                    "next_action_component_keys": ["google_workspace_oauth"],
                    "supplemental_attention_count": 2,
                    "supplemental_blocked_count": 1,
                    "supplemental_probe_failed_count": 0,
                    "supplemental_attention_component_keys": ["pushbullet", "whatsapp_pairing"],
                    "supplemental_blocked_component_keys": ["whatsapp_pairing"],
                    "supplemental_probe_failed_component_keys": [],
                    "supplemental_next_action_component_keys": ["pushbullet", "whatsapp_pairing"],
                    "supplemental_next_actions": [
                        {
                            "component_key": "pushbullet",
                            "component_label": "Pushbullet operator delivery",
                            "action": "create_missing_pushbullet_access_tokens",
                            "reason": "pushbullet_token_missing",
                            "href": "https://www.pushbullet.com/#settings/account",
                            "label": "Open Pushbullet account settings",
                            "method": "get",
                        },
                        {
                            "component_key": "whatsapp_pairing",
                            "component_label": "WhatsApp Web pairing recovery",
                            "action": "scan_whatsapp_web_qr",
                            "reason": "",
                            "href": "host-local:///sessions/redacted/pair",
                            "label": "Open WhatsApp pairing",
                            "method": "get",
                        },
                    ],
                    "next_actions": [
                        {
                            "component_key": "google_workspace_oauth",
                            "component_label": "Google Workspace OAuth",
                            "action": "retry_full_workspace_auth_with_approved_account",
                            "reason": "oauth_retry_or_account_selection_required",
                            "href": "/integrations/google",
                            "label": "Retry Google auth",
                            "method": "get",
                        }
                    ],
                }
            )

            receipts = {
                published / "QBITTORRENT_STAGING_HYGIENE.generated.json": passing_qbittorrent_staging_hygiene_payload(),
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "EA_OPERATOR_READINESS.generated.json": ea_payload,
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                markdown = module.build_markdown(module.build_payload())

        self.assertIn(
            "ea operator readiness: ready=false runtime_status=blocked attention=1 blocked=1 next=google_workspace_oauth supplemental=pushbullet,whatsapp_pairing advisory=mymedia_alexa",
            markdown,
        )

    def test_dashboard_accepts_nested_current_public_edge_anchor_shape(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-legacy-public-edge-anchor-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": nested_public_edge_postdeploy_anchor_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        public_edge = payload["checks"]["public_edge_postdeploy_gate"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(public_edge["pass"])
        self.assertEqual("pass", public_edge["status"])
        self.assertNotIn("missing postdeploy fields", "\n".join(public_edge.get("failures", [])))
        self.assertEqual(
            "chummer.frontdoor_mobile_anchor_redirect.v2",
            public_edge["summary"]["frontdoor_navigation_anchor_artifact_contract"],
        )
        self.assertEqual(
            "/mobile/player",
            public_edge["summary"]["frontdoor_navigation_anchor_final_path"],
        )
        self.assertIn("- PASS `public_edge_postdeploy_gate`: `pass`", markdown)

    def test_dashboard_marks_stale_ea_operator_readiness_as_stale_info_not_release_blocker(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-stale-ea-operator-readiness-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            ea_payload = passing_ea_operator_readiness_payload()
            ea_payload["generated_at_utc"] = stale_timestamp()

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "EA_OPERATOR_READINESS.generated.json": ea_payload,
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        ea = payload["checks"]["ea_operator_readiness"]
        self.assertEqual("pass", payload["status"])
        self.assertFalse(ea["pass"])
        self.assertFalse(ea["release_blocking"])
        self.assertFalse(ea["fresh"])
        self.assertIn(
            "ea_operator_readiness generated_at is missing or stale for operator dashboard",
            ea["failures"],
        )
        self.assertNotIn("ea_operator_readiness", payload["failures"])
        self.assertIn("fresh=False", markdown)

    def test_dashboard_surfaces_mymedia_public_surface_as_non_release_blocking_info(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-mymedia-public-surface-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "verdict": "READY", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "MYMEDIA_PUBLIC_SURFACE.generated.json": passing_mymedia_public_surface_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        mymedia = payload["checks"]["mymedia_public_surface"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(mymedia["pass"])
        self.assertFalse(mymedia["release_blocking"])
        self.assertEqual("access_protected", mymedia["status"])
        self.assertEqual("pass", mymedia["receipt_verifier"]["status"])
        self.assertNotIn("mymedia_public_surface", payload["failures"])
        self.assertIn(
            "- PASS `mymedia_public_surface`: `access_protected` (operator context, not release-blocking)",
            markdown,
        )
        self.assertIn(
            "mymedia public surface: ready=true status=access_protected runtime_status=ready http=302 access_protected=true cloudflare_blocked=false url=https://mymedia.girschele.com",
            markdown,
        )
        self.assertIn(
            "mymedia public surface verifier: structural_status=pass mymedia_status=ready_library_scan_in_progress runtime_status=ready",
            markdown,
        )

    def test_dashboard_surfaces_host_workload_mirror_eta_as_non_release_blocking_info(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-host-workload-runtime-health-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json": passing_host_workload_runtime_health_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        host = payload["checks"]["host_workload_runtime_health"]
        self.assertEqual("pass", payload["status"])
        self.assertFalse(host["pass"])
        self.assertFalse(host["release_blocking"])
        self.assertEqual("degraded", host["status"])
        self.assertEqual("pass", host["receipt_verifier"]["status"])
        self.assertNotIn("host_workload_runtime_health", payload["failures"])
        self.assertIn(
            "- INFO `host_workload_runtime_health`: `degraded` (operator context, not release-blocking)",
            markdown,
        )
        self.assertIn(
            "host workload runtime: ready=false status=degraded blocking=none advisory=plex_internxt_mirror_failed qbit_write_probe=true qbit_fast_resume_rejected=0 cache_mode=writes internxt_cache_bytes=6654089437 mirror=running mirror_phase=movies mirror_progress=325/2235 mirror_eta_seconds=1800 next=none advisory_components=internxt_mirror",
            markdown,
        )
        self.assertIn(
            "host workload runtime verifier: structural_status=pass runtime_status=degraded",
            markdown,
        )

    def test_dashboard_surfaces_suppressed_host_workload_mirror_eta_honestly(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-host-workload-runtime-health-suppressed-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            host_payload = passing_host_workload_runtime_health_payload()
            host_payload["runtime_observation"]["plex_internxt_mirror"]["phase"] = "tv"
            host_payload["runtime_observation"]["plex_internxt_mirror"]["overall_current"] = 1655
            host_payload["runtime_observation"]["plex_internxt_mirror"]["eta_seconds"] = None
            host_payload["runtime_observation"]["plex_internxt_mirror"]["eta_suppressed_reason"] = "journal_current_entry_long_running"
            host_payload["stdout_tail"] = "runtime_status=degraded mirror_status=running mirror_phase=tv mirror_progress=1655/2235"

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json": host_payload,
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        self.assertIn(
            "host workload runtime: ready=false status=degraded blocking=none advisory=plex_internxt_mirror_failed qbit_write_probe=true qbit_fast_resume_rejected=0 cache_mode=writes internxt_cache_bytes=6654089437 mirror=running mirror_phase=tv mirror_progress=1655/2235 mirror_eta_seconds=suppressed:journal_current_entry_long_running next=none advisory_components=internxt_mirror",
            markdown,
        )

    def test_dashboard_surfaces_qbittorrent_staging_hygiene_as_non_release_blocking_info(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-qbittorrent-staging-hygiene-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "FLAGSHIP_PRODUCT_READINESS.generated.json": passing_flagship_product_readiness_payload(),
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "summary": {"route_count": 12, "failed_count": 0, "negative_path_failed_count": 0},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": passing_public_edge_postdeploy_payload(),
                published / "TEABLE_IMPORTANT_WORK.generated.json": passing_teable_important_work_payload(),
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": passing_windows_installer_visual_audit_payload(),
                completion / "UI_FRAME_INTEGRITY.generated.json": {
                    "status": "pass",
                    "verdict": "READY", "base_url": "https://chummer.run",
                    "summary": {"checked_pages": 1, "failure_count": 0},
                },
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "DESIGN_READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": passing_release_ready_payload(),
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": passing_google_oauth_linking_proof_payload(),
                published / "QBITTORRENT_STAGING_HYGIENE.generated.json": passing_qbittorrent_staging_hygiene_payload(),
                registry / "RELEASE_CHANNEL.generated.json": {"status": "published", "version": "run-test", "channel": "stable"},
            }
            write_receipts(receipts)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        qbit = payload["checks"]["qbittorrent_staging_hygiene"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(qbit["pass"])
        self.assertFalse(qbit["release_blocking"])
        self.assertEqual("ready", qbit["status"])
        self.assertEqual("pass", qbit["receipt_verifier"]["status"])
        self.assertNotIn("qbittorrent_staging_hygiene", payload["failures"])
        self.assertIn(
            "- PASS `qbittorrent_staging_hygiene`: `ready` (operator context, not release-blocking)",
            markdown,
        )
        self.assertIn(
            "qbittorrent staging hygiene: ready=true status=ready orphan_partials=0 orphan_partial_gib=0 dead_meta=0 dead_stalled=0 dead_checking=0 requeued_meta=1 requeued_stalled=2 requeued_checking=3 advisory=none",
            markdown,
        )
        self.assertIn(
            "qbittorrent staging hygiene verifier: structural_status=pass runtime_status=ready",
            markdown,
        )
