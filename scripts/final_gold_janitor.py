#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_windows_installer_visual_audit_intake_request import (
    verify as verify_windows_visual_intake_request_receipt,
)
from public_edge_postdeploy_contract import (
    normalize_public_edge_postdeploy_payload,
    public_edge_v2_offline_failures,
    public_edge_v2_private_identity_failures,
)

RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
PUBLISHED_ROOT = DEFAULT_PUBLISHED_ROOT
DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND = [
    "python3",
    "scripts/verify_flagship_product_readiness_gate.py",
    "--summary-output",
    str(DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH),
]
TELEGRAM_TEXT_DELIVERY_ROOT = RUN_SERVICES_ROOT.parent / "_completion" / "telegram_text_delivery"
REGISTRY_ROOT = RUN_SERVICES_ROOT.parent / "chummer-hub-registry" / ".codex-studio" / "published"
ROOT_RELEASE_BLOCKERS_PATH = RUN_SERVICES_ROOT.parent / "RELEASE_BLOCKERS.generated.json"
WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES = (
    RUN_SERVICES_ROOT.parent / "chummer-presentation" / ".codex-studio" / "published" / "BLAZOR_PLAY_SURFACE_HORIZON.generated.json",
    RUN_SERVICES_ROOT.parent / "chummer6-ui" / ".codex-studio" / "published" / "BLAZOR_PLAY_SURFACE_HORIZON.generated.json",
)
PUBLIC_RELEASE_SNAPSHOT_PATH = RUN_SERVICES_ROOT.parent / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT.generated.json"
PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH = RUN_SERVICES_ROOT.parent / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
COMPLETION_ROOT = Path("/docker/chummercomplete/_completion")
ARTIFACT_ROOT_NAME = os.environ.get("CHUMMER_FINAL_GOLD_ARTIFACT_ROOT", "full_product_reaudit_v20")
ARTIFACT_ROOT = COMPLETION_ROOT / ARTIFACT_ROOT_NAME
UI_LAYOUT_COMPLETION_ROOT = COMPLETION_ROOT / "chummer_run_redesign_closure"
LEGACY_GOLD_CLOSURE_ROOT = COMPLETION_ROOT / "gold_readiness_closure"
FLEET_COMPLETION_ROOT = Path(os.environ.get("CHUMMER_FLEET_COMPLETION_ROOT", "/docker/fleet/_completion"))
FLEET_ARTIFACT_ROOT = FLEET_COMPLETION_ROOT / ARTIFACT_ROOT_NAME
DEFAULT_BASE_URL = os.environ.get("CHUMMER_FINAL_GOLD_BASE_URL", "https://chummer.run")
EXPECTED_PUBLIC_EDGE_RELEASE_CHANNEL = os.environ.get("CHUMMER_FINAL_GOLD_EXPECTED_RELEASE_CHANNEL", "nightly")
RECRAWL_MAX_AGE_HOURS = 24
MATERIALIZER_TIMEOUT_SECONDS = int(os.environ.get("CHUMMER_FINAL_GOLD_MATERIALIZER_TIMEOUT_SECONDS", "600"))
FRESHNESS_REQUIRED_GATES = {
    "live_public_web_recrawl",
    "rule_authority_minimum_coverage",
    "ruleset_readiness",
    "public_route_proof",
    "icanpreneur_discovery_lane",
    "provider_proof_discoverability",
    "desktop_native_model_depth",
    "black_ledger_live_media_proof",
    "table_pulse_scenario_replay",
    "live_surface_parity",
    "live_public_windows_installer",
    "public_edge_postdeploy_gate",
    "blazor_execution_horizon_bridge",
    "ltd_optimization_stack",
    "external_distribution_mirror_proof",
    "public_copy_leak_gate",
    "participate_billing_honesty",
    "account_handoff_runtime_config",
    "premium_ui_design_exit_gate",
    "design_quality_gate",
    "windows_installer_visual_audit",
    "ui_layout_exit_gate",
    "operator_release_dashboard",
    "release_ready",
}


def _effective_freshness_required_gates() -> set[str]:
    checks = set(FRESHNESS_REQUIRED_GATES)
    if IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        checks.discard("windows_installer_visual_audit")
    return checks


# Accepted boundaries and operator advisories should be surfaced, but they should not
# override passing required gates into a false NOT_GOLD verdict.
FAIL_CLOSED_CAVEAT_IDS: set[str] = set()
RELEASE_READY_CONTRACT_NAME = "chummer.release_ready"
READY_VERDICT = "READY"
RELEASE_READY_VERDICT = "RELEASE_READY"
DESIGN_READY_VERDICT = "DESIGN_READY"
FLAGSHIP_PRODUCT_READY_VERDICT = "FLAGSHIP_PRODUCT_READY"
FLAGSHIP_PRODUCT_NOT_READY_VERDICT = "NOT_FLAGSHIP_PRODUCT_READY"
OPERATOR_DASHBOARD_CONTRACT_NAME = "chummer.operator_release_dashboard"
PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME = "chummer.public_edge_postdeploy_gate.v1"
WINDOWS_INSTALLER_VISUAL_AUDIT_CONTRACT_NAME = "chummer.windows_installer_visual_audit"
PASS_VERDICT_EXPECTATIONS: dict[str, set[str]] = {
    "desktop_native_model_depth": {"DESKTOP_NATIVE_MODEL_READY"},
    "live_surface_parity": {"LIVE_SURFACE_PARITY_READY"},
    "live_public_windows_installer": {"LIVE_PUBLIC_WINDOWS_INSTALLER_READY"},
    "blazor_execution_horizon_bridge": {
        "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven",
        "mobile_pwa_and_blazor_full_matrix_integrated",
        "mobile_pwa_and_blazor_full_matrix_and_long_term_browser_parity_integrated",
    },
    "ltd_optimization_stack": {"LTD_OPTIMIZATION_STACK_READY"},
    "participate_billing_honesty": {READY_VERDICT},
    "account_handoff_runtime_config": {READY_VERDICT},
    "design_quality_gate": {DESIGN_READY_VERDICT},
    "ui_layout_exit_gate": {"UI_LAYOUT_EXIT_READY"},
}
WINDOWS_RUNTIME_ARTIFACT_FIELDS = (
    "operator_ask_send_command",
    "operator_ask_resend_command",
    "watcher_state_receipt_path",
    "watcher_state_receipt_exists",
    "watcher_state_receipt_load_status",
    "watcher_state_receipt_generated_at_utc",
    "watcher_status",
    "watcher_pid",
    "watcher_process_alive",
    "watcher_matching_process_pids",
    "watcher_matching_process_count",
    "watcher_duplicate_process_pids",
    "watcher_duplicate_process_count",
    "watcher_note",
    "watcher_attention_required",
    "auto_import_receipt_path",
    "auto_import_receipt_exists",
    "auto_import_receipt_load_status",
    "auto_import_receipt_status",
    "auto_import_receipt_generated_at_utc",
    "auto_import_artifact",
    "auto_import_import_failure",
    "auto_import_import_failure_type",
    "auto_import_import_failure_message",
    "auto_import_import_failure_code",
    "auto_import_import_failure_summary",
    "auto_import_actionable_candidate_count",
    "auto_import_matching_promoted_directory_candidate_count",
    "auto_import_matching_promoted_zip_candidate_count",
    "auto_import_stale_directory_candidate_count",
    "auto_import_stage_like_stale_directory_candidate_count",
    "auto_import_stage_visual_proof_receipt_count",
    "auto_import_matching_promoted_stage_visual_proof_receipt_count",
    "auto_import_stale_stage_visual_proof_receipt_count",
    "auto_import_suppressed_stale_stage_visual_proof_receipt_count",
    "auto_import_stage_startup_smoke_receipt_count",
    "auto_import_matching_promoted_stage_startup_smoke_receipt_count",
    "auto_import_stale_stage_startup_smoke_receipt_count",
    "auto_import_suppressed_stale_stage_startup_smoke_receipt_count",
    "auto_import_stale_directory_digest_summary",
    "auto_import_stage_visual_proof_receipt_note",
    "auto_import_stage_startup_smoke_receipt_note",
    "auto_import_directory_candidate_note",
)
FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME = "chummer.flagship_product_readiness_gate.v1"
PASS_STATES = {"pass", "passed", "ready"}
SNAPSHOT_CONSISTENT_LAUNCH_READY_VERDICT = "SNAPSHOT_CONSISTENT_LAUNCH_READY"
FLAGSHIP_PRODUCT_READINESS_RECOVERABLE_LAUNCH_BLOCKERS = {
    "final gold janitor state is 'fail'",
    "final gold janitor verdict is 'NOT_GOLD'",
    "live-backed gold claim is not allowed",
}
IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = os.environ.get(
    "CHUMMER_IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING",
    "0",
).strip().lower() in {"1", "true", "yes", "on"}
WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST_NAME = "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT_NAME = "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json"
INACTIVE_OPERATOR_REQUEST_ACTION_FIELDS = (
    "operator_ask_send_command",
    "preferred_drop_path",
    "preferred_drop_path_exists",
    "preferred_zip_name",
    "required_zip_filename",
    "discover_command",
    "import_command",
    "auto_import_command",
    "auto_import_watch_command",
    "post_import_verify_command",
    "post_import_verify_note",
    "post_import_commands",
    "expected_artifact_patterns",
    "drop_roots_checked",
)


def is_published_stable_release(
    expected_release_status: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
) -> bool:
    normalized_status = str(expected_release_status or "").strip().lower()
    normalized_channel = str(expected_release_channel or "").strip().lower()
    normalized_supportability_state = str(expected_supportability_state or "").strip().lower()
    normalized_rollout_state = str(expected_rollout_state or "").strip().lower()
    stable_lane_published = (
        normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == RELEASE_CHANNEL_PUBLIC_STABLE_ROLLOUT_STATE
    )
    status_allows_stable_release = not normalized_status or normalized_status == "published"
    return (
        stable_lane_published
        and normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        and status_allows_stable_release
    )


def expected_visible_version_candidates(
    expected_release_version: str,
    expected_release_status: str = "",
    expected_release_channel: str = "",
    expected_supportability_state: str = "",
    expected_rollout_state: str = "",
) -> list[str]:
    normalized = str(expected_release_version or "").strip()
    if not normalized:
        return []

    posture_known = any(
        (
            str(expected_release_status or "").strip(),
            str(expected_release_channel or "").strip(),
            str(expected_supportability_state or "").strip(),
            str(expected_rollout_state or "").strip(),
        )
    )
    stable_release = is_published_stable_release(
        expected_release_status,
        expected_release_channel,
        expected_supportability_state,
        expected_rollout_state,
    )
    candidates: list[str] = [f"Version {normalized}"]
    if normalized.lower().startswith("run-") and len(normalized) >= 12:
        stamp = normalized[4:12]
        if stamp.isdigit():
            stable_label = f"Version {stamp[0:4]}.{stamp[4:6]}.{stamp[6:8]}"
            preview_label = f"{stable_label} (Preview)"
            candidates.insert(0, stable_label if stable_release else preview_label)
            if not posture_known:
                candidates.insert(1, preview_label)
                candidates.insert(2, stable_label)
        else:
            candidates.insert(0, "Version" if stable_release else "Version Preview")
            if not posture_known:
                candidates.insert(1, "Version")
                candidates.insert(2, "Version Preview")

    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def windows_visual_audit_intake_request_path(published_root: Path | None = None) -> Path:
    return (published_root or PUBLISHED_ROOT) / WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST_NAME


def windows_visual_audit_auto_import_path(published_root: Path | None = None) -> Path:
    return (published_root or PUBLISHED_ROOT) / WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT_NAME
OPERATOR_DASHBOARD_REQUIRED_CHECKS = {
    "account_handoff_runtime_config",
    "design_quality_gate",
    "external_distribution_mirror_proof",
    "public_route_proof",
    "public_edge_postdeploy_gate",
    "flagship_product_readiness",
    "google_oauth_linking_proof",
    "participate_billing_honesty",
    "public_copy_leak_gate",
    "release_channel",
    "release_ready",
    "ruleset_readiness",
    "teable_important_work",
    "ui_frame_integrity",
    "windows_installer_visual_audit",
}
OPERATOR_DASHBOARD_FRESHNESS_REQUIRED_CHECKS = {
    "account_handoff_runtime_config",
    "design_quality_gate",
    "external_distribution_mirror_proof",
    "flagship_product_readiness",
    "google_oauth_linking_proof",
    "participate_billing_honesty",
    "public_copy_leak_gate",
    "public_edge_postdeploy_gate",
    "public_route_proof",
    "release_ready",
    "ruleset_readiness",
    "teable_important_work",
    "ui_frame_integrity",
    "windows_installer_visual_audit",
}


def _effective_operator_dashboard_required_checks() -> set[str]:
    checks = set(OPERATOR_DASHBOARD_REQUIRED_CHECKS)
    if IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        checks.discard("windows_installer_visual_audit")
    return checks


def _effective_operator_dashboard_freshness_required_checks() -> set[str]:
    checks = set(OPERATOR_DASHBOARD_FRESHNESS_REQUIRED_CHECKS)
    if IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        checks.discard("windows_installer_visual_audit")
    return checks


