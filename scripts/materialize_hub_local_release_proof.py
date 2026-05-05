#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


M102_SUCCESSOR_FRONTIER_ID = 2897065929
M102_ACTIVE_FLAGSHIP_FRONTIER_ID = 2594403904
M102_FRONTIER_IDS = [M102_SUCCESSOR_FRONTIER_ID, M102_ACTIVE_FLAGSHIP_FRONTIER_ID]


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_payload(payload: dict) -> dict:
    stable = dict(payload)
    stable.pop("generated_at", None)
    stable.pop("generatedAt", None)
    return stable


def _load_existing_payload(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _parse_int_env(*names: str, default: int) -> int:
    for name in names:
        raw = str(os.environ.get(name) or "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value >= 0:
            return value
    return default


def _parse_iso_timestamp(raw_value: str | None) -> dt.datetime | None:
    if not raw_value:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _payload_is_fresh(payload: dict, *, max_age_seconds: int, max_future_skew_seconds: int) -> bool:
    raw_generated_at = str(payload.get("generatedAt") or payload.get("generated_at") or "").strip() or None
    generated_at = _parse_iso_timestamp(raw_generated_at)
    if generated_at is None:
        return False

    age_seconds = int((dt.datetime.now(dt.timezone.utc) - generated_at).total_seconds())
    if age_seconds < 0:
        return abs(age_seconds) <= max_future_skew_seconds
    return age_seconds <= max_age_seconds


def main() -> int:
    if len(sys.argv) != 6:
        print(
            "usage: materialize_hub_local_release_proof.py <out_path> <base_url> <compose_file> <timeout_seconds> <skip_rebuild>",
            file=sys.stderr,
        )
        return 1

    out_path_text, base_url, compose_file, timeout_seconds, skip_rebuild = sys.argv[1:]
    out_path = Path(out_path_text)
    proof_max_age_seconds = _parse_int_env(
        "CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS",
        "CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS",
        default=86400,
    )
    proof_max_future_skew_seconds = _parse_int_env(
        "CHUMMER_VERIFY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
        "CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
        default=300,
    )

    successor_queue_packages = [
        {
            "package_id": "next90-m102-hub-desktop-native-trust",
            "milestone_id": 102,
            "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
            "frontier_ids": M102_FRONTIER_IDS,
            "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
            "landed_commit": "160af58f",
            "title": "Unify claim, install, update, and support recovery into one desktop-native flow",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "desktop_native_claim_and_recovery",
                "support_followthrough:install_truth",
            ],
            "exit_criterion": "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
        },
        {
            "package_id": "next90-m107-hub-artifact-factory",
            "milestone_id": 107,
            "frontier_id": 1421219975,
            "task": "Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W9",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M107 chummer6-hub artifact factory orchestration is complete; future shards must verify this receipt, registry row, Fleet queue row, and design queue row instead of reopening the artifact-factory orchestration and public proof shelf release-bundles package.",
            "landed_commit": "b9e6b52e",
            "title": "Stand up artifact-factory orchestration for release, support, and publication bundles",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "artifact_factory:orchestration",
                "public_proof_shelf:release_bundles",
            ],
            "exit_criterion": "Release, fix, support, and publication explainers can ship as approved video, audio, preview, and packet bundles from the same underlying release and support truth.",
        },
        {
            "package_id": "next90-m108-hub-campaign-briefing-bundles",
            "milestone_id": 108,
            "frontier_id": 1639715882,
            "repo": "chummer6-hub",
            "task": "Turn approved campaign primer and mission packs into locale-matched cold-open and briefing requests with audience-safe proof anchors.",
            "status": "complete",
            "wave": "W10",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M108 chummer6-hub campaign briefing bundle composition is complete; future shards must verify the API orchestration service, launcher proof guard, focused tests, and queue/registry rows instead of reopening this package.",
            "landed_commit": "d0a84683",
            "title": "Compose campaign cold-open and mission-briefing bundles from approved packs",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "campaign_cold_open_pack",
                "mission_briefing_reel",
            ],
            "exit_criterion": "Approved campaign primer and mission packs launch locale-matched cold-open and briefing artifact requests with audience-safe proof anchors and stable public shelf refs.",
        },
        {
            "package_id": "next90-m110-hub-runsite-orientation-requests",
            "milestone_id": 110,
            "frontier_id": 1545739925,
            "repo": "chummer6-hub",
            "task": "Compose governed runsite orientation requests from approved runsite packs, route summaries, and preview-safe pre-session truth.",
            "status": "complete",
            "wave": "W10",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M110 chummer6-hub runsite orientation requests are complete; future shards must verify the governed composition route, generated proof receipts, and queue/registry rows instead of reopening this package.",
            "title": "Compose runsite orientation requests from approved runsite packs and route summaries",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "runsite_orientation_requests",
                "route_summary:artifact_launch",
            ],
            "exit_criterion": "Compose governed runsite orientation requests from approved runsite packs, route summaries, and preview-safe pre-session truth.",
        },
        {
            "package_id": "next90-m105-hub-workspace-continuity",
            "milestone_id": 105,
            "frontier_id": 4623636482,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.",
            "landed_commit": "4d4b3856",
            "title": "Emit provenance and conflict receipts for workspace restore and continuity",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "workspace_restore:provenance",
                "entitlement_sync:conflict_receipts",
            ],
            "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
        },
        {
            "package_id": "next90-m111-hub-support-concierge",
            "milestone_id": 111,
            "frontier_id": 2746902416,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M111 chummer6-hub support concierge is complete; future shards must verify the authenticated concierge packet route, generated proof receipts, verifier, and queue/registry rows instead of reopening this package.",
            "landed_commit": "3fb14923",
            "title": "Emit install-aware release and support concierge packets from installed-build truth",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "install_aware_support_concierge",
                "release_concierge:hub",
            ],
            "exit_criterion": "Compile support closure and release explainer packets from installed build, channel, and support-case truth.",
        },
        {
            "package_id": "next90-m112-hub-campaign-consequence-truth",
            "work_task_id": "112.1",
            "milestone_id": 112,
            "frontier_id": 4730880976,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W11",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M112 chummer6-hub campaign consequence truth is complete; future shards must verify the governed campaign consequence proof, local release proof receipts, registry row, queue row, and design queue row instead of reopening this package.",
            "landed_commit": "f2b0b5a6",
            "title": "Promote campaign consequence state into governed campaign APIs",
            "task": "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "campaign_memory:consequence_truth",
                "downtime_aftermath:api",
            ],
            "exit_criterion": "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.",
        },
        {
            "package_id": "next90-m114-hub-rule-environment-receipts",
            "work_task_id": "114.3",
            "milestone_id": 114,
            "frontier_id": 4934642390,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W12",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M114 chummer6-hub rule-environment receipts are complete; future shards must verify this package receipt, registry row, queue row, and design-queue row instead of reopening the campaign/support/install-aware receipt lane.",
            "task": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts.",
            "title": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "campaign_rule_environment_receipts",
                "support_rule_environment_receipts",
                "install_aware_support_receipts",
            ],
            "exit_criterion": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts.",
        },
        {
            "package_id": "next90-m117-hub-artifact-shelf-v2",
            "work_task_id": "117.1",
            "milestone_id": 117,
            "frontier_id": 4041187890,
            "repo": "chummer6-hub",
            "status": "in_progress",
            "wave": "W13",
            "task": "Serve personal, campaign, creator, and public artifact shelves with proof, preview, captions, sibling packets, audience, locale, retention, and publication state.",
            "title": "Build artifact shelf APIs and audience filters",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "artifact_shelf:v2",
                "artifact_audience_filters",
            ],
            "exit_criterion": "Serve personal, campaign, creator, and public artifact shelves with proof, preview, captions, sibling packets, audience, locale, retention, and publication state.",
        },
        {
            "package_id": "next90-m119-hub-first-session-onboarding",
            "work_task_id": "119.1",
            "milestone_id": 119,
            "frontier_id": 1130567614,
            "repo": "chummer6-hub",
            "status": "in_progress",
            "wave": "W14",
            "task": "Join install, claim, campaign primer, starter build, briefing, and support-safe recovery into a measured first-session lane.",
            "title": "Orchestrate guided first-playable-session onboarding",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "first_playable_session:onboarding",
                "starter_lane:hub",
            ],
            "exit_criterion": "Join install, claim, campaign primer, starter build, briefing, and support-safe recovery into a measured first-session lane.",
        },
    ]

    payload = {
        "contract_name": "chummer6-hub.local_release_proof",
        "package_repo": "chummer6-hub",
        "status": "passed",
        "successor_queue_package": {
            "package_id": "next90-m105-hub-workspace-continuity",
            "milestone_id": 105,
            "frontier_id": 4623636482,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.",
            "landed_commit": "4d4b3856",
            "title": "Emit provenance and conflict receipts for workspace restore and continuity",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "workspace_restore:provenance",
                "entitlement_sync:conflict_receipts",
            ],
            "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
        },
        "successor_queue_packages": successor_queue_packages,
        "successor_queue_packages_by_id": {
            package["package_id"]: dict(package)
            for package in successor_queue_packages
        },
        "base_url": base_url,
        "compose_file": compose_file,
        "playwright_timeout_seconds": int(timeout_seconds),
        "edge_rebuild_skipped": skip_rebuild.lower() in {"1", "true"},
        "journeys_passed": [
            "install_claim_restore_continue",
            "build_explain_publish",
            "campaign_session_recover_recap",
            "report_cluster_release_notify",
            "organize_community_and_close_loop",
        ],
        "proof_routes": [
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/access",
            "/account/work",
            "/account/support",
            "/contact",
            "/downloads",
            "/downloads/install/avalonia-osx-arm64-installer",
            "/downloads/install/avalonia-win-x64-installer",
        ],
        "proof_receipts": [
            {
                "receipt_id": "desktop_native_claim_and_recovery",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Claim and recovery continuation now have installer/app-native receipts: guided setup is the default, claim codes are recovery fallback only, and the claimed desktop app can call the grant-bound continuation endpoint without a browser redemption ritual.",
                "routes": [
                    "/downloads/install/avalonia-linux-x64-installer/continue.json",
                    "/api/v1/install-linking/continuation",
                    "/account/access",
                ],
                "surfaces": [
                    "desktop_native_claim_and_recovery",
                    "install_claim_restore_continue",
                    "claimed_install_continuation",
                ],
            },
            {
                "receipt_id": "support_followthrough:install_truth",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Support follow-through carries installed build, current release, channel, head, platform, fallback, update, and rollback truth on the same install rail used by the desktop client.",
                "routes": [
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                    "/account/support",
                    "/contact",
                ],
                "surfaces": [
                    "support_followthrough:install_truth",
                    "support_case_install_readiness",
                    "desktop_update_rollback_recovery",
                ],
            },
            {
                "receipt_id": "fleet_and_operator_loop:desktop_native_trust",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Hub publishes implementation-backed desktop-native trust receipts for the fleet/operator loop: claimed installs stay on grant-bound continuation, support follows installed-build truth, and proof refreshes come from verifier-owned scripts and tests rather than worker-state polling.",
                "routes": [
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                    "/api/v1/install-linking/continuation/update",
                    "/api/v1/install-linking/continuation/rollback",
                ],
                "surfaces": [
                    "fleet_and_operator_loop",
                    "desktop_native_claim_and_recovery",
                    "support_followthrough:install_truth",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_desktop_native_trust_receipts.py verifies the M102 generated proof package, owned surfaces, grant-bound native routes, and forbidden operator-helper evidence markers.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_desktop_native_trust_receipts.py fails closed when generated proof drops the fleet_and_operator_loop desktop-native trust receipt.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesVerification/InstallLinkingContinuationVerification.cs exercises continuation, support, update, rollback, recovery, callback, receipt-matching, and support-action sanitization on the claimed desktop rail.",
                ],
            },
            {
                "receipt_id": "public_proof_shelf:release_bundles",
                "package_id": "next90-m107-hub-artifact-factory",
                "milestone_id": 107,
                "frontier_id": 1421219975,
                "summary": "Approved release source packs now launch recipe-backed artifact jobs whose preview, caption, packet, audio, and video outputs bind onto stable public release-bundle shelf refs instead of one-off provider flows.",
                "routes": [
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/artifacts/release-bundles/avalonia-linux-x64-installer",
                    "/artifacts/release-bundles/avalonia-linux-x64-installer/preview_card",
                ],
                "surfaces": [
                    "artifact_factory:orchestration",
                    "public_proof_shelf:release_bundles",
                    "build_explain_publish",
                ],
            },
            {
                "receipt_id": "campaign_cold_open_pack",
                "package_id": "next90-m108-hub-campaign-briefing-bundles",
                "milestone_id": 108,
                "frontier_id": 1639715882,
                "summary": "Approved campaign primers now compose locale-matched cold-open artifact requests with audience-safe proof anchors and stable campaign proof shelf refs instead of ad hoc launch packets.",
                "routes": [
                    "/api/internal/artifact-factory/source-pack-batches",
                    "/api/internal/artifact-factory/recipes",
                    "/artifacts/campaigns/{campaignId}/cold-open",
                    "/artifacts/campaigns/{campaignId}/cold-open/preview_card",
                ],
                "surfaces": [
                    "campaign_cold_open_pack",
                    "campaign_onboarding",
                    "artifact_factory:campaign_cold_open",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs composes campaign_cold_open jobs from approved campaign primer packs with explicit audience and locale validation.",
                    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py fail-closes campaign cold-open responses that omit audience/locale proof anchors or drift off the stable campaign cold-open shelf.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_source_pack_launcher.py covers locale-matched campaign cold-open launches and fail-closed proof-anchor drift.",
                ],
            },
            {
                "receipt_id": "mission_briefing_reel",
                "package_id": "next90-m108-hub-campaign-briefing-bundles",
                "milestone_id": 108,
                "frontier_id": 1639715882,
                "summary": "Approved mission packs now compose locale-matched briefing artifact requests with audience-safe proof anchors and stable mission briefing shelf refs before media-factory launch.",
                "routes": [
                    "/api/internal/artifact-factory/source-pack-batches",
                    "/api/internal/artifact-factory/recipes",
                    "/artifacts/missions/{missionId}/briefing",
                    "/artifacts/missions/{missionId}/briefing/preview_card",
                ],
                "surfaces": [
                    "mission_briefing_reel",
                    "campaign_onboarding",
                    "artifact_factory:mission_briefing",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs composes mission_briefing jobs from approved mission packs with explicit audience and locale validation.",
                    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py fail-closes mission briefing responses that omit audience/locale proof anchors or drift off the stable mission briefing shelf.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_source_pack_launcher.py covers locale-matched mission briefing launches and fail-closed proof-anchor drift.",
                ],
            },
            {
                "receipt_id": "runsite_orientation_requests",
                "package_id": "next90-m110-hub-runsite-orientation-requests",
                "milestone_id": 110,
                "frontier_id": 1545739925,
                "summary": "Approved runsite packs now compose governed host clips, tour siblings, audio companions, and preview-safe pre-session truth through one internal runsite orientation request contract before downstream media launch.",
                "routes": [
                    "/api/internal/runsite-orientation/requests",
                    "/artifacts/routes/{routeSummaryId}/{routeSegmentId}",
                ],
                "surfaces": [
                    "runsite_orientation_requests",
                    "runsite_orientation_bundle",
                    "preview_safe_truth:pre_session",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs composes governed runsite orientation bundles from approved packs, route summaries, and preview-safe inspectable truth refs.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs exposes the bounded internal request route and rejects unauthorized or malformed orientation requests.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_runsite_orientation_requests.py covers composed bundle output, preview-safe evidence anchors, duplicate-deduplication rejection, and queue/registry proof drift.",
                ],
            },
            {
                "receipt_id": "route_summary:artifact_launch",
                "package_id": "next90-m110-hub-runsite-orientation-requests",
                "milestone_id": 110,
                "frontier_id": 1545739925,
                "summary": "Route summaries remain the only authority for runsite route previews: route preview artifacts stay inspectable, preview-safe, and route-summary governed even when approved packs provide the rest of the orientation bundle.",
                "routes": [
                    "/api/internal/runsite-orientation/requests",
                    "/artifacts/routes/{routeSummaryId}/{routeSegmentId}",
                ],
                "surfaces": [
                    "route_summary:artifact_launch",
                    "route_preview:inspectable_truth",
                    "runsite_orientation_bundle",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs rejects pack-owned route preview templates and forces route-summary route preview categories to remain inspectable and preview-safe.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Tests/RunsiteOrientationRequestComposerServiceTests.cs proves route previews stay route-summary governed and that internal authorization still gates the composition route.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_runsite_orientation_requests.py fail-closes missing route_summary:artifact_launch proof, weakened closure metadata, or worker-unsafe queue and registry evidence.",
                ],
            },
            {
                "receipt_id": "workspace_restore:provenance",
                "package_id": "next90-m105-hub-workspace-continuity",
                "milestone_id": 105,
                "frontier_id": 4623636482,
                "summary": "Workspace restore continuity emits provenance receipts and typed recovery actions for claimed installs, recent artifacts, rule environments, and restore inventory on the shared account workspace surfaces.",
                "routes": [
                    "/home/work",
                    "/account/work",
                    "/account/access",
                ],
                "surfaces": [
                    "workspace_restore:provenance",
                    "workspace_restore:recoverable_actions",
                    "workspace_restore",
                    "account_workspace_detail",
                ],
            },
            {
                "receipt_id": "entitlement_sync:conflict_receipts",
                "package_id": "next90-m105-hub-workspace-continuity",
                "milestone_id": 105,
                "frontier_id": 4623636482,
                "summary": "Entitlement drift, stale claims, missing grants, and continue-blocking conflicts emit recoverable receipts and typed account-access actions on the same restore lane instead of falling back to support folklore.",
                "routes": [
                    "/home/work",
                    "/account/work",
                    "/account/access",
                    "/downloads",
                ],
                "surfaces": [
                    "entitlement_sync:conflict_receipts",
                    "entitlement_sync:recoverable_actions",
                    "entitlement_sync",
                    "workspace_restore",
                ],
            },
            {
                "receipt_id": "install_aware_support_concierge",
                "package_id": "next90-m111-hub-support-concierge",
                "milestone_id": 111,
                "frontier_id": 2746902416,
                "summary": "Hub now compiles authenticated support closure packets from support-case truth, installed build, release channel, claimed install context, and installed-build receipt ids instead of queued support status alone.",
                "routes": [
                    "/api/v1/support/cases/{caseId}/concierge",
                    "/api/v1/install-linking/continuation/support",
                    "/account/support",
                    "/account/access",
                ],
                "surfaces": [
                    "install_aware_support_concierge",
                    "support_case_install_readiness",
                    "support_closure_packets",
                ],
            },
            {
                "receipt_id": "release_concierge:hub",
                "package_id": "next90-m111-hub-support-concierge",
                "milestone_id": 111,
                "frontier_id": 2746902416,
                "summary": "Hub release concierge packets explain why the current or fixed release is correct for the reporter's installed build and channel, while public wrappers stay bounded to first-party support and download routes.",
                "routes": [
                    "/api/v1/support/cases/{caseId}/concierge",
                    "/now",
                    "/status",
                    "/help",
                    "/downloads",
                    "/downloads/install/{artifactId}",
                    "/api/v1/install-linking/continuation",
                ],
                "surfaces": [
                    "release_concierge:hub",
                    "release_explainer_packets",
                    "public_concierge_trust_wrapper",
                ],
            },
            {
                "receipt_id": "campaign_memory:consequence_truth",
                "package_id": "next90-m112-hub-campaign-consequence-truth",
                "milestone_id": 112,
                "frontier_id": 4730880976,
                "summary": "Campaign memory and governed consequence truth now stay on one bounded return-loop lane so heat, faction, contact, reputation, downtime, and aftermath posture remain inspectable on the signed-in work surface.",
                "routes": [
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/campaign-memory",
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/consequence-truth",
                    "/account/work#campaign-consequences",
                ],
                "surfaces": [
                    "campaign_memory:consequence_truth",
                    "campaign_consequence_truth",
                    "campaign_return_loop",
                ],
            },
            {
                "receipt_id": "downtime_aftermath:api",
                "package_id": "next90-m112-hub-campaign-consequence-truth",
                "milestone_id": 112,
                "frontier_id": 4730880976,
                "summary": "Downtime and aftermath state now ship with governed package receipts, explicit return-loop actions, and one aftermath rail instead of recap prose alone.",
                "routes": [
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/aftermath-recap-packages",
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/downtime-aftermath",
                    "/account/work#aftermath-packages",
                ],
                "surfaces": [
                    "downtime_aftermath:api",
                    "governed_aftermath_package",
                    "return_loop_action",
                ],
            },
            {
                "receipt_id": "campaign_rule_environment_receipts",
                "package_id": "next90-m114-hub-rule-environment-receipts",
                "milestone_id": 114,
                "frontier_id": 4934642390,
                "summary": "Campaign rules answers, workspace readiness cues, and rule-environment studio lifecycle all keep the same explain-entry receipts visible on signed-in campaign surfaces instead of splitting campaign truth into separate support-only interpretations.",
                "routes": [
                    "/home",
                    "/account/work",
                    "/api/v1/campaign-spine/me",
                    "/api/v1/campaign-spine/me/rules/{entryId}",
                ],
                "surfaces": [
                    "campaign_rule_environment_receipts",
                    "rules_navigator",
                    "rule_environment_studio:hub",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs projects rules navigator answers with stable ExplainEntryId values, before/after diffs, and rule-environment studio lifecycle posture on the signed-in campaign rail.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves signed-in account and home surfaces keep grounded rules navigator answers and studio stages visible.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m114_hub_rule_environment_receipts.py fail-closes queue, registry, and proof drift if campaign rule-environment receipts stop sharing the same explain-entry ids with support diagnostics.",
                ],
            },
            {
                "receipt_id": "support_rule_environment_receipts",
                "package_id": "next90-m114-hub-rule-environment-receipts",
                "milestone_id": 114,
                "frontier_id": 4934642390,
                "summary": "Signed-in support assistant answers now carry the same rule-environment explain-entry receipts that campaign surfaces expose, so support questions about visibility, permissions, and campaign return posture cite campaign-owned rules truth instead of parallel help copy.",
                "routes": [
                    "/api/v1/support/cases/assistant",
                    "/home",
                    "/api/v1/campaign-spine/me/rules/{entryId}",
                ],
                "surfaces": [
                    "support_rule_environment_receipts",
                    "support_assistant",
                    "rules_truth",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Support/SupportAssistantService.cs forwards RulesNavigator ExplainEntryId values into support citations for grounded rules questions.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Control.Contracts/SupportContracts.cs preserves optional citation receipt ids so support routes can name the same explain receipts without inventing a second contract.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves rules-truth assistant answers expose the same explain receipt ids surfaced by campaign rules navigator entries.",
                ],
            },
            {
                "receipt_id": "install_aware_support_receipts",
                "package_id": "next90-m114-hub-rule-environment-receipts",
                "milestone_id": 114,
                "frontier_id": 4934642390,
                "summary": "Install-aware support diagnostics keep installation-scoped support questions on the same receipt-backed rule-environment lane, so signed-in assistant answers can pivot from a linked install back to the grounded campaign or build explain receipt instead of drifting into install-only folklore.",
                "routes": [
                    "/api/v1/support/cases/assistant",
                    "/account/access",
                    "/account/work",
                    "/home",
                ],
                "surfaces": [
                    "install_aware_support_receipts",
                    "support_assistant",
                    "install_aware_diagnostics",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Support/SupportAssistantService.cs keeps installation-aware rules and build questions tied to open_home and open_work actions while carrying shared explain-entry receipt ids.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves install-aware rules and build assistant requests route back to the signed-in home and work surfaces instead of a detached diagnostic lane.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m114_hub_rule_environment_receipts.py rejects release-proof drift when install-aware support receipts stop naming the shared rule-environment support lane.",
                ],
            },
            {
                "receipt_id": "artifact_shelf:v2",
                "package_id": "next90-m117-hub-artifact-shelf-v2",
                "milestone_id": 117,
                "frontier_id": 4041187890,
                "summary": "Hub now serves one governed artifact shelf lane for signed-in personal, campaign, creator, and public views, keeping recap lineage, publication state, trust posture, and public publication detail on the same inspectable surface instead of splitting them into unrelated routes.",
                "routes": [
                    "/artifacts",
                    "/api/v1/public/artifacts/shelf",
                    "/artifacts/publications/{publicationId}",
                    "/api/v1/public/artifacts/publications/{publicationId}",
                    "/home/work",
                    "/account/work",
                ],
                "surfaces": [
                    "artifact_shelf:v2",
                    "artifact_shelf_api",
                    "signed_in_return_shelf",
                    "public_creator_discovery",
                    "creator_publication_detail",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs serves the governed artifact shelf, public shelf APIs, public creator publication detail route, and signed-in overlay projections from one bounded controller path.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs keeps public creator discovery published-only and manifest-authority-backed before the shared shelf surfaces it.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml renders signed-in return shelf entries and public creator discovery with audience, publication, trust, discovery, lineage, moderation, and next-step posture kept together.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves personal, campaign, creator, and public artifact views plus the mirrored shelf APIs keep proof, preview, caption, sibling-packet, locale, retention, and publication-state truth visible on the shared shelf.",
                ],
            },
            {
                "receipt_id": "artifact_audience_filters",
                "package_id": "next90-m117-hub-artifact-shelf-v2",
                "milestone_id": 117,
                "frontier_id": 4041187890,
                "summary": "Signed-in artifact shelf filters now fail closed to all, personal, campaign, or creator while workspace and campaign projections stamp recap entries with audience and publication posture before the public shelf renders them.",
                "routes": [
                    "/artifacts",
                    "/home/work",
                    "/account/work",
                ],
                "surfaces": [
                    "artifact_audience_filters",
                    "artifact_view:all",
                    "artifact_view:personal",
                    "artifact_view:campaign",
                    "artifact_view:creator",
                    "artifact_view:public",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs normalizes the signed-in view query, filters recap and creator-publication overlays, and falls unknown filters back to the all-views shelf.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs and CampaignSpineService.cs stamp creator-linked recap entries with campaign, personal, and creator audience plus publication state before the shelf view filters them.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs requires approved manifest-backed audit authority before creator-publication moderation and publication can widen onto the public shelf.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m117_hub_artifact_shelf_v2.py fail-closes queue, registry, and source-proof drift if artifact shelf audience filtering or signed-in view controls regress.",
                ],
            },
            {
                "receipt_id": "first_playable_session:onboarding",
                "package_id": "next90-m119-hub-first-session-onboarding",
                "milestone_id": 119,
                "frontier_id": 1130567614,
                "summary": "Hub now keeps signed-in install return, starter-workspace seeding, campaign-primer-backed first-session proof, and support-safe recovery on one bounded first-playable-session onboarding lane instead of a separate onboarding ritual.",
                "routes": [
                    "/home",
                    "/home/work",
                    "/account/work",
                    "/api/v1/campaign-spine/me",
                    "/api/v1/campaign-spine/me/workspaces/starter",
                ],
                "surfaces": [
                    "first_playable_session:onboarding",
                    "campaign_onboarding",
                    "install_claim_restore_continue",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs exposes the bounded starter-workspace seeding route so the signed-in starter lane reuses campaign-spine truth instead of inventing a second onboarding API.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs projects first-playable-session summaries, legal-runner proof, understandable-return proof, and primer-safe publication titles on the same campaign return lane.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves landing, home, account, and starter-workspace API surfaces keep the first-session lane grounded on the shared campaign projection.",
                ],
            },
            {
                "receipt_id": "starter_lane:hub",
                "package_id": "next90-m119-hub-first-session-onboarding",
                "milestone_id": 119,
                "frontier_id": 1130567614,
                "summary": "The hub-owned starter lane now gives signed-in users one calmer route from linked install into first-session proof, build follow-through, campaign-primer follow-through, and install support without hiding the next safe action behind deeper admin-only pages.",
                "routes": [
                    "/home/work",
                    "/account/work",
                    "/account/access",
                    "/contact",
                ],
                "surfaces": [
                    "starter_lane:hub",
                    "first_session:proof_drawer",
                    "starter_build:follow_through",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml wires starter-workspace seeding to the campaign-spine starter endpoint and keeps first-session proof, build-path follow-through, and claimed-device return on the signed-in Home rail.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml keeps the selected first-session drawer, legal-runner and return proof, and install-support follow-through on the shared account work route.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs promotes the starter lane as the primary signed-in action when a linked install exists but shared campaign work has not been seeded yet.",
                ],
            },
        ],
    }

    existing_payload = _load_existing_payload(out_path)
    if (
        existing_payload is not None
        and _stable_payload(existing_payload) == _stable_payload(payload)
        and _payload_is_fresh(
            existing_payload,
            max_age_seconds=proof_max_age_seconds,
            max_future_skew_seconds=proof_max_future_skew_seconds,
        )
    ):
        print(f"hub local proof unchanged and still fresh: {out_path}")
        return 0

    generated_at = iso_now()
    payload["generated_at"] = generated_at
    payload["generatedAt"] = generated_at

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote hub local proof: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
