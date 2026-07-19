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
LIVE_PUBLIC_WINDOWS_VERIFIER_PATH = (
    RUN_SERVICES_ROOT / "scripts" / "verify-windows-installer-payloads.py"
)
LIVE_PUBLIC_WINDOWS_VERIFIER_URI = (
    "repo://ArchonMegalon/chummer6-hub/"
    "scripts/verify-windows-installer-payloads.py"
)
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
COMPLETION_ROOT = RUN_SERVICES_ROOT.parent / "_completion"
ARTIFACT_ROOT_NAME = os.environ.get("CHUMMER_FINAL_GOLD_ARTIFACT_ROOT", "full_product_reaudit_v20")
ARTIFACT_ROOT = COMPLETION_ROOT / ARTIFACT_ROOT_NAME
UI_LAYOUT_COMPLETION_ROOT = COMPLETION_ROOT / "chummer_run_redesign_closure"
LEGACY_GOLD_CLOSURE_ROOT = COMPLETION_ROOT / "gold_readiness_closure"
FLEET_COMPLETION_ROOT = Path(os.environ.get("CHUMMER_FLEET_COMPLETION_ROOT", "/docker/fleet/_completion"))
FLEET_ARTIFACT_ROOT = FLEET_COMPLETION_ROOT / ARTIFACT_ROOT_NAME
DEFAULT_BASE_URL = os.environ.get("CHUMMER_FINAL_GOLD_BASE_URL", "https://chummer.run")
EXPECTED_PUBLIC_EDGE_RELEASE_CHANNEL = os.environ.get(
    "CHUMMER_FINAL_GOLD_EXPECTED_RELEASE_CHANNEL",
    "nightly",
)
PUBLIC_EDGE_POSTDEPLOY_PREFLIGHT_ARGS = [
    "--expected-release-channel",
    EXPECTED_PUBLIC_EDGE_RELEASE_CHANNEL,
]
PUBLIC_EDGE_BROWSER_PROOF_ROOT = PUBLISHED_ROOT / "public-edge-browser-proofs"
PUBLIC_EDGE_DOWNLOADS_STATUS_ARTIFACT_DIR = PUBLIC_EDGE_BROWSER_PROOF_ROOT / "downloads-status"
PUBLIC_EDGE_MOBILE_VIEWPORT_ARTIFACT_DIR = PUBLIC_EDGE_BROWSER_PROOF_ROOT / "mobile-viewport"
PUBLIC_EDGE_OFFLINE_CACHE_ARTIFACT_DIR = PUBLIC_EDGE_BROWSER_PROOF_ROOT / "offline-cache"
PUBLIC_EDGE_BLAZOR_NEW_RUNNER_ARTIFACT_DIR = PUBLIC_EDGE_BROWSER_PROOF_ROOT / "blazor-new-runner-menu"
PUBLIC_EDGE_FRONTDOOR_ARTIFACT_DIR = PUBLIC_EDGE_BROWSER_PROOF_ROOT / "frontdoor-navigation"
RECRAWL_MAX_AGE_HOURS = 24
MATERIALIZER_TIMEOUT_SECONDS = int(os.environ.get("CHUMMER_FINAL_GOLD_MATERIALIZER_TIMEOUT_SECONDS", "180"))
PARTICIPATE_BILLING_MATERIALIZER_TIMEOUT_SECONDS = int(
    os.environ.get("CHUMMER_FINAL_GOLD_PARTICIPATE_BILLING_TIMEOUT_SECONDS", "300")
)
BLACK_LEDGER_LIVE_MEDIA_MATERIALIZER_TIMEOUT_SECONDS = int(
    os.environ.get("CHUMMER_FINAL_GOLD_BLACK_LEDGER_MEDIA_TIMEOUT_SECONDS", "300")
)
RELEASE_READY_MATERIALIZER_TIMEOUT_SECONDS = int(
    os.environ.get(
        "CHUMMER_FINAL_GOLD_RELEASE_READY_MATERIALIZER_TIMEOUT_SECONDS",
        str(
            int(os.environ.get("CHUMMER_RELEASE_READY_TIMEOUT_SECONDS", "3600"))
            + int(os.environ.get("CHUMMER_RELEASE_READY_TERMINATION_GRACE_SECONDS", "10"))
            + 60
        ),
    )
)
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
    "flagship_product_readiness",
    "public_edge_postdeploy_gate",
    "teable_important_work",
    "blazor_execution_horizon_bridge",
    "ltd_optimization_stack",
    "external_distribution_mirror_proof",
    "public_copy_leak_gate",
    "participate_billing_honesty",
    "account_handoff_runtime_config",
    "google_oauth_linking_proof",
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
    "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_install_boundary.v2",
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
        "manifest_start_url": "/mobile/player",
        "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
        "frontdoor_default": True,
    },
    "GameMaster": {
        "mode": "gm",
        "route": "/mobile/gm",
        "manifest_path": "/manifest.gm.webmanifest",
        "manifest_id": "/mobile/gm",
        "manifest_start_url": "/mobile/gm",
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
    "Player": ("/manifest.player.webmanifest", "/mobile/player", "/mobile/player"),
    "GameMaster": ("/manifest.gm.webmanifest", "/mobile/gm", "/mobile/gm"),
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
    "flagship_product_readiness": PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS.generated.json",
    "public_edge_postdeploy_gate": PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
    "teable_important_work": PUBLISHED_ROOT / "TEABLE_IMPORTANT_WORK.generated.json",
    "blazor_execution_horizon_bridge": PUBLISHED_ROOT / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
    "icanpreneur_discovery_lane": PUBLISHED_ROOT / "ICANPRENEUR_DISCOVERY_LANE.generated.json",
    "ltd_optimization_stack": PUBLISHED_ROOT / "LTD_OPTIMIZATION_STACK.generated.json",
    "external_distribution_mirror_proof": PUBLISHED_ROOT / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json",
    "public_copy_leak_gate": PUBLISHED_ROOT / "PUBLIC_COPY_LEAK_GATE.generated.json",
    "participate_billing_honesty": PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json",
    "account_handoff_runtime_config": PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json",
    "google_oauth_linking_proof": PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
    "premium_ui_design_exit_gate": PUBLISHED_ROOT / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json",
    "design_quality_gate": PUBLISHED_ROOT / "DESIGN_QUALITY_GATE.generated.json",
    "windows_installer_visual_audit": PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    "ui_layout_exit_gate": UI_LAYOUT_COMPLETION_ROOT / "UI_LAYOUT_EXIT_GATE.generated.json",
    "operator_release_dashboard": PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json",
    "release_ready": PUBLISHED_ROOT / "RELEASE_READY.generated.json",
}
BLAZOR_PUBLIC_ENTRY_CHECK_IDS = (
    "postdeployContract",
    "postdeployPass",
    "postdeployNoFailures",
    "canonicalBaseUrl",
    "browserProofsPass",
    "frontdoorProofPass",
    "frontdoorContractV2",
    "installContractSatisfied",
    "publicInstallTargets",
    "installOnlyBoundary",
    "privateRuntimeAbsent",
    "proofClosurePass",
)
BLAZOR_PUBLIC_ENTRY_CONTRACT = "chummer.mobile_pwa_frontdoor_install_entry.v2"
BLAZOR_MOBILE_SOURCE_CONTRACT = "chummer.mobile_pwa_public_projection.v2"
BLAZOR_PUBLIC_INSTALL_TARGETS = ["/build", "/mobile/player"]
BLAZOR_MOBILE_BASE_CHECK_IDS = (
    "exactContract",
    "passingStatus",
    "noFailures",
    "recognizedMode",
    "staticAssetsPass",
)
BLAZOR_MOBILE_MODE_CHECK_IDS = {
    "source": BLAZOR_MOBILE_BASE_CHECK_IDS
    + (
        "sourceTopologyClosed",
        "sourceGatewayClosed",
        "sourceReadinessCombined",
        "sourceInstallOnlyRoleShell",
        "sourceRetiredEnvAbsent",
    ),
    "live": BLAZOR_MOBILE_BASE_CHECK_IDS
    + (
        "liveBaseUrl",
        "liveReadinessConsistent",
        "liveRoleProbesComplete",
        "liveRoleProbesPass",
    ),
}

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
    ["python3", "scripts/verify_flagship_product_readiness_gate.py"],
    [
        "python3",
        "scripts/verify_public_edge_postdeploy_gate.py",
        "--base-url",
        DEFAULT_BASE_URL,
        *PUBLIC_EDGE_POSTDEPLOY_PREFLIGHT_ARGS,
        "--require-downloads-status-playwright",
        "--require-mobile-pwa-viewport-playwright",
        "--require-pwa-offline-cache-playwright",
        "--require-blazor-new-runner-menu-playwright",
        "--require-frontdoor-navigation-playwright",
        "--reuse-existing-playwright-artifacts",
        "--reuse-artifact-max-age-hours",
        str(RECRAWL_MAX_AGE_HOURS),
        "--playwright-artifact-dir",
        str(PUBLIC_EDGE_DOWNLOADS_STATUS_ARTIFACT_DIR),
        "--mobile-pwa-viewport-artifact-dir",
        str(PUBLIC_EDGE_MOBILE_VIEWPORT_ARTIFACT_DIR),
        "--pwa-offline-cache-artifact-dir",
        str(PUBLIC_EDGE_OFFLINE_CACHE_ARTIFACT_DIR),
        "--blazor-new-runner-menu-artifact-dir",
        str(PUBLIC_EDGE_BLAZOR_NEW_RUNNER_ARTIFACT_DIR),
        "--frontdoor-navigation-artifact-dir",
        str(PUBLIC_EDGE_FRONTDOOR_ARTIFACT_DIR),
        "--output",
        str(PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"),
    ],
    ["python3", "scripts/sync_important_work_to_teable.py", "--sync"],
    ["python3", "scripts/verify_mobile_pwa_public_projection.py"],
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
    [
        "python3",
        "scripts/verify_premium_ui_design_exit_gate.py",
        "--completion-dir",
        str(UI_LAYOUT_COMPLETION_ROOT),
    ],
    ["python3", "scripts/materialize_design_quality_gate.py"],
    ["python3", "scripts/verify_windows_installer_visual_audit.py"],
    [
        "python3",
        "scripts/materialize_windows_installer_visual_audit_intake_request.py",
        "--output",
        str(PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
    ],
    [
        "python3",
        "scripts/auto_import_windows_installer_gold_proof.py",
        "--intake-request",
        str(PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
        "--output",
        str(PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"),
        "--wait-seconds",
        "0",
    ],
    [
        "python3",
        "scripts/materialize_google_oauth_linking_operator_evidence_request.py",
        "--base-url",
        DEFAULT_BASE_URL,
        "--output",
        str(PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"),
        "--evidence-path",
        str(PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"),
    ],
    ["python3", "scripts/verify_google_oauth_linking_operator_evidence_request.py"],
    [
        "python3",
        "scripts/auto_import_google_oauth_linking_operator_evidence.py",
        "--intake-request",
        str(PUBLISHED_ROOT / GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST_NAME),
        "--output",
        str(PUBLISHED_ROOT / GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT_NAME),
        "--wait-seconds",
        "0",
    ],
    ["python3", "scripts/materialize_google_oauth_linking_proof.py", "--base-url", DEFAULT_BASE_URL],
    ["python3", "scripts/verify_google_oauth_linking_proof.py"],
    ["python3", "scripts/materialize_ea_operator_readiness.py"],
    ["python3", "scripts/verify_ea_operator_readiness.py"],
    ["python3", "scripts/materialize_mymedia_public_surface.py"],
    ["python3", "scripts/verify_mymedia_public_surface.py"],
    [
        "python3",
        "scripts/materialize_operator_release_dashboard.py",
        "--release-ready-self-check",
    ],
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
    source_contract = proof.get("source_contract") if isinstance(proof.get("source_contract"), dict) else {}
    source_checks = source_contract.get("checks") if isinstance(source_contract.get("checks"), dict) else {}
    source_mode = source_contract.get("mode")
    expected_source_checks = BLAZOR_MOBILE_MODE_CHECK_IDS.get(source_mode, ())
    checks = public_entry.get("checks") if isinstance(public_entry.get("checks"), dict) else {}
    check_summary = {
        check_id: {
            "present": check_id in checks,
            "pass": checks.get(check_id) is True,
        }
        for check_id in BLAZOR_PUBLIC_ENTRY_CHECK_IDS
    }
    holds = (
        proof.get("pass") is True
        and proof.get("base_url") == DEFAULT_BASE_URL
        and source_contract.get("pass") is True
        and source_contract.get("contractName") == BLAZOR_MOBILE_SOURCE_CONTRACT
        and bool(expected_source_checks)
        and set(source_checks) == set(expected_source_checks)
        and all(source_checks.get(check_id) is True for check_id in expected_source_checks)
        and public_entry.get("contract_name") == BLAZOR_PUBLIC_ENTRY_CONTRACT
        and public_entry.get("public_install_targets") == BLAZOR_PUBLIC_INSTALL_TARGETS
        and public_entry.get("build_target") == "/build"
        and public_entry.get("play_target") == "/mobile/player"
        and public_entry.get("play_surface") == "install-only"
        and public_entry.get("play_authority") == "none"
        and public_entry.get("live_session") == "unavailable"
        and public_entry.get("pwa_manifest_path") == "/manifest.player.webmanifest"
        and public_entry.get("checks_pass") is True
        and set(checks) == set(BLAZOR_PUBLIC_ENTRY_CHECK_IDS)
        and all(item["pass"] for item in check_summary.values())
    )
    return {
        "pass": holds,
        "base_url": proof.get("base_url"),
        "contract_name": public_entry.get("contract_name"),
        "source_contract_pass": source_contract.get("pass") is True,
        "source_contract_name": source_contract.get("contractName"),
        "source_contract_mode": source_contract.get("mode"),
        "public_install_targets": public_entry.get("public_install_targets"),
        "build_target": public_entry.get("build_target"),
        "play_target": public_entry.get("play_target"),
        "play_surface": public_entry.get("play_surface"),
        "play_authority": public_entry.get("play_authority"),
        "live_session": public_entry.get("live_session"),
        "pwa_manifest_path": public_entry.get("pwa_manifest_path"),
        "checks_pass": public_entry.get("checks_pass") is True,
        "checks": check_summary,
    }


def parse_utc_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def materializer_timeout_seconds(command: list[str]) -> int:
    command_text = " ".join(command)
    if "scripts/materialize_participate_billing_honesty.py" in command_text:
        return max(MATERIALIZER_TIMEOUT_SECONDS, PARTICIPATE_BILLING_MATERIALIZER_TIMEOUT_SECONDS)
    if "scripts/verify_black_ledger_live_media_proof.py" in command_text:
        return max(MATERIALIZER_TIMEOUT_SECONDS, BLACK_LEDGER_LIVE_MEDIA_MATERIALIZER_TIMEOUT_SECONDS)
    if "scripts/materialize_release_ready_receipt.py" in command_text:
        return max(MATERIALIZER_TIMEOUT_SECONDS, RELEASE_READY_MATERIALIZER_TIMEOUT_SECONDS)
    return MATERIALIZER_TIMEOUT_SECONDS


def teable_important_work_sync_summary(payload: dict[str, Any]) -> dict[str, Any]:
    sync = payload.get("sync") if isinstance(payload.get("sync"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    try:
        row_count = int(payload.get("row_count") or 0)
        synced_count = int(sync.get("synced_count") or 0)
        failed_count = int(sync.get("failed_count") or 0)
    except (TypeError, ValueError):
        row_count = 0
        synced_count = 0
        failed_count = 1
    summary = {
        "contract_name": payload.get("contract_name"),
        "row_count": row_count,
        "rows_count": len(rows),
        "table_name": payload.get("table_name"),
        "sync_state": sync.get("state"),
        "sync_attempted": sync.get("attempted") is True,
        "synced_count": synced_count,
        "failed_count": failed_count,
        "created_count": sync.get("created_count"),
        "updated_count": sync.get("updated_count"),
    }
    summary["pass"] = (
        summary["contract_name"] == "chummer.teable_important_work.v1"
        and row_count > 0
        and len(rows) == row_count
        and summary["sync_state"] == "passed"
        and summary["sync_attempted"]
        and synced_count == row_count
        and failed_count == 0
    )
    return summary


def int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def auto_import_failure_fields(auto_import_payload: dict[str, Any]) -> dict[str, Any]:
    failure = auto_import_payload.get("import_failure")
    failure = dict(failure) if isinstance(failure, dict) else {}
    return {
        "auto_import_import_failure": failure,
        "auto_import_import_failure_type": str(failure.get("type") or "").strip(),
        "auto_import_import_failure_message": str(failure.get("message") or "").strip(),
        "auto_import_import_failure_code": failure.get("code") if failure else None,
        "auto_import_import_failure_summary": str(auto_import_payload.get("summary") or "").strip(),
    }


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def route_from_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme and not parsed.netloc:
        return text
    route = parsed.path or "/"
    return route + (f"?{parsed.query}" if parsed.query else "")


def nonempty_string_list(value: object) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def windows_visual_root_blocker_summary(payload: dict[str, Any]) -> str:
    startup = payload.get("startupReceipt") if isinstance(payload.get("startupReceipt"), dict) else {}
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    startup_digest = normalized_token(str(startup.get("artifactDigest") or "").removeprefix("sha256:"))
    startup_matches_promoted = startup.get("artifactDigestMatchesPromoted")
    if not isinstance(startup_matches_promoted, bool):
        startup_matches_promoted = bool(startup_digest and startup_digest == normalized_token(artifact.get("sha256")))
    startup_confirmed = (
        normalized_token(startup.get("status")) == "pass"
        and bool(startup_matches_promoted)
        and normalized_token(startup.get("verificationDisposition")) != "incompatible_host"
        and normalized_token(startup.get("skipClass")) != "incompatible_host"
    )
    if startup_confirmed:
        return (
            "Native Windows installer execution is confirmed, but the matching visual proof is still missing or mismatched for the promoted bytes."
        )
    return "Native Windows installer visual proof is still missing or mismatched for the promoted bytes."


def first_candidate_path(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return paths[0] if paths else None


def blazor_play_surface_horizon_summary(payload: dict[str, Any]) -> dict[str, Any]:
    horizons_payload = payload.get("horizons") if isinstance(payload.get("horizons"), list) else []
    horizons: list[dict[str, str]] = []
    mid_term_server_bound_boundaries: list[str] = []
    long_term_unproven_claims: list[str] = []
    for row in horizons_payload:
        if not isinstance(row, dict):
            continue
        horizon_id = str(row.get("id") or "").strip()
        if not horizon_id:
            continue
        horizons.append(
            {
                "id": horizon_id,
                "title": str(row.get("title") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "evidence_tier": str(row.get("evidence_tier") or "").strip(),
            }
        )
        if horizon_id == "mid_term_pwa_session_utility":
            mid_term_server_bound_boundaries = normalized_string_list(row.get("server_bound_boundaries"))
        if horizon_id == "long_term_living_world_expansion":
            long_term_unproven_claims = normalized_string_list(row.get("unproven_claims"))

    return {
        "status": str(payload.get("status") or "").strip(),
        "contract_name": str(payload.get("contract_name") or "").strip(),
        "horizons": horizons,
        "mid_term_server_bound_boundaries": mid_term_server_bound_boundaries,
        "long_term_unproven_claims": long_term_unproven_claims,
    }


def release_blocker_local_surface_status(required_gates: dict[str, Any]) -> dict[str, Any]:
    surface_checks: list[dict[str, Any]] = []
    for name in ROOT_BLOCKER_LOCAL_SURFACE_GATES:
        gate = required_gates.get(name)
        if not isinstance(gate, dict):
            continue
        effective_pass = bool(gate.get("pass"))
        derived_root_cause = ""
        if name == "public_edge_postdeploy_gate":
            blocker_class = str(gate.get("release_truth_runtime_blocker_class") or "").strip()
            if not effective_pass and blocker_class == "deployment_activation_proof_required":
                derived_root_cause = blocker_class
            alignment_failures = normalized_string_list(gate.get("releaseChannelAlignmentFailures"))
            if not alignment_failures:
                summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
                alignment_failures = normalized_string_list(summary.get("release_channel_alignment_failures"))
            observed_failures = normalized_string_list(gate.get("failures")) or normalized_string_list(
                gate.get("semanticFailures")
            )
            if (
                not effective_pass
                and not derived_root_cause
                and alignment_failures
                and observed_failures
                and all(item in alignment_failures for item in observed_failures)
            ):
                effective_pass = True
                derived_root_cause = "release_lane_posture"
        surface_checks.append(
            {
                "name": name,
                "status": str(gate.get("status") or "missing").strip() or "missing",
                "pass": effective_pass,
                "derived_root_cause": derived_root_cause,
            }
        )
    return {
        "checks": surface_checks,
        "all_passing": bool(surface_checks) and all(item.get("pass") for item in surface_checks),
    }


def final_gold_root_blocker_families(
    required_gates: dict[str, Any],
    root_release_blockers: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    families: list[dict[str, Any]] = []
    local_surface_status = release_blocker_local_surface_status(required_gates)
    release_posture_blocker = root_release_blocker_entry(
        root_release_blockers if isinstance(root_release_blockers, dict) else {},
        "release_posture:non_flagship_channel",
    )

    release_lane_details: list[str] = []
    flagship_summary = (
        required_gates.get("flagship_product_readiness", {}).get("summary")
        if isinstance(required_gates.get("flagship_product_readiness"), dict)
        else {}
    )
    if isinstance(flagship_summary, dict):
        for blocker in normalized_string_list(flagship_summary.get("launch_critical_nested_blockers")):
            if blocker.startswith("release channel "):
                release_lane_details.append(blocker)
    release_ready_gate = required_gates.get("release_ready")
    if isinstance(release_ready_gate, dict):
        for failure in normalized_string_list(release_ready_gate.get("failures")):
            if failure.startswith("FAIL release_channel: "):
                detail = failure.replace("FAIL release_channel: ", "", 1).strip()
                if detail and detail not in release_lane_details:
                    release_lane_details.append(detail)
    if release_lane_details:
        families.append(
            {
                "id": "release_lane_posture",
                "kind": "release_lane",
                "summary": "Live release channel is not yet on a flagship stable lane.",
                "blocking_checks": ["flagship_product_readiness", "release_ready", "operator_release_dashboard"],
                "details": release_lane_details,
                "stable_promotion_command": str(release_posture_blocker.get("stable_promotion_command") or "").strip(),
                "post_promotion_verify_command": str(
                    release_posture_blocker.get("post_promotion_verify_command") or ""
                ).strip(),
                "operator_action_required": False,
                "local_surface_regression": False,
            }
        )

    public_edge_gate = required_gates.get("public_edge_postdeploy_gate")
    public_edge_blocker_class = str(
        public_edge_gate.get("release_truth_runtime_blocker_class")
        if isinstance(public_edge_gate, dict)
        else ""
    ).strip()
    if (
        isinstance(public_edge_gate, dict)
        and not public_edge_gate.get("pass")
        and public_edge_blocker_class == "deployment_activation_proof_required"
    ):
        canonical_blocker = root_release_blocker_entry(
            root_release_blockers if isinstance(root_release_blockers, dict) else {},
            "release_truth:public_edge_postdeploy_gate",
        )
        staged_overlay = public_edge_gate.get("release_truth_staged_overlay_observation")
        staged_overlay = staged_overlay if isinstance(staged_overlay, dict) else {}
        details = normalized_string_list(public_edge_gate.get("release_truth_runtime_failures"))
        families.append(
            {
                "id": "public_edge_activation_proof",
                "kind": "deployment_activation_proof",
                "summary": (
                    "A hardened current-source overlay is staged and verified, but the mounted public edge "
                    "still uses the legacy active overlay."
                ),
                "blocking_checks": ["public_edge_postdeploy_gate", "release_ready"],
                "details": details,
                "blocker_class": public_edge_blocker_class,
                "active_root": str(public_edge_gate.get("release_truth_runtime_overlay_root") or "").strip(),
                "staging_root": str(staged_overlay.get("staging_root") or "").strip(),
                "staged_overlay_receipt_path": str(staged_overlay.get("receipt_path") or "").strip(),
                "staged_overlay_status": str(staged_overlay.get("status") or "").strip(),
                "activation_transaction_journal_path": str(
                    staged_overlay.get("activation_transaction_journal_path") or ""
                ).strip(),
                "activation_transaction_journal_exists": staged_overlay.get(
                    "activation_transaction_journal_exists"
                ),
                "external_prerequisite": str(canonical_blocker.get("external_prerequisite") or "").strip(),
                "verify_command": str(canonical_blocker.get("verify_command") or "").strip(),
                "activation_authority_required": True,
                "post_activation_proof_required": True,
                "operator_action_required": True,
                "local_surface_regression": False,
            }
        )

    google_gate = required_gates.get("google_oauth_linking_proof")
    google_request = (
        google_gate.get("operator_request_artifacts")
        if isinstance(google_gate, dict) and isinstance(google_gate.get("operator_request_artifacts"), dict)
        else {}
    )
    google_details = [
        detail
        for detail in normalized_string_list(google_gate.get("failures") if isinstance(google_gate, dict) else [])
        if "google oauth operator evidence" in detail.lower()
            or "operator_end_to_end_evidence" in detail.lower()
    ]
    if google_details:
        families.append(
            {
                "id": "google_oauth_operator_evidence",
                "kind": "external_operator_evidence",
                "summary": "Browser-backed Google OAuth linking evidence is still missing.",
                "blocking_checks": ["google_oauth_linking_proof", "flagship_product_readiness", "release_ready"],
                "details": google_details,
                "required_path": str(google_request.get("required_operator_evidence_path") or "").strip(),
                "preferred_drop_path": str(google_request.get("preferred_drop_path") or "").strip(),
                "operator_action_required": True,
                "local_surface_regression": False,
            }
        )

    if not IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        windows_gate = required_gates.get("windows_installer_visual_audit")
        windows_request = (
            windows_gate.get("operator_request_artifacts")
            if isinstance(windows_gate, dict) and isinstance(windows_gate.get("operator_request_artifacts"), dict)
            else {}
        )
        windows_details = [
            detail
            for detail in normalized_string_list(windows_gate.get("failures") if isinstance(windows_gate, dict) else [])
            if "windows installer visual audit source" in detail.lower()
            or "windows installer gold proof artifact is still missing" in detail.lower()
            or "windows installer visual audit source digest does not match promoted installer" in detail.lower()
        ]
        if windows_details:
            families.append(
                {
                    "id": "windows_native_visual_proof",
                    "kind": "external_native_visual_proof",
                    "summary": windows_visual_root_blocker_summary(windows_gate if isinstance(windows_gate, dict) else {}),
                    "blocking_checks": [
                        "windows_installer_visual_audit",
                        "flagship_product_readiness",
                        "release_ready",
                    ],
                    "details": windows_details,
                    "required_path": str(windows_request.get("preferred_drop_path") or "").strip(),
                    "preferred_drop_path": str(windows_request.get("preferred_drop_path") or "").strip(),
                    "operator_action_required": True,
                    "local_surface_regression": False,
                }
            )

    local_surface_failures = [
        item["name"]
        for item in local_surface_status.get("checks", [])
        if isinstance(item, dict) and not item.get("pass") and not item.get("derived_root_cause")
    ]
    if local_surface_failures:
        families.append(
            {
                "id": "local_surface_regressions",
                "kind": "local_surface",
                "summary": "At least one flagship public-surface proof is failing locally.",
                "blocking_checks": local_surface_failures,
                "details": local_surface_failures,
                "operator_action_required": False,
                "local_surface_regression": True,
            }
        )

    return families, local_surface_status


def append_unique_failure(target: dict[str, Any], message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    failures = target.setdefault("failures", [])
    if not isinstance(failures, list):
        return
    if text not in failures:
        failures.append(text)


def append_unique_advisory_action(target: dict[str, Any], message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    advisories = target.setdefault("advisoryActions", [])
    if not isinstance(advisories, list):
        return
    if text not in advisories:
        advisories.append(text)


def public_edge_release_truth_state(snapshot: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    release_truth = snapshot.get("release_truth")
    if not isinstance(release_truth, dict):
        return {}
    state = release_truth.get("public_edge_postdeploy_gate")
    if not isinstance(state, dict):
        return {}
    state_path = str(state.get("path") or "").strip()
    if state_path and Path(state_path).resolve() != receipt_path.resolve():
        return {}
    return state


def public_edge_release_truth_runtime_failures(state: dict[str, Any]) -> list[str]:
    if state.get("runtime_override_applied") is not True:
        return []

    runtime_observation = state.get("runtime_observation")
    runtime_observation = runtime_observation if isinstance(runtime_observation, dict) else {}
    failures: list[str] = []
    verdict = str(state.get("verdict") or "").strip()
    if verdict:
        failures.append(f"public_edge_postdeploy_gate release truth verdict is {verdict}")
    override_reason = str(
        state.get("runtime_override_reason")
        or runtime_observation.get("summary")
        or ""
    ).strip()
    if override_reason:
        failures.append(override_reason)
    failures.extend(normalized_string_list(runtime_observation.get("blocking_findings")))

    deduped: list[str] = []
    seen: set[str] = set()
    for failure in failures:
        if failure in seen:
            continue
        seen.add(failure)
        deduped.append(failure)
    return deduped


def dashboard_required_check_contradictions(check: dict[str, Any]) -> list[str]:
    check_status = str(check.get("status") or "").strip().lower()
    check_pass = (
        check.get("pass") is True
        or (
            check.get("pass") is not False
            and check_status in {"pass", "passed", "ready", "published"}
        )
    )
    if not check_pass:
        return []

    contradictions: list[str] = []
    for field, label in (
        ("failures", "failures"),
        ("failed_gates", "failed gates"),
        ("semanticFailures", "semantic failures"),
        ("nextActions", "next actions"),
    ):
        if nonempty_string_list(check.get(field)):
            contradictions.append(label)
    return contradictions


def operator_dashboard_release_channel_failures(check: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    summary = check.get("summary") if isinstance(check.get("summary"), dict) else {}
    status = str(summary.get("status") or "").strip().lower()
    channel = str(check.get("channel") or summary.get("channel") or "").strip().lower()
    supportability_state = str(check.get("supportability_state") or summary.get("supportability_state") or "").strip().lower()
    rollout_state = str(check.get("rollout_state") or summary.get("rollout_state") or "").strip().lower()
    semantic_failures = check.get("semantic_failures")
    if not isinstance(semantic_failures, list):
        semantic_failures = summary.get("semantic_failures")

    if status != "published":
        failures.append("operator dashboard release_channel status is not published")
    if channel and channel not in RELEASE_CHANNEL_STABLE_CHANNELS:
        failures.append(f"operator dashboard release_channel channel is {channel}, not a flagship stable lane")
    if supportability_state != RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE:
        failures.append("operator dashboard release_channel supportability is not gold_supported")
    if rollout_state in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        failures.append(f"operator dashboard release_channel rollout is blocking: {rollout_state}")
    elif rollout_state and rollout_state != RELEASE_CHANNEL_PUBLIC_STABLE_ROLLOUT_STATE:
        failures.append(f"operator dashboard release_channel rollout is {rollout_state}, not public_stable")
    if not isinstance(semantic_failures, list):
        failures.append("operator dashboard release_channel semantic_failures is missing")
    elif semantic_failures:
        failures.extend(str(item) for item in semantic_failures if str(item).strip())
    return failures


def live_surface_parity_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    release_posture = payload.get("release_posture") if isinstance(payload.get("release_posture"), dict) else {}
    if not release_posture:
        return ["live_surface_parity release_posture is missing"]

    expected_failures = release_posture.get("expected_failures")
    if not isinstance(expected_failures, list):
        failures.append("live_surface_parity release_posture expected_failures is missing")
    elif expected_failures:
        failures.extend(str(item) for item in expected_failures if str(item).strip())

    for field, message in (
        ("status_matches_expected", "live_surface_parity release status does not match expected release channel"),
        ("version_matches_expected", "live_surface_parity release version does not match expected release channel"),
        ("channel_matches_expected", "live_surface_parity release channel does not match expected release channel"),
        ("supportability_matches_expected", "live_surface_parity release supportability does not match expected release channel"),
        ("rollout_matches_expected", "live_surface_parity release rollout does not match expected release channel"),
    ):
        if release_posture.get(field) is not True:
            failures.append(message)

    for field in (
        "expected_status",
        "expected_version",
        "expected_channel",
        "expected_supportability_state",
        "expected_rollout_state",
    ):
        if not str(release_posture.get(field) or "").strip():
            failures.append(f"live_surface_parity release_posture {field} is missing")

    expected_status = str(release_posture.get("expected_status") or "").strip().lower()
    expected_channel = str(release_posture.get("expected_channel") or "").strip().lower()
    expected_supportability_state = str(release_posture.get("expected_supportability_state") or "").strip().lower()
    expected_rollout_state = str(release_posture.get("expected_rollout_state") or "").strip().lower()
    if expected_status and expected_status != "published":
        failures.append("live_surface_parity expected release status is not published")
    if expected_channel and expected_channel not in RELEASE_CHANNEL_STABLE_CHANNELS:
        failures.append(f"live_surface_parity expected release channel is {expected_channel}, not a flagship stable lane")
    if expected_supportability_state and expected_supportability_state != RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE:
        failures.append("live_surface_parity expected release supportability is not gold_supported")
    if expected_rollout_state and expected_rollout_state in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        failures.append(f"live_surface_parity expected release rollout is blocking: {expected_rollout_state}")
    elif expected_rollout_state and expected_rollout_state != RELEASE_CHANNEL_PUBLIC_STABLE_ROLLOUT_STATE:
        failures.append(f"live_surface_parity expected release rollout is {expected_rollout_state}, not public_stable")

    return failures


def contains_tokens(value: object, required_tokens: set[str]) -> bool:
    normalized = str(value or "").lower()
    return all(token in normalized for token in required_tokens)


def supportability_state_supported_for_channel(channel: object, supportability_state: object) -> bool:
    normalized_channel = str(channel or "").strip().lower()
    normalized_state = str(supportability_state or "").strip().lower()
    if normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS:
        return normalized_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
    if normalized_channel == "preview":
        return normalized_state in {
            RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE,
            RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE,
        }
    return bool(normalized_state)


def release_channel_from_operator_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    release_channel_check = checks.get("release_channel") if isinstance(checks.get("release_channel"), dict) else {}
    summary = release_channel_check.get("summary") if isinstance(release_channel_check.get("summary"), dict) else {}
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}

    status = str(release_channel_check.get("status") or summary.get("status") or "").strip()
    version = str(release_channel_check.get("version") or summary.get("version") or release.get("version") or "").strip()
    channel = str(release_channel_check.get("channel") or summary.get("channel") or release.get("channel") or "").strip()
    supportability_state = str(
        release_channel_check.get("supportability_state")
        or summary.get("supportability_state")
        or release.get("supportability_state")
        or ""
    ).strip()
    rollout_state = str(
        release_channel_check.get("rollout_state")
        or summary.get("rollout_state")
        or release.get("rollout_state")
        or ""
    ).strip()

    if not any((status, version, channel, supportability_state, rollout_state)):
        return {}

    synthesized = {
        "status": status,
        "version": version,
        "channel": channel,
        "supportabilityState": supportability_state,
        "rolloutState": rollout_state,
    }
    generated_at = str(payload.get("generated_at_utc") or "").strip()
    if generated_at:
        synthesized["generated_at_utc"] = generated_at
    return synthesized


def public_edge_postdeploy_release_channel_alignment_failures(
    payload: dict[str, Any],
    release_channel: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    canonical_release_channel = lambda value: "stable_lane" if normalized_token(value) in RELEASE_CHANNEL_STABLE_CHANNELS else normalized_token(value)
    authoritative_version = str(release_channel.get("version") or "").strip()
    authoritative_channel = str(release_channel.get("channel") or release_channel.get("channelId") or "").strip()
    authoritative_supportability = str(release_channel.get("supportabilityState") or "").strip()
    authoritative_rollout = str(release_channel.get("rolloutState") or "").strip()

    expected_version = str(payload.get("expectedReleaseVersion") or "").strip()
    manifest_version = str(payload.get("releaseManifestVersion") or "").strip()
    expected_channel = str(payload.get("expectedReleaseChannel") or "").strip()
    manifest_channel = str(payload.get("releaseManifestChannel") or "").strip()
    expected_supportability = str(payload.get("expectedReleaseSupportabilityState") or "").strip()
    manifest_supportability = str(payload.get("releaseManifestSupportabilityState") or "").strip()
    expected_rollout = str(payload.get("expectedReleaseRolloutState") or "").strip()
    manifest_rollout = str(payload.get("releaseManifestRolloutState") or "").strip()

    if authoritative_version:
        if expected_version and expected_version != authoritative_version:
            failures.append("public-edge postdeploy expected release version does not match current release channel version")
        if manifest_version and manifest_version != authoritative_version:
            failures.append("public-edge postdeploy release manifest version does not match current release channel version")
    if authoritative_channel:
        if expected_channel and canonical_release_channel(expected_channel) != canonical_release_channel(authoritative_channel):
            failures.append("public-edge postdeploy expected release channel does not match current release channel")
        if manifest_channel and canonical_release_channel(manifest_channel) != canonical_release_channel(authoritative_channel):
            failures.append("public-edge postdeploy release manifest channel does not match current release channel")
    if authoritative_supportability:
        if expected_supportability and normalized_token(expected_supportability) != normalized_token(authoritative_supportability):
            failures.append("public-edge postdeploy expected release supportability does not match current release channel")
        if manifest_supportability and normalized_token(manifest_supportability) != normalized_token(authoritative_supportability):
            failures.append("public-edge postdeploy release manifest supportability does not match current release channel")
    if authoritative_rollout:
        if expected_rollout and normalized_token(expected_rollout) != normalized_token(authoritative_rollout):
            failures.append("public-edge postdeploy expected release rollout does not match current release channel")
        if manifest_rollout and normalized_token(manifest_rollout) != normalized_token(authoritative_rollout):
            failures.append("public-edge postdeploy release manifest rollout does not match current release channel")
    return failures


def public_edge_postdeploy_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    frontdoor_homepage_lane_disclosure_missing = public_edge_postdeploy_homepage_lane_disclosure_missing(payload)
    frontdoor_homepage_lane_copy_mismatch = public_edge_postdeploy_homepage_lane_copy_mismatch(payload)
    for field in sorted(PUBLIC_EDGE_REQUIRED_RELEASE_STATUS_FIELDS):
        if frontdoor_homepage_lane_disclosure_missing and field == "frontdoorNavigationStatus":
            continue
        if str(payload.get(field) or "").strip().lower() != "pass":
            failures.append(f"public-edge postdeploy {field} is not pass")
    if payload.get("downloadsHasMarker") is not True:
        failures.append("public-edge postdeploy downloads marker is not proven")
    if payload.get("statusRedirectHasMarker") is not True:
        failures.append("public-edge postdeploy status redirect marker is not proven")
    if not str(payload.get("statusRedirectHeading") or "").strip():
        failures.append("public-edge postdeploy status redirect heading is not proven")
    if payload.get("statusRedirectHeadingRecognized") is not True:
        failures.append("public-edge postdeploy status redirect heading is not a recognized release-status decision")
    if payload.get("statusRedirectHeadingUsesGenericUpdatedCopy") is True:
        failures.append("public-edge postdeploy status redirect still uses the stale generic Updated heading")
    if str(payload.get("statusRedirectHeadingExpected") or "").strip() and payload.get("statusRedirectHeadingMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy status redirect heading does not match release posture")
    if not str(payload.get("visibleVersion") or "").strip().startswith("Version "):
        failures.append("public-edge postdeploy visible Version text is not proven")
    if not str(payload.get("statusRedirectVersion") or "").strip().startswith("Version "):
        failures.append("public-edge postdeploy status redirect Version text is not proven")
    expected_release_version = str(payload.get("expectedReleaseVersion") or "").strip()
    expected_visible_versions = expected_visible_version_candidates(
        expected_release_version,
        str(payload.get("expectedReleaseStatus") or "").strip(),
        str(payload.get("expectedReleaseChannel") or "").strip(),
        str(payload.get("expectedReleaseSupportabilityState") or "").strip(),
        str(payload.get("expectedReleaseRolloutState") or "").strip(),
    )
    if not expected_release_version:
        failures.append("public-edge postdeploy expected release version is missing")
    if payload.get("visibleVersionMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy visible Version text does not match release channel")
    if payload.get("statusRedirectVersionMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy status redirect Version text does not match release channel")
    if expected_visible_versions and str(payload.get("visibleVersion") or "").strip() not in expected_visible_versions:
        failures.append("public-edge postdeploy visible Version text does not equal expected release version")
    if expected_visible_versions and str(payload.get("statusRedirectVersion") or "").strip() not in expected_visible_versions:
        failures.append("public-edge postdeploy status redirect Version text does not equal expected release version")
    expected_release_status = str(payload.get("expectedReleaseStatus") or "").strip().lower()
    if not expected_release_status:
        failures.append("public-edge postdeploy expected release status is missing")
    elif expected_release_status != "published":
        failures.append("public-edge postdeploy expected release status is not published")
    expected_release_channel = str(payload.get("expectedReleaseChannel") or "").strip()
    if not expected_release_channel:
        failures.append("public-edge postdeploy expected release channel is missing")
    expected_supportability_state = str(payload.get("expectedReleaseSupportabilityState") or "").strip()
    if not expected_supportability_state:
        failures.append("public-edge postdeploy expected release supportability is missing")
    elif not expected_release_channel:
        failures.append("public-edge postdeploy expected release supportability cannot be evaluated without a channel")
    elif not supportability_state_supported_for_channel(expected_release_channel, expected_supportability_state):
        failures.append("public-edge postdeploy expected release supportability is not supported for expected release channel")
    if not str(payload.get("expectedReleaseRolloutState") or "").strip():
        failures.append("public-edge postdeploy expected release rollout is missing")
    elif str(payload.get("expectedReleaseRolloutState") or "").strip().lower() in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        failures.append(
            "public-edge postdeploy expected release rollout is blocking: "
            + str(payload.get("expectedReleaseRolloutState") or "").strip().lower()
        )
    if payload.get("releaseManifestHttpStatus") != 200:
        failures.append("public-edge postdeploy live release manifest HTTP status is not 200")
    if payload.get("releaseManifestStatusMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy live release manifest status does not match release channel")
    if payload.get("releaseManifestChannelMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy live release manifest channel does not match release channel")
    if payload.get("releaseManifestVersionMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy live release manifest version does not match release channel")
    if payload.get("releaseManifestSupportabilityMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy live release manifest supportability does not match release channel")
    if payload.get("releaseManifestRolloutMatchesReleaseChannel") is not True:
        failures.append("public-edge postdeploy live release manifest rollout does not match release channel")
    if int_value(payload.get("pwaManifestCount")) < PUBLIC_EDGE_REQUIRED_PWA_MANIFEST_COUNT:
        failures.append("public-edge postdeploy PWA manifest count is below required count")
    if int_value(payload.get("rolePwaManifestCount")) < len(PUBLIC_EDGE_REQUIRED_ROLE_PWA_MANIFESTS):
        failures.append("public-edge postdeploy role PWA manifest count is below required count")
    role_manifests = payload.get("rolePwaManifests") if isinstance(payload.get("rolePwaManifests"), list) else []
    role_manifest_by_role = {
        str(entry.get("role") or "").strip(): entry
        for entry in role_manifests
        if isinstance(entry, dict)
    }
    for role, (expected_path, expected_id, expected_start_url) in PUBLIC_EDGE_REQUIRED_ROLE_PWA_MANIFESTS.items():
        manifest = role_manifest_by_role.get(role)
        if not manifest:
            failures.append(f"public-edge postdeploy PWA static proof is missing the {role} role manifest")
            continue
        if str(manifest.get("path") or "").strip() != expected_path:
            failures.append(f"public-edge postdeploy PWA static proof {role} manifest path is not {expected_path}")
        if str(manifest.get("id") or "").strip() != expected_id:
            failures.append(f"public-edge postdeploy PWA static proof {role} manifest id is not {expected_id}")
        if str(manifest.get("start_url") or "").strip() != expected_start_url:
            failures.append(f"public-edge postdeploy PWA static proof {role} manifest start_url is not {expected_start_url}")
        if str(manifest.get("display") or "").strip() != "standalone":
            failures.append(f"public-edge postdeploy PWA static proof {role} manifest display is not standalone")
    if int_value(payload.get("pwaAssetCount")) < PUBLIC_EDGE_MINIMUM_PWA_ASSET_COUNT:
        failures.append("public-edge postdeploy PWA asset count is below required count")
    if payload.get("ledgerStreamNonCacheable") is not True:
        failures.append("public-edge postdeploy ledger stream is not non-cacheable")
    if payload.get("ledgerStreamPrecached") is not False:
        failures.append("public-edge postdeploy ledger stream is precached")
    if payload.get("mobileLedgerPayloadStatus") != "opt_in_required":
        failures.append("public-edge postdeploy mobile ledger payload is not opt_in_required")
    if not contains_tokens(payload.get("mobileLedgerCacheControl"), PUBLIC_EDGE_REQUIRED_LEDGER_CACHE_CONTROL_TOKENS):
        failures.append("public-edge postdeploy mobile ledger cache-control is incomplete")
    if not contains_tokens(payload.get("mobileLedgerVary"), PUBLIC_EDGE_REQUIRED_LEDGER_VARY_TOKENS):
        failures.append("public-edge postdeploy mobile ledger vary is incomplete")

    tool_ids = string_set(payload.get("readyMobileHandoffToolIds"))
    missing_tools = sorted(PUBLIC_EDGE_REQUIRED_READY_MOBILE_TOOLS - tool_ids)
    if missing_tools:
        failures.append("public-edge postdeploy Ready mobile handoff tools are incomplete: " + ", ".join(missing_tools))
    packet_roles = string_set(payload.get("readyMobileHandoffPacketRoles"))
    missing_roles = sorted(PUBLIC_EDGE_REQUIRED_READY_MOBILE_PACKET_ROLES - packet_roles)
    if missing_roles:
        failures.append("public-edge postdeploy Ready mobile handoff packet roles are incomplete: " + ", ".join(missing_roles))
    if str(payload.get("readyMobileHandoffFrontdoorLaunchRoute") or "").strip() != PUBLIC_EDGE_REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE:
        failures.append(
            "public-edge postdeploy Ready mobile handoff frontdoor launch route is not "
            + PUBLIC_EDGE_REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE
        )
    ready_mobile_role_routes = payload.get("readyMobileHandoffRoleRoutes") if isinstance(payload.get("readyMobileHandoffRoleRoutes"), list) else []
    ready_mobile_role_routes_by_role = {
        str(item.get("role") or "").strip(): item
        for item in ready_mobile_role_routes
        if isinstance(item, dict)
    }
    for role_name, expected in PUBLIC_EDGE_REQUIRED_READY_MOBILE_ROLE_ROUTES.items():
        route = ready_mobile_role_routes_by_role.get(role_name)
        if not route:
            failures.append(f"public-edge postdeploy Ready mobile handoff is missing the {role_name} role route")
            continue
        if str(route.get("mode") or "").strip() != expected["mode"]:
            failures.append(f"public-edge postdeploy Ready mobile handoff {role_name} mode is not {expected['mode']}")
        if str(route.get("route") or "").strip() != expected["route"]:
            failures.append(f"public-edge postdeploy Ready mobile handoff {role_name} route is not {expected['route']}")
        if str(route.get("manifest_path") or "").strip() != expected["manifest_path"]:
            failures.append(
                f"public-edge postdeploy Ready mobile handoff {role_name} manifest path is not {expected['manifest_path']}"
            )
        if str(route.get("manifest_id") or "").strip() != expected["manifest_id"]:
            failures.append(
                f"public-edge postdeploy Ready mobile handoff {role_name} manifest id is not {expected['manifest_id']}"
            )
        if str(route.get("manifest_start_url") or "").strip() != expected["manifest_start_url"]:
            failures.append(
                "public-edge postdeploy Ready mobile handoff "
                f"{role_name} manifest start_url is not {expected['manifest_start_url']}"
            )
        if (
            str(route.get("session_handoff_route_template") or "").strip()
            != expected["session_handoff_route_template"]
        ):
            failures.append(
                "public-edge postdeploy Ready mobile handoff "
                f"{role_name} session handoff route template is not {expected['session_handoff_route_template']}"
            )
        if route.get("frontdoor_default") is not expected["frontdoor_default"]:
            failures.append(
                "public-edge postdeploy Ready mobile handoff "
                f"{role_name} frontdoor_default is not {str(expected['frontdoor_default']).lower()}"
            )

    if int_value(payload.get("mobilePwaViewportRouteCount")) < len(PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES):
        failures.append("public-edge postdeploy mobile PWA viewport route count is below required count")
    missing_mobile_routes = string_set(payload.get("mobilePwaViewportMissingRoutes"))
    if not missing_mobile_routes:
        mobile_routes = string_set(payload.get("mobilePwaViewportRoutes"))
        missing_mobile_routes = PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - mobile_routes
    if missing_mobile_routes:
        failures.append("public-edge postdeploy mobile PWA viewport routes are incomplete: " + ", ".join(sorted(missing_mobile_routes)))
    if int_value(payload.get("mobilePwaViewportViewportCount")) < PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_COUNT:
        failures.append("public-edge postdeploy mobile PWA viewport count is below required count")
    failures.extend(public_edge_v2_offline_failures(payload))
    role_alias_results = payload.get("roleAliasRouteResults") if isinstance(payload.get("roleAliasRouteResults"), list) else []
    role_alias_results_by_alias = {
        str(item.get("aliasPath") or "").strip(): item
        for item in role_alias_results
        if isinstance(item, dict)
    }
    role_alias_drift = payload.get("roleAliasRouteDrift") if isinstance(payload.get("roleAliasRouteDrift"), list) else []
    if role_alias_drift:
        failures.append("public-edge postdeploy role alias routes drifted")
    for alias_path, expected_final_route in PUBLIC_EDGE_REQUIRED_ROLE_ALIAS_ROUTES.items():
        result = role_alias_results_by_alias.get(alias_path)
        if not result:
            failures.append(f"public-edge postdeploy {alias_path} alias route proof is missing")
            continue
        final_route = str(result.get("finalRoute") or route_from_url(result.get("finalUrl"))).strip()
        if final_route != expected_final_route or result.get("pass") is not True:
            failures.append(f"public-edge postdeploy {alias_path} resolved to {final_route or '<missing>'} instead of {expected_final_route}")
    if int_value(payload.get("participateIframeRouteCount")) < PUBLIC_EDGE_REQUIRED_PARTICIPATE_IFRAME_ROUTES:
        failures.append("public-edge postdeploy Participate route count is below required count")
    if int_value(payload.get("participateIframeRouteIframeCount")) < PUBLIC_EDGE_REQUIRED_PARTICIPATE_IFRAME_ROUTES:
        failures.append("public-edge postdeploy Participate iframe route count is below required count")
    if int_value(payload.get("participateIframeRouteOfflineFallbackCount")) != 0:
        failures.append("public-edge postdeploy Participate iframe shell is using offline fallback routes")

    if frontdoor_homepage_lane_disclosure_missing:
        failures.append("public-edge postdeploy homepage does not disclose current public lane")
    else:
        if frontdoor_homepage_lane_copy_mismatch:
            failures.append("public-edge postdeploy homepage current public lane copy does not match release posture")
        failures.extend(public_edge_v2_private_identity_failures(payload))
        gated_targets = string_set(payload.get("frontdoorNavigationGatedTargets"))
        public_targets = string_set(payload.get("frontdoorNavigationPublicTargets"))
        play_route = str(payload.get("frontdoorNavigationPlayRoute") or "").strip()
        direct_player_route = str(payload.get("frontdoorNavigationDirectPlayerRoute") or "").strip()
        frontdoor_final_path = ""
        frontdoor_final_url = str(payload.get("frontdoorNavigationFinalUrl") or "").strip()
        if frontdoor_final_url:
            frontdoor_final_path = urlparse(frontdoor_final_url).path
        frontdoor_gm_final_path = ""
        frontdoor_gm_final_url = str(payload.get("frontdoorNavigationGmFinalUrl") or "").strip()
        if frontdoor_gm_final_url:
            frontdoor_gm_final_path = urlparse(frontdoor_gm_final_url).path
        if "Build" not in gated_targets:
            failures.append("public-edge postdeploy front-door navigation does not gate Build")
        if "Build" in public_targets:
            failures.append("public-edge postdeploy front-door navigation exposes Build as public")
        if "Play" not in gated_targets:
            failures.append("public-edge postdeploy front-door navigation does not gate Play")
        if "Play" in public_targets:
            failures.append("public-edge postdeploy front-door navigation exposes Play as public")
        if play_route != "/mobile/player":
            failures.append("public-edge postdeploy front-door navigation Play route is not /mobile/player")
        if str(payload.get("frontdoorNavigationPlaySignInRoute") or "").strip() != "/login?next=%2Fmobile%2Fplayer":
            failures.append("public-edge postdeploy front-door navigation Play sign-in route is not /login?next=%2Fmobile%2Fplayer")
        if direct_player_route != "/mobile/player":
            failures.append("public-edge postdeploy front-door navigation direct player route is not /mobile/player")
        if int_value(payload.get("frontdoorNavigationDirectPlayerHttpStatus")) != 200:
            failures.append("public-edge postdeploy front-door navigation Play launch did not return HTTP 200")
        if frontdoor_final_path != "/mobile/player":
            failures.append("public-edge postdeploy front-door navigation Play launch did not land on /mobile/player")
        if payload.get("frontdoorNavigationLiveTurnCompanionShell") is not True:
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove the live turn companion shell")
        if str(payload.get("frontdoorNavigationPwaManifestPath") or "").strip() != "/manifest.player.webmanifest":
            failures.append("public-edge postdeploy front-door navigation Play launch did not activate the player PWA manifest")
        if str(payload.get("frontdoorNavigationPwaRole") or "").strip() != "Player":
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove the Player role")
        if str(payload.get("frontdoorNavigationBlazorShell") or "").strip() != "interactive-server":
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove the interactive Blazor shell")
        if payload.get("frontdoorNavigationRybbitConfigured") is not True or str(payload.get("frontdoorNavigationRybbitTag") or "").strip() != "mobile_play_shell":
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove the Rybbit mobile shell config")
        if (
            str(payload.get("frontdoorNavigationRybbitRoute") or "").strip() != "/mobile/player"
            or str(payload.get("frontdoorNavigationRybbitMode") or "").strip() != "player"
            or str(payload.get("frontdoorNavigationRybbitRole") or "").strip() != "Player"
        ):
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove the Player Rybbit role config")
        if payload.get("frontdoorNavigationRybbitSiteIdPresent") is not True or payload.get("frontdoorNavigationRybbitScriptUrlAllowed") is not True:
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove the Rybbit provider config")
        if payload.get("frontdoorNavigationRybbitSkipMobilePaths") is not True:
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove Rybbit skips mobile paths")
        if payload.get("frontdoorNavigationRybbitMaskMobilePaths") is not True:
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove Rybbit masks mobile paths")
        if payload.get("frontdoorNavigationRybbitMasksPrivatePlayRoutes") is not True:
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove Rybbit masks private play routes")
        if payload.get("frontdoorNavigationRybbitReplayBlocksTurnRoot") is not True:
            failures.append("public-edge postdeploy front-door navigation Play launch did not prove Rybbit replay blocks turn content")
        if "/mobile/player?" not in str(payload.get("frontdoorNavigationPlayerSessionHandoffUrl") or "").strip():
            failures.append("public-edge postdeploy front-door navigation Player session handoff URL is not a player mobile route")
        if str(payload.get("frontdoorNavigationPlayerSessionHandoffStatus") or "").strip() != "Session handoff is ready in the link above.":
            failures.append("public-edge postdeploy front-door navigation Player session handoff did not expose ready status")
        if str(payload.get("frontdoorNavigationPlayerSessionHandoffLinkText") or "").strip() != "Open session handoff link":
            failures.append("public-edge postdeploy front-door navigation Player session handoff did not relabel the visible route")
        if payload.get("frontdoorNavigationPlayerSessionHandoffPreservesSession") is not True:
            failures.append("public-edge postdeploy front-door navigation Player session handoff did not preserve session id")
        if payload.get("frontdoorNavigationPlayerSessionHandoffPreservesRole") is not True:
            failures.append("public-edge postdeploy front-door navigation Player session handoff did not preserve role")
        if payload.get("frontdoorNavigationPlayerSessionHandoffStripsDevice") is not True:
            failures.append("public-edge postdeploy front-door navigation Player session handoff leaked sender device id")
        if payload.get("frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent") is not True:
            failures.append("public-edge postdeploy front-door navigation Player session handoff did not prove a sender device id was stripped")
        if not str(payload.get("frontdoorNavigationGmRoute") or "").strip().startswith("/mobile/gm"):
            failures.append("public-edge postdeploy front-door navigation GM switch route is not /mobile/gm")
        if int_value(payload.get("frontdoorNavigationGmHttpStatus")) != 200:
            failures.append("public-edge postdeploy front-door navigation GM switch did not return HTTP 200")
        if frontdoor_gm_final_path != "/mobile/gm":
            failures.append("public-edge postdeploy front-door navigation GM switch did not land on /mobile/gm")
        if payload.get("frontdoorNavigationGmLiveTurnCompanionShell") is not True:
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove the live turn companion shell")
        if str(payload.get("frontdoorNavigationGmPwaManifestPath") or "").strip() != "/manifest.gm.webmanifest":
            failures.append("public-edge postdeploy front-door navigation GM switch did not activate the GM PWA manifest")
        if str(payload.get("frontdoorNavigationGmPwaRole") or "").strip() != "GameMaster":
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove the GameMaster role")
        if str(payload.get("frontdoorNavigationGmBlazorShell") or "").strip() != "interactive-server":
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove the interactive Blazor shell")
        if payload.get("frontdoorNavigationGmRybbitConfigured") is not True or str(payload.get("frontdoorNavigationGmRybbitTag") or "").strip() != "mobile_play_shell":
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove the Rybbit mobile shell config")
        if (
            str(payload.get("frontdoorNavigationGmRybbitRoute") or "").strip() != "/mobile/gm"
            or str(payload.get("frontdoorNavigationGmRybbitMode") or "").strip() != "gm"
            or str(payload.get("frontdoorNavigationGmRybbitRole") or "").strip() != "GameMaster"
        ):
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove the GM Rybbit role config")
        if payload.get("frontdoorNavigationGmRybbitSiteIdPresent") is not True or payload.get("frontdoorNavigationGmRybbitScriptUrlAllowed") is not True:
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove the Rybbit provider config")
        if payload.get("frontdoorNavigationGmRybbitSkipMobilePaths") is not True:
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove Rybbit skips mobile paths")
        if payload.get("frontdoorNavigationGmRybbitMaskMobilePaths") is not True:
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove Rybbit masks mobile paths")
        if payload.get("frontdoorNavigationGmRybbitMasksPrivatePlayRoutes") is not True:
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove Rybbit masks private play routes")
        if payload.get("frontdoorNavigationGmRybbitReplayBlocksTurnRoot") is not True:
            failures.append("public-edge postdeploy front-door navigation GM switch did not prove Rybbit replay blocks turn content")
        if "/mobile/gm?" not in str(payload.get("frontdoorNavigationGmSessionHandoffUrl") or "").strip():
            failures.append("public-edge postdeploy front-door navigation GM session handoff URL is not a GM mobile route")
        if str(payload.get("frontdoorNavigationGmSessionHandoffStatus") or "").strip() != "Session handoff is ready in the link above.":
            failures.append("public-edge postdeploy front-door navigation GM session handoff did not expose ready status")
        if str(payload.get("frontdoorNavigationGmSessionHandoffLinkText") or "").strip() != "Open session handoff link":
            failures.append("public-edge postdeploy front-door navigation GM session handoff did not relabel the visible route")
        if payload.get("frontdoorNavigationGmSessionHandoffPreservesSession") is not True:
            failures.append("public-edge postdeploy front-door navigation GM session handoff did not preserve session id")
        if payload.get("frontdoorNavigationGmSessionHandoffPreservesRole") is not True:
            failures.append("public-edge postdeploy front-door navigation GM session handoff did not preserve role")
        if payload.get("frontdoorNavigationGmSessionHandoffStripsDevice") is not True:
            failures.append("public-edge postdeploy front-door navigation GM session handoff leaked sender device id")
        if payload.get("frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent") is not True:
            failures.append("public-edge postdeploy front-door navigation GM session handoff did not prove a sender device id was stripped")
        if payload.get("frontdoorNavigationLedgerPrimary") is not False:
            failures.append("public-edge postdeploy Black Ledger remains primary on the front door")

    core_child_contracts = payload.get("coreChildContracts") if isinstance(payload.get("coreChildContracts"), dict) else {}
    for child, expected_contract in sorted(PUBLIC_EDGE_REQUIRED_CORE_CHILD_CONTRACTS.items()):
        if str(core_child_contracts.get(child) or "").strip() != expected_contract:
            failures.append(f"public-edge postdeploy {child} child contract is not {expected_contract}")
    for field, expected_contract in sorted(PUBLIC_EDGE_REQUIRED_ARTIFACT_CONTRACT_FIELDS.items()):
        if frontdoor_homepage_lane_disclosure_missing and field in PUBLIC_EDGE_FRONTDOOR_ARTIFACT_CONTRACT_FIELDS:
            continue
        if str(payload.get(field) or "").strip() != expected_contract:
            failures.append(f"public-edge postdeploy {field} is not {expected_contract}")
    if public_edge_postdeploy_non_preflight_receipt_failures(payload):
        failures.append("public-edge postdeploy receipt contains failures")
    return failures


def public_edge_postdeploy_receipt_failures(payload: dict[str, Any]) -> list[str]:
    return normalized_string_list(payload.get("failures"))


def public_edge_postdeploy_non_preflight_receipt_failures(payload: dict[str, Any]) -> list[str]:
    return [
        failure
        for failure in public_edge_postdeploy_receipt_failures(payload)
        if "preflight" not in failure.lower()
    ]


def public_edge_postdeploy_homepage_lane_disclosure_missing(payload: dict[str, Any]) -> bool:
    return PUBLIC_EDGE_HOMEPAGE_LANE_DISCLOSURE_RECEIPT_FAILURE in set(
        public_edge_postdeploy_non_preflight_receipt_failures(payload)
    )


def public_edge_postdeploy_homepage_lane_copy_mismatch(payload: dict[str, Any]) -> bool:
    return PUBLIC_EDGE_HOMEPAGE_LANE_COPY_MISMATCH_RECEIPT_FAILURE in set(
        public_edge_postdeploy_non_preflight_receipt_failures(payload)
    )


def release_ready_receipt_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if "returncode" not in payload:
        failures.append("release_ready receipt is missing verifier returncode")
    elif int_value(payload.get("returncode")) != 0:
        failures.append("release_ready verifier returncode is not zero")
    if payload.get("timed_out") is not False:
        failures.append("release_ready verifier timed_out is not false")
    if payload.get("saw_release_ready_marker") is not True:
        failures.append("release_ready receipt did not record RELEASE_READY marker")
    not_ready_markers = payload.get("not_release_ready_markers")
    if isinstance(not_ready_markers, list) and not_ready_markers:
        failures.append("release_ready receipt contains NOT_RELEASE_READY markers")
    receipt_failures = payload.get("failures")
    if isinstance(receipt_failures, list) and receipt_failures:
        failures.append("release_ready receipt contains failures")
    failed_gates = payload.get("failed_gates")
    if isinstance(failed_gates, list) and failed_gates:
        failures.append("release_ready receipt contains failed gates")
    return failures


def normalized_sha(value: object) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def path_exists(path_value: object) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        return Path(text).is_file()
    except OSError:
        return False


def telegram_delivery_receipt_details(receipt_name: object) -> dict[str, Any]:
    normalized_receipt_name = str(receipt_name or "").strip()
    receipt_path = TELEGRAM_TEXT_DELIVERY_ROOT / normalized_receipt_name if normalized_receipt_name else None
    receipt_exists = bool(receipt_path and receipt_path.is_file())
    payload = load_json(receipt_path) if receipt_exists and receipt_path is not None else {}
    return {
        "operator_ask_delivery_receipt_path": str(receipt_path) if receipt_path is not None else "",
        "operator_ask_delivery_receipt_exists": receipt_exists,
        "operator_ask_delivery_status": str(payload.get("status") or "").strip(),
        "operator_ask_delivery_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
        "operator_ask_delivery_message_ids": list(payload.get("message_ids")) if isinstance(payload.get("message_ids"), list) else [],
        "operator_ask_delivery_text_sha256": str(payload.get("text_sha256") or "").strip(),
        "operator_ask_delivery_text_preview": str(payload.get("text_preview") or "").strip(),
    }


def text_sha256(path_value: object) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    try:
        return hashlib.sha256(Path(text).read_bytes()).hexdigest()
    except OSError:
        return ""


def suppress_inactive_operator_request_actions(artifacts: dict[str, Any]) -> dict[str, Any]:
    historical = (
        dict(artifacts.get("operator_action_historical_artifacts"))
        if isinstance(artifacts.get("operator_action_historical_artifacts"), dict)
        else {}
    )
    for field in INACTIVE_OPERATOR_REQUEST_ACTION_FIELDS:
        if field not in artifacts:
            continue
        value = artifacts.get(field)
        if isinstance(value, list):
            if value:
                historical[field] = list(value)
            artifacts[field] = []
            continue
        if isinstance(value, bool):
            if value:
                historical[field] = value
            artifacts[field] = False
            continue
        text = str(value or "").strip()
        if text:
            historical[field] = text
        artifacts[field] = ""
    artifacts["operator_action_historical_only"] = bool(historical)
    if historical:
        artifacts["operator_action_historical_artifacts"] = historical
    return artifacts


def restore_inactive_operator_request_actions(artifacts: dict[str, Any]) -> dict[str, Any]:
    historical = (
        dict(artifacts.get("operator_action_historical_artifacts"))
        if isinstance(artifacts.get("operator_action_historical_artifacts"), dict)
        else {}
    )
    for field in INACTIVE_OPERATOR_REQUEST_ACTION_FIELDS:
        if field not in historical:
            continue
        value = historical.pop(field)
        current = artifacts.get(field)
        if isinstance(value, list):
            if not current:
                artifacts[field] = list(value)
            continue
        if isinstance(value, bool):
            if not current:
                artifacts[field] = value
            continue
        if not str(current or "").strip():
            artifacts[field] = value
    if not str(artifacts.get("operator_ask_delivery_text_preview") or "").strip():
        historical_preview = str(artifacts.get("operator_ask_delivery_historical_text_preview") or "").strip()
        if historical_preview:
            artifacts["operator_ask_delivery_text_preview"] = historical_preview
    artifacts["operator_action_historical_artifacts"] = historical
    artifacts["operator_action_historical_only"] = bool(historical)
    return artifacts


def enrich_operator_ask_delivery_details(artifacts: dict[str, Any]) -> dict[str, Any]:
    delivery_receipt_path = str(artifacts.get("operator_ask_delivery_receipt_path") or "").strip()
    operator_ask_receipt_name = str(artifacts.get("operator_ask_receipt_name") or "").strip()
    if not delivery_receipt_path and operator_ask_receipt_name:
        artifacts.update(telegram_delivery_receipt_details(operator_ask_receipt_name))

    current_text_sha256 = str(artifacts.get("operator_ask_message_sha256") or "").strip()
    if not current_text_sha256:
        current_text_sha256 = text_sha256(artifacts.get("operator_ask_text_path"))
        if current_text_sha256:
            artifacts["operator_ask_message_sha256"] = current_text_sha256

    delivery_text_sha256 = str(artifacts.get("operator_ask_delivery_text_sha256") or "").strip()
    comparable = bool(current_text_sha256 and delivery_text_sha256)
    request_status = str(artifacts.get("request_status") or "").strip()
    effective_request_status = str(
        artifacts.get("request_effective_status")
        or request_status
        or ""
    ).strip()
    matches_current = bool(comparable and current_text_sha256 == delivery_text_sha256)
    explicit_needs_resend = bool(artifacts.get("operator_ask_delivery_needs_resend"))
    needs_resend = bool(
        comparable
        and not matches_current
        and effective_request_status != "not_required"
    )
    if not comparable and explicit_needs_resend and effective_request_status != "not_required":
        needs_resend = True
    if effective_request_status == "not_required":
        historical_preview = str(artifacts.get("operator_ask_delivery_text_preview") or "").strip()
        if historical_preview:
            artifacts["operator_ask_delivery_historical_text_preview"] = historical_preview
            artifacts["operator_ask_delivery_text_preview"] = ""
        suppress_inactive_operator_request_actions(artifacts)
        artifacts["operator_ask_delivery_historical_only"] = True
        comparable = False
        matches_current = False
        needs_resend = False
    else:
        restore_inactive_operator_request_actions(artifacts)
        artifacts["operator_ask_delivery_historical_only"] = False
    artifacts["operator_ask_delivery_current_text_comparable"] = comparable
    artifacts["operator_ask_delivery_matches_current_text"] = matches_current
    artifacts["operator_ask_delivery_needs_resend"] = needs_resend
    send_command = str(artifacts.get("operator_ask_send_command") or "").strip()
    artifacts["operator_ask_resend_command"] = send_command if artifacts["operator_ask_delivery_needs_resend"] else ""
    return artifacts


def refresh_windows_watcher_state(
    watcher_status_command: str,
    watcher_path: Path,
    *,
    refresh_runtime_receipts: bool = True,
) -> tuple[dict[str, Any], str]:
    command_text = str(watcher_status_command or "").strip()
    if refresh_runtime_receipts and command_text:
        try:
            subprocess.run(
                shlex.split(command_text),
                cwd=RUN_SERVICES_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
            pass
    return load_json_with_status(watcher_path)


def refresh_windows_auto_import_state(
    auto_import_command: str,
    auto_import_path: Path,
    *,
    refresh_runtime_receipts: bool = True,
) -> tuple[dict[str, Any], str]:
    command_text = str(auto_import_command or "").strip()
    if refresh_runtime_receipts and command_text:
        try:
            subprocess.run(
                shlex.split(command_text),
                cwd=RUN_SERVICES_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
            pass
    return load_json_with_status(auto_import_path)


def windows_operator_request_artifacts(
    request_path: Path,
    payload: dict[str, Any],
    *,
    refresh_runtime_receipts: bool = True,
    runtime_refresh_authorized: bool = False,
) -> dict[str, Any]:
    operator_draft = payload.get("operator_telegram_draft")
    operator_draft = operator_draft if isinstance(operator_draft, dict) else {}
    artifact_intake = payload.get("artifact_intake")
    artifact_intake = artifact_intake if isinstance(artifact_intake, dict) else {}
    watcher_state_path = str(artifact_intake.get("watcher_state_path") or "").strip()

    operator_ask_text_path = str(
        operator_draft.get("current_message_path")
        or operator_draft.get("message_path")
        or ""
    ).strip()
    operator_ask_metadata_path = str(
        operator_draft.get("current_metadata_path")
        or operator_draft.get("metadata_path")
        or ""
    ).strip()
    operator_ask_receipt_name = str(operator_draft.get("receipt_name") or "").strip()
    delivery_receipt = telegram_delivery_receipt_details(operator_ask_receipt_name)
    artifacts = {
        "request_receipt_path": str(request_path),
        "request_receipt_exists": request_path.is_file(),
        "request_status": str(payload.get("request_status") or payload.get("status") or "").strip(),
        "operator_action_still_required": str(payload.get("request_status") or payload.get("status") or "").strip()
        in {"external_artifact_required", "operator_action_required"},
        "operator_ask_text_path": operator_ask_text_path,
        "operator_ask_text_exists": path_exists(operator_ask_text_path),
        "operator_ask_metadata_path": operator_ask_metadata_path,
        "operator_ask_metadata_exists": path_exists(operator_ask_metadata_path),
        "operator_ask_send_command": str(operator_draft.get("send_command") or "").strip(),
        "operator_ask_receipt_name": operator_ask_receipt_name,
        "operator_ask_message_preview": str(operator_draft.get("message_preview") or "").strip(),
        "operator_ask_message_sha256": str(operator_draft.get("message_sha256") or "").strip(),
        "preferred_drop_path": str(
            payload.get("preferred_drop_path")
            or operator_draft.get("preferred_drop_path")
            or ""
        ).strip(),
        "preferred_drop_path_exists": path_exists(
            payload.get("preferred_drop_path")
            or operator_draft.get("preferred_drop_path")
            or ""
        ),
        "preferred_zip_name": str(
            payload.get("preferred_zip_name")
            or operator_draft.get("preferred_zip_name")
            or ""
        ).strip(),
        "required_zip_filename": str(
            payload.get("required_zip_filename")
            or operator_draft.get("required_zip_filename")
            or ""
        ).strip(),
        "preferred_extracted_visual_dir": str(
            payload.get("preferred_extracted_visual_dir")
            or artifact_intake.get("preferred_extracted_visual_dir")
            or operator_draft.get("preferred_extracted_visual_dir")
            or ""
        ).strip(),
        "preferred_extracted_visual_dir_exists": path_exists(
            payload.get("preferred_extracted_visual_dir")
            or artifact_intake.get("preferred_extracted_visual_dir")
            or operator_draft.get("preferred_extracted_visual_dir")
            or ""
        ),
        "discover_command": str(artifact_intake.get("discover_command") or "").strip(),
        "discover_visual_source_command": str(
            artifact_intake.get("discover_visual_source_command")
            or operator_draft.get("discover_visual_source_command")
            or ""
        ).strip(),
        "import_command": str(artifact_intake.get("import_command") or "").strip(),
        "auto_import_command": str(artifact_intake.get("auto_import_command") or "").strip(),
        "auto_import_watch_command": str(artifact_intake.get("auto_import_watch_command") or "").strip(),
        "watcher_launch_mode": str(artifact_intake.get("watcher_launch_mode") or "").strip(),
        "watcher_state_path": watcher_state_path,
        "watcher_pid_file": str(artifact_intake.get("watcher_pid_file") or "").strip(),
        "watcher_log_path": str(artifact_intake.get("watcher_log_path") or "").strip(),
        "watcher_start_command": str(artifact_intake.get("watcher_start_command") or "").strip(),
        "watcher_status_command": str(artifact_intake.get("watcher_status_command") or "").strip(),
        "watcher_stop_command": str(artifact_intake.get("watcher_stop_command") or "").strip(),
        "post_import_verify_command": str(artifact_intake.get("post_import_verify_command") or "").strip(),
        "expected_artifact_patterns": list(payload.get("expected_artifact_patterns"))
        if isinstance(payload.get("expected_artifact_patterns"), list)
        else [],
        "drop_roots_checked": list(payload.get("drop_roots_checked"))
        if isinstance(payload.get("drop_roots_checked"), list)
        else [],
        "promoted_installer_sha256": str(
            payload.get("promoted_installer_sha256")
            or operator_draft.get("promoted_installer_sha256")
            or ""
        ).strip(),
        "auto_import_receipt_path": str(windows_visual_audit_auto_import_path(request_path.parent)),
        **delivery_receipt,
    }
    watcher_path = (
        Path(watcher_state_path)
        if watcher_state_path
        else RUN_SERVICES_ROOT / ".state" / "windows_installer_gold_proof_watcher.generated.json"
    )
    auto_import_path = windows_visual_audit_auto_import_path(request_path.parent)
    auto_import_payload, auto_import_load_status = refresh_windows_auto_import_state(
        str(artifacts.get("auto_import_command") or "").strip(),
        auto_import_path,
        refresh_runtime_receipts=(
            refresh_runtime_receipts and runtime_refresh_authorized
        ),
    )
    watcher_payload, watcher_load_status = refresh_windows_watcher_state(
        str(artifacts.get("watcher_status_command") or "").strip(),
        watcher_path,
        refresh_runtime_receipts=(
            refresh_runtime_receipts and runtime_refresh_authorized
        ),
    )
    watcher_matching_process_pids = (
        list(watcher_payload.get("matching_process_pids"))
        if isinstance(watcher_payload.get("matching_process_pids"), list)
        else []
    )
    watcher_duplicate_process_pids = (
        list(watcher_payload.get("duplicate_process_pids"))
        if isinstance(watcher_payload.get("duplicate_process_pids"), list)
        else []
    )
    watcher_status = str(watcher_payload.get("status") or "").strip()
    watcher_duplicate_count = int(watcher_payload.get("duplicate_process_count") or len(watcher_duplicate_process_pids))
    artifacts.update(
        {
            "watcher_state_receipt_path": str(watcher_path),
            "watcher_state_receipt_exists": watcher_path.is_file(),
            "watcher_state_receipt_load_status": watcher_load_status,
            "watcher_state_receipt_generated_at_utc": str(watcher_payload.get("generated_at_utc") or "").strip(),
            "watcher_status": watcher_status,
            "watcher_pid": watcher_payload.get("pid"),
            "watcher_process_alive": bool(watcher_payload.get("process_alive")),
            "watcher_matching_process_pids": watcher_matching_process_pids,
            "watcher_matching_process_count": int(
                watcher_payload.get("matching_process_count") or len(watcher_matching_process_pids)
            ),
            "watcher_duplicate_process_pids": watcher_duplicate_process_pids,
            "watcher_duplicate_process_count": watcher_duplicate_count,
            "watcher_note": str(watcher_payload.get("note") or "").strip(),
            "watcher_attention_required": watcher_status != "running" or watcher_duplicate_count > 0,
        }
    )
    artifacts.update(
        {
            "auto_import_receipt_exists": auto_import_path.is_file(),
            "auto_import_receipt_load_status": auto_import_load_status,
            "auto_import_receipt_status": str(auto_import_payload.get("status") or "").strip(),
            "auto_import_receipt_generated_at_utc": str(auto_import_payload.get("generated_at_utc") or "").strip(),
            "auto_import_artifact": str(auto_import_payload.get("artifact") or "").strip(),
            **auto_import_failure_fields(auto_import_payload),
            "auto_import_actionable_candidate_count": int_value(auto_import_payload.get("actionable_candidate_count")),
            "auto_import_matching_promoted_directory_candidate_count": int_value(
                auto_import_payload.get("matching_promoted_directory_candidate_count")
            ),
            "auto_import_matching_promoted_zip_candidate_count": int_value(
                auto_import_payload.get("matching_promoted_zip_candidate_count")
            ),
            "auto_import_stale_directory_candidate_count": int_value(
                auto_import_payload.get("stale_directory_candidate_count")
            ),
            "auto_import_stage_like_stale_directory_candidate_count": int_value(
                auto_import_payload.get("stage_like_stale_directory_candidate_count")
            ),
            "auto_import_stage_visual_proof_receipt_count": int_value(
                auto_import_payload.get("stage_visual_proof_receipt_count")
            ),
            "auto_import_matching_promoted_stage_visual_proof_receipt_count": int_value(
                auto_import_payload.get("matching_promoted_stage_visual_proof_receipt_count")
            ),
            "auto_import_stale_stage_visual_proof_receipt_count": int_value(
                auto_import_payload.get("stale_stage_visual_proof_receipt_count")
            ),
            "auto_import_suppressed_stale_stage_visual_proof_receipt_count": int_value(
                auto_import_payload.get("suppressed_stale_stage_visual_proof_receipt_count")
            ),
            "auto_import_stage_startup_smoke_receipt_count": int_value(
                auto_import_payload.get("stage_startup_smoke_receipt_count")
            ),
            "auto_import_matching_promoted_stage_startup_smoke_receipt_count": int_value(
                auto_import_payload.get("matching_promoted_stage_startup_smoke_receipt_count")
            ),
            "auto_import_stale_stage_startup_smoke_receipt_count": int_value(
                auto_import_payload.get("stale_stage_startup_smoke_receipt_count")
            ),
            "auto_import_suppressed_stale_stage_startup_smoke_receipt_count": int_value(
                auto_import_payload.get("suppressed_stale_stage_startup_smoke_receipt_count")
            ),
            "auto_import_stale_directory_digest_summary": list(
                auto_import_payload.get("stale_directory_digest_summary")
            ) if isinstance(auto_import_payload.get("stale_directory_digest_summary"), list) else [],
            "auto_import_matching_promoted_stage_visual_proof_receipts": list(
                auto_import_payload.get("matching_promoted_stage_visual_proof_receipts")
            ) if isinstance(auto_import_payload.get("matching_promoted_stage_visual_proof_receipts"), list) else [],
            "auto_import_stale_stage_visual_proof_receipts": list(
                auto_import_payload.get("stale_stage_visual_proof_receipts")
            ) if isinstance(auto_import_payload.get("stale_stage_visual_proof_receipts"), list) else [],
            "auto_import_matching_promoted_stage_startup_smoke_receipts": list(
                auto_import_payload.get("matching_promoted_stage_startup_smoke_receipts")
            ) if isinstance(auto_import_payload.get("matching_promoted_stage_startup_smoke_receipts"), list) else [],
            "auto_import_stale_stage_startup_smoke_receipts": list(
                auto_import_payload.get("stale_stage_startup_smoke_receipts")
            ) if isinstance(auto_import_payload.get("stale_stage_startup_smoke_receipts"), list) else [],
            "auto_import_stage_visual_proof_receipt_note": str(
                auto_import_payload.get("stage_visual_proof_receipt_note") or ""
            ).strip(),
            "auto_import_stage_startup_smoke_receipt_note": str(
                auto_import_payload.get("stage_startup_smoke_receipt_note") or ""
            ).strip(),
            "auto_import_directory_candidate_note": str(
                auto_import_payload.get("directory_candidate_note") or ""
            ).strip(),
        }
    )
    return enrich_operator_ask_delivery_details(artifacts)


def windows_installer_visual_audit_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if str(payload.get("contract_name") or "").strip() != WINDOWS_INSTALLER_VISUAL_AUDIT_CONTRACT_NAME:
        failures.append("windows_installer_visual_audit receipt has unexpected contract")

    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    startup = payload.get("startupReceipt") if isinstance(payload.get("startupReceipt"), dict) else {}
    visual = payload.get("visualAuditSource") if isinstance(payload.get("visualAuditSource"), dict) else {}
    artifact_sha = normalized_sha(artifact.get("sha256"))
    actual_artifact_sha = normalized_sha(artifact.get("actualSha256"))
    startup_sha = normalized_sha(startup.get("artifactDigest"))
    visual_sha = normalized_sha(visual.get("artifactSha256"))

    if not artifact_sha or len(artifact_sha) != 64:
        failures.append("windows_installer_visual_audit artifact sha256 is missing")
    if not actual_artifact_sha or len(actual_artifact_sha) != 64:
        failures.append("windows_installer_visual_audit actual artifact sha256 is missing")
    if artifact_sha and actual_artifact_sha and artifact_sha != actual_artifact_sha:
        failures.append("windows_installer_visual_audit artifact sha256 does not match actual artifact bytes")
    if str(startup.get("status") or "").strip().lower() != "pass":
        failures.append("windows_installer_visual_audit startup receipt is not pass")
    startup_disposition = str(startup.get("verificationDisposition") or "").strip().lower()
    startup_skip = str(startup.get("skipClass") or "").strip().lower()
    if startup_disposition == "incompatible_host" or startup_skip == "incompatible_host":
        failures.append("windows_installer_visual_audit startup receipt is incompatible-host")
    if not startup_sha or len(startup_sha) != 64:
        failures.append("windows_installer_visual_audit startup receipt digest is missing")
    if artifact_sha and startup_sha and startup_sha != artifact_sha:
        failures.append("windows_installer_visual_audit startup digest does not match artifact")

    if visual.get("exists") is not True:
        failures.append("windows_installer_visual_audit visual source is missing")
    if str(visual.get("status") or "").strip().lower() != "pass":
        failures.append("windows_installer_visual_audit visual source is not pass")
    if str(visual.get("platform") or "").strip().lower() != "windows":
        failures.append("windows_installer_visual_audit visual source platform is not windows")
    host_class = str(visual.get("hostClass") or "").strip().lower()
    if "windows" not in host_class and host_class != "native":
        failures.append("windows_installer_visual_audit visual source is not native Windows")
    if not visual_sha or len(visual_sha) != 64:
        failures.append("windows_installer_visual_audit visual source artifact digest is missing")
    if artifact_sha and visual_sha and visual_sha != artifact_sha:
        failures.append("windows_installer_visual_audit visual source digest does not match artifact")
    required_surfaces = {
        str(item).strip()
        for item in (visual.get("requiredSurfaces") if isinstance(visual.get("requiredSurfaces"), list) else [])
        if str(item).strip()
    }
    if not {"install-progress", "completion"}.issubset(required_surfaces):
        failures.append("windows_installer_visual_audit required surfaces are incomplete")
    if int_value(visual.get("screenshotCount")) < 4:
        failures.append("windows_installer_visual_audit screenshot count is below required count")
    if int_value(visual.get("defaultDpiScreenshotCount")) < 2:
        failures.append("windows_installer_visual_audit default-DPI screenshot count is below required count")
    if int_value(visual.get("scaledDpiScreenshotCount")) < 2:
        failures.append("windows_installer_visual_audit scaled-DPI screenshot count is below required count")

    receipt_failures = payload.get("failures")
    if isinstance(receipt_failures, list) and receipt_failures:
        failures.append("windows_installer_visual_audit receipt contains failures")
    next_actions = payload.get("nextActions")
    if isinstance(next_actions, list) and next_actions:
        failures.append("windows_installer_visual_audit receipt contains next actions")
    return failures


def mirror_windows_runtime_artifacts(target: dict[str, object]) -> None:
    request_artifacts = (
        target.get("operator_request_artifacts")
        if isinstance(target.get("operator_request_artifacts"), dict)
        else {}
    )
    for key in WINDOWS_RUNTIME_ARTIFACT_FIELDS:
        if key in request_artifacts:
            target[key] = request_artifacts[key]


def flagship_product_readiness_structural_pass(summary: dict[str, Any]) -> bool:
    if str(summary.get("contract_name") or "").strip() != "fleet.flagship_product_readiness":
        return False
    if int_value(summary.get("missing_count")) != 0:
        return False
    if int_value(summary.get("scoped_missing_count")) != 0:
        return False
    if normalized_string_list(summary.get("coverage_gap_keys")):
        return False
    if normalized_string_list(summary.get("scoped_coverage_gap_keys")):
        return False
    if flagship_product_readiness_gate_semantic_failures(summary):
        return False

    completion_status = normalized_token(summary.get("completion_audit_status"))
    readiness_status = normalized_token(summary.get("flagship_readiness_audit_status"))
    if completion_status in PASS_STATES and readiness_status in PASS_STATES:
        return True

    return (
        str(summary.get("source_receipt") or "").strip() == "gate"
        and flagship_product_readiness_launch_blockers_recoverable(summary)
    )


def flagship_product_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("contract_name") or "").strip() == FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME:
        summary_payload = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        coverage_gaps = normalized_string_list(summary_payload.get("coverage_gap_keys"))
        scoped_gaps = normalized_string_list(summary_payload.get("scoped_coverage_gap_keys"))
        launch_critical_nested_blockers = normalized_string_list(
            summary_payload.get("launch_critical_nested_blockers")
        )
        summary = {
            "contract_name": summary_payload.get("contract_name"),
            "gate_contract_name": payload.get("contract_name"),
            "source_receipt": "gate",
            "status": summary_payload.get("status") or payload.get("status"),
            "gate_status": payload.get("status"),
            "verdict": payload.get("verdict"),
            "completion_audit_status": summary_payload.get("completion_audit_status"),
            "flagship_readiness_audit_status": summary_payload.get("flagship_readiness_audit_status"),
            "reason": summary_payload.get("reason"),
            "ready_count": int_value(summary_payload.get("ready_count")),
            "missing_count": int_value(summary_payload.get("missing_count")),
            "scoped_missing_count": int_value(summary_payload.get("scoped_missing_count")),
            "warning_count": int_value(summary_payload.get("warning_count")),
            "coverage_gap_keys": coverage_gaps,
            "scoped_coverage_gap_keys": scoped_gaps,
            "launch_critical_nested_blockers": launch_critical_nested_blockers,
            "launch_critical_nested_blocker_count": len(launch_critical_nested_blockers),
        }
        summary["structural_pass"] = flagship_product_readiness_structural_pass(summary)
        summary["pass"] = (
            summary["structural_pass"]
            and normalized_token(payload.get("status")) in PASS_STATES
            and not launch_critical_nested_blockers
        )
        summary["recovered_for_final_gold"] = False
        return summary

    summary_payload = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    completion = payload.get("completion_audit") if isinstance(payload.get("completion_audit"), dict) else {}
    readiness = payload.get("flagship_readiness_audit") if isinstance(payload.get("flagship_readiness_audit"), dict) else {}
    coverage_gaps = [
        str(item).strip()
        for item in readiness.get("coverage_gap_keys", [])
        if str(item).strip()
    ] if isinstance(readiness.get("coverage_gap_keys"), list) else []
    scoped_gaps = [
        str(item).strip()
        for item in readiness.get("scoped_coverage_gap_keys", [])
        if str(item).strip()
    ] if isinstance(readiness.get("scoped_coverage_gap_keys"), list) else []
    summary = {
        "contract_name": payload.get("contract_name"),
        "source_receipt": "raw",
        "status": payload.get("status"),
        "gate_status": None,
        "verdict": payload.get("verdict"),
        "completion_audit_status": completion.get("status"),
        "flagship_readiness_audit_status": readiness.get("status"),
        "reason": readiness.get("reason") or completion.get("reason"),
        "ready_count": int_value(summary_payload.get("ready_count")),
        "missing_count": int_value(summary_payload.get("missing_count")),
        "scoped_missing_count": int_value(summary_payload.get("scoped_missing_count")),
        "warning_count": int_value(summary_payload.get("warning_count")),
        "coverage_gap_keys": coverage_gaps,
        "scoped_coverage_gap_keys": scoped_gaps,
        "launch_critical_nested_blockers": [],
        "launch_critical_nested_blocker_count": 0,
    }
    summary["structural_pass"] = flagship_product_readiness_structural_pass(summary)
    summary["pass"] = (
        summary["structural_pass"]
        and normalized_token(summary["status"]) in PASS_STATES
    )
    summary["recovered_for_final_gold"] = False
    return summary


def flagship_product_readiness_expected_gate_verdict(status: object) -> str:
    return (
        FLAGSHIP_PRODUCT_READY_VERDICT
        if normalized_token(status) in PASS_STATES
        else FLAGSHIP_PRODUCT_NOT_READY_VERDICT
    )


def flagship_product_readiness_gate_semantic_failures(summary: dict[str, Any]) -> list[str]:
    if str(summary.get("source_receipt") or "").strip() != "gate":
        return []
    expected_verdict = flagship_product_readiness_expected_gate_verdict(
        summary.get("gate_status") if "gate_status" in summary else summary.get("status")
    )
    actual_verdict = str(summary.get("verdict") or "").strip()
    if actual_verdict == expected_verdict:
        return []
    return [f"flagship_product_readiness gate has unexpected verdict (expected {expected_verdict})"]


def required_gate_pass_verdict_semantic_failures(name: str, payload: dict[str, Any]) -> list[str]:
    semantic_failures: list[str] = []
    if name == "live_public_windows_installer":
        verifier_sha256 = str(payload.get("verify_script_sha256") or "").strip().lower()
        verifier_reference = str(payload.get("verify_script_path") or "").strip()
        try:
            expected_verifier_sha256 = hashlib.sha256(
                LIVE_PUBLIC_WINDOWS_VERIFIER_PATH.read_bytes()
            ).hexdigest()
        except OSError:
            expected_verifier_sha256 = ""
        if not expected_verifier_sha256 or verifier_sha256 != expected_verifier_sha256:
            semantic_failures.append(
                "live_public_windows_installer verifier SHA256 does not match the checked-in canonical verifier"
            )
        if verifier_reference != LIVE_PUBLIC_WINDOWS_VERIFIER_URI:
            semantic_failures.append(
                "live_public_windows_installer verifier URI is not the canonical checked-in verifier"
            )
    expected_verdicts = PASS_VERDICT_EXPECTATIONS.get(name)
    if not expected_verdicts:
        return semantic_failures
    verdict = str(payload.get("verdict") or "").strip()
    if verdict in expected_verdicts:
        return semantic_failures
    expected_text = ", ".join(sorted(expected_verdicts))
    semantic_failures.append(
        f"{name} has unexpected verdict (expected one of: {expected_text})"
    )
    return semantic_failures


def flagship_product_readiness_launch_blockers_recoverable(summary: dict[str, Any]) -> bool:
    blockers = normalized_string_list(summary.get("launch_critical_nested_blockers"))
    return bool(blockers) and all(
        is_recoverable_flagship_product_readiness_blocker(blocker)
        for blocker in blockers
    )


def is_recoverable_flagship_product_readiness_blocker(blocker: str) -> bool:
    candidate = str(blocker or "").strip()
    if not candidate:
        return False
    if candidate in FLAGSHIP_PRODUCT_READINESS_RECOVERABLE_LAUNCH_BLOCKERS:
        return True

    folded = candidate.casefold()
    return (
        folded.startswith("release channel ")
        or folded.startswith("windows installer visual audit ")
    )


def recover_flagship_product_readiness_for_final_gold(
    required_gates: dict[str, Any],
    failures: list[str],
) -> None:
    gate = required_gates.get("flagship_product_readiness")
    if not isinstance(gate, dict):
        return
    summary = gate.get("summary")
    if not isinstance(summary, dict):
        return
    if summary.get("source_receipt") != "gate":
        return
    if summary.get("structural_pass") is not True:
        return
    if not flagship_product_readiness_launch_blockers_recoverable(summary):
        return
    independent_blockers = sorted(
        name
        for name, data in required_gates.items()
        if name != "flagship_product_readiness"
        and isinstance(data, dict)
        and not bool(data.get("pass"))
    )
    if not independent_blockers:
        return
    gate["pass"] = True
    gate["status"] = "pass"
    gate["recovered_for_final_gold"] = True
    gate["recovered_because_of_gates"] = independent_blockers
    gate["recovered_launch_blockers"] = normalized_string_list(
        summary.get("launch_critical_nested_blockers")
    )
    summary["recovered_for_final_gold"] = True
    summary["recovered_because_of_gates"] = independent_blockers
    while "flagship_product_readiness failed" in failures:
        failures.remove("flagship_product_readiness failed")


def live_surface_parity_release_posture_only_failures_recoverable(gate: dict[str, Any]) -> bool:
    if int_value(gate.get("structured_failures_count")) != 0:
        return False
    semantic_failures = normalized_string_list(gate.get("semanticFailures"))
    if not semantic_failures:
        return False
    if any(
        not any(failure.startswith(prefix) for prefix in LIVE_SURFACE_PARITY_RECOVERABLE_EXPECTED_POSTURE_PREFIXES)
        for failure in semantic_failures
    ):
        return False
    release_posture = gate.get("release_posture") if isinstance(gate.get("release_posture"), dict) else {}
    if not release_posture:
        return False
    if normalized_string_list(release_posture.get("expected_failures")):
        return False
    for field in (
        "status_matches_expected",
        "version_matches_expected",
        "channel_matches_expected",
        "supportability_matches_expected",
        "rollout_matches_expected",
    ):
        if release_posture.get(field) is not True:
            return False
    return normalized_token(release_posture.get("expected_status")) == "published"


def release_channel_truth_blocking_gates(required_gates: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    release_ready = required_gates.get("release_ready")
    if isinstance(release_ready, dict) and not bool(release_ready.get("pass")):
        if "release_channel" in normalized_string_list(release_ready.get("failed_gates")):
            blockers.append("release_ready")

    operator_dashboard = required_gates.get("operator_release_dashboard")
    if isinstance(operator_dashboard, dict) and not bool(operator_dashboard.get("pass")):
        failed_required_checks = normalized_string_list(operator_dashboard.get("failed_required_checks"))
        dashboard_failures = normalized_string_list(operator_dashboard.get("failures"))
        if "release_channel" in failed_required_checks or "release_channel" in dashboard_failures:
            blockers.append("operator_release_dashboard")

    return sorted(set(blockers))


def release_lane_root_blocker_sources(required_gates: dict[str, Any]) -> list[str]:
    blockers = release_channel_truth_blocking_gates(required_gates)
    if blockers:
        return blockers

    flagship_gate = required_gates.get("flagship_product_readiness")
    if isinstance(flagship_gate, dict) and flagship_product_readiness_failures_only_root_blocker_echoes(flagship_gate):
        return ["flagship_product_readiness"]

    return []


def recover_live_surface_parity_for_final_gold(
    required_gates: dict[str, Any],
    failures: list[str],
) -> None:
    gate = required_gates.get("live_surface_parity")
    if not isinstance(gate, dict):
        return
    if gate.get("pass") is True:
        return
    if not live_surface_parity_release_posture_only_failures_recoverable(gate):
        return
    independent_blockers = release_lane_root_blocker_sources(required_gates)
    if not independent_blockers:
        return

    gate["pass"] = True
    gate["status"] = "pass"
    gate["recovered_for_final_gold"] = True
    gate["recovered_because_of_gates"] = independent_blockers
    gate["recovered_semantic_failures"] = normalized_string_list(gate.get("semanticFailures"))
    gate["failures"] = []
    while "live_surface_parity semantic proof failed" in failures:
        failures.remove("live_surface_parity semantic proof failed")


def public_edge_postdeploy_release_posture_only_failures_recoverable(gate: dict[str, Any]) -> bool:
    if normalized_string_list(gate.get("missingRequiredFields")):
        return False
    if normalized_string_list(gate.get("nonPreflightReceiptFailures")):
        return False
    if normalized_string_list(gate.get("release_truth_runtime_failures")):
        return False
    if normalized_string_list(gate.get("releaseChannelAlignmentFailures")):
        return False

    semantic_failures = normalized_string_list(gate.get("semanticFailures"))
    if not semantic_failures:
        return False
    if any(
        not any(
            failure.startswith(prefix)
            for prefix in PUBLIC_EDGE_POSTDEPLOY_RECOVERABLE_EXPECTED_POSTURE_PREFIXES
        )
        for failure in semantic_failures
    ):
        return False

    if normalized_token(gate.get("expectedReleaseStatus")) != "published":
        return False

    for field in (
        "visibleVersionMatchesReleaseChannel",
        "statusRedirectVersionMatchesReleaseChannel",
        "releaseManifestStatusMatchesReleaseChannel",
        "releaseManifestChannelMatchesReleaseChannel",
        "releaseManifestVersionMatchesReleaseChannel",
        "releaseManifestSupportabilityMatchesReleaseChannel",
        "releaseManifestRolloutMatchesReleaseChannel",
    ):
        if gate.get(field) is not True:
            return False

    heading_expected = str(gate.get("statusRedirectHeadingExpected") or "").strip()
    if heading_expected and gate.get("statusRedirectHeadingMatchesReleaseChannel") is not True:
        return False

    return True


def recover_public_edge_postdeploy_for_final_gold(
    required_gates: dict[str, Any],
    failures: list[str],
) -> None:
    gate = required_gates.get("public_edge_postdeploy_gate")
    if not isinstance(gate, dict):
        return
    if gate.get("pass") is True:
        return
    if not public_edge_postdeploy_release_posture_only_failures_recoverable(gate):
        return

    independent_blockers = release_lane_root_blocker_sources(required_gates)
    if not independent_blockers:
        return

    gate["pass"] = True
    gate["status"] = "pass"
    gate["recovered_for_final_gold"] = True
    gate["recovered_because_of_gates"] = independent_blockers
    gate["recovered_semantic_failures"] = normalized_string_list(gate.get("semanticFailures"))
    gate["failures"] = []
    while "public_edge_postdeploy_gate semantic proof failed" in failures:
        failures.remove("public_edge_postdeploy_gate semantic proof failed")


DEPENDENT_RELEASE_READY_FAILED_GATES = {
    "public_edge_postdeploy_gate",
    "release_channel",
    "flagship_product_readiness",
    "windows_installer_visual_audit",
}
DEPENDENT_OPERATOR_DASHBOARD_FAILED_CHECKS = {
    "public_edge_postdeploy_gate",
    "release_channel",
    "flagship_product_readiness",
    "release_ready",
    "windows_installer_visual_audit",
}


def release_or_windows_blocker_text(text: str) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    folded = candidate.casefold()
    return (
        folded.startswith("release channel ")
        or folded.startswith("windows installer visual audit ")
        or folded.startswith("windows installer gold proof artifact is still missing")
    )


def google_oauth_release_truth_effective_pass(gate: dict[str, Any]) -> bool:
    if not isinstance(gate, dict):
        return False

    failures = normalized_string_list(gate.get("failures"))
    failed_gates = normalized_string_list(gate.get("failed_gates"))
    if normalized_token(gate.get("status")) in PASS_STATES and not failures and not failed_gates:
        return True

    operator_evidence = (
        gate.get("operator_end_to_end_evidence")
        if isinstance(gate.get("operator_end_to_end_evidence"), dict)
        else {}
    )
    operator_request_artifacts = (
        gate.get("operator_request_artifacts")
        if isinstance(gate.get("operator_request_artifacts"), dict)
        else {}
    )
    quick_probe = gate.get("quick_handoff_probe") if isinstance(gate.get("quick_handoff_probe"), dict) else {}
    signed_in_probe = gate.get("signed_in_link_handoff") if isinstance(gate.get("signed_in_link_handoff"), dict) else {}
    request_status = normalized_token(
        operator_request_artifacts.get("request_effective_status")
        or operator_request_artifacts.get("request_status")
    )
    signed_in_status = normalized_token(signed_in_probe.get("status"))
    only_signed_in_failures = bool(failures) and all(
        item.startswith("signed_in_link_handoff:") for item in failures
    )
    only_paused_auth_failures = bool(failures) and all(
        item.startswith("auth_signin_automation_paused:") for item in failures
    )

    if (
        request_status == "not_required"
        and operator_request_artifacts.get("operator_action_still_required") is False
        and not failed_gates
        and only_paused_auth_failures
    ):
        return True

    return (
        operator_evidence.get("pass") is True
        and request_status == "not_required"
        and quick_probe.get("pass") is True
        and signed_in_status == "fail"
        and only_signed_in_failures
    )


def release_ready_failures_only_root_blocker_echoes(gate: dict[str, Any]) -> bool:
    if bool(gate.get("pass")):
        return False
    if gate.get("timed_out") is True:
        return False

    returncode = gate.get("returncode")
    if returncode not in (None, 0):
        return False

    failed_gates = set(normalized_string_list(gate.get("failed_gates")))
    if not failed_gates or not failed_gates.issubset(DEPENDENT_RELEASE_READY_FAILED_GATES):
        return False

    failures = normalized_string_list(gate.get("failures"))
    if not failures:
        return False

    allowed_prefixes = (
        "FAIL public_edge_postdeploy_gate: ",
        "FAIL release_channel: ",
        "FAIL flagship_product_readiness: ",
        "FAIL windows_installer_visual_audit: ",
    )
    for failure in failures:
        matched = False
        for prefix in allowed_prefixes:
            if failure.startswith(prefix):
                matched = True
                if prefix == "FAIL public_edge_postdeploy_gate: ":
                    break
                if not release_or_windows_blocker_text(failure.removeprefix(prefix).strip()):
                    return False
                break
        if not matched:
            return False
    return True


def operator_dashboard_failures_only_root_blocker_echoes(
    gate: dict[str, Any],
    google_gate: dict[str, Any] | None = None,
) -> bool:
    if bool(gate.get("pass")):
        return False
    if normalized_string_list(gate.get("missing_required_checks")):
        return False
    if normalized_string_list(gate.get("missing_required_check_fields")):
        return False
    if normalized_string_list(gate.get("stale_required_checks")):
        return False
    if normalized_string_list(gate.get("nonblocking_required_checks")):
        return False

    google_effective_pass = bool(isinstance(google_gate, dict) and google_oauth_release_truth_effective_pass(google_gate))
    allowed_exact = set(DEPENDENT_OPERATOR_DASHBOARD_FAILED_CHECKS)
    if google_effective_pass:
        allowed_exact.add("google_oauth_linking_proof")

    failed_required_checks = set(normalized_string_list(gate.get("failed_required_checks")))
    if not failed_required_checks or not failed_required_checks.issubset(allowed_exact):
        return False

    contradictory_required_checks = set(normalized_string_list(gate.get("contradictory_required_checks")))
    if contradictory_required_checks and not contradictory_required_checks.issubset(allowed_exact):
        return False

    failures = normalized_string_list(gate.get("failures"))
    if not failures:
        return False

    for failure in failures:
        if failure in allowed_exact:
            continue
        if release_or_windows_blocker_text(failure):
            continue
        return False
    return True


def flagship_product_readiness_failures_only_root_blocker_echoes(gate: dict[str, Any]) -> bool:
    if bool(gate.get("pass")):
        return False

    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    return flagship_product_readiness_summary_only_root_blocker_echoes(summary)


def flagship_product_readiness_summary_only_root_blocker_echoes(summary: dict[str, Any]) -> bool:
    if not summary:
        return False

    if normalized_string_list(summary.get("coverage_gap_keys")):
        return False
    if normalized_string_list(summary.get("scoped_coverage_gap_keys")):
        return False
    if int_value(summary.get("missing_count")) != 0:
        return False
    if int_value(summary.get("scoped_missing_count")) != 0:
        return False

    launch_blockers = normalized_string_list(summary.get("launch_critical_nested_blockers"))
    if not launch_blockers:
        return False

    return all(
        is_recoverable_flagship_product_readiness_blocker(blocker)
        or release_or_windows_blocker_text(blocker)
        for blocker in launch_blockers
    )


def suppress_dependent_summary_gate_failures_for_final_gold(
    required_gates: dict[str, Any],
    failures: list[str],
) -> None:
    covered_by_release_blockers = ["release_lane_posture"]
    if not IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        covered_by_release_blockers.append("windows_native_visual_proof")

    google_oauth_gate = required_gates.get("google_oauth_linking_proof")
    if (
        isinstance(google_oauth_gate, dict)
        and not google_oauth_gate.get("pass")
        and google_oauth_release_truth_effective_pass(google_oauth_gate)
    ):
        google_oauth_gate["release_truth_effective_pass"] = True
        google_oauth_gate["release_truth_effective_pass_reason"] = (
            "auth_signin_automation_paused_by_user_request"
            if normalized_string_list(google_oauth_gate.get("failures"))
            and all(
                item.startswith("auth_signin_automation_paused:")
                for item in normalized_string_list(google_oauth_gate.get("failures"))
            )
            else "operator_evidence_green_signed_in_preflight_only_failure"
        )
        google_oauth_gate["release_blocking"] = False
        while "google_oauth_linking_proof failed" in failures:
            failures.remove("google_oauth_linking_proof failed")
        while "google_oauth_linking_proof has structured failures" in failures:
            failures.remove("google_oauth_linking_proof has structured failures")

    flagship_gate = required_gates.get("flagship_product_readiness")
    flagship_gate_summary = (
        flagship_gate.get("summary")
        if isinstance(flagship_gate, dict) and isinstance(flagship_gate.get("summary"), dict)
        else {}
    )
    if isinstance(flagship_gate, dict) and (
        flagship_product_readiness_failures_only_root_blocker_echoes(flagship_gate)
        or (
            flagship_gate.get("recovered_for_final_gold") is True
            and flagship_product_readiness_summary_only_root_blocker_echoes(flagship_gate_summary)
        )
    ):
        flagship_gate["covered_by_root_blockers_for_final_gold"] = list(covered_by_release_blockers)
        while "flagship_product_readiness failed" in failures:
            failures.remove("flagship_product_readiness failed")

    release_ready_gate = required_gates.get("release_ready")
    if isinstance(release_ready_gate, dict) and release_ready_failures_only_root_blocker_echoes(release_ready_gate):
        release_ready_gate["covered_by_root_blockers_for_final_gold"] = list(covered_by_release_blockers)
        while "release_ready failed" in failures:
            failures.remove("release_ready failed")
        while "release_ready semantic proof failed" in failures:
            failures.remove("release_ready semantic proof failed")

    operator_dashboard_gate = required_gates.get("operator_release_dashboard")
    if isinstance(operator_dashboard_gate, dict) and operator_dashboard_failures_only_root_blocker_echoes(
        operator_dashboard_gate,
        google_oauth_gate if isinstance(google_oauth_gate, dict) else None,
    ):
        operator_dashboard_gate["covered_by_root_blockers_for_final_gold"] = list(covered_by_release_blockers)
        while "operator_release_dashboard failed" in failures:
            failures.remove("operator_release_dashboard failed")
        while "operator_release_dashboard has failing required checks" in failures:
            failures.remove("operator_release_dashboard has failing required checks")


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
        raw_path = path
        payload, load_status = load_json_with_status(path)
        raw_load_status = load_status
        if name == "flagship_product_readiness":
            gate_path = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            refresh_flagship_product_readiness_gate(
                gate_path,
                refresh_receipt=refresh_flagship_product_readiness_gate_receipt,
            )
            gate_payload, gate_load_status = load_json_with_status(gate_path)
            if gate_path.is_file():
                path = gate_path
                payload = gate_payload
                load_status = gate_load_status
        receipt_loaded = load_status == "loaded"
        generated_at = str(
            payload.get("generated_at_utc")
            or payload.get("generatedAtUtc")
            or payload.get("generatedAt")
            or payload.get("generated_at")
            or ""
        )
        is_fresh = (
            generated_at_is_fresh(generated_at, RECRAWL_MAX_AGE_HOURS)
            if name in effective_freshness_required_gates
            else True
        )
        source_status_value = str(payload.get("status") or "").strip()
        source_reported_status = source_status_value or ("invalid" if load_status == "invalid" else "missing")
        status_value = source_status_value.lower()
        structured_failures = normalized_string_list(payload.get("failures"))
        has_structured_failures = bool(structured_failures)
        structured_failed_gates = normalized_string_list(payload.get("failed_gates"))
        has_failed_gates = bool(structured_failed_gates)
        gate_failure_reason: str | None = None
        passed = receipt_loaded and path.is_file() and status_value in {"pass", "passed", "ready"} and is_fresh
        if name == "public_route_proof" and receipt_loaded:
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            passed = (
                status_value in {"pass", "passed", "ready"}
                and int(summary.get("route_count") or 0) > 0
                and int(summary.get("failed_count") or 0) == 0
                and int(summary.get("negative_path_failed_count") or 0) == 0
                and is_fresh
            )
            status_value = "pass" if passed else "fail"
        if name == "blazor_execution_horizon_bridge" and receipt_loaded:
            blazor_public_entry = blazor_bridge_public_entry_summary(payload)
            if not blazor_public_entry["pass"]:
                passed = False
                status_value = "fail"
                gate_failure_reason = (
                    "blazor_execution_horizon_bridge missing the v2 public Build/Play "
                    "install-boundary proof"
                )
        pass_verdict_semantic_failures = (
            required_gate_pass_verdict_semantic_failures(name, payload)
            if receipt_loaded and status_value in {"pass", "passed", "ready"}
            else []
        )
        if passed and pass_verdict_semantic_failures:
            passed = False
        if name == "public_edge_postdeploy_gate" and receipt_loaded:
            passed = True
        if passed and (has_structured_failures or has_failed_gates):
            if name != "public_edge_postdeploy_gate":
                passed = False
        load_failure = receipt_load_failure(name, path, load_status)
        if not passed:
            if load_failure:
                reason = load_failure
            elif gate_failure_reason:
                reason = gate_failure_reason
            else:
                reason = f"{name} missing" if not path.is_file() else f"{name} failed"
                if path.is_file() and name in effective_freshness_required_gates and not is_fresh:
                    reason = f"{name} stale"
                elif (
                    path.is_file()
                    and status_value in {"pass", "passed", "ready"}
                    and pass_verdict_semantic_failures
                ):
                    reason = f"{name} has unexpected verdict"
                elif (
                    path.is_file()
                    and status_value in {"pass", "passed", "ready"}
                    and has_structured_failures
                    and name != "public_edge_postdeploy_gate"
                ):
                    reason = f"{name} has structured failures"
                elif (
                    path.is_file()
                    and status_value in {"pass", "passed", "ready"}
                    and has_failed_gates
                    and name != "public_edge_postdeploy_gate"
                ):
                    reason = f"{name} has failed gates"
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
        if name == "blazor_execution_horizon_bridge" and receipt_loaded:
            bridge_proofs = (
                payload.get("proofs")
                if isinstance(payload.get("proofs"), dict)
                else {}
            )
            hosted_execution = (
                bridge_proofs.get("blazor_hosted_execution_horizon")
                if isinstance(bridge_proofs.get("blazor_hosted_execution_horizon"), dict)
                else {}
            )
            hosted_pwa = (
                bridge_proofs.get("blazor_hosted_pwa_public_edge")
                if isinstance(bridge_proofs.get("blazor_hosted_pwa_public_edge"), dict)
                else {}
            )
            hub_mobile = (
                bridge_proofs.get("hub_mobile_pwa_public_projection")
                if isinstance(bridge_proofs.get("hub_mobile_pwa_public_projection"), dict)
                else {}
            )
            bridge_summary = {
                "verdict": str(payload.get("verdict") or "").strip(),
                "hub_mobile_pwa_public_projection_status": str(hub_mobile.get("status") or "").strip(),
                "blazor_hosted_pwa_public_edge_status": str(hosted_pwa.get("status") or "").strip(),
                "near_term_smoke_status": str(hosted_execution.get("near_term_smoke_status") or "").strip(),
                "mid_term_full_matrix_status": str(hosted_execution.get("mid_term_full_matrix_status") or "").strip(),
                "mid_term_full_required_workflow_family_count": int_value(
                    hosted_execution.get("mid_term_full_required_workflow_family_count")
                ),
                "mid_term_full_covered_workflow_family_count": int_value(
                    hosted_execution.get("mid_term_full_covered_workflow_family_count")
                ),
                "long_term_full_browser_parity_status": str(
                    hosted_execution.get("long_term_full_browser_parity_status") or ""
                ).strip(),
                "notes": normalized_string_list(payload.get("notes")),
            }
            if isinstance(blazor_play_surface_horizon_path, Path):
                bridge_summary["play_surface_horizon_path"] = str(blazor_play_surface_horizon_path)
            if isinstance(blazor_play_surface_horizon, dict) and blazor_play_surface_horizon:
                bridge_summary["play_surface_horizon"] = blazor_play_surface_horizon_summary(
                    blazor_play_surface_horizon
                )
            required_gates[name]["summary"] = bridge_summary
            required_gates[name]["public_entry"] = blazor_bridge_public_entry_summary(payload)
        if name == "live_surface_parity" and receipt_loaded:
            live_surface_semantic_failures = live_surface_parity_semantic_failures(payload)
            required_gates[name]["release_posture"] = payload.get("release_posture", {})
            existing_semantic_failures = required_gates[name].get("semanticFailures", [])
            if not isinstance(existing_semantic_failures, list):
                existing_semantic_failures = []
            required_gates[name]["semanticFailures"] = [
                str(item)
                for item in existing_semantic_failures
                if str(item).strip()
            ]
            for failure in live_surface_semantic_failures:
                if failure not in required_gates[name]["semanticFailures"]:
                    required_gates[name]["semanticFailures"].append(failure)
            if status_value in {"pass", "passed", "ready"} and live_surface_semantic_failures:
                if required_gates[name]["pass"]:
                    failures.append("live_surface_parity semantic proof failed")
                required_gates[name]["pass"] = False
                required_gates[name]["status"] = "fail"
                existing_failures = required_gates[name].get("failures", [])
                if not isinstance(existing_failures, list):
                    existing_failures = []
                required_gates[name]["failures"] = [
                    str(item)
                    for item in existing_failures
                    if str(item).strip()
                ]
                required_gates[name]["failures"].extend(live_surface_semantic_failures)
        if name == "public_edge_postdeploy_gate" and receipt_loaded:
            payload = normalize_public_edge_postdeploy_payload(payload)
            public_edge_contract_name = str(payload.get("contractName") or payload.get("contract_name") or "").strip()
            public_edge_receipt_failures = public_edge_postdeploy_receipt_failures(payload)
            public_edge_non_preflight_receipt_failures = public_edge_postdeploy_non_preflight_receipt_failures(payload)
            public_edge_release_truth = public_edge_release_truth_state(public_release_snapshot, path)
            public_edge_release_truth_runtime_failure_lines = public_edge_release_truth_runtime_failures(public_edge_release_truth)
            public_edge_runtime_observation = (
                public_edge_release_truth.get("runtime_observation")
                if isinstance(public_edge_release_truth.get("runtime_observation"), dict)
                else {}
            )
            required_gates[name]["contractName"] = public_edge_contract_name
            if public_edge_contract_name != PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME:
                if f"{name} has unexpected contract" not in failures:
                    failures.append(f"{name} has unexpected contract")
                required_gates[name]["pass"] = False
                required_gates[name]["status"] = "fail"
            missing_postdeploy_fields = sorted(
                field
                for field in PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS
                if field not in payload
            )
            if missing_postdeploy_fields:
                if f"{name} missing required fields" not in failures:
                    failures.append(f"{name} missing required fields")
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
            postdeploy_semantic_failures = public_edge_postdeploy_semantic_failures(payload)
            postdeploy_release_channel_alignment_failures = public_edge_postdeploy_release_channel_alignment_failures(
                payload,
                release_channel,
            )
            if postdeploy_semantic_failures:
                if f"{name} semantic proof failed" not in failures:
                    failures.append(f"{name} semantic proof failed")
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
            required_gates[name]["baseUrl"] = payload.get("baseUrl")
            required_gates[name]["coreChildContracts"] = payload.get("coreChildContracts")
            required_gates[name]["preflightStatus"] = payload.get("preflightStatus")
            required_gates[name]["preflightActiveLockCount"] = payload.get("preflightActiveLockCount")
            required_gates[name]["preflightBlockingLockCount"] = payload.get("preflightBlockingLockCount")
            required_gates[name]["preflightStaleLookingLockCount"] = payload.get("preflightStaleLookingLockCount")
            required_gates[name]["preflightStaleForeignLockCount"] = payload.get("preflightStaleForeignLockCount")
            required_gates[name]["preflightStaleForeignLocksIgnored"] = payload.get("preflightStaleForeignLocksIgnored")
            required_gates[name]["downloadsStatus"] = payload.get("downloadsStatus")
            required_gates[name]["downloadsHasMarker"] = payload.get("downloadsHasMarker")
            required_gates[name]["statusRedirectHasMarker"] = payload.get("statusRedirectHasMarker")
            required_gates[name]["visibleVersion"] = payload.get("visibleVersion")
            required_gates[name]["statusRedirectVersion"] = payload.get("statusRedirectVersion")
            required_gates[name]["expectedReleaseVersion"] = payload.get("expectedReleaseVersion")
            required_gates[name]["visibleVersionMatchesReleaseChannel"] = payload.get("visibleVersionMatchesReleaseChannel")
            required_gates[name]["statusRedirectVersionMatchesReleaseChannel"] = payload.get("statusRedirectVersionMatchesReleaseChannel")
            required_gates[name]["expectedReleaseStatus"] = payload.get("expectedReleaseStatus")
            required_gates[name]["expectedReleaseChannel"] = payload.get("expectedReleaseChannel")
            required_gates[name]["expectedReleaseSupportabilityState"] = payload.get("expectedReleaseSupportabilityState")
            required_gates[name]["expectedReleaseRolloutState"] = payload.get("expectedReleaseRolloutState")
            required_gates[name]["releaseManifestHttpStatus"] = payload.get("releaseManifestHttpStatus")
            required_gates[name]["releaseManifestStatus"] = payload.get("releaseManifestStatus")
            required_gates[name]["releaseManifestStatusMatchesReleaseChannel"] = payload.get("releaseManifestStatusMatchesReleaseChannel")
            required_gates[name]["releaseManifestChannel"] = payload.get("releaseManifestChannel")
            required_gates[name]["releaseManifestChannelMatchesReleaseChannel"] = payload.get("releaseManifestChannelMatchesReleaseChannel")
            required_gates[name]["releaseManifestVersion"] = payload.get("releaseManifestVersion")
            required_gates[name]["releaseManifestVersionMatchesReleaseChannel"] = payload.get("releaseManifestVersionMatchesReleaseChannel")
            required_gates[name]["releaseManifestSupportabilityState"] = payload.get("releaseManifestSupportabilityState")
            required_gates[name]["releaseManifestSupportabilityMatchesReleaseChannel"] = payload.get("releaseManifestSupportabilityMatchesReleaseChannel")
            required_gates[name]["releaseManifestRolloutState"] = payload.get("releaseManifestRolloutState")
            required_gates[name]["releaseManifestRolloutMatchesReleaseChannel"] = payload.get("releaseManifestRolloutMatchesReleaseChannel")
            required_gates[name]["releaseChannelAlignmentFailures"] = postdeploy_release_channel_alignment_failures
            required_gates[name]["currentReleaseChannelVersion"] = release_channel.get("version")
            required_gates[name]["currentReleaseChannelChannel"] = release_channel.get("channel") or release_channel.get("channelId")
            required_gates[name]["currentReleaseChannelSupportabilityState"] = release_channel.get("supportabilityState")
            required_gates[name]["currentReleaseChannelRolloutState"] = release_channel.get("rolloutState")
            required_gates[name]["pwaStaticStatus"] = payload.get("pwaStaticStatus")
            required_gates[name]["pwaManifestCount"] = payload.get("pwaManifestCount")
            required_gates[name]["rolePwaManifestCount"] = payload.get("rolePwaManifestCount")
            required_gates[name]["rolePwaManifests"] = payload.get("rolePwaManifests")
            required_gates[name]["pwaAssetCount"] = payload.get("pwaAssetCount")
            required_gates[name]["ledgerStreamNonCacheable"] = payload.get("ledgerStreamNonCacheable")
            required_gates[name]["ledgerStreamPrecached"] = payload.get("ledgerStreamPrecached")
            required_gates[name]["mobileLedgerStatus"] = payload.get("mobileLedgerStatus")
            required_gates[name]["mobileLedgerPayloadStatus"] = payload.get("mobileLedgerPayloadStatus")
            required_gates[name]["mobileLedgerCacheControl"] = payload.get("mobileLedgerCacheControl")
            required_gates[name]["mobileLedgerVary"] = payload.get("mobileLedgerVary")
            required_gates[name]["readyMobileHandoffStatus"] = payload.get("readyMobileHandoffStatus")
            required_gates[name]["readyMobileHandoffToolIds"] = payload.get("readyMobileHandoffToolIds")
            required_gates[name]["readyMobileHandoffPacketRoles"] = payload.get("readyMobileHandoffPacketRoles")
            required_gates[name]["readyMobileHandoffFrontdoorLaunchRoute"] = payload.get("readyMobileHandoffFrontdoorLaunchRoute")
            required_gates[name]["readyMobileHandoffRoleRoutes"] = payload.get("readyMobileHandoffRoleRoutes")
            required_gates[name]["downloadsStatusBrowserStatus"] = payload.get("downloadsStatusBrowserStatus")
            required_gates[name]["downloadsStatusBrowserArtifactContract"] = payload.get("downloadsStatusBrowserArtifactContract")
            required_gates[name]["mobilePwaViewportStatus"] = payload.get("mobilePwaViewportStatus")
            required_gates[name]["mobilePwaViewportArtifactContract"] = payload.get("mobilePwaViewportArtifactContract")
            required_gates[name]["mobilePwaViewportRouteCount"] = payload.get("mobilePwaViewportRouteCount")
            required_gates[name]["mobilePwaViewportViewportCount"] = payload.get("mobilePwaViewportViewportCount")
            required_gates[name]["mobilePwaViewportRoutes"] = payload.get("mobilePwaViewportRoutes")
            required_gates[name]["mobilePwaViewportMissingRoutes"] = payload.get("mobilePwaViewportMissingRoutes")
            required_gates[name]["pwaOfflineCacheStatus"] = payload.get("pwaOfflineCacheStatus")
            required_gates[name]["pwaOfflineCacheArtifactContract"] = payload.get("pwaOfflineCacheArtifactContract")
            required_gates[name]["pwaOfflineCacheCacheVersion"] = payload.get("pwaOfflineCacheCacheVersion")
            required_gates[name]["pwaOfflineCacheNavigationPolicy"] = payload.get("pwaOfflineCacheNavigationPolicy")
            required_gates[name]["pwaOfflineCachePrivateStateScope"] = payload.get("pwaOfflineCachePrivateStateScope")
            required_gates[name]["pwaOfflineCacheStaticPaths"] = payload.get("pwaOfflineCacheStaticPaths")
            required_gates[name]["pwaOfflineCacheOfflineRoleFallbacks"] = payload.get("pwaOfflineCacheOfflineRoleFallbacks")
            required_gates[name]["pwaOfflineCacheQueryBearingRequestsCached"] = payload.get("pwaOfflineCacheQueryBearingRequestsCached")
            required_gates[name]["pwaOfflineCachePrivateNavigationCached"] = payload.get("pwaOfflineCachePrivateNavigationCached")
            required_gates[name]["pwaOfflineCachePrivateApiCached"] = payload.get("pwaOfflineCachePrivateApiCached")
            required_gates[name]["pwaOfflineCachePersonalizedLedgerCached"] = payload.get("pwaOfflineCachePersonalizedLedgerCached")
            required_gates[name]["pwaOfflineCacheLegacyPrivateCachePrefixesPurged"] = payload.get("pwaOfflineCacheLegacyPrivateCachePrefixesPurged")
            required_gates[name]["pwaOfflineCacheUnrelatedCachePreserved"] = payload.get("pwaOfflineCacheUnrelatedCachePreserved")
            required_gates[name]["roleAliasRouteStatus"] = payload.get("roleAliasRouteStatus")
            required_gates[name]["roleAliasRouteContract"] = payload.get("roleAliasRouteContract")
            required_gates[name]["roleAliasRouteResults"] = payload.get("roleAliasRouteResults")
            required_gates[name]["roleAliasRouteDrift"] = payload.get("roleAliasRouteDrift")
            required_gates[name]["participateIframeShellStatus"] = payload.get("participateIframeShellStatus")
            required_gates[name]["participateIframeRouteCount"] = payload.get("participateIframeRouteCount")
            required_gates[name]["participateIframeRouteIframeCount"] = payload.get("participateIframeRouteIframeCount")
            required_gates[name]["participateIframeRouteOfflineFallbackCount"] = payload.get("participateIframeRouteOfflineFallbackCount")
            required_gates[name]["frontdoorNavigationStatus"] = payload.get("frontdoorNavigationStatus")
            required_gates[name]["frontdoorNavigationMobileArtifactContract"] = payload.get("frontdoorNavigationMobileArtifactContract")
            required_gates[name]["frontdoorNavigationLedgerArtifactContract"] = payload.get("frontdoorNavigationLedgerArtifactContract")
            required_gates[name]["frontdoorNavigationGatedTargets"] = payload.get("frontdoorNavigationGatedTargets")
            required_gates[name]["frontdoorNavigationPublicTargets"] = payload.get("frontdoorNavigationPublicTargets")
            required_gates[name]["frontdoorNavigationPlayRoute"] = payload.get("frontdoorNavigationPlayRoute")
            required_gates[name]["frontdoorNavigationPlaySignInRoute"] = payload.get("frontdoorNavigationPlaySignInRoute")
            required_gates[name]["frontdoorNavigationDirectPlayerRoute"] = payload.get("frontdoorNavigationDirectPlayerRoute")
            required_gates[name]["frontdoorNavigationDirectPlayerHttpStatus"] = payload.get("frontdoorNavigationDirectPlayerHttpStatus")
            required_gates[name]["frontdoorNavigationFinalUrl"] = payload.get("frontdoorNavigationFinalUrl")
            required_gates[name]["frontdoorNavigationPrivateIdentityRedacted"] = payload.get("frontdoorNavigationPrivateIdentityRedacted")
            required_gates[name]["frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent"] = payload.get("frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent")
            required_gates[name]["frontdoorNavigationPlayerSessionContextPresent"] = payload.get("frontdoorNavigationPlayerSessionContextPresent")
            required_gates[name]["frontdoorNavigationPlayerDeviceContextPresent"] = payload.get("frontdoorNavigationPlayerDeviceContextPresent")
            required_gates[name]["frontdoorNavigationLiveTurnCompanionShell"] = payload.get("frontdoorNavigationLiveTurnCompanionShell")
            required_gates[name]["frontdoorNavigationPwaManifestPath"] = payload.get("frontdoorNavigationPwaManifestPath")
            required_gates[name]["frontdoorNavigationPwaRole"] = payload.get("frontdoorNavigationPwaRole")
            required_gates[name]["frontdoorNavigationBlazorShell"] = payload.get("frontdoorNavigationBlazorShell")
            required_gates[name]["frontdoorNavigationRybbitConfigured"] = payload.get("frontdoorNavigationRybbitConfigured")
            required_gates[name]["frontdoorNavigationRybbitTag"] = payload.get("frontdoorNavigationRybbitTag")
            required_gates[name]["frontdoorNavigationPlayerSessionHandoffUrl"] = payload.get("frontdoorNavigationPlayerSessionHandoffUrl")
            required_gates[name]["frontdoorNavigationPlayerSessionHandoffPreservesSession"] = payload.get("frontdoorNavigationPlayerSessionHandoffPreservesSession")
            required_gates[name]["frontdoorNavigationPlayerSessionHandoffPreservesRole"] = payload.get("frontdoorNavigationPlayerSessionHandoffPreservesRole")
            required_gates[name]["frontdoorNavigationPlayerSessionHandoffStripsDevice"] = payload.get("frontdoorNavigationPlayerSessionHandoffStripsDevice")
            required_gates[name]["frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted"] = payload.get("frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted")
            required_gates[name]["frontdoorNavigationGmRoute"] = payload.get("frontdoorNavigationGmRoute")
            required_gates[name]["frontdoorNavigationGmRouteSessionIdPresent"] = payload.get("frontdoorNavigationGmRouteSessionIdPresent")
            required_gates[name]["frontdoorNavigationGmRoutePrivateIdentityRedacted"] = payload.get("frontdoorNavigationGmRoutePrivateIdentityRedacted")
            required_gates[name]["frontdoorNavigationGmHttpStatus"] = payload.get("frontdoorNavigationGmHttpStatus")
            required_gates[name]["frontdoorNavigationGmFinalUrl"] = payload.get("frontdoorNavigationGmFinalUrl")
            required_gates[name]["frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent"] = payload.get("frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent")
            required_gates[name]["frontdoorNavigationGmSessionContextPresent"] = payload.get("frontdoorNavigationGmSessionContextPresent")
            required_gates[name]["frontdoorNavigationGmDeviceContextPresent"] = payload.get("frontdoorNavigationGmDeviceContextPresent")
            required_gates[name]["frontdoorNavigationGmLiveTurnCompanionShell"] = payload.get("frontdoorNavigationGmLiveTurnCompanionShell")
            required_gates[name]["frontdoorNavigationGmPwaManifestPath"] = payload.get("frontdoorNavigationGmPwaManifestPath")
            required_gates[name]["frontdoorNavigationGmPwaRole"] = payload.get("frontdoorNavigationGmPwaRole")
            required_gates[name]["frontdoorNavigationGmBlazorShell"] = payload.get("frontdoorNavigationGmBlazorShell")
            required_gates[name]["frontdoorNavigationGmRybbitConfigured"] = payload.get("frontdoorNavigationGmRybbitConfigured")
            required_gates[name]["frontdoorNavigationGmRybbitTag"] = payload.get("frontdoorNavigationGmRybbitTag")
            required_gates[name]["frontdoorNavigationGmSessionHandoffUrl"] = payload.get("frontdoorNavigationGmSessionHandoffUrl")
            required_gates[name]["frontdoorNavigationGmSessionHandoffPreservesSession"] = payload.get("frontdoorNavigationGmSessionHandoffPreservesSession")
            required_gates[name]["frontdoorNavigationGmSessionHandoffPreservesRole"] = payload.get("frontdoorNavigationGmSessionHandoffPreservesRole")
            required_gates[name]["frontdoorNavigationGmSessionHandoffStripsDevice"] = payload.get("frontdoorNavigationGmSessionHandoffStripsDevice")
            required_gates[name]["frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted"] = payload.get("frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted")
            required_gates[name]["frontdoorNavigationLedgerPrimary"] = payload.get("frontdoorNavigationLedgerPrimary")
            for field in (
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
            ):
                required_gates[name][field] = payload.get(field)
            required_gates[name]["release_truth_status"] = public_edge_release_truth.get("status")
            required_gates[name]["release_truth_verdict"] = public_edge_release_truth.get("verdict")
            required_gates[name]["release_truth_generated_at"] = public_edge_release_truth.get("generated_at")
            required_gates[name]["release_truth_runtime_override_applied"] = public_edge_release_truth.get("runtime_override_applied")
            required_gates[name]["release_truth_runtime_override_reason"] = public_edge_release_truth.get("runtime_override_reason")
            required_gates[name]["release_truth_runtime_blocker_class"] = public_edge_release_truth.get(
                "runtime_blocker_class"
            )
            required_gates[name]["release_truth_local_surface_regression"] = public_edge_release_truth.get(
                "local_surface_regression"
            )
            required_gates[name]["release_truth_deployment_activation_proof_required"] = (
                public_edge_release_truth.get("deployment_activation_proof_required")
            )
            required_gates[name]["release_truth_activation_authority_required"] = public_edge_release_truth.get(
                "activation_authority_required"
            )
            required_gates[name]["release_truth_post_activation_proof_required"] = public_edge_release_truth.get(
                "post_activation_proof_required"
            )
            required_gates[name]["release_truth_staged_overlay_observation"] = public_edge_release_truth.get(
                "staged_overlay_observation"
            )
            required_gates[name]["release_truth_runtime_observation_status"] = public_edge_runtime_observation.get("status")
            required_gates[name]["release_truth_runtime_overlay_root"] = public_edge_runtime_observation.get("overlay_root")
            required_gates[name]["release_truth_runtime_active_lock_count"] = public_edge_runtime_observation.get("active_lock_count")
            required_gates[name]["release_truth_runtime_foreign_lock_count"] = public_edge_runtime_observation.get("foreign_lock_count")
            required_gates[name]["release_truth_runtime_stale_foreign_lock_count"] = public_edge_runtime_observation.get("stale_foreign_lock_count")
            required_gates[name]["release_truth_runtime_blocking_findings"] = normalized_string_list(
                public_edge_runtime_observation.get("blocking_findings")
            )
            required_gates[name]["release_truth_runtime_failures"] = list(public_edge_release_truth_runtime_failure_lines)
            required_gates[name]["missingRequiredFields"] = missing_postdeploy_fields
            required_gates[name]["semanticFailures"] = list(postdeploy_semantic_failures)
            required_gates[name]["semanticFailures"].extend(postdeploy_release_channel_alignment_failures)
            required_gates[name]["receiptFailures"] = public_edge_receipt_failures
            required_gates[name]["nonPreflightReceiptFailures"] = public_edge_non_preflight_receipt_failures
            required_gates[name]["failures"] = list(public_edge_non_preflight_receipt_failures)
            required_gates[name]["failures"].extend(postdeploy_semantic_failures)
            required_gates[name]["failures"].extend(postdeploy_release_channel_alignment_failures)
            for failure in public_edge_release_truth_runtime_failure_lines:
                append_unique_failure(required_gates[name], failure)
            if public_edge_non_preflight_receipt_failures:
                if f"{name} failed" not in failures:
                    failures.append(f"{name} failed")
                required_gates[name]["pass"] = False
                required_gates[name]["status"] = "fail"
            if public_edge_release_truth_runtime_failure_lines:
                if "public_edge_postdeploy_gate release truth failed" not in failures:
                    failures.append("public_edge_postdeploy_gate release truth failed")
                required_gates[name]["pass"] = False
                required_gates[name]["status"] = "fail"
            if postdeploy_release_channel_alignment_failures:
                if f"{name} semantic proof failed" not in failures:
                    failures.append(f"{name} semantic proof failed")
                required_gates[name]["pass"] = False
                required_gates[name]["status"] = "fail"
            if (
                public_edge_contract_name == PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME
                and not missing_postdeploy_fields
                and not postdeploy_semantic_failures
                and not postdeploy_release_channel_alignment_failures
                and not public_edge_non_preflight_receipt_failures
                and not public_edge_release_truth_runtime_failure_lines
            ):
                required_gates[name]["pass"] = True
                required_gates[name]["status"] = "pass"
                required_gates[name]["release_blocking_recovered_from_preflight"] = (
                    normalized_token(payload.get("preflightStatus")) != "pass"
                    or int_value(payload.get("preflightBlockingLockCount")) != 0
                )
                required_gates[name]["failures"] = []
        if name == "teable_important_work" and receipt_loaded:
            teable_summary = teable_important_work_sync_summary(payload)
            required_gates[name]["summary"] = teable_summary
            if not teable_summary["pass"]:
                if required_gates[name]["pass"]:
                    failures.append(f"{name} sync not passed")
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
        if name == "flagship_product_readiness" and receipt_loaded:
            required_gates[name]["verdict"] = payload.get("verdict")
            flagship_summary = flagship_product_readiness_summary(payload)
            required_gates[name]["summary"] = flagship_summary
            flagship_semantic_failures = flagship_product_readiness_gate_semantic_failures(flagship_summary)
            required_gates[name]["semanticFailures"] = flagship_semantic_failures
            for failure in flagship_semantic_failures:
                append_unique_failure(required_gates[name], failure)
            if not flagship_summary["pass"]:
                if required_gates[name]["pass"]:
                    failures.append(f"{name} failed")
                required_gates[name]["pass"] = False
                if status_value in {"pass", "passed", "ready"}:
                    required_gates[name]["status"] = "fail"
        if name == "external_distribution_mirror_proof" and receipt_loaded:
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
                windows_runtime_refresh_authorized = (
                    str(verifier.get("status") or "").strip().lower() == "pass"
                    and verifier.get("recovery_pack_pass") is True
                    and verifier.get("runtime_refresh_commands_trusted") is True
                    and not normalized_string_list(verifier.get("issues"))
                )
                required_gates[name]["operator_request_artifacts"] = windows_operator_request_artifacts(
                    windows_request_path,
                    windows_request_payload,
                    refresh_runtime_receipts=refresh_windows_runtime_receipts,
                    runtime_refresh_authorized=windows_runtime_refresh_authorized,
                )
                required_gates[name]["operator_request_artifacts"][
                    "runtime_refresh_authorized"
                ] = windows_runtime_refresh_authorized
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
                    required_gates[name]["operator_request_artifacts"].get(
                        "operator_action_still_required"
                    )
                    or verifier.get("operator_action_still_required")
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
        if name == "operator_release_dashboard" and gate.get("missing_required_checks"):
            lines.append(f"  - missing dashboard checks: {', '.join(str(item) for item in gate['missing_required_checks'])}")
        if name == "operator_release_dashboard" and gate.get("missing_required_check_fields"):
            lines.append(f"  - missing dashboard check fields: {', '.join(str(item) for item in gate['missing_required_check_fields'])}")
        if name == "operator_release_dashboard" and gate.get("stale_required_checks"):
            lines.append(f"  - stale dashboard checks: {', '.join(str(item) for item in gate['stale_required_checks'])}")
        if name == "operator_release_dashboard" and gate.get("failed_required_checks"):
            lines.append(f"  - failing dashboard checks: {', '.join(str(item) for item in gate['failed_required_checks'])}")
        if name == "operator_release_dashboard" and gate.get("contradictory_required_checks"):
            lines.append(f"  - contradictory dashboard checks: {', '.join(str(item) for item in gate['contradictory_required_checks'])}")
        if name == "operator_release_dashboard" and gate.get("nonblocking_required_checks"):
            lines.append(f"  - nonblocking dashboard checks: {', '.join(str(item) for item in gate['nonblocking_required_checks'])}")
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
    payload = build_payload(
        command_results,
        refresh_windows_runtime_receipts=not (
            args.skip_windows_runtime_refresh or args.skip_materializers
        ),
        refresh_flagship_product_readiness_gate_receipt=not args.skip_materializers,
    )
    if args.skip_materializers:
        payload["materializers"] = []
        payload["materializers_skipped"] = True
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