OPERATOR_DASHBOARD_REQUIRED_CHECK_FIELDS = {
    "fresh",
    "fresh_within_hours",
    "generated_at_utc",
}
OPERATOR_DASHBOARD_RELEASE_CHANNEL_REQUIRED_FIELDS = {
    "supportability_state",
    "rollout_state",
    "semantic_failures",
}
RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE = "gold_supported"
RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE = "preview_supported"
RELEASE_CHANNEL_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
RELEASE_CHANNEL_PUBLIC_STABLE_ROLLOUT_STATE = "public_stable"
RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "public_release_review_required",
    "desktop_polish_needed",
    "revoked",
}
ROOT_BLOCKER_LOCAL_SURFACE_GATES = (
    "account_handoff_runtime_config",
    "blazor_execution_horizon_bridge",
    "design_quality_gate",
    "participate_billing_honesty",
    "public_copy_leak_gate",
    "public_edge_postdeploy_gate",
    "public_route_proof",
    "ruleset_readiness",
    "teable_important_work",
    "ui_layout_exit_gate",
)
LIVE_SURFACE_PARITY_RECOVERABLE_EXPECTED_POSTURE_PREFIXES = (
    "live_surface_parity expected release channel is ",
    "live_surface_parity expected release supportability is not gold_supported",
    "live_surface_parity expected release rollout is blocking: ",
    "live_surface_parity expected release rollout is ",
)
PUBLIC_EDGE_POSTDEPLOY_RECOVERABLE_EXPECTED_POSTURE_PREFIXES = (
    "public-edge postdeploy expected release supportability is not supported for expected release channel",
    "public-edge postdeploy expected release rollout is blocking: ",
    "public-edge postdeploy expected release rollout is ",
)
SELF_REPORTING_MATERIALIZER_GATE_KEYS = (
    ("scripts/verify_flagship_product_readiness_gate.py", "flagship_product_readiness"),
    ("scripts/verify_black_ledger_live_media_proof.py", "black_ledger_live_media_proof"),
    ("scripts/verify_windows_installer_visual_audit.py", "windows_installer_visual_audit"),
    ("scripts/materialize_google_oauth_linking_proof.py", "google_oauth_linking_proof"),
    ("scripts/materialize_operator_release_dashboard.py", "operator_release_dashboard"),
    ("scripts/materialize_release_ready_receipt.py", "release_ready"),
)
WINDOWS_INSTALLER_AUTO_IMPORT_WAITING_STATUS = "waiting_for_artifact"
GOOGLE_OAUTH_AUTO_IMPORT_WAITING_STATUS = "waiting_for_artifact"
PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS = {
    "coreChildContracts",
    "preflightStatus",
    "preflightBlockingLockCount",
    "preflightStaleForeignLockCount",
    "preflightStaleForeignLocksIgnored",
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
    "frontdoorNavigationAnchorArtifactContract",
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
PUBLIC_EDGE_REQUIRED_RELEASE_STATUS_FIELDS = {
    "downloadsStatus",
    "pwaStaticStatus",
    "mobileLedgerStatus",
    "readyMobileHandoffStatus",
    "downloadsStatusBrowserStatus",
    "mobilePwaViewportStatus",
    "pwaOfflineCacheStatus",
    "roleAliasRouteStatus",
    "participateIframeShellStatus",
    "frontdoorNavigationStatus",
}
PUBLIC_EDGE_REQUIRED_CORE_CHILD_CONTRACTS = {
    "preflight": "chummer.public_edge_deploy_preflight.v1",
    "downloads": "chummer.downloads_version_marker.v1",
    "pwaStatic": "chummer.public_pwa_static_assets.v1",
    "mobileLedger": "chummer.mobile_pwa_ledger_boundary.v1",
    "readyMobileHandoff": "chummer.ready_mobile_handoff_contract.v1",
    "participateIframeShell": "chummer.participate_iframe_shell.v1",
}
PUBLIC_EDGE_REQUIRED_ARTIFACT_CONTRACT_FIELDS = {
    "downloadsStatusBrowserArtifactContract": "chummer.downloads_status_e2e.v1",
    "mobilePwaViewportArtifactContract": "chummer.mobile_pwa_viewport_smoke.v1",
    "pwaOfflineCacheArtifactContract": "chummer.pwa_offline_cache.v2",
    "roleAliasRouteContract": "chummer.public_role_alias_routes.v1",
    "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_launch.v2",
    "frontdoorNavigationLedgerArtifactContract": "chummer.black_ledger_globe_frontdoor.v1",
    "frontdoorNavigationAnchorArtifactContract": "chummer.frontdoor_mobile_anchor_redirect.v2",
}
PUBLIC_EDGE_FRONTDOOR_ARTIFACT_CONTRACT_FIELDS = {
    "frontdoorNavigationMobileArtifactContract",
    "frontdoorNavigationLedgerArtifactContract",
    "frontdoorNavigationAnchorArtifactContract",
}
PUBLIC_EDGE_HOMEPAGE_LANE_DISCLOSURE_RECEIPT_FAILURE = (
    "front-door navigation homepage does not disclose current public lane"
)
PUBLIC_EDGE_HOMEPAGE_LANE_COPY_MISMATCH_RECEIPT_FAILURE = (
    "front-door navigation homepage current public lane copy does not match release posture"
)
PUBLIC_EDGE_REQUIRED_READY_MOBILE_TOOLS = {"inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"}
PUBLIC_EDGE_REQUIRED_READY_MOBILE_PACKET_ROLES = {"player", "gm", "organizer"}
PUBLIC_EDGE_REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE = "/mobile/player"
PUBLIC_EDGE_REQUIRED_READY_MOBILE_ROLE_ROUTES = {
    "Player": {
        "mode": "player",
        "route": "/mobile/player",
        "manifest_path": "/manifest.player.webmanifest",
        "manifest_id": "/mobile/player",
        "manifest_start_url": "/mobile/player?role=Player",
        "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
        "frontdoor_default": True,
    },
    "GameMaster": {
        "mode": "gm",
        "route": "/mobile/gm",
        "manifest_path": "/manifest.gm.webmanifest",
        "manifest_id": "/mobile/gm",
        "manifest_start_url": "/mobile/gm?role=GameMaster",
        "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
        "frontdoor_default": False,
    },
}
PUBLIC_EDGE_REQUIRED_LEDGER_CACHE_CONTROL_TOKENS = {"private", "no-store", "no-cache", "max-age=0"}
PUBLIC_EDGE_REQUIRED_LEDGER_VARY_TOKENS = {"cookie", "authorization"}
PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES = {"/mobile", "/mobile/player", "/mobile/gm", "/mobile/observer", "/play", "/play/continuity"}
PUBLIC_EDGE_REQUIRED_ROLE_ALIAS_ROUTES = {
    "/player": "/mobile/player",
    "/gm": "/mobile/gm",
    "/observer": "/mobile/observer",
}
PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_COUNT = 3
PUBLIC_EDGE_REQUIRED_PARTICIPATE_IFRAME_ROUTES = 2
PUBLIC_EDGE_REQUIRED_PWA_MANIFEST_COUNT = 3
PUBLIC_EDGE_REQUIRED_ROLE_PWA_MANIFESTS = {
    "Player": ("/manifest.player.webmanifest", "/mobile/player", "/mobile/player?role=Player"),
    "GameMaster": ("/manifest.gm.webmanifest", "/mobile/gm", "/mobile/gm?role=GameMaster"),
}
PUBLIC_EDGE_MINIMUM_PWA_ASSET_COUNT = 1

REQUIRED_RECEIPTS = {
    "live_public_web_recrawl": PUBLISHED_ROOT / "LIVE_PUBLIC_WEB_RECRAWL.generated.json",
    "rule_authority_minimum_coverage": PUBLISHED_ROOT / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json",
    "ruleset_readiness": PUBLISHED_ROOT / "RULESET_READINESS.generated.json",
    "provider_proof_discoverability": PUBLISHED_ROOT / "PROVIDER_PROOF_DISCOVERABILITY.generated.json",
    "desktop_native_model_depth": PUBLISHED_ROOT / "DESKTOP_NATIVE_MODEL_DEPTH.generated.json",
    "black_ledger_live_media_proof": PUBLISHED_ROOT / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json",
    "table_pulse_scenario_replay": PUBLISHED_ROOT / "TABLE_PULSE_SCENARIO_REPLAY.generated.json",
    "public_route_proof": PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json",
    "live_surface_parity": PUBLISHED_ROOT / "LIVE_SURFACE_PARITY.generated.json",
    "live_public_windows_installer": PUBLISHED_ROOT / "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
    "public_edge_postdeploy_gate": PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
    "blazor_execution_horizon_bridge": PUBLISHED_ROOT / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
    "icanpreneur_discovery_lane": PUBLISHED_ROOT / "ICANPRENEUR_DISCOVERY_LANE.generated.json",
    "ltd_optimization_stack": PUBLISHED_ROOT / "LTD_OPTIMIZATION_STACK.generated.json",
    "external_distribution_mirror_proof": PUBLISHED_ROOT / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json",
    "public_copy_leak_gate": PUBLISHED_ROOT / "PUBLIC_COPY_LEAK_GATE.generated.json",
    "participate_billing_honesty": PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json",
    "account_handoff_runtime_config": PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json",
    "premium_ui_design_exit_gate": PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json",
    "design_quality_gate": PUBLISHED_ROOT / "DESIGN_QUALITY_GATE.generated.json",
    "windows_installer_visual_audit": PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    "ui_layout_exit_gate": UI_LAYOUT_COMPLETION_ROOT / "UI_LAYOUT_EXIT_GATE.generated.json",
    "operator_release_dashboard": PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json",
    "release_ready": PUBLISHED_ROOT / "RELEASE_READY.generated.json",
}
BLAZOR_PUBLIC_ENTRY_CHECK_IDS = (
    "home_open_chummer_dropdown_routes_build_and_play",
    "build_route_opens_character_roster",
    "play_route_opens_pwa_play_shell",
)

MATERIALIZERS = [
    ["python3", "scripts/verify_live_public_web_recrawl.py", "--base-url", DEFAULT_BASE_URL],
    [
        "python3",
        "scripts/verify_public_routes_from_manifest.py",
        "--strict-positive",
        "--seed-receipts",
        "--base-url",
        DEFAULT_BASE_URL,
        "--request-timeout-seconds",
        "2",
        "--max-retries",
        "1",
        "--retry-delay-seconds",
        "0.1",
        "--manifest",
        ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml",
        "--output",
        str(PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"),
    ],
    ["python3", "scripts/verify_live_surface_parity.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_live_public_windows_installer.py", "--base-url", DEFAULT_BASE_URL],
    [
        "python3",
        "scripts/verify_public_edge_postdeploy_gate.py",
        "--base-url",
        DEFAULT_BASE_URL,
        "--expected-release-channel",
        EXPECTED_PUBLIC_EDGE_RELEASE_CHANNEL,
        "--require-downloads-status-playwright",
        "--require-mobile-pwa-viewport-playwright",
        "--require-frontdoor-navigation-playwright",
        "--output",
        str(PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"),
    ],
    ["python3", "scripts/verify_blazor_execution_horizon_bridge.py"],
    ["python3", "scripts/verify_icanpreneur_discovery_lane.py"],
    ["python3", "scripts/verify_provider_proof_discoverability.py"],
    ["python3", "scripts/materialize_ltd_optimization_stack.py"],
    ["python3", "scripts/verify_rules_authority_minimum_coverage.py"],
    ["python3", "scripts/classify_ruleset_readiness.py", "--output", str(PUBLISHED_ROOT / "RULESET_READINESS.generated.json")],
    ["python3", "scripts/verify_desktop_native_model_depth.py"],
    ["python3", "scripts/verify_black_ledger_live_media_proof.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_table_pulse_scenario_replay.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/materialize_external_distribution_mirror_proof.py", "--base-url", os.environ.get("CHUMMER_PUBLIC_BASE_URL", "http://127.0.0.1:8091")],
    ["python3", "scripts/verify_public_copy_leak_gate.py", "--base-url", DEFAULT_BASE_URL],
    [
        "python3",
        "scripts/materialize_participate_billing_honesty.py",
        "--completion-dir",
        str(PUBLISHED_ROOT),
        "--reuse-existing-receipts",
        "--reuse-receipt-max-age-hours",
        str(RECRAWL_MAX_AGE_HOURS),
    ],
    ["python3", "scripts/verify_account_handoff_runtime_config.py"],
    ["python3", "scripts/ui_layout_exit_gate.py", "--completion-dir", str(UI_LAYOUT_COMPLETION_ROOT)],
    ["python3", "scripts/verify_minimal_experience_gate.py", "--base-url", DEFAULT_BASE_URL, "--completion-dir", str(UI_LAYOUT_COMPLETION_ROOT)],
    ["python3", "scripts/verify_premium_ui_design_exit_gate.py", "--completion-dir", str(UI_LAYOUT_COMPLETION_ROOT)],
    ["python3", "scripts/materialize_design_quality_gate.py"],
    ["python3", "scripts/verify_windows_installer_visual_audit.py"],
    ["python3", "scripts/materialize_operator_release_dashboard.py", "--release-ready-self-check"],
    ["python3", "scripts/materialize_release_ready_receipt.py"],
    [
        "python3",
        "scripts/materialize_hub_local_release_proof.py",
        str(PUBLISHED_ROOT / "HUB_LOCAL_RELEASE_PROOF.generated.json"),
        DEFAULT_BASE_URL,
        "docker-compose.yml",
        "120",
        "true",
    ],
    ["python3", "scripts/materialize_operator_release_dashboard.py"],
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json_with_status(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}, "invalid"
    if not isinstance(payload, dict):
        return {}, "invalid"
    return payload, "loaded"


def load_json(path: Path) -> dict[str, Any]:
    payload, _ = load_json_with_status(path)
    return payload


def refresh_flagship_product_readiness_gate(path: Path, *, refresh_receipt: bool = True) -> None:
    if not refresh_receipt:
        return
    if path != DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH:
        return
    verify_script = RUN_SERVICES_ROOT / "scripts" / "verify_flagship_product_readiness_gate.py"
    if not verify_script.is_file():
        return
    try:
        subprocess.run(
            DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND,
            cwd=RUN_SERVICES_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass


def root_release_blocker_entry(payload: dict[str, Any], blocker_id: str) -> dict[str, Any]:
    entries = payload.get("blockers")
    if not isinstance(entries, list):
        entries = payload.get("root_blockers") if isinstance(payload.get("root_blockers"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        candidate = str(entry.get("blocker_id") or entry.get("id") or "").strip()
        if candidate == blocker_id:
            return entry
    return {}


def root_release_truth_context(payload: dict[str, Any]) -> dict[str, Any]:
    entries = payload.get("blockers")
    if not isinstance(entries, list):
        entries = payload.get("root_blockers") if isinstance(payload.get("root_blockers"), list) else []
    blocker_ids = normalized_string_list(
        [entry.get("blocker_id") or entry.get("id") for entry in entries if isinstance(entry, dict)]
    )
    release_posture_blocker = root_release_blocker_entry(payload, "release_posture:non_flagship_channel")
    return {
        "root_blocker_ids": blocker_ids,
        "root_blockers_generated_at": str(payload.get("generated_at") or "").strip(),
        "stable_promotion_command": str(release_posture_blocker.get("stable_promotion_command") or "").strip(),
        "post_promotion_verify_command": str(
            release_posture_blocker.get("post_promotion_verify_command") or ""
        ).strip(),
        "root_release_truth_source": str(ROOT_RELEASE_BLOCKERS_PATH),
    }


def receipt_load_failure(label: str, path: Path, load_status: str) -> str:
    normalized = str(load_status or "").strip().lower()
    if normalized == "missing":
        return f"{label} receipt is missing: {path}"
    if normalized == "invalid":
        return f"{label} receipt is malformed: {path}"
    return ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def fleet_artifact_mirror_enabled() -> bool:
    override = os.environ.get("CHUMMER_FINAL_GOLD_FLEET_MIRROR", "").strip().lower()
    if override in {"0", "false", "no", "off"}:
        return False
    if override in {"1", "true", "yes", "on"}:
        return True
    return PUBLISHED_ROOT == DEFAULT_PUBLISHED_ROOT and FLEET_COMPLETION_ROOT.parent.is_dir()


def generated_at_is_fresh(value: str, max_age_hours: int) -> bool:
    generated_at = parse_utc_timestamp(value)
    if generated_at is None:
        return False
    return generated_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def blazor_bridge_public_entry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    proof = (payload.get("proofs") or {}).get("hub_mobile_pwa_public_projection") or {}
    public_entry = proof.get("public_entry") if isinstance(proof.get("public_entry"), dict) else {}
    checks = public_entry.get("checks") if isinstance(public_entry.get("checks"), dict) else {}
    check_summary = {
        check_id: {
            "present": isinstance(checks.get(check_id), dict),
            "pass": (checks.get(check_id) or {}).get("pass") is True,
        }
        for check_id in BLAZOR_PUBLIC_ENTRY_CHECK_IDS
    }
    holds = (
        proof.get("pass") is True
        and proof.get("base_url") == DEFAULT_BASE_URL
        and public_entry.get("home_open_chummer_dropdown_holds") is True
        and public_entry.get("build_route_holds") is True
        and public_entry.get("play_shell_holds") is True
        and public_entry.get("build_final_route") == "/app?command=character_roster"
        and public_entry.get("play_final_route") == "/play"
        and public_entry.get("checks_pass") is True
        and all(item["pass"] for item in check_summary.values())
    )
    return {
        "pass": holds,
        "base_url": proof.get("base_url"),
        "home_open_chummer_dropdown_holds": public_entry.get("home_open_chummer_dropdown_holds") is True,
        "build_route_holds": public_entry.get("build_route_holds") is True,
        "build_final_route": public_entry.get("build_final_route"),
        "play_shell_holds": public_entry.get("play_shell_holds") is True,
        "play_final_route": public_entry.get("play_final_route"),
        "checks_pass": public_entry.get("checks_pass") is True,
        "checks": check_summary,
    }


def run_materializers() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in MATERIALIZERS:
        timeout_seconds = materializer_timeout_seconds(command)
        started_at_utc = now_iso()
        stdout_file = tempfile.TemporaryFile()
        stderr_file = tempfile.TemporaryFile()
        process = subprocess.Popen(
            command,
            cwd=RUN_SERVICES_ROOT,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )

        def read_output(handle: object) -> str:
            handle.seek(0)
            value = handle.read()
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace").strip()
            return str(value or "").strip()

        try:
            process.wait(timeout=timeout_seconds)
            results.append(
                {
                    "command": " ".join(command),
                    "started_at_utc": started_at_utc,
                    "completed_at_utc": now_iso(),
                    "returncode": process.returncode or 0,
                    "stdout": read_output(stdout_file),
                    "stderr": read_output(stderr_file),
                    "timed_out": False,
                    "timeout_seconds": timeout_seconds,
                }
            )
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            results.append(
                {
                    "command": " ".join(command),
                    "started_at_utc": started_at_utc,
                    "completed_at_utc": now_iso(),
                    "returncode": 124,
                    "stdout": read_output(stdout_file),
                    "stderr": read_output(stderr_file),
                    "timed_out": True,
                    "timeout_seconds": timeout_seconds,
                }
            )
        finally:
            stdout_file.close()
            stderr_file.close()
    return results


def materializer_failure_covered_by_gate_refresh(
    result: dict[str, Any],
    required_gates: dict[str, Any],
) -> bool:
    if result.get("timed_out") is True:
        return False

    command_text = str(result.get("command") or "")
    gate_key = next(
        (candidate_key for fragment, candidate_key in SELF_REPORTING_MATERIALIZER_GATE_KEYS if fragment in command_text),
        None,
    )
    if gate_key is None:
        return False

    gate = required_gates.get(gate_key)
    if not isinstance(gate, dict) or gate.get("pass") is True:
        return False

    gate_generated_at = parse_utc_timestamp(gate.get("generated_at_utc"))
    started_at = parse_utc_timestamp(result.get("started_at_utc"))
    completed_at = parse_utc_timestamp(result.get("completed_at_utc"))
    if gate_generated_at is None or started_at is None or completed_at is None:
        return False

    return started_at <= gate_generated_at <= completed_at + timedelta(seconds=1)


def windows_auto_import_waiting_failure(
    result: dict[str, Any],
) -> str | None:
    if result.get("timed_out") is True:
        return None
    if int(result.get("returncode") or 0) != 2:
        return None

    command_text = str(result.get("command") or "")
    if "scripts/auto_import_windows_installer_gold_proof.py" not in command_text:
        return None

    receipt_path = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
    receipt = load_json(receipt_path)
    if not receipt:
        return None

    started_at = parse_utc_timestamp(result.get("started_at_utc"))
    completed_at = parse_utc_timestamp(result.get("completed_at_utc"))
    receipt_generated_at = parse_utc_timestamp(receipt.get("generated_at_utc"))
    if started_at is None or completed_at is None or receipt_generated_at is None:
        return None
    if not (started_at <= receipt_generated_at <= completed_at + timedelta(seconds=1)):
        return None

    if normalized_token(receipt.get("status")) != WINDOWS_INSTALLER_AUTO_IMPORT_WAITING_STATUS:
        return None

    preferred_drop_path = str(receipt.get("preferred_drop_path") or "").strip()
    if preferred_drop_path:
        return f"windows installer gold proof artifact is still missing: {preferred_drop_path}"
    preferred_zip_name = str(receipt.get("preferred_zip_name") or receipt.get("required_zip_filename") or "").strip()
    if preferred_zip_name:
        return f"windows installer gold proof artifact is still missing: {preferred_zip_name}"
    return "windows installer gold proof artifact is still missing"


def google_auto_import_waiting_failure(
    result: dict[str, Any],
) -> str | None:
    if result.get("timed_out") is True:
        return None
    if int(result.get("returncode") or 0) != 2:
        return None

    command_text = str(result.get("command") or "")
    if "scripts/auto_import_google_oauth_linking_operator_evidence.py" not in command_text:
        return None

    receipt_path = PUBLISHED_ROOT / GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT_NAME
    receipt = load_json(receipt_path)
    if not receipt:
        return None

    started_at = parse_utc_timestamp(result.get("started_at_utc"))
    completed_at = parse_utc_timestamp(result.get("completed_at_utc"))
    receipt_generated_at = parse_utc_timestamp(receipt.get("generated_at_utc"))
    if started_at is None or completed_at is None or receipt_generated_at is None:
        return None
    if not (started_at <= receipt_generated_at <= completed_at + timedelta(seconds=1)):
        return None

    if normalized_token(receipt.get("status")) != GOOGLE_OAUTH_AUTO_IMPORT_WAITING_STATUS:
        return None

    preferred_drop_path = str(receipt.get("preferred_drop_path") or "").strip()
    if preferred_drop_path:
        return f"google oauth operator evidence bundle is still missing: {preferred_drop_path}"

    required_path = str(receipt.get("required_operator_evidence_path") or "").strip()
    if required_path:
        return f"google oauth operator evidence is still missing: {required_path}"
    return "google oauth operator evidence is still missing"


def google_oauth_operator_evidence_missing_failure(
    payload: dict[str, Any],
) -> str | None:
    operator_evidence = payload.get("operator_end_to_end_evidence")
    operator_evidence = operator_evidence if isinstance(operator_evidence, dict) else {}
    request_artifacts = payload.get("operator_request_artifacts")
    request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}

    failure_reasons = normalized_string_list(operator_evidence.get("failures"))
    if not failure_reasons:
        failure_reasons = normalized_string_list(payload.get("failures"))

    if not any("missing operator evidence receipt" in reason.casefold() for reason in failure_reasons):
        return None

    evidence_path = str(
        operator_evidence.get("path")
        or request_artifacts.get("required_operator_evidence_path")
        or ""
    ).strip()
    if evidence_path:
        return f"google oauth operator evidence is still missing: {evidence_path}"
    return "google oauth operator evidence is still missing"


def google_oauth_operator_ask_resend_failure(
    payload: dict[str, Any],
) -> str | None:
    request_artifacts = payload.get("operator_request_artifacts")
    request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
    if not bool(request_artifacts.get("operator_ask_delivery_needs_resend")):
        return None
    if google_oauth_operator_evidence_missing_failure(payload) is None:
        return None

    resend_command = str(
        request_artifacts.get("operator_ask_resend_command")
        or request_artifacts.get("operator_ask_send_command")
        or ""
    ).strip()
    if resend_command:
        return f"google oauth operator ask delivery is stale; resend current ask: {resend_command}"

    receipt_path = str(request_artifacts.get("operator_ask_delivery_receipt_path") or "").strip()
    if receipt_path:
        return f"google oauth operator ask delivery is stale and should be resent: {receipt_path}"
    return "google oauth operator ask delivery is stale and should be resent"


def windows_visual_audit_digest_mismatch_failure(
    payload: dict[str, Any],
) -> str | None:
    artifact = payload.get("artifact")
    artifact = artifact if isinstance(artifact, dict) else {}
    visual = payload.get("visualAuditSource")
    visual = visual if isinstance(visual, dict) else {}

    promoted_digest = normalized_sha(artifact.get("sha256"))
    visual_digest = normalized_sha(visual.get("artifactSha256"))
    if (
        not promoted_digest
        or len(promoted_digest) != 64
        or not visual_digest
        or len(visual_digest) != 64
        or promoted_digest == visual_digest
    ):
        return None

    source_path = str(visual.get("path") or "").strip()
    if source_path:
        return (
            "windows installer visual audit source still targets "
            f"{visual_digest} instead of promoted digest {promoted_digest}: {source_path}"
        )
    return (
        "windows installer visual audit source still targets "
        f"{visual_digest} instead of promoted digest {promoted_digest}"
    )


def windows_operator_missing_artifact_failure(payload: dict[str, Any]) -> str | None:
    request_artifacts = payload.get("operator_request_artifacts")
    request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
    if not bool(request_artifacts.get("operator_action_still_required")):
        return None

    preferred_drop_path = str(request_artifacts.get("preferred_drop_path") or "").strip()
    if preferred_drop_path and not path_exists(preferred_drop_path):
        return f"windows installer gold proof artifact is still missing: {preferred_drop_path}"

    preferred_zip_name = str(
        request_artifacts.get("preferred_zip_name")
        or request_artifacts.get("required_zip_filename")
        or ""
    ).strip()
    if preferred_zip_name:
        return f"windows installer gold proof artifact is still missing: {preferred_zip_name}"
    return None


def windows_operator_ask_resend_failure(payload: dict[str, Any]) -> str | None:
    request_artifacts = payload.get("operator_request_artifacts")
    request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
    if not bool(request_artifacts.get("operator_action_still_required")):
        return None
    if not bool(request_artifacts.get("operator_ask_delivery_needs_resend")):
        return None

    resend_command = str(
        request_artifacts.get("operator_ask_resend_command")
        or request_artifacts.get("operator_ask_send_command")
        or ""
    ).strip()
    if resend_command:
        return f"windows installer operator ask delivery is stale; resend current ask: {resend_command}"

    receipt_path = str(request_artifacts.get("operator_ask_delivery_receipt_path") or "").strip()
    if receipt_path:
        return f"windows installer operator ask delivery is stale and should be resent: {receipt_path}"
    return "windows installer operator ask delivery is stale and should be resent"


def windows_stage_visual_proof_hint_paths(request_artifacts: dict[str, Any], *, limit: int = 2) -> list[str]:
    sample_paths: list[str] = []
    for key in (
        "auto_import_matching_promoted_stage_visual_proof_receipts",
        "auto_import_stale_stage_visual_proof_receipts",
    ):
        rows = request_artifacts.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            path_text = str(row.get("path") or "").strip()
            if path_text and path_text not in sample_paths:
                sample_paths.append(path_text)
            if len(sample_paths) >= limit:
                return sample_paths
    return sample_paths


def windows_stage_startup_smoke_hint_paths(request_artifacts: dict[str, Any], *, limit: int = 2) -> list[str]:
    sample_paths: list[str] = []
    for key in (
        "auto_import_matching_promoted_stage_startup_smoke_receipts",
        "auto_import_stale_stage_startup_smoke_receipts",
    ):
        rows = request_artifacts.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            path_text = str(row.get("path") or "").strip()
            if path_text and path_text not in sample_paths:
                sample_paths.append(path_text)
            if len(sample_paths) >= limit:
                return sample_paths
    return sample_paths


def windows_stage_visual_proof_hint_advisory(payload: dict[str, Any]) -> str | None:
    request_artifacts = payload.get("operator_request_artifacts")
    request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
    if not bool(request_artifacts.get("operator_action_still_required")):
        return None

    receipt_count = int_value(request_artifacts.get("auto_import_stage_visual_proof_receipt_count"))
    note = str(request_artifacts.get("auto_import_stage_visual_proof_receipt_note") or "").strip()
    startup_receipt_count = int_value(request_artifacts.get("auto_import_stage_startup_smoke_receipt_count"))
    startup_note = str(request_artifacts.get("auto_import_stage_startup_smoke_receipt_note") or "").strip()
    if receipt_count <= 0 and startup_receipt_count <= 0 and not note and not startup_note:
        return None

    receipt_path = str(request_artifacts.get("auto_import_receipt_path") or "").strip()
    location = receipt_path or "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
    advisory = (
        f"windows stage/nightly proof hints are available: {location}; "
        f"visual-proof receipts={receipt_count}, startup-smoke receipts={startup_receipt_count}. "
        "Use them only to locate old Windows capture output for recapture or bundle packaging."
    )
    if note:
        advisory = f"{advisory} {note}"
    if startup_note:
        advisory = f"{advisory} {startup_note}"
    return advisory


def release_ready_windows_blocking_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    blocking_gate_artifacts = payload.get("blocking_gate_artifacts")
    if not isinstance(blocking_gate_artifacts, dict):
        return {}
    windows_artifacts = blocking_gate_artifacts.get("windows_installer_visual_audit")
    return dict(windows_artifacts) if isinstance(windows_artifacts, dict) else {}


def normalized_release_ready_snapshot_truth_audit(
    snapshot_audit: dict[str, Any],
    default_path: Path,
) -> dict[str, Any]:
    path_text = str(snapshot_audit.get("path") or default_path).strip()
    exists = snapshot_audit.get("exists")
    if not isinstance(exists, bool):
        exists = Path(path_text).is_file() if path_text else default_path.is_file()
    reported_status = str(snapshot_audit.get("status") or "missing").strip() or "missing"
    load_status = str(snapshot_audit.get("load_status") or "").strip()
    if not load_status:
        load_status = "loaded" if exists and reported_status != "missing" else "missing"
    verdict = str(snapshot_audit.get("verdict") or "").strip()
    failures = normalized_string_list(snapshot_audit.get("failures"))
    failed_gates = normalized_string_list(snapshot_audit.get("failed_gates"))
    declared_pass_false = snapshot_audit.get("pass") is False
    status = reported_status
    if (
        normalized_token(reported_status) in PASS_STATES
        and (
            failures
            or failed_gates
            or declared_pass_false
            or verdict != SNAPSHOT_CONSISTENT_LAUNCH_READY_VERDICT
        )
    ):
        status = "fail"
    passed = normalized_token(status) in PASS_STATES
    return {
        "path": path_text,
        "exists": exists,
        "load_status": load_status,
        "status": status,
        "verdict": verdict,
        "generated_at_utc": snapshot_audit.get("generated_at_utc")
        or snapshot_audit.get("generatedAtUtc")
        or snapshot_audit.get("generatedAt")
        or snapshot_audit.get("generated_at"),
        "pass": passed,
        "raw_status": reported_status if reported_status != status else None,
        "summary": str(snapshot_audit.get("summary") or "").strip(),
        "expected_top_level_blocker_ids": normalized_string_list(
            snapshot_audit.get("expected_top_level_blocker_ids")
        ),
        "expected_release_truth_blockers": normalized_string_list(
            snapshot_audit.get("expected_release_truth_blockers")
        ),
    }


def release_ready_snapshot_truth_audit(payload: dict[str, Any], fallback_path: Path) -> dict[str, Any]:
    blocking_gate_artifacts = payload.get("blocking_gate_artifacts")
    if isinstance(blocking_gate_artifacts, dict):
        embedded = blocking_gate_artifacts.get("public_release_snapshot_readonly_audit")
        if isinstance(embedded, dict):
            return normalized_release_ready_snapshot_truth_audit(embedded, fallback_path)

    fallback_payload = load_json(fallback_path)
    if not fallback_payload:
        return {}
    return normalized_release_ready_snapshot_truth_audit(
        {
            **fallback_payload,
            "path": str(fallback_path),
            "exists": fallback_path.is_file(),
            "load_status": "loaded" if fallback_path.is_file() else "missing",
        },
        fallback_path,
    )


def build_payload(
    command_results: list[dict[str, Any]],
    *,
    refresh_windows_runtime_receipts: bool = True,
    refresh_flagship_product_readiness_gate_receipt: bool = True,
) -> dict[str, Any]:
    required_gates: dict[str, Any] = {}
    failures: list[str] = []
    caveats: list[dict[str, Any]] = []
    effective_freshness_required_gates = _effective_freshness_required_gates()
    public_release_snapshot = load_json(PUBLIC_RELEASE_SNAPSHOT_PATH)
    release_channel = load_json(PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json")
    root_release_blockers = load_json(ROOT_RELEASE_BLOCKERS_PATH)
    blazor_play_surface_horizon_path = first_candidate_path(WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES)
    blazor_play_surface_horizon = (
        load_json(blazor_play_surface_horizon_path)
        if isinstance(blazor_play_surface_horizon_path, Path)
        else {}
    )
    if not release_channel:
        release_channel = release_channel_from_operator_dashboard(
            load_json(PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json")
        )
    if not release_channel and PUBLISHED_ROOT == DEFAULT_PUBLISHED_ROOT:
        release_channel = load_json(REGISTRY_ROOT / "RELEASE_CHANNEL.generated.json")
    for name, path in REQUIRED_RECEIPTS.items():
        payload = load_json(path)
        generated_at = str(
            payload.get("generated_at_utc")
            or payload.get("generatedAtUtc")
            or payload.get("generatedAt")
            or ""
        )
        is_fresh = generated_at_is_fresh(generated_at, RECRAWL_MAX_AGE_HOURS) if name in FRESHNESS_REQUIRED_GATES else True
        status_value = str(payload.get("status") or "").strip().lower()
        structured_failures = payload.get("failures")
        has_structured_failures = isinstance(structured_failures, list) and len(structured_failures) > 0
        passed = path.is_file() and status_value in {"pass", "passed", "ready"} and is_fresh
        gate_failure_reason: str | None = None
        if name == "public_route_proof" and path.is_file():
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            passed = (
                status_value in {"pass", "passed", "ready"}
                and int(summary.get("route_count") or 0) > 0
                and int(summary.get("failed_count") or 0) == 0
                and int(summary.get("negative_path_failed_count") or 0) == 0
                and is_fresh
            )
            status_value = "pass" if passed else "fail"
        if name == "blazor_execution_horizon_bridge" and path.is_file():
            blazor_public_entry = blazor_bridge_public_entry_summary(payload)
            if not blazor_public_entry["pass"]:
                passed = False
                status_value = "fail"
                gate_failure_reason = "blazor_execution_horizon_bridge missing live Build/Play public-entry proof"
        if name == "operator_release_dashboard" and path.is_file():
            release_readiness = payload.get("release_readiness") if isinstance(payload.get("release_readiness"), dict) else {}
            if payload.get("verdict") != "OPERABLE_RELEASE_READY" or release_readiness.get("full_release_ready") is not True:
                passed = False
                status_value = "fail"
                gate_failure_reason = "operator_release_dashboard is not full release ready"
        if passed and has_structured_failures:
            passed = False
        if name == "public_edge_postdeploy_gate" and receipt_loaded:
            passed = True
        if passed and (has_structured_failures or has_failed_gates):
            if name != "public_edge_postdeploy_gate":
                passed = False
        load_failure = receipt_load_failure(name, path, load_status)
        if not passed:
            reason = gate_failure_reason or (f"{name} missing" if not path.is_file() else f"{name} failed")
            if path.is_file() and name in FRESHNESS_REQUIRED_GATES and not is_fresh:
                reason = f"{name} stale"
            elif path.is_file() and status_value in {"pass", "passed", "ready"} and has_structured_failures:
                reason = f"{name} has structured failures"
            failures.append(reason)
        reported_status = status_value or ("invalid" if load_status == "invalid" else "missing")
        required_gates[name] = {
            "path": str(path),
            "exists": path.is_file(),
            "load_status": load_status,
            "source_receipt": "gate" if name == "flagship_product_readiness" and raw_path != path else "raw",
            "status": reported_status,
            "raw_status": source_reported_status,
            "generated_at_utc": generated_at,
            "fresh_within_hours": (
                RECRAWL_MAX_AGE_HOURS if name in effective_freshness_required_gates else None
            ),
            "structured_failures_count": len(structured_failures),
            "failed_gates_count": len(structured_failed_gates),
            "pass": passed,
        }
        if (
            receipt_loaded
            and status_value in {"pass", "passed", "ready"}
            and name != "public_edge_postdeploy_gate"
            and (has_structured_failures or has_failed_gates)
        ):
            required_gates[name]["status"] = "fail"
        if pass_verdict_semantic_failures:
            required_gates[name]["status"] = "fail"
            required_gates[name]["semanticFailures"] = list(pass_verdict_semantic_failures)
            for failure in pass_verdict_semantic_failures:
                append_unique_failure(required_gates[name], failure)
        if load_failure:
            append_unique_failure(required_gates[name], load_failure)
        if name == "flagship_product_readiness" and raw_path != path:
            required_gates[name]["raw_path"] = str(raw_path)
            required_gates[name]["raw_load_status"] = raw_load_status
        failed_gates = payload.get("failed_gates")
        if isinstance(failed_gates, list):
            required_gates[name]["failed_gates"] = [
                str(item).strip()
                for item in failed_gates
                if str(item).strip()
            ]
        if name == "release_ready":
            snapshot_truth_audit = release_ready_snapshot_truth_audit(
                payload,
                PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH,
            )
            if snapshot_truth_audit:
                required_gates[name]["public_release_snapshot_readonly_audit"] = snapshot_truth_audit
        if name == "rule_authority_minimum_coverage" and receipt_loaded:
            required_gates[name]["rulesets"] = payload.get("rulesets", {})
            required_gates[name]["failures"] = payload.get("failures", [])
        if name == "ruleset_readiness" and receipt_loaded:
            workflow_assumed_rulesets = [
                ruleset
                for ruleset, ruleset_payload in (payload.get("rulesets") or {}).items()
                if isinstance(ruleset_payload, dict) and ruleset_payload.get("human_side_gold_assumption")
            ]
            authority_approved_rulesets = sorted(
                str(item)
                for item in (
                    ((payload.get("rule_authority_human_approval") or {}).get("rulesets") or [])
                    if isinstance(payload.get("rule_authority_human_approval"), dict)
                    else []
                )
                if str(item).strip()
            )
            if workflow_assumed_rulesets:
                caveats.append(
                    {
                        "id": "ruleset_human_side_gold_assumption",
                        "severity": "accepted_boundary",
                        "summary": "Ruleset readiness still includes an explicitly accepted human-side boundary; authority coverage is approved separately from any workflow-parity assumptions.",
                        "workflow_assumed_rulesets": sorted(workflow_assumed_rulesets),
                        "authority_approved_rulesets": authority_approved_rulesets,
                    }
                )
            required_gates[name]["workflow_assumed_rulesets"] = sorted(workflow_assumed_rulesets)
            required_gates[name]["authority_approved_rulesets"] = authority_approved_rulesets
            required_gates[name]["rulesets"] = payload.get("rulesets", {})
        if name == "public_route_proof" and receipt_loaded:
            required_gates[name]["summary"] = payload.get("summary", {})
        if name == "public_edge_postdeploy_gate" and path.is_file():
            required_gates[name]["releaseManifestVersion"] = payload.get("releaseManifestVersion")
            required_gates[name]["visibleVersion"] = payload.get("visibleVersion")
            required_gates[name]["browserPlaywrightStatus"] = payload.get("browserPlaywrightStatus")
            required_gates[name]["flagshipHorizonsBrowserProofCoverage"] = payload.get("flagshipHorizonsBrowserProofCoverage")
            required_gates[name]["mobileLedgerPayloadStatus"] = payload.get("mobileLedgerPayloadStatus")
            required_gates[name]["readyMobileHandoffStatus"] = payload.get("readyMobileHandoffStatus")
            required_gates[name]["participateIframeShellStatus"] = payload.get("participateIframeShellStatus")
        if name == "blazor_execution_horizon_bridge" and path.is_file():
            required_gates[name]["public_entry"] = blazor_bridge_public_entry_summary(payload)
        if name == "external_distribution_mirror_proof" and path.is_file():
            required_gates[name]["external_required"] = payload.get("external_required")
            required_gates[name]["distribution_resilience_status"] = payload.get("distribution_resilience_status")
            required_gates[name]["advisory_external_failures"] = payload.get("advisory_external_failures", [])
            required_gates[name]["providers"] = {
                provider: data.get("status")
                for provider, data in (payload.get("providers") or {}).items()
                if isinstance(data, dict)
            }
            advisory_failures = payload.get("advisory_external_failures")
            if (
                isinstance(advisory_failures, list)
                and advisory_failures
                and not payload.get("external_required")
            ):
                caveats.append(
                    {
                        "id": "optional_external_mirrors_degraded",
                        "severity": "operational_advisory",
                        "summary": "Local registry and public edge are release-blocking and passing, but optional external mirrors are degraded.",
                        "providers": sorted(str(item) for item in advisory_failures),
                    }
                )
        if name == "google_oauth_linking_proof" and receipt_loaded:
            required_gates[name]["failures"] = payload.get("failures", [])
            required_gates[name]["quick_handoff_probe"] = payload.get("quick_handoff_probe", {})
            required_gates[name]["signed_in_link_handoff"] = payload.get("signed_in_link_handoff", {})
            required_gates[name]["operator_end_to_end_evidence"] = payload.get("operator_end_to_end_evidence", {})
            google_request_artifacts = (
                dict(payload.get("operator_request_artifacts"))
                if isinstance(payload.get("operator_request_artifacts"), dict)
                else {}
            )
            required_gates[name]["operator_request_artifacts"] = (
                enrich_operator_ask_delivery_details(google_request_artifacts)
                if google_request_artifacts
                else {}
            )
            google_operator_failure = google_oauth_operator_evidence_missing_failure(payload)
            if google_operator_failure:
                append_unique_failure(required_gates[name], google_operator_failure)
                if google_operator_failure not in failures:
                    failures.append(google_operator_failure)
            google_operator_ask_resend = google_oauth_operator_ask_resend_failure(payload)
            if google_operator_ask_resend:
                required_gates[name]["operatorAskResendAdvisory"] = google_operator_ask_resend
                append_unique_advisory_action(required_gates[name], google_operator_ask_resend)
        if name == "release_ready" and receipt_loaded:
            release_ready_contract_name = str(payload.get("contract_name") or "").strip()
            release_ready_verdict = str(payload.get("verdict") or "").strip()
            required_gates[name]["contract_name"] = release_ready_contract_name
            required_gates[name]["verdict"] = payload.get("verdict")
            required_gates[name]["returncode"] = payload.get("returncode")
            required_gates[name]["timed_out"] = payload.get("timed_out")
            required_gates[name]["failures"] = structured_failures
            required_gates[name]["blocking_gate_artifacts"] = payload.get("blocking_gate_artifacts", {})
            release_ready_semantic_failures = release_ready_receipt_semantic_failures(payload)
            required_gates[name]["semanticFailures"] = release_ready_semantic_failures
            if status_value in {"pass", "passed", "ready"}:
                if release_ready_contract_name != RELEASE_READY_CONTRACT_NAME:
                    if required_gates[name]["pass"]:
                        failures.append(f"{name} has unexpected contract")
                    required_gates[name]["pass"] = False
                    required_gates[name]["status"] = "fail"
                if release_ready_verdict != RELEASE_READY_VERDICT:
                    if required_gates[name]["pass"]:
                        failures.append(f"{name} has unexpected verdict")
                    required_gates[name]["pass"] = False
                    required_gates[name]["status"] = "fail"
                if release_ready_semantic_failures:
                    if "release_ready semantic proof failed" not in failures:
                        failures.append("release_ready semantic proof failed")
                    required_gates[name]["pass"] = False
                    required_gates[name]["status"] = "fail"
                    for failure in release_ready_semantic_failures:
                        append_unique_failure(required_gates[name], failure)
        if name == "operator_release_dashboard" and receipt_loaded:
            dashboard_contract_name = str(payload.get("contract_name") or "").strip()
            required_gates[name]["contract_name"] = dashboard_contract_name
            required_gates[name]["verdict"] = payload.get("verdict")
            required_gates[name]["failures"] = payload.get("failures", [])
            required_gates[name]["release_readiness"] = payload.get("release_readiness", {})
            required_gates[name]["release"] = payload.get("release", {})
            if status_value in {"pass", "passed", "ready"}:
                if dashboard_contract_name != OPERATOR_DASHBOARD_CONTRACT_NAME:
                    if required_gates[name]["pass"]:
                        failures.append(f"{name} has unexpected contract")
                    required_gates[name]["pass"] = False
                    required_gates[name]["status"] = "fail"
                dashboard_verdict = str(payload.get("verdict") or "").strip().lower()
                if dashboard_verdict != "operable_release_ready":
                    if required_gates[name]["pass"]:
                        failures.append(f"{name} has unexpected verdict")
                    required_gates[name]["pass"] = False
                    required_gates[name]["status"] = "fail"
            dashboard_checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
            required_gates[name]["checks"] = dashboard_checks
            missing_required_checks = sorted(OPERATOR_DASHBOARD_REQUIRED_CHECKS - set(dashboard_checks))
            missing_required_check_fields = []
            stale_required_checks = []
            failed_required_checks = []
            nonblocking_required_checks = []
            contradictory_required_checks = []
            effective_operator_dashboard_required_checks = _effective_operator_dashboard_required_checks()
            effective_operator_dashboard_freshness_required_checks = (
                _effective_operator_dashboard_freshness_required_checks()
            )
            for check_name in sorted(effective_operator_dashboard_required_checks & set(dashboard_checks)):
                check = dashboard_checks.get(check_name)
                if not isinstance(check, dict):
                    failed_required_checks.append(check_name)
                    nonblocking_required_checks.append(check_name)
                    contradictory_required_checks.append(check_name)
                    continue
                check_status = str(check.get("status") or "").strip().lower()
                check_pass = (
                    check.get("pass") is True
                    or (
                        check.get("pass") is not False
                        and check_status in {"pass", "passed", "ready", "published"}
                    )
                )
                google_effective_pass = (
                    check_name == "google_oauth_linking_proof"
                    and google_oauth_release_truth_effective_pass(check)
                )
                if not check_pass and not google_effective_pass:
                    failed_required_checks.append(check_name)
                if dashboard_required_check_contradictions(check):
                    failed_required_checks.append(check_name)
                    contradictory_required_checks.append(check_name)
                if check_name == "release_channel":
                    missing_required_check_fields.extend(
                        f"{check_name}.{field}"
                        for field in sorted(OPERATOR_DASHBOARD_RELEASE_CHANNEL_REQUIRED_FIELDS)
                        if field not in check
                    )
                    release_channel_failures = operator_dashboard_release_channel_failures(check)
                    if release_channel_failures:
                        failed_required_checks.append(check_name)
                        if check_pass:
                            contradictory_required_checks.append(check_name)
                        check["release_channel_semantic_failures"] = release_channel_failures
                if check.get("release_blocking") is False and not google_effective_pass:
                    nonblocking_required_checks.append(check_name)
            for check_name in sorted(
                effective_operator_dashboard_freshness_required_checks & set(dashboard_checks)
            ):
                check = dashboard_checks.get(check_name)
                if not isinstance(check, dict):
                    missing_required_check_fields.extend(
                        f"{check_name}.{field}"
                        for field in sorted(OPERATOR_DASHBOARD_REQUIRED_CHECK_FIELDS)
                    )
                    stale_required_checks.append(check_name)
                    continue
                missing_required_check_fields.extend(
                    f"{check_name}.{field}"
                    for field in sorted(OPERATOR_DASHBOARD_REQUIRED_CHECK_FIELDS)
                    if field not in check or check.get(field) in (None, "")
                )
                generated_at = str(check.get("generated_at_utc") or "")
                if (
                    check.get("fresh") is not True
                    or not generated_at_is_fresh(generated_at, RECRAWL_MAX_AGE_HOURS)
                ):
                    stale_required_checks.append(check_name)
            required_gates[name]["required_checks"] = sorted(effective_operator_dashboard_required_checks)
            required_gates[name]["missing_required_checks"] = missing_required_checks
            required_gates[name]["missing_required_check_fields"] = sorted(set(missing_required_check_fields))
            required_gates[name]["stale_required_checks"] = sorted(set(stale_required_checks))
            required_gates[name]["failed_required_checks"] = sorted(set(failed_required_checks))
            required_gates[name]["nonblocking_required_checks"] = sorted(set(nonblocking_required_checks))
            required_gates[name]["contradictory_required_checks"] = sorted(set(contradictory_required_checks))
            if missing_required_checks:
                failure = f"{name} missing required checks"
                if failure not in failures:
                    failures.append(failure)
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
            if missing_required_check_fields:
                failure = f"{name} missing required check freshness fields"
                if failure not in failures:
                    failures.append(failure)
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
            if stale_required_checks:
                failure = f"{name} has stale required checks"
                if failure not in failures:
                    failures.append(failure)
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
            if failed_required_checks:
                failure = f"{name} has failing required checks"
                if failure not in failures:
                    failures.append(failure)
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
            if nonblocking_required_checks:
                failure = f"{name} marks required checks nonblocking"
                if failure not in failures:
                    failures.append(failure)
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
        if name == "windows_installer_visual_audit" and receipt_loaded:
            windows_semantic_failures = windows_installer_visual_audit_semantic_failures(payload)
            required_gates[name]["artifact"] = payload.get("artifact", {})
            required_gates[name]["semanticFailures"] = windows_semantic_failures
            required_gates[name]["failures"] = structured_failures
            if status_value in {"pass", "passed", "ready"} and windows_semantic_failures:
                if (
                    not IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING
                    and "windows_installer_visual_audit semantic proof failed" not in failures
                ):
                    failures.append("windows_installer_visual_audit semantic proof failed")
                required_gates[name]["pass"] = False
                required_gates[name]["status"] = "fail"
                for failure in windows_semantic_failures:
                    append_unique_failure(required_gates[name], failure)
            required_gates[name]["nextActions"] = payload.get("nextActions", [])
            required_gates[name]["startupReceipt"] = payload.get("startupReceipt", {})
            required_gates[name]["visualAuditSource"] = payload.get("visualAuditSource", {})
            windows_request_path = windows_visual_audit_intake_request_path()
            windows_request_payload = load_json(windows_request_path)
            if windows_request_path.is_file() and windows_request_payload:
                required_gates[name]["operator_request_artifacts"] = windows_operator_request_artifacts(
                    windows_request_path,
                    windows_request_payload,
                    refresh_runtime_receipts=refresh_windows_runtime_receipts,
                )
                try:
                    _ok, verifier = verify_windows_visual_intake_request_receipt(
                        windows_request_path,
                        require_pass=False,
                    )
                    verifier = dict(verifier) if isinstance(verifier, dict) else {}
                except Exception as exc:
                    verifier = {
                        "status": "fail",
                        "issues": [f"windows_visual_audit_intake_request_verifier_failed:{type(exc).__name__}"],
                        "path": str(windows_request_path),
                        "require_pass": False,
                        "operator_action_still_required": False,
                        "recovery_pack_pass": False,
                    }
                required_gates[name]["receipt_verifier"] = verifier
                required_gates[name]["operator_request_artifacts"]["pass"] = bool(
                    verifier.get("recovery_pack_pass")
                )
                required_gates[name]["operator_request_artifacts"]["failures"] = normalized_string_list(
                    verifier.get("issues")
                )
                required_gates[name]["operator_request_artifacts"]["receipt_verifier_status"] = str(
                    verifier.get("status") or ""
                ).strip()
                required_gates[name]["operator_request_artifacts"]["request_effective_status"] = str(
                    verifier.get("effective_status") or ""
                ).strip()
                required_gates[name]["operator_request_artifacts"]["operator_action_still_required"] = bool(
                    verifier.get("operator_action_still_required")
                )
                required_gates[name]["operator_request_artifacts"]["current_windows_visual_audit_status"] = str(
                    verifier.get("current_windows_visual_audit_status") or ""
                ).strip()
                required_gates[name]["operator_request_artifacts"]["current_windows_visual_audit_effective_pass"] = bool(
                    verifier.get("current_windows_visual_audit_effective_pass")
                )
                required_gates[name]["operator_request_artifacts"]["current_windows_visual_audit_issues"] = normalized_string_list(
                    verifier.get("current_windows_visual_audit_issues")
                )
                required_gates[name]["operator_request_artifacts"] = enrich_operator_ask_delivery_details(
                    required_gates[name]["operator_request_artifacts"]
                )
                mirror_windows_runtime_artifacts(required_gates[name])
            windows_digest_mismatch = windows_visual_audit_digest_mismatch_failure(payload)
            if windows_digest_mismatch:
                append_unique_failure(required_gates[name], windows_digest_mismatch)
                if (
                    not IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING
                    and windows_digest_mismatch not in failures
                ):
                    failures.append(windows_digest_mismatch)
            windows_missing_artifact = windows_operator_missing_artifact_failure(required_gates[name])
            if windows_missing_artifact and not required_gates[name]["pass"]:
                append_unique_failure(required_gates[name], windows_missing_artifact)
                if not IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING and windows_missing_artifact not in failures:
                    failures.append(windows_missing_artifact)
            windows_operator_ask_resend = windows_operator_ask_resend_failure(required_gates[name])
            if windows_operator_ask_resend and not required_gates[name]["pass"]:
                required_gates[name]["operatorAskResendAdvisory"] = windows_operator_ask_resend
                append_unique_advisory_action(required_gates[name], windows_operator_ask_resend)
            windows_stage_hint_advisory = windows_stage_visual_proof_hint_advisory(required_gates[name])
            if windows_stage_hint_advisory and not required_gates[name]["pass"]:
                required_gates[name]["stageVisualProofHintAdvisory"] = windows_stage_hint_advisory
                append_unique_advisory_action(required_gates[name], windows_stage_hint_advisory)

    release_ready_gate = required_gates.get("release_ready")
    windows_gate = required_gates.get("windows_installer_visual_audit")
    if isinstance(release_ready_gate, dict) and isinstance(windows_gate, dict):
        release_ready_windows_artifacts = release_ready_windows_blocking_artifacts(release_ready_gate)
        if release_ready_windows_artifacts:
            windows_gate["release_ready_blocking_artifacts"] = release_ready_windows_artifacts
            for key, value in release_ready_windows_artifacts.items():
                if key.startswith("stage_"):
                    windows_gate[key] = value

    recover_live_surface_parity_for_final_gold(required_gates, failures)
    recover_public_edge_postdeploy_for_final_gold(required_gates, failures)
    recover_flagship_product_readiness_for_final_gold(required_gates, failures)
    suppress_dependent_summary_gate_failures_for_final_gold(required_gates, failures)

    for caveat in caveats:
        if not isinstance(caveat, dict):
            continue
        caveat_id = str(caveat.get("id") or "").strip()
        if caveat_id in FAIL_CLOSED_CAVEAT_IDS:
            failures.append(f"{caveat_id} unresolved")

    for result in command_results:
        if result["returncode"] != 0:
            command_text = str(result.get("command") or "")
            public_edge_gate = required_gates.get("public_edge_postdeploy_gate")
            if (
                "scripts/verify_public_edge_postdeploy_gate.py" in command_text
                and isinstance(public_edge_gate, dict)
                and public_edge_gate.get("release_blocking_recovered_from_preflight") is True
            ):
                continue
            if materializer_failure_covered_by_gate_refresh(result, required_gates):
                continue
            waiting_failure = windows_auto_import_waiting_failure(result)
            if waiting_failure:
                if waiting_failure not in failures:
                    failures.append(waiting_failure)
                continue
            waiting_failure = google_auto_import_waiting_failure(result)
            if waiting_failure:
                if waiting_failure not in failures:
                    failures.append(waiting_failure)
                continue
            failures.append(f"materializer failed: {result['command']}")
    root_blockers, local_surface_status = final_gold_root_blocker_families(required_gates, root_release_blockers)
    root_context = root_release_truth_context(root_release_blockers)

    return {
        "contract_name": "chummer.final_gold_janitor",
        "generated_at_utc": now_iso(),
        "scope": "full_estate_v20",
        "artifact_root": f"_completion/{ARTIFACT_ROOT_NAME}",
        "durable_artifacts_required": True,
        "live_backed_required": True,
        "live_recrawl_required": True,
        "recrawl_max_age_hours": RECRAWL_MAX_AGE_HOURS,
        "status": "pass" if not failures else "fail",
        "verdict": "GOLD_READY" if not failures else "NOT_GOLD",
        "required_gates": required_gates,
        "materializers": command_results,
        "caveats": caveats,
        "root_blockers": root_blockers,
        "local_surface_status": local_surface_status,
        "failures": failures,
        "root_blocker_ids": root_context["root_blocker_ids"],
        "root_blockers_generated_at": root_context["root_blockers_generated_at"],
        "stable_promotion_command": root_context["stable_promotion_command"],
        "post_promotion_verify_command": root_context["post_promotion_verify_command"],
        "root_release_truth_source": root_context["root_release_truth_source"],
    }


def build_verdict_markdown(payload: dict[str, Any]) -> str:
    verdict = str(payload.get("verdict") or "NOT_GOLD")
    caveats = payload.get("caveats") if isinstance(payload.get("caveats"), list) else []
    root_blockers = payload.get("root_blockers") if isinstance(payload.get("root_blockers"), list) else []
    local_surface_status = (
        payload.get("local_surface_status")
        if isinstance(payload.get("local_surface_status"), dict)
        else {}
    )
    lines = [
        f"# {verdict}",
        "",
        f"Generated: {payload.get('generated_at_utc')}",
        f"Scope: {payload.get('scope')}",
    ]
    if caveats:
        lines.append("Accepted boundaries: yes")
    lines.extend([
        "",
        "## Root Blockers",
    ])
    if root_blockers:
        for blocker in root_blockers:
            if not isinstance(blocker, dict):
                continue
            lines.append(f"- `{blocker.get('id')}`: {blocker.get('summary')}")
            blocking_checks = normalized_string_list(blocker.get("blocking_checks"))
            if blocking_checks:
                lines.append(f"  - blocking checks: {', '.join(blocking_checks)}")
            details = normalized_string_list(blocker.get("details"))
            if details:
                lines.append(f"  - details: {', '.join(details)}")
            stable_promotion_command = str(blocker.get("stable_promotion_command") or "").strip()
            if stable_promotion_command:
                lines.append(f"  - stable promotion command: `{stable_promotion_command}`")
            post_promotion_verify_command = str(blocker.get("post_promotion_verify_command") or "").strip()
            if post_promotion_verify_command:
                lines.append(f"  - post-promotion verify command: `{post_promotion_verify_command}`")
            required_path = str(blocker.get("required_path") or "").strip()
            preferred_drop_path = str(blocker.get("preferred_drop_path") or "").strip()
            if required_path or preferred_drop_path:
                lines.append(
                    "  - artifact handoff: "
                    f"required_path={required_path or 'missing'} "
                    f"preferred_drop={preferred_drop_path or 'missing'}"
                )
            blocker_class = str(blocker.get("blocker_class") or "").strip()
            if blocker_class:
                lines.append(f"  - blocker class: `{blocker_class}`")
            if blocker.get("activation_authority_required") is not None:
                lines.append(
                    "  - activation authority required: "
                    f"`{str(bool(blocker.get('activation_authority_required'))).lower()}`"
                )
            if blocker.get("post_activation_proof_required") is not None:
                lines.append(
                    "  - post-activation proof required: "
                    f"`{str(bool(blocker.get('post_activation_proof_required'))).lower()}`"
                )
            staged_overlay_receipt_path = str(blocker.get("staged_overlay_receipt_path") or "").strip()
            if staged_overlay_receipt_path:
                lines.append(f"  - staged overlay receipt: `{staged_overlay_receipt_path}`")
            staging_root = str(blocker.get("staging_root") or "").strip()
            if staging_root:
                lines.append(f"  - staged overlay root: `{staging_root}`")
            external_prerequisite = str(blocker.get("external_prerequisite") or "").strip()
            if external_prerequisite:
                lines.append(f"  - prerequisite: {external_prerequisite}")
            verify_command = str(blocker.get("verify_command") or "").strip()
            if verify_command:
                lines.append(f"  - post-activation verify command: `{verify_command}`")
    else:
        lines.append("- none")
    local_surface_checks = (
        local_surface_status.get("checks")
        if isinstance(local_surface_status.get("checks"), list)
        else []
    )
    if local_surface_checks:
        rendered_surface_checks = ", ".join(
            f"{str(item.get('name') or '').strip()}={str(item.get('status') or '').strip()}"
            for item in local_surface_checks
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )
        lines.append(
            f"- local flagship surfaces: all_passing={bool(local_surface_status.get('all_passing'))} checks={rendered_surface_checks}"
        )
    lines.extend([
        "",
        "## Gate Summary",
    ])
    for name, gate in sorted((payload.get("required_gates") or {}).items()):
        if not isinstance(gate, dict):
            continue
        mark = "PASS" if gate.get("pass") else "FAIL"
        lines.append(f"- {mark} `{name}`: `{gate.get('status')}` at `{gate.get('path')}`")
        if gate.get("raw_status") and gate.get("raw_status") != gate.get("status"):
            lines.append(f"  - raw status: `{gate.get('raw_status')}`")
        if name == "public_route_proof" and isinstance(gate.get("summary"), dict):
            summary = gate["summary"]
            lines.append(
                f"  - routes {summary.get('passed_count')}/{summary.get('route_count')}, failed {summary.get('failed_count')}, negative-path failures {summary.get('negative_path_failed_count')}"
            )
        if name == "blazor_execution_horizon_bridge" and isinstance(gate.get("summary"), dict):
            summary = gate["summary"]
            lines.append(
                "  - blazor bridge: "
                f"verdict={summary.get('verdict')} "
                f"hub_mobile={summary.get('hub_mobile_pwa_public_projection_status')} "
                f"blazor_pwa={summary.get('blazor_hosted_pwa_public_edge_status')} "
                f"near_term={summary.get('near_term_smoke_status')} "
                f"mid_term={summary.get('mid_term_full_matrix_status')} "
                f"mid_term_workflows={summary.get('mid_term_full_covered_workflow_family_count')}/{summary.get('mid_term_full_required_workflow_family_count')} "
                f"long_term={summary.get('long_term_full_browser_parity_status')}"
            )
            play_surface = gate["summary"].get("play_surface_horizon")
            play_surface = play_surface if isinstance(play_surface, dict) else {}
            horizons = play_surface.get("horizons") if isinstance(play_surface.get("horizons"), list) else []
            if horizons:
                rendered_horizons = ", ".join(
                    f"{str(item.get('id') or '').strip()}={str(item.get('status') or '').strip()}"
                    for item in horizons
                    if isinstance(item, dict) and str(item.get("id") or "").strip()
                )
                if rendered_horizons:
                    lines.append(f"  - play-surface horizons: {rendered_horizons}")
            server_bound_boundaries = play_surface.get("mid_term_server_bound_boundaries")
            if isinstance(server_bound_boundaries, list) and server_bound_boundaries:
                lines.append(
                    "  - mid-term server-bound boundaries: "
                    + ", ".join(str(item) for item in server_bound_boundaries)
                )
        if name == "public_edge_postdeploy_gate":
            lines.append(
                "  - edge: "
                f"preflight={gate.get('preflightStatus')} blocking_locks={gate.get('preflightBlockingLockCount')} "
                f"active_locks={gate.get('preflightActiveLockCount')} stale_locks={gate.get('preflightStaleLookingLockCount')} "
                f"stale_foreign={gate.get('preflightStaleForeignLockCount')} ignored={gate.get('preflightStaleForeignLocksIgnored')} "
                f"downloads={gate.get('downloadsStatus')} "
                f"marker={gate.get('downloadsHasMarker')} status_marker={gate.get('statusRedirectHasMarker')} "
                f"visible_version={gate.get('visibleVersion')} "
                f"status_version={gate.get('statusRedirectVersion')} "
                f"expected_version={gate.get('expectedReleaseVersion')} "
                f"version_match={gate.get('visibleVersionMatchesReleaseChannel')} "
                f"status_version_match={gate.get('statusRedirectVersionMatchesReleaseChannel')} "
                f"release_manifest_supportability={gate.get('releaseManifestSupportabilityState')} "
                f"expected_supportability={gate.get('expectedReleaseSupportabilityState')} "
                f"supportability_match={gate.get('releaseManifestSupportabilityMatchesReleaseChannel')} "
                f"release_manifest_rollout={gate.get('releaseManifestRolloutState')} "
                f"expected_rollout={gate.get('expectedReleaseRolloutState')} "
                f"rollout_match={gate.get('releaseManifestRolloutMatchesReleaseChannel')} "
                f"browser={gate.get('downloadsStatusBrowserStatus')} "
                f"mobile_viewport={gate.get('mobilePwaViewportStatus')} "
                f"offline_cache={gate.get('pwaOfflineCacheStatus')} "
                f"role_aliases={gate.get('roleAliasRouteStatus')} "
                f"frontdoor={gate.get('frontdoorNavigationStatus')} "
                f"participate_iframe={gate.get('participateIframeShellStatus')}"
            )
            lines.append(
                "  - edge release truth: "
                f"status={gate.get('release_truth_status')} "
                f"verdict={gate.get('release_truth_verdict')} "
                f"runtime_override={gate.get('release_truth_runtime_override_applied')} "
                f"runtime_observation={gate.get('release_truth_runtime_observation_status')} "
                f"overlay_root={gate.get('release_truth_runtime_overlay_root')} "
                f"active_locks={gate.get('release_truth_runtime_active_lock_count')} "
                f"foreign_locks={gate.get('release_truth_runtime_foreign_lock_count')} "
                f"stale_foreign={gate.get('release_truth_runtime_stale_foreign_lock_count')}"
            )
            lines.append(
                "  - mobile PWA viewport: "
                f"routes={gate.get('mobilePwaViewportRouteCount')} "
                f"viewports={gate.get('mobilePwaViewportViewportCount')}"
            )
            lines.append(
                "  - role PWA manifests: "
                f"count={gate.get('rolePwaManifestCount')} "
                f"manifests={gate.get('rolePwaManifests')}"
            )
            lines.append(
                "  - ready mobile handoff: "
                f"frontdoor_launch_route={gate.get('readyMobileHandoffFrontdoorLaunchRoute')} "
                f"role_routes={gate.get('readyMobileHandoffRoleRoutes')}"
            )
            lines.append(
                "  - PWA offline cache: "
                f"version={gate.get('pwaOfflineCacheCacheVersion')} "
                f"navigation={gate.get('pwaOfflineCacheNavigationPolicy')} "
                f"private_state={gate.get('pwaOfflineCachePrivateStateScope')} "
                f"static_paths={gate.get('pwaOfflineCacheStaticPaths')} "
                f"role_fallbacks={gate.get('pwaOfflineCacheOfflineRoleFallbacks')} "
                f"private_navigation_cached={gate.get('pwaOfflineCachePrivateNavigationCached')} "
                f"private_api_cached={gate.get('pwaOfflineCachePrivateApiCached')} "
                f"personalized_ledger_cached={gate.get('pwaOfflineCachePersonalizedLedgerCached')}"
            )
            lines.append(
                "  - public role aliases: "
                f"results={gate.get('roleAliasRouteResults')} "
                f"drift={gate.get('roleAliasRouteDrift')}"
            )
            lines.append(
                "  - front-door navigation: "
                f"gated_targets={gate.get('frontdoorNavigationGatedTargets')} "
                f"public_targets={gate.get('frontdoorNavigationPublicTargets')} "
                f"play_route={gate.get('frontdoorNavigationPlayRoute')} "
                f"play_sign_in_route={gate.get('frontdoorNavigationPlaySignInRoute')} "
                f"direct_player_route={gate.get('frontdoorNavigationDirectPlayerRoute')} "
                f"player_http={gate.get('frontdoorNavigationDirectPlayerHttpStatus')} "
                f"player_manifest={gate.get('frontdoorNavigationPwaManifestPath')} "
                f"player_role={gate.get('frontdoorNavigationPwaRole')} "
                f"player_rybbit_skip_mobile={gate.get('frontdoorNavigationRybbitSkipMobilePaths')} "
                f"player_rybbit_mask_api={gate.get('frontdoorNavigationRybbitMasksPrivatePlayRoutes')} "
                f"player_rybbit_replay_block={gate.get('frontdoorNavigationRybbitReplayBlocksTurnRoot')} "
                f"gm_route={gate.get('frontdoorNavigationGmRoute')} "
                f"gm_http={gate.get('frontdoorNavigationGmHttpStatus')} "
                f"gm_manifest={gate.get('frontdoorNavigationGmPwaManifestPath')} "
                f"gm_role={gate.get('frontdoorNavigationGmPwaRole')} "
                f"gm_rybbit_skip_mobile={gate.get('frontdoorNavigationGmRybbitSkipMobilePaths')} "
                f"gm_rybbit_mask_api={gate.get('frontdoorNavigationGmRybbitMasksPrivatePlayRoutes')} "
                f"gm_rybbit_replay_block={gate.get('frontdoorNavigationGmRybbitReplayBlocksTurnRoot')} "
                f"ledger_primary={gate.get('frontdoorNavigationLedgerPrimary')}"
            )
            lines.append(
                "  - front-door session handoff: "
                f"player_preserves_session={gate.get('frontdoorNavigationPlayerSessionHandoffPreservesSession')} "
                f"player_preserves_role={gate.get('frontdoorNavigationPlayerSessionHandoffPreservesRole')} "
                f"player_strips_device={gate.get('frontdoorNavigationPlayerSessionHandoffStripsDevice')} "
                f"player_identity_redacted={gate.get('frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted')} "
                f"gm_preserves_session={gate.get('frontdoorNavigationGmSessionHandoffPreservesSession')} "
                f"gm_preserves_role={gate.get('frontdoorNavigationGmSessionHandoffPreservesRole')} "
                f"gm_strips_device={gate.get('frontdoorNavigationGmSessionHandoffStripsDevice')} "
                f"gm_identity_redacted={gate.get('frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted')}"
            )
            lines.append(
                "  - participate iframe shell: "
                f"routes={gate.get('participateIframeRouteCount')} "
                f"iframe_routes={gate.get('participateIframeRouteIframeCount')} "
                f"fallback_routes={gate.get('participateIframeRouteOfflineFallbackCount')}"
            )
            if gate.get("missingRequiredFields"):
                lines.append(f"  - missing postdeploy fields: {', '.join(str(item) for item in gate['missingRequiredFields'])}")
            if gate.get("failures"):
                lines.append(f"  - edge failures: {', '.join(str(item) for item in gate['failures'])}")
        if name == "teable_important_work" and isinstance(gate.get("summary"), dict):
            summary = gate["summary"]
            lines.append(
                "  - teable: "
                f"state={summary.get('sync_state')} "
                f"attempted={summary.get('sync_attempted')} "
                f"rows={summary.get('synced_count')}/{summary.get('row_count')} "
                f"failed={summary.get('failed_count')} "
                f"table={summary.get('table_name')}"
            )
        if name == "flagship_product_readiness" and isinstance(gate.get("summary"), dict):
            summary = gate["summary"]
            lines.append(
                "  - flagship readiness: "
                f"source={summary.get('source_receipt')} "
                f"verdict={summary.get('verdict') or 'missing'} "
                f"audit={summary.get('flagship_readiness_audit_status')} "
                f"completion={summary.get('completion_audit_status')} "
                f"ready={summary.get('ready_count')} "
                f"missing={summary.get('missing_count')} "
                f"scoped_missing={summary.get('scoped_missing_count')} "
                f"coverage_gaps={summary.get('coverage_gap_keys')}"
            )
            if summary.get("recovered_for_final_gold"):
                lines.append(
                    "  - release-blocking recovered via: "
                    + ", ".join(str(item) for item in summary.get("recovered_because_of_gates") or [])
                )
            if summary.get("launch_critical_nested_blockers"):
                lines.append(
                    "  - launch blockers: "
                    + ", ".join(str(item) for item in summary["launch_critical_nested_blockers"])
                )
            if summary.get("reason"):
                lines.append(f"  - readiness reason: {summary.get('reason')}")
        if name == "external_distribution_mirror_proof" and isinstance(gate.get("providers"), dict):
            provider_summary = ", ".join(f"{provider}={status}" for provider, status in sorted(gate["providers"].items()))
            lines.append(f"  - mirrors: {provider_summary}; external_required={gate.get('external_required')}")
        if name == "public_edge_postdeploy_gate":
            lines.append(
                f"  - public edge: {gate.get('visibleVersion')} "
                f"with browser proof `{gate.get('browserPlaywrightStatus')}` "
                f"and horizons `{gate.get('flagshipHorizonsBrowserProofCoverage')}`"
            )
            if gate.get("mobileLedgerPayloadStatus"):
                lines.append(f"  - mobile ledger: {gate.get('mobileLedgerPayloadStatus')}")
        if name == "ruleset_readiness":
            workflow_assumed = gate.get("workflow_assumed_rulesets") or []
            authority_approved = gate.get("authority_approved_rulesets") or []
            if workflow_assumed:
                lines.append(f"  - workflow assumption: {', '.join(workflow_assumed)}")
            if authority_approved:
                lines.append(f"  - authority approved: {', '.join(authority_approved)}")
        if name != "release_ready" and gate.get("failed_gates"):
            lines.append(f"  - failed gates: {', '.join(str(item) for item in gate['failed_gates'])}")
        if name == "release_ready" and gate.get("failures"):
            lines.append(f"  - release failures: {', '.join(str(item) for item in gate['failures'])}")
        if name == "release_ready" and gate.get("failed_gates"):
            lines.append(f"  - release failed gates: {', '.join(str(item) for item in gate['failed_gates'])}")
        if name == "release_ready" and isinstance(gate.get("public_release_snapshot_readonly_audit"), dict):
            snapshot_audit = gate["public_release_snapshot_readonly_audit"]
            lines.append(
                "  - snapshot truth audit: "
                f"status={snapshot_audit.get('status') or 'missing'} "
                f"verdict={snapshot_audit.get('verdict') or 'missing'} "
                f"path={snapshot_audit.get('path') or 'missing'}"
            )
            if snapshot_audit.get("raw_status") and snapshot_audit.get("raw_status") != snapshot_audit.get("status"):
                lines.append(f"  - snapshot truth audit raw status: {snapshot_audit.get('raw_status')}")
            if snapshot_audit.get("summary"):
                lines.append(f"  - snapshot truth audit summary: {snapshot_audit['summary']}")
            expected_root_blockers = snapshot_audit.get("expected_top_level_blocker_ids") or []
            if expected_root_blockers:
                lines.append(
                    "  - snapshot truth audit expected root blockers: "
                    + ", ".join(str(item) for item in expected_root_blockers)
                )
        if name == "operator_release_dashboard" and isinstance(gate.get("release"), dict):
            release = gate["release"]
            lines.append(f"  - release: {release.get('version')} on {release.get('channel')}")
        if name == "operator_release_dashboard" and isinstance(gate.get("release_readiness"), dict):
            release_readiness = gate["release_readiness"]
            lines.append(
                f"  - readiness: full_release_ready={release_readiness.get('full_release_ready')}, "
                f"nightly_handoff_ready={release_readiness.get('nightly_handoff_ready')}"
            )
            blockers = release_readiness.get("full_release_blockers")
            if isinstance(blockers, list) and blockers:
                lines.append(f"  - full release blockers: {', '.join(str(item) for item in blockers)}")
            blocker_details = release_readiness.get("full_release_blocker_details")
            if isinstance(blocker_details, list) and blocker_details:
                lines.append("  - full release blocker details:")
                lines.extend(f"    - {item}" for item in blocker_details)
        if name == "operator_release_dashboard" and gate.get("failures"):
            lines.append(f"  - dashboard failures: {', '.join(str(item) for item in gate['failures'])}")
        if name == "google_oauth_linking_proof" and gate.get("failures"):
            lines.append(f"  - google oauth failures: {', '.join(str(item) for item in gate['failures'])}")
            request_artifacts = gate.get("operator_request_artifacts")
            request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
            required_operator_evidence_path = str(request_artifacts.get("required_operator_evidence_path") or "").strip()
            request_receipt_path = str(request_artifacts.get("request_receipt_path") or "").strip()
            operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or "").strip()
            operator_ask_send_command = str(request_artifacts.get("operator_ask_send_command") or "").strip()
            operator_ask_resend_command = str(request_artifacts.get("operator_ask_resend_command") or "").strip()
            show_google_action_commands = normalized_token(request_artifacts.get("request_status")) != "not_required"
            if required_operator_evidence_path or request_receipt_path or operator_ask_text_path:
                lines.append(
                    "  - google oauth operator evidence: "
                    f"required_path={required_operator_evidence_path or 'missing'} "
                    f"request_receipt={request_receipt_path or 'missing'} "
                    f"ask_text={operator_ask_text_path or 'missing'}"
                )
            if show_google_action_commands and operator_ask_send_command:
                lines.append(f"  - google oauth operator ask send: {operator_ask_send_command}")
            if show_google_action_commands and operator_ask_resend_command:
                lines.append(f"  - google oauth operator ask resend: {operator_ask_resend_command}")
        if name == "windows_installer_visual_audit" and gate.get("failures"):
            lines.append(f"  - visual audit failures: {', '.join(str(item) for item in gate['failures'])}")
            artifact = gate.get("artifact")
            artifact = artifact if isinstance(artifact, dict) else {}
            visual = gate.get("visualAuditSource")
            visual = visual if isinstance(visual, dict) else {}
            startup = gate.get("startupReceipt")
            startup = startup if isinstance(startup, dict) else {}
            promoted_digest = normalized_sha(artifact.get("sha256")) or "missing"
            visual_digest = normalized_sha(visual.get("artifactSha256")) or "missing"
            visual_source_path = str(visual.get("path") or "").strip() or "missing"
            startup_path = str(startup.get("path") or "").strip() or "missing"
            lines.append(
                "  - visual audit source: "
                f"promoted_digest={promoted_digest} "
                f"source_digest={visual_digest} "
                f"source_path={visual_source_path} "
                f"startup_path={startup_path}"
            )
            request_artifacts = gate.get("operator_request_artifacts")
            request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
            request_receipt_path = str(request_artifacts.get("request_receipt_path") or "").strip()
            operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or "").strip()
            preferred_drop_path = str(request_artifacts.get("preferred_drop_path") or "").strip()
            preferred_extracted_visual_dir = str(
                request_artifacts.get("preferred_extracted_visual_dir") or ""
            ).strip()
            discover_command = str(request_artifacts.get("discover_command") or "").strip()
            discover_visual_source_command = str(
                request_artifacts.get("discover_visual_source_command") or ""
            ).strip()
            operator_ask_send_command = str(request_artifacts.get("operator_ask_send_command") or "").strip()
            operator_ask_resend_command = str(request_artifacts.get("operator_ask_resend_command") or "").strip()
            import_command = str(request_artifacts.get("import_command") or "").strip()
            auto_import_watch_command = str(request_artifacts.get("auto_import_watch_command") or "").strip()
            auto_import_receipt_path = str(request_artifacts.get("auto_import_receipt_path") or "").strip()
            auto_import_receipt_status = str(request_artifacts.get("auto_import_receipt_status") or "").strip()
            auto_import_artifact = str(request_artifacts.get("auto_import_artifact") or "").strip()
            auto_import_import_failure_type = str(
                request_artifacts.get("auto_import_import_failure_type") or ""
            ).strip()
            auto_import_import_failure_message = str(
                request_artifacts.get("auto_import_import_failure_message") or ""
            ).strip()
            auto_import_import_failure_code = request_artifacts.get("auto_import_import_failure_code")
            auto_import_import_failure_summary = str(
                request_artifacts.get("auto_import_import_failure_summary") or ""
            ).strip()
            auto_import_actionable_candidate_count = int_value(
                request_artifacts.get("auto_import_actionable_candidate_count")
            )
            auto_import_matching_promoted_directory_candidate_count = int_value(
                request_artifacts.get("auto_import_matching_promoted_directory_candidate_count")
            )
            auto_import_matching_promoted_zip_candidate_count = int_value(
                request_artifacts.get("auto_import_matching_promoted_zip_candidate_count")
            )
            auto_import_stale_directory_candidate_count = int_value(
                request_artifacts.get("auto_import_stale_directory_candidate_count")
            )
            auto_import_stage_like_stale_directory_candidate_count = int_value(
                request_artifacts.get("auto_import_stage_like_stale_directory_candidate_count")
            )
            auto_import_stage_visual_proof_receipt_count = int_value(
                request_artifacts.get("auto_import_stage_visual_proof_receipt_count")
            )
            auto_import_matching_promoted_stage_visual_proof_receipt_count = int_value(
                request_artifacts.get("auto_import_matching_promoted_stage_visual_proof_receipt_count")
            )
            auto_import_stale_stage_visual_proof_receipt_count = int_value(
                request_artifacts.get("auto_import_stale_stage_visual_proof_receipt_count")
            )
            auto_import_stage_startup_smoke_receipt_count = int_value(
                request_artifacts.get("auto_import_stage_startup_smoke_receipt_count")
            )
            auto_import_matching_promoted_stage_startup_smoke_receipt_count = int_value(
                request_artifacts.get("auto_import_matching_promoted_stage_startup_smoke_receipt_count")
            )
            auto_import_stale_stage_startup_smoke_receipt_count = int_value(
                request_artifacts.get("auto_import_stale_stage_startup_smoke_receipt_count")
            )
            auto_import_stage_visual_proof_hint_paths_sample = windows_stage_visual_proof_hint_paths(
                request_artifacts
            )
            auto_import_stage_startup_smoke_hint_paths_sample = windows_stage_startup_smoke_hint_paths(
                request_artifacts
            )
            auto_import_stale_directory_digest_summary = (
                request_artifacts.get("auto_import_stale_directory_digest_summary")
                if isinstance(request_artifacts.get("auto_import_stale_directory_digest_summary"), list)
                else []
            )
            auto_import_stage_visual_proof_receipt_note = str(
                request_artifacts.get("auto_import_stage_visual_proof_receipt_note") or ""
            ).strip()
            auto_import_stage_startup_smoke_receipt_note = str(
                request_artifacts.get("auto_import_stage_startup_smoke_receipt_note") or ""
            ).strip()
            auto_import_directory_candidate_note = str(
                request_artifacts.get("auto_import_directory_candidate_note") or ""
            ).strip()
            watcher_status = str(request_artifacts.get("watcher_status") or "").strip()
            watcher_pid = request_artifacts.get("watcher_pid")
            watcher_matching_process_count = int_value(request_artifacts.get("watcher_matching_process_count"))
            watcher_duplicate_process_count = int_value(request_artifacts.get("watcher_duplicate_process_count"))
            watcher_state_receipt_path = str(request_artifacts.get("watcher_state_receipt_path") or "").strip()
            watcher_attention_required = bool(request_artifacts.get("watcher_attention_required"))
            watcher_note = str(request_artifacts.get("watcher_note") or "").strip()
            watcher_start_command = str(request_artifacts.get("watcher_start_command") or "").strip()
            watcher_status_command = str(request_artifacts.get("watcher_status_command") or "").strip()
            watcher_stop_command = str(request_artifacts.get("watcher_stop_command") or "").strip()
            if request_receipt_path or operator_ask_text_path or preferred_drop_path or preferred_extracted_visual_dir:
                lines.append(
                    "  - windows visual proof request: "
                    f"request_receipt={request_receipt_path or 'missing'} "
                    f"ask_text={operator_ask_text_path or 'missing'} "
                    f"preferred_drop={preferred_drop_path or 'missing'} "
                    f"fallback_dir={preferred_extracted_visual_dir or 'missing'}"
                )
            if discover_command or discover_visual_source_command:
                lines.append(
                    "  - windows proof discovery: "
                    f"bundle={discover_command or 'missing'} "
                    f"visual_source={discover_visual_source_command or 'missing'}"
                )
            stage_release_handoff_path = str(gate.get("stage_release_build_handoff_path") or "").strip()
            stage_release_handoff_status = str(gate.get("stage_release_build_handoff_status") or "").strip()
            stage_visual_handoff_path = str(gate.get("stage_windows_visual_proof_handoff_path") or "").strip()
            stage_visual_handoff_status = str(gate.get("stage_windows_visual_proof_handoff_status") or "").strip()
            stage_visual_handoff_summary = str(gate.get("stage_windows_visual_proof_handoff_summary") or "").strip()
            if stage_release_handoff_path or stage_visual_handoff_path:
                lines.append(
                    "  - staged windows handoff: "
                    f"release_build={stage_release_handoff_path or 'missing'} "
                    f"release_status={stage_release_handoff_status or 'missing'} "
                    f"visual_handoff={stage_visual_handoff_path or 'missing'} "
                    f"visual_status={stage_visual_handoff_status or 'missing'}"
                )
            if stage_visual_handoff_summary:
                lines.append(f"  - staged windows handoff summary: {stage_visual_handoff_summary}")
            if operator_ask_send_command:
                lines.append(f"  - windows operator ask send: {operator_ask_send_command}")
            if operator_ask_resend_command:
                lines.append(f"  - windows operator ask resend: {operator_ask_resend_command}")
            if import_command or auto_import_watch_command:
                lines.append(
                    "  - windows proof intake: "
                    f"import={import_command or 'missing'} "
                    f"watch={auto_import_watch_command or 'missing'}"
                )
            if watcher_state_receipt_path or watcher_status or watcher_start_command or watcher_status_command or watcher_stop_command:
                lines.append(
                    "  - windows watcher state: "
                    f"status={watcher_status or 'missing'} "
                    f"pid={watcher_pid if watcher_pid is not None else 'missing'} "
                    f"matches={watcher_matching_process_count} "
                    f"duplicates={watcher_duplicate_process_count} "
                    f"attention={str(watcher_attention_required).lower()} "
                    f"state={watcher_state_receipt_path or 'missing'}"
                )
            if watcher_note:
                lines.append(f"  - windows watcher note: {watcher_note}")
            if watcher_start_command or watcher_status_command or watcher_stop_command:
                lines.append(
                    "  - windows watcher control: "
                    f"start={watcher_start_command or 'missing'} "
                    f"status={watcher_status_command or 'missing'} "
                    f"stop={watcher_stop_command or 'missing'}"
                )
            if auto_import_receipt_path or auto_import_receipt_status:
                lines.append(
                    "  - windows auto-import state: "
                    f"status={auto_import_receipt_status or 'missing'} "
                    f"actionable={auto_import_actionable_candidate_count} "
                    f"matching_dirs={auto_import_matching_promoted_directory_candidate_count} "
                    f"matching_zips={auto_import_matching_promoted_zip_candidate_count} "
                    f"stale_dirs={auto_import_stale_directory_candidate_count} "
                    f"artifact={auto_import_artifact or 'missing'} "
                    f"receipt={auto_import_receipt_path or 'missing'}"
                )
            if (
                auto_import_import_failure_type
                or auto_import_import_failure_message
                or auto_import_import_failure_summary
            ):
                failure_code = (
                    f" code={auto_import_import_failure_code}"
                    if auto_import_import_failure_code not in (None, "")
                    else ""
                )
                lines.append(
                    "  - windows auto-import failure: "
                    f"type={auto_import_import_failure_type or 'missing'} "
                    f"message={auto_import_import_failure_message or 'missing'}"
                    f"{failure_code} "
                    f"summary={auto_import_import_failure_summary or 'missing'}"
                )
            if (
                auto_import_stage_visual_proof_receipt_count
                or auto_import_matching_promoted_stage_visual_proof_receipt_count
                or auto_import_stale_stage_visual_proof_receipt_count
                or auto_import_stage_visual_proof_receipt_note
            ):
                lines.append(
                    "  - windows stage-proof hints: "
                    f"total={auto_import_stage_visual_proof_receipt_count} "
                    f"matching_promoted={auto_import_matching_promoted_stage_visual_proof_receipt_count} "
                    f"stale={auto_import_stale_stage_visual_proof_receipt_count} "
                    f"receipt={auto_import_receipt_path or 'missing'}"
                )
            if auto_import_stage_visual_proof_hint_paths_sample:
                lines.append(
                    "  - windows stage-proof hint paths: "
                    + "; ".join(auto_import_stage_visual_proof_hint_paths_sample)
                )
            if auto_import_stage_visual_proof_receipt_note:
                lines.append(
                    f"  - windows stage-proof hint note: {auto_import_stage_visual_proof_receipt_note}"
                )
            if (
                auto_import_stage_startup_smoke_receipt_count
                or auto_import_matching_promoted_stage_startup_smoke_receipt_count
                or auto_import_stale_stage_startup_smoke_receipt_count
                or auto_import_stage_startup_smoke_receipt_note
            ):
                lines.append(
                    "  - windows startup-smoke hints: "
                    f"total={auto_import_stage_startup_smoke_receipt_count} "
                    f"matching_promoted={auto_import_matching_promoted_stage_startup_smoke_receipt_count} "
                    f"stale={auto_import_stale_stage_startup_smoke_receipt_count} "
                    f"receipt={auto_import_receipt_path or 'missing'}"
                )
            if auto_import_stage_startup_smoke_receipt_note:
                lines.append(
                    f"  - windows startup-smoke hint note: {auto_import_stage_startup_smoke_receipt_note}"
                )
            if auto_import_stage_startup_smoke_hint_paths_sample:
                lines.append(
                    "  - windows startup-smoke hint paths: "
                    + "; ".join(auto_import_stage_startup_smoke_hint_paths_sample)
                )
            if auto_import_stale_directory_digest_summary:
                digest_summary_text = "; ".join(
                    f"{str(item.get('artifact_sha256') or '')[:12] or 'missing'} "
                    f"count={int_value(item.get('count'))} "
                    f"stage_like={int_value(item.get('stage_like_count'))}"
                    for item in auto_import_stale_directory_digest_summary
                    if isinstance(item, dict)
                )
                lines.append(
                    "  - windows auto-import stale digests: "
                    f"{digest_summary_text or 'missing'} "
                    f"(stage_like_total={auto_import_stage_like_stale_directory_candidate_count})"
                )
            if auto_import_directory_candidate_note:
                lines.append(f"  - windows auto-import note: {auto_import_directory_candidate_note}")
            if gate.get("nextActions"):
                lines.append("  - next actions:")
                lines.extend(f"    - {item}" for item in gate["nextActions"])
        if gate.get("advisoryActions"):
            lines.append("  - advisory actions:")
            lines.extend(f"    - {item}" for item in gate["advisoryActions"])

    if caveats:
        lines.extend(["", "## Accepted Boundaries"])
        for item in caveats:
            if not isinstance(item, dict):
                continue
            lines.append(f"- `{item.get('id')}`: {item.get('summary')}")

    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in failures)

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the final gold verdict from committed, fresh, fail-closed receipts.")
    parser.add_argument("--skip-materializers", action="store_true", help="Read receipts without regenerating them.")
    parser.add_argument(
        "--skip-windows-runtime-refresh",
        action="store_true",
        help="Read existing Windows watcher/auto-import receipts without invoking their refresh commands.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command_results = [] if args.skip_materializers else run_materializers()
    payload = build_payload(command_results)
    legacy_payload = dict(payload)
    legacy_payload["mirrors"] = {
        "authoritative_artifact_root": payload["artifact_root"],
        "legacy_closure_root": str(LEGACY_GOLD_CLOSURE_ROOT),
    }
    if fleet_artifact_mirror_enabled():
        legacy_payload["mirrors"]["fleet_artifact_root"] = str(FLEET_ARTIFACT_ROOT)
    write_json(PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    write_json(ARTIFACT_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    if fleet_artifact_mirror_enabled():
        write_json(FLEET_ARTIFACT_ROOT / "FINAL_GOLD_JANITOR.generated.json", payload)
    write_json(LEGACY_GOLD_CLOSURE_ROOT / "FINAL_GOLD_JANITOR.generated.json", legacy_payload)
    verdict_markdown = build_verdict_markdown(payload)
    write_text(PUBLISHED_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    write_text(ARTIFACT_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    if fleet_artifact_mirror_enabled():
        write_text(FLEET_ARTIFACT_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    write_text(LEGACY_GOLD_CLOSURE_ROOT / "FINAL_GOLD_VERDICT.md", verdict_markdown)
    if payload["status"] != "pass":
        print(json.dumps({
            "status": payload["status"],
            "verdict": payload["verdict"],
            "failures": payload["failures"],
            "required_gates": {
                name: gate
                for name, gate in payload["required_gates"].items()
                if not gate.get("pass")
            },
            "failed_materializers": [
                result for result in payload["materializers"]
                if result.get("returncode") != 0
            ],
        }, indent=2), file=sys.stderr)
        raise SystemExit("final gold janitor failed")
    print("final_gold_janitor:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
