#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_ea_operator_readiness import verify_receipt as verify_ea_operator_readiness_receipt
from verify_host_workload_runtime_health import verify_receipt as verify_host_workload_runtime_health_receipt
from verify_qbittorrent_staging_hygiene import verify_receipt as verify_qbittorrent_staging_hygiene_receipt
from verify_google_oauth_linking_proof import verify as verify_google_oauth_linking_proof_receipt
from verify_mymedia_public_surface import verify as verify_mymedia_public_surface_receipt
from verify_windows_installer_visual_audit_intake_request import (
    verify as verify_windows_visual_intake_request_receipt,
)
from public_edge_postdeploy_contract import (
    PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME,
    PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS,
    normalize_public_edge_postdeploy_payload,
    public_edge_v2_offline_failures,
    public_edge_v2_private_identity_failures,
)


ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = ROOT / "chummer.run-services"
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND = [
    "python3",
    "scripts/verify_flagship_product_readiness_gate.py",
    "--summary-output",
    str(DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH),
]
TELEGRAM_TEXT_DELIVERY_ROOT = ROOT / "_completion" / "telegram_text_delivery"
COMPLETION_ROOT = ROOT / "_completion" / "chummer_run_redesign_closure"
REGISTRY_ROOT = ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
PUBLIC_RELEASE_SNAPSHOT_PATH = ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT.generated.json"
PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH = ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
ROOT_RELEASE_BLOCKERS_PATH = ROOT / "RELEASE_BLOCKERS.generated.json"
DEFAULT_SUPPLY_CHAIN_RELEASE_GATE_PATH = (
    ROOT / ".codex-studio" / "published" / "SUPPLY_CHAIN_RELEASE_GATE.generated.json"
)
WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES = (
    ROOT / "chummer.run-services" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer-presentation" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer6-ui" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer-presentation" / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer6-ui" / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
)
WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES = (
    ROOT / "chummer-presentation" / ".codex-studio" / "published" / "BLAZOR_PLAY_SURFACE_HORIZON.generated.json",
    ROOT / "chummer6-ui" / ".codex-studio" / "published" / "BLAZOR_PLAY_SURFACE_HORIZON.generated.json",
)
OUTPUT_JSON = PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json"
OUTPUT_MD = PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.md"
WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
RELEASE_BLOCKING_MAX_AGE_HOURS = 24
READY_VERDICT = "READY"
DESIGN_READY_VERDICT = "DESIGN_READY"
RELEASE_READY_CONTRACT_NAME = "chummer.release_ready"
RELEASE_READY_VERDICT = "RELEASE_READY"
FLAGSHIP_PRODUCT_READY_VERDICT = "FLAGSHIP_PRODUCT_READY"
FLAGSHIP_PRODUCT_NOT_READY_VERDICT = "NOT_FLAGSHIP_PRODUCT_READY"
WINDOWS_INSTALLER_VISUAL_AUDIT_CONTRACT_NAME = "chummer.windows_installer_visual_audit"
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
PORTABLE_RECEIPTS_AUDIT_CONTRACT_NAME = "chummer.run.portable_receipts_audit"
SUPPLY_CHAIN_RELEASE_GATE_CONTRACT_NAME = "chummer6.supply_chain_release_gate.v1"
PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE_CONTRACT_NAME = (
    "chummer.public_edge_observability_release_gate.v1"
)
SUPPLY_CHAIN_REQUIRED_CHECKS = {
    "container_vulnerability_audit",
    "dependency_vulnerability_audit",
    "provenance",
    "sbom",
    "secret_scan",
}
PUBLIC_EDGE_OBSERVABILITY_REQUIRED_CHECKS = {
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
}
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
FRESHNESS_REQUIRED_CHECKS = {
    "account_handoff_runtime_config",
    "design_quality_gate",
    "external_distribution_mirror_proof",
    "flagship_product_readiness",
    "google_oauth_linking_proof",
    "participate_billing_honesty",
    "portable_receipts_audit",
    "public_copy_leak_gate",
    "public_edge_observability_release_gate",
    "public_edge_postdeploy_gate",
    "public_route_proof",
    "release_ready",
    "ruleset_readiness",
    "supply_chain_release_gate",
    "teable_important_work",
    "ui_frame_integrity",
    "windows_installer_visual_audit",
}


def _effective_freshness_required_checks() -> set[str]:
    checks = set(FRESHNESS_REQUIRED_CHECKS)
    if IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        checks.discard("windows_installer_visual_audit")
    return checks


def _effective_required_checks(checks: dict[str, Any]) -> set[str]:
    required = {
        name
        for name, data in checks.items()
        if isinstance(data, dict) and data.get("release_blocking", True) is not False
    }
    if IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        required.discard("windows_installer_visual_audit")
    return required


CONTEXT_FRESHNESS_CHECKS = {
    "blazor_execution_horizon_bridge",
    "ea_operator_readiness",
    "host_workload_runtime_health",
    "mymedia_public_surface",
}
ROOT_BLOCKER_LOCAL_SURFACE_CHECKS = (
    "account_handoff_runtime_config",
    "blazor_execution_horizon_bridge",
    "design_quality_gate",
    "participate_billing_honesty",
    "public_copy_leak_gate",
    "public_edge_postdeploy_gate",
    "public_route_proof",
    "ruleset_readiness",
    "teable_important_work",
    "ui_frame_integrity",
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
PUBLIC_EDGE_LIVE_ALIAS_BASE_URL = "https://chummer.run"
PUBLIC_EDGE_LIVE_ALIAS_TIMEOUT_SECONDS = 5.0
PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_COUNT = 3
PUBLIC_EDGE_REQUIRED_PARTICIPATE_IFRAME_ROUTES = 2
PUBLIC_EDGE_REQUIRED_PWA_MANIFEST_COUNT = 3
PUBLIC_EDGE_MINIMUM_PWA_ASSET_COUNT = 1
RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE = "gold_supported"
RELEASE_CHANNEL_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
RELEASE_CHANNEL_PUBLIC_STABLE_ROLLOUT_STATE = "public_stable"
RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "public_release_review_required",
    "desktop_polish_needed",
    "revoked",
}
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


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def refresh_flagship_product_readiness_gate(path: Path) -> None:
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


def load_json_with_status(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "invalid"
    if not isinstance(parsed, dict):
        return {}, "invalid"
    return parsed, "loaded"


def generated_at_is_fresh(value: object, max_age_hours: int = RELEASE_BLOCKING_MAX_AGE_HOURS) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        generated_at = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return False
    return generated_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def is_pass(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"pass", "passed", "ready"}


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


def normalize_base_url(value: object) -> str:
    return str(value or "").strip().rstrip("/")


def public_safe_base_url(value: object) -> str | None:
    base_url = normalize_base_url(value)
    parsed = urlparse(base_url)
    if parsed.scheme == "https" and parsed.netloc.lower() == "chummer.run":
        return base_url
    return None


def customer_safe_release_text(value: object) -> str:
    text = str(value or "").strip()
    replacements = (
        ("Current release proof is green", "Current release checks are clear"),
        ("proof is green", "release checks are clear"),
        ("startup-smoke proof", "startup verification"),
        ("startup-smoke", "startup verification"),
        ("executable-gate proof", "executable verification"),
        ("executable-gate", "executable"),
        ("promoted flagship bytes", "promoted release packages"),
        ("proof", "checks"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
        text = text.replace(old.capitalize(), new.capitalize())
    return text


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


def probe_public_edge_live_role_alias_routes(
    *,
    base_url: str = PUBLIC_EDGE_LIVE_ALIAS_BASE_URL,
    timeout_seconds: float = PUBLIC_EDGE_LIVE_ALIAS_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    results: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []
    for alias_path, expected_final_route in PUBLIC_EDGE_REQUIRED_ROLE_ALIAS_ROUTES.items():
        requested_url = f"{normalized_base_url}{alias_path}"
        result: dict[str, Any] = {
            "aliasPath": alias_path,
            "requestedUrl": requested_url,
            "expectedFinalRoute": expected_final_route,
            "httpStatus": None,
            "finalUrl": "",
            "finalRoute": "",
            "pass": False,
            "error": "",
        }
        try:
            request = Request(
                requested_url,
                headers={"User-Agent": "chummer-operator-release-dashboard/1.0"},
            )
            with urlopen(request, timeout=timeout_seconds) as response:
                result["httpStatus"] = int(getattr(response, "status", 0) or 0)
                result["finalUrl"] = response.geturl()
                result["finalRoute"] = route_from_url(result["finalUrl"])
        except Exception as exc:  # pragma: no cover - exact network errors vary by host
            result["error"] = f"{type(exc).__name__}: {exc}"
        result["pass"] = (
            result["httpStatus"] == 200
            and result["finalRoute"] == expected_final_route
            and not result["error"]
        )
        results.append(result)
        if result["pass"] is not True:
            drift.append(result)
    return {
        "status": "pass" if not drift else "fail",
        "checkedAtUtc": now_iso(),
        "baseUrl": normalized_base_url,
        "results": results,
        "drift": drift,
    }


def public_edge_live_role_alias_failures(live_alias_routes: dict[str, Any] | None) -> list[str]:
    if not live_alias_routes:
        return []
    failures: list[str] = []
    if str(live_alias_routes.get("status") or "").strip().lower() != "pass":
        failures.append("public-edge live role alias routes are not pass")
    results = live_alias_routes.get("results") if isinstance(live_alias_routes.get("results"), list) else []
    results_by_alias = {
        str(item.get("aliasPath") or "").strip(): item
        for item in results
        if isinstance(item, dict)
    }
    for alias_path, expected_final_route in PUBLIC_EDGE_REQUIRED_ROLE_ALIAS_ROUTES.items():
        result = results_by_alias.get(alias_path)
        if not result:
            failures.append(f"public-edge live {alias_path} alias route proof is missing")
            continue
        final_route = str(result.get("finalRoute") or route_from_url(result.get("finalUrl"))).strip()
        error = str(result.get("error") or "").strip()
        if error:
            failures.append(f"public-edge live {alias_path} probe failed: {error}")
            continue
        if final_route != expected_final_route or result.get("pass") is not True:
            failures.append(f"public-edge live {alias_path} resolved to {final_route or '<missing>'} instead of {expected_final_route}")
    return failures


def public_edge_receipt_role_alias_routes_proven(payload: dict[str, Any]) -> bool:
    if normalized_token(payload.get("roleAliasRouteStatus")) != "pass":
        return False
    drift = payload.get("roleAliasRouteDrift")
    if isinstance(drift, list) and drift:
        return False
    results = payload.get("roleAliasRouteResults") if isinstance(payload.get("roleAliasRouteResults"), list) else []
    results_by_alias = {
        str(item.get("aliasPath") or "").strip(): item
        for item in results
        if isinstance(item, dict)
    }
    for alias_path, expected_final_route in PUBLIC_EDGE_REQUIRED_ROLE_ALIAS_ROUTES.items():
        result = results_by_alias.get(alias_path)
        if not result:
            return False
        final_route = str(result.get("finalRoute") or route_from_url(result.get("finalUrl"))).strip()
        if final_route != expected_final_route or result.get("pass") is not True:
            return False
    return True


def public_edge_live_role_alias_timeout_only(live_alias_routes: dict[str, Any] | None) -> bool:
    if not live_alias_routes or normalized_token(live_alias_routes.get("status")) == "pass":
        return False
    results = live_alias_routes.get("results") if isinstance(live_alias_routes.get("results"), list) else []
    results_by_alias = {
        str(item.get("aliasPath") or "").strip(): item
        for item in results
        if isinstance(item, dict)
    }
    saw_timeout = False
    for alias_path in PUBLIC_EDGE_REQUIRED_ROLE_ALIAS_ROUTES:
        result = results_by_alias.get(alias_path)
        if not result or result.get("pass") is True:
            continue
        error = str(result.get("error") or "").strip().lower()
        if "timeout" not in error:
            return False
        saw_timeout = True
    return saw_timeout


def contains_tokens(value: object, required_tokens: set[str]) -> bool:
    normalized = str(value or "").lower()
    return all(token in normalized for token in required_tokens)


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def optional_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


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


def release_channel_identity(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "status": normalized_token(payload.get("status")),
        "channel": normalized_token(payload.get("channelId") or payload.get("channel")),
        "version": str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
        "supportability_state": normalized_token(payload.get("supportabilityState")),
        "rollout_state": normalized_token(payload.get("rolloutState")),
    }


def release_channel_identity_text(identity: dict[str, str]) -> str:
    return (
        f"channel={identity.get('channel') or 'missing'}, "
        f"version={identity.get('version') or 'missing'}, "
        f"supportability={identity.get('supportability_state') or 'missing'}, "
        f"rollout={identity.get('rollout_state') or 'missing'}"
    )


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def workspace_portal_release_channel_observations(
    authoritative_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    authoritative_identity = release_channel_identity(authoritative_payload)
    checked: list[dict[str, Any]] = []
    failures: list[str] = []
    seen_paths: set[Path] = set()
    for candidate in WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES:
        path = Path(candidate)
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        local_payload = load_json(resolved_path)
        local_identity = release_channel_identity(local_payload)
        matches_authoritative = local_identity == authoritative_identity
        checked.append(
            {
                "path": display_path(resolved_path),
                "status": local_identity["status"],
                "channel": local_identity["channel"],
                "version": local_identity["version"],
                "supportability_state": local_identity["supportability_state"],
                "rollout_state": local_identity["rollout_state"],
                "matches_authoritative": matches_authoritative,
            }
        )
        if matches_authoritative:
            continue
        failures.append(
            "workspace portal release channel artifact "
            f"{display_path(resolved_path)} disagrees with authoritative registry receipt "
            f"(local {release_channel_identity_text(local_identity)}; "
            f"authoritative {release_channel_identity_text(authoritative_identity)})"
        )
    return checked, failures


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


def flagship_product_readiness_expected_gate_verdict(status: object) -> str:
    return (
        FLAGSHIP_PRODUCT_READY_VERDICT
        if normalized_token(status) in PASS_STATES
        else FLAGSHIP_PRODUCT_NOT_READY_VERDICT
    )


def flagship_product_readiness_gate_semantic_failures(summary: dict[str, Any]) -> list[str]:
    if str(summary.get("source_receipt") or "").strip() != "gate":
        return []
    expected_verdict = flagship_product_readiness_expected_gate_verdict(summary.get("status"))
    actual_verdict = str(summary.get("verdict") or "").strip()
    if actual_verdict == expected_verdict:
        return []
    return [f"flagship_product_readiness gate has unexpected verdict (expected {expected_verdict})"]


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


def release_channel_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    status = normalized_token(payload.get("status"))
    version = str(payload.get("version") or "").strip()
    channel = str(payload.get("channel") or payload.get("channelId") or "").strip()
    normalized_channel = channel.lower()
    supportability_state = normalized_token(payload.get("supportabilityState"))
    rollout_state = normalized_token(payload.get("rolloutState"))

    if status != "published":
        failures.append("release channel status is not published")
    if not version:
        failures.append("release channel version is missing")
    if not channel:
        failures.append("release channel channel is missing")
    elif normalized_channel not in RELEASE_CHANNEL_STABLE_CHANNELS:
        failures.append(f"release channel channel is {normalized_channel}, not a flagship stable lane")
    if supportability_state != RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE:
        failures.append("release channel supportability is not gold_supported")
    if rollout_state in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        failures.append(f"release channel rollout is blocking: {rollout_state}")
    elif rollout_state and rollout_state != RELEASE_CHANNEL_PUBLIC_STABLE_ROLLOUT_STATE:
        failures.append(f"release channel rollout is {rollout_state}, not public_stable")
    return failures


def supply_chain_release_gate_path() -> Path:
    """Return the estate-wide supply-chain gate produced by the root verifier."""

    return DEFAULT_SUPPLY_CHAIN_RELEASE_GATE_PATH


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def portable_receipts_audit_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if str(payload.get("contract_name") or "").strip() != PORTABLE_RECEIPTS_AUDIT_CONTRACT_NAME:
        failures.append("portable_receipts_audit receipt has unexpected contract")

    scanned_count = payload.get("scanned_artifact_count")
    if not _is_nonnegative_int(scanned_count) or int(scanned_count) <= 0:
        failures.append("portable_receipts_audit scanned artifact count is missing or zero")

    failure_counts = payload.get("failure_counts")
    if not isinstance(failure_counts, dict):
        failures.append("portable_receipts_audit failure counts are missing")
        failure_counts = {}

    typed_hits: dict[str, list[str]] = {}
    for field, count_field, label in (
        ("machine_specific_path_hits", "machine_specific_paths", "machine-specific path"),
        ("artifact_integrity_hits", "artifact_integrity", "artifact-integrity"),
    ):
        raw_hits = payload.get(field)
        if not isinstance(raw_hits, list):
            failures.append(f"portable_receipts_audit {label} hits are missing")
            hits: list[str] = []
        else:
            hits = normalized_string_list(raw_hits)
        typed_hits[field] = hits

        reported_count = failure_counts.get(count_field)
        if not _is_nonnegative_int(reported_count):
            failures.append(f"portable_receipts_audit {label} failure count is missing or invalid")
        elif int(reported_count) != len(hits):
            failures.append(f"portable_receipts_audit {label} failure count does not match its hit list")
        if hits:
            failures.append(f"portable_receipts_audit has {len(hits)} {label} failure(s)")

    aggregate_hits_raw = payload.get("machine_specific_hits")
    if not isinstance(aggregate_hits_raw, list):
        failures.append("portable_receipts_audit aggregate failure hits are missing")
    else:
        aggregate_hits = set(normalized_string_list(aggregate_hits_raw))
        expected_hits = set(typed_hits["machine_specific_path_hits"]) | set(
            typed_hits["artifact_integrity_hits"]
        )
        if aggregate_hits != expected_hits:
            failures.append("portable_receipts_audit aggregate failure hits do not match typed failures")

    unreadable_raw = payload.get("unreadable_artifacts")
    if not isinstance(unreadable_raw, list):
        failures.append("portable_receipts_audit unreadable artifact list is missing")
    elif set(normalized_string_list(unreadable_raw)) != set(typed_hits["artifact_integrity_hits"]):
        failures.append("portable_receipts_audit unreadable artifacts do not match integrity failures")

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    for field in (
        "forbid_machine_specific_paths",
        "redact_failure_samples",
        "scan_nested_json_artifacts",
        "fail_on_artifact_integrity_errors",
    ):
        if policy.get(field) is not True:
            failures.append(f"portable_receipts_audit policy does not require {field}")
    return list(dict.fromkeys(failures))


def supply_chain_release_gate_semantic_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if str(payload.get("contract_name") or "").strip() != SUPPLY_CHAIN_RELEASE_GATE_CONTRACT_NAME:
        failures.append("supply_chain_release_gate receipt has unexpected contract")
    if payload.get("pass") is not True:
        failures.append("supply_chain_release_gate pass marker is not true")
    if str(payload.get("verdict") or "").strip() != "SUPPLY_CHAIN_READY":
        failures.append("supply_chain_release_gate verdict is not SUPPLY_CHAIN_READY")

    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        failures.append("supply_chain_release_gate blocker list is missing")
    elif normalized_string_list(blockers):
        failures.append(
            "supply_chain_release_gate blockers remain: "
            + ", ".join(normalized_string_list(blockers))
        )

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        failures.append("supply_chain_release_gate checks are missing")
        checks = {}
    for check_id in sorted(SUPPLY_CHAIN_REQUIRED_CHECKS):
        check = checks.get(check_id)
        if not isinstance(check, dict):
            failures.append(f"supply_chain_release_gate check is missing: {check_id}")
            continue
        if normalized_token(check.get("status")) != "pass":
            failures.append(
                f"supply_chain_release_gate check {check_id} is "
                f"{normalized_token(check.get('status')) or 'missing'}"
            )
    return list(dict.fromkeys(failures))


def public_edge_observability_release_gate_semantic_failures(
    payload: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if (
        str(payload.get("contract_name") or "").strip()
        != PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE_CONTRACT_NAME
    ):
        failures.append("public_edge_observability_release_gate receipt has unexpected contract")
    if str(payload.get("verdict") or "").strip() != "OBSERVABILITY_RELEASE_READY":
        failures.append(
            "public_edge_observability_release_gate verdict is not OBSERVABILITY_RELEASE_READY"
        )

    receipt_failures = payload.get("failures")
    if not isinstance(receipt_failures, list):
        failures.append("public_edge_observability_release_gate failure list is missing")
        receipt_failure_lines: list[str] = []
    else:
        receipt_failure_lines = normalized_string_list(receipt_failures)
        if receipt_failure_lines:
            failures.append(
                "public_edge_observability_release_gate failures remain: "
                + ", ".join(receipt_failure_lines)
            )

    failure_count = payload.get("failure_count")
    if not _is_nonnegative_int(failure_count):
        failures.append("public_edge_observability_release_gate failure count is missing or invalid")
    elif int(failure_count) != len(receipt_failure_lines):
        failures.append(
            "public_edge_observability_release_gate failure count does not match its failure list"
        )

    checks_raw = payload.get("checks")
    if not isinstance(checks_raw, list):
        failures.append("public_edge_observability_release_gate checks are missing")
        checks_raw = []
    checks: dict[str, dict[str, Any]] = {}
    for item in checks_raw:
        if not isinstance(item, dict):
            failures.append("public_edge_observability_release_gate contains a malformed check")
            continue
        check_id = str(item.get("id") or "").strip()
        if not check_id:
            failures.append("public_edge_observability_release_gate contains a check without an id")
            continue
        if check_id in checks:
            failures.append(f"public_edge_observability_release_gate check is duplicated: {check_id}")
            continue
        checks[check_id] = item

    for check_id in sorted(PUBLIC_EDGE_OBSERVABILITY_REQUIRED_CHECKS):
        check = checks.get(check_id)
        if not isinstance(check, dict):
            failures.append(f"public_edge_observability_release_gate check is missing: {check_id}")
            continue
        if normalized_token(check.get("status")) != "pass":
            failures.append(
                f"public_edge_observability_release_gate check {check_id} is "
                f"{normalized_token(check.get('status')) or 'missing'}"
            )
    for check_id, check in sorted(checks.items()):
        if check_id in PUBLIC_EDGE_OBSERVABILITY_REQUIRED_CHECKS:
            continue
        if normalized_token(check.get("status")) != "pass":
            failures.append(
                f"public_edge_observability_release_gate additional check {check_id} is "
                f"{normalized_token(check.get('status')) or 'missing'}"
            )
    return list(dict.fromkeys(failures))


def apply_direct_release_gate_semantics(
    name: str,
    check: dict[str, Any],
    semantic_failures: list[str],
) -> None:
    check["semanticFailures"] = semantic_failures
    if semantic_failures:
        check["pass"] = False
        check["status"] = "fail"
        for failure in semantic_failures:
            append_unique_failure(check, failure)
    elif not check.get("pass") and not normalized_string_list(check.get("failures")):
        append_unique_failure(
            check,
            f"{name} receipt status is {str(check.get('raw_status') or 'missing').strip() or 'missing'}",
        )


def release_blocker_local_surface_status(checks: dict[str, Any]) -> dict[str, Any]:
    surface_checks: list[dict[str, Any]] = []
    for name in ROOT_BLOCKER_LOCAL_SURFACE_CHECKS:
        data = checks.get(name)
        if not isinstance(data, dict):
            continue
        effective_pass = bool(data.get("pass"))
        derived_root_cause = ""
        if name == "public_edge_postdeploy_gate":
            alignment_failures = normalized_string_list(data.get("releaseChannelAlignmentFailures"))
            if not alignment_failures:
                summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
                alignment_failures = normalized_string_list(summary.get("release_channel_alignment_failures"))
            observed_failures = normalized_string_list(data.get("failures")) or normalized_string_list(
                data.get("semanticFailures")
            )
            if (
                not effective_pass
                and alignment_failures
                and observed_failures
                and all(item in alignment_failures for item in observed_failures)
            ):
                effective_pass = True
                derived_root_cause = "release_lane_posture"
        surface_checks.append(
            {
                "name": name,
                "status": str(data.get("status") or "missing").strip() or "missing",
                "pass": effective_pass,
                "derived_root_cause": derived_root_cause,
            }
        )
    return {
        "checks": surface_checks,
        "all_passing": bool(surface_checks) and all(item.get("pass") for item in surface_checks),
    }


def root_release_blocker_entry(payload: dict[str, Any], blocker_id: str) -> dict[str, Any]:
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        blockers = payload.get("root_blockers") if isinstance(payload.get("root_blockers"), list) else []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        candidate = str(blocker.get("blocker_id") or blocker.get("id") or "").strip()
        if candidate == blocker_id:
            return blocker
    return {}


def root_release_truth_context(payload: dict[str, Any]) -> dict[str, Any]:
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        blockers = payload.get("root_blockers") if isinstance(payload.get("root_blockers"), list) else []
    blocker_ids = normalized_string_list(
        [entry.get("blocker_id") or entry.get("id") for entry in blockers if isinstance(entry, dict)]
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


def release_root_blocker_families(
    checks: dict[str, Any],
    root_release_blockers: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    families: list[dict[str, Any]] = []
    local_surface_status = release_blocker_local_surface_status(checks)
    root_release_blockers = root_release_blockers if isinstance(root_release_blockers, dict) else {}

    release_channel_check = checks.get("release_channel")
    release_channel_summary = (
        release_channel_check.get("summary")
        if isinstance(release_channel_check, dict) and isinstance(release_channel_check.get("summary"), dict)
        else {}
    )
    release_lane_details = normalized_string_list(
        release_channel_summary.get("semantic_failures")
        if release_channel_summary
        else release_channel_check.get("semantic_failures") if isinstance(release_channel_check, dict) else []
    )
    if not release_lane_details and isinstance(release_channel_check, dict):
        release_lane_details = normalized_string_list(release_channel_check.get("semantic_failures"))
    release_lane_details = [detail for detail in release_lane_details if detail.startswith("release channel ")]
    if release_lane_details:
        release_posture_blocker = root_release_blocker_entry(
            root_release_blockers,
            "release_posture:non_flagship_channel",
        )
        families.append(
            {
                "id": "release_lane_posture",
                "kind": "release_lane",
                "summary": "Live release channel is not yet on a flagship stable lane.",
                "blocking_checks": ["release_channel", "flagship_product_readiness", "release_ready"],
                "details": release_lane_details,
                "stable_promotion_command": str(release_posture_blocker.get("stable_promotion_command") or "").strip(),
                "post_promotion_verify_command": str(
                    release_posture_blocker.get("post_promotion_verify_command") or ""
                ).strip(),
                "operator_action_required": False,
                "local_surface_regression": False,
            }
        )

    google_check = checks.get("google_oauth_linking_proof")
    google_request = (
        google_check.get("operator_request_artifacts")
        if isinstance(google_check, dict) and isinstance(google_check.get("operator_request_artifacts"), dict)
        else {}
    )
    google_failure = optional_string(
        google_check.get("operatorEvidenceMissingFailure") if isinstance(google_check, dict) else ""
    )
    google_details = [detail for detail in (google_failure,) if detail]
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
        windows_check = checks.get("windows_installer_visual_audit")
        windows_request = (
            windows_check.get("operator_request_artifacts")
            if isinstance(windows_check, dict) and isinstance(windows_check.get("operator_request_artifacts"), dict)
            else {}
        )
        windows_details = [
            detail
            for detail in (
                optional_string(windows_check.get("digestMismatchFailure") if isinstance(windows_check, dict) else ""),
                optional_string(
                    windows_check.get("operatorArtifactMissingFailure") if isinstance(windows_check, dict) else ""
                ),
                optional_string(windows_check.get("operatorRequestFailure") if isinstance(windows_check, dict) else ""),
            )
            if detail
        ]
        if windows_details:
            families.append(
                {
                    "id": "windows_native_visual_proof",
                    "kind": "external_native_visual_proof",
                    "summary": windows_visual_root_blocker_summary(
                        windows_check if isinstance(windows_check, dict) else {}
                    ),
                    "blocking_checks": ["windows_installer_visual_audit", "flagship_product_readiness", "release_ready"],
                    "details": windows_details,
                    "required_path": str(windows_request.get("preferred_drop_path") or "").strip(),
                    "preferred_drop_path": str(windows_request.get("preferred_drop_path") or "").strip(),
                    "operator_action_required": True,
                    "local_surface_regression": False,
                }
            )

    direct_release_evidence_families = (
        (
            "portable_receipts_audit",
            "portable_receipt_integrity",
            "release_evidence_integrity",
            "Published release receipts are not yet portable and integrity-clean.",
            False,
        ),
        (
            "supply_chain_release_gate",
            "supply_chain_evidence",
            "supply_chain",
            "Supply-chain verification is not yet release-ready.",
            False,
        ),
        (
            "public_edge_observability_release_gate",
            "public_edge_observability",
            "external_operator_evidence",
            "Public-edge monitoring and alert-delivery evidence is not yet release-ready.",
            True,
        ),
    )
    for check_name, family_id, kind, summary_text, default_operator_action_required in direct_release_evidence_families:
        direct_check = checks.get(check_name)
        if not isinstance(direct_check, dict) or direct_check.get("pass") is True:
            continue
        direct_summary = (
            direct_check.get("summary")
            if isinstance(direct_check.get("summary"), dict)
            else {}
        )
        operator_action_required = (
            bool(direct_summary.get("external_evidence_required"))
            if check_name == "public_edge_observability_release_gate"
            else default_operator_action_required
        )
        details = normalized_string_list(direct_check.get("semanticFailures"))
        if not details:
            details = normalized_string_list(direct_check.get("failures"))
        if not details:
            details = [
                f"{check_name} status is {str(direct_check.get('status') or 'missing').strip() or 'missing'}"
            ]
        families.append(
            {
                "id": family_id,
                "kind": kind,
                "summary": summary_text,
                "blocking_checks": [check_name, "flagship_product_readiness", "release_ready"],
                "details": details,
                "operator_action_required": operator_action_required,
                "local_surface_regression": False,
            }
        )

    local_surface_failures = [
        item["name"]
        for item in local_surface_status.get("checks", [])
        if isinstance(item, dict) and not item.get("pass")
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
    if not str(payload.get("expectedReleaseChannel") or "").strip():
        failures.append("public-edge postdeploy expected release channel is missing")
    expected_supportability_state = str(payload.get("expectedReleaseSupportabilityState") or "").strip().lower()
    release_manifest_supportability_state = str(payload.get("releaseManifestSupportabilityState") or "").strip().lower()
    if not expected_supportability_state:
        failures.append("public-edge postdeploy expected release supportability is missing")
    elif (
        release_manifest_supportability_state
        and release_manifest_supportability_state != expected_supportability_state
    ):
        failures.append("public-edge postdeploy live release supportability does not match expected release supportability")
    if not str(payload.get("expectedReleaseRolloutState") or "").strip():
        failures.append("public-edge postdeploy expected release rollout is missing")
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
    role_manifests = payload.get("rolePwaManifests") if isinstance(payload.get("rolePwaManifests"), list) else []
    role_manifest_by_role = {
        str(entry.get("role") or "").strip(): entry
        for entry in role_manifests
        if isinstance(entry, dict)
    }
    for role, expected_id, expected_start_url in [
        ("Player", "/mobile/player", "/mobile/player?role=Player"),
        ("GameMaster", "/mobile/gm", "/mobile/gm?role=GameMaster"),
    ]:
        manifest = role_manifest_by_role.get(role)
        if not manifest:
            failures.append(f"public-edge postdeploy PWA static proof is missing the {role} role manifest")
            continue
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
    if missing_mobile_routes:
        failures.append(
            "public-edge postdeploy mobile PWA viewport is missing required routes: "
            + ", ".join(sorted(missing_mobile_routes))
        )
    else:
        mobile_routes = string_set(payload.get("mobilePwaViewportRoutes"))
        route_gaps = PUBLIC_EDGE_REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - mobile_routes
        if route_gaps:
            failures.append(
                "public-edge postdeploy mobile PWA viewport is missing required routes: "
                + ", ".join(sorted(route_gaps))
            )
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
    if str(payload.get("contract_name") or "").strip() != RELEASE_READY_CONTRACT_NAME:
        failures.append("release_ready receipt has unexpected contract")
    if str(payload.get("verdict") or "").strip() != RELEASE_READY_VERDICT:
        failures.append("release_ready receipt has unexpected verdict")
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


def expected_verdict_receipt_semantic_failures(
    name: str,
    payload: dict[str, Any],
    expected_verdict: str,
) -> list[str]:
    failures: list[str] = []
    if str(payload.get("verdict") or "").strip() != expected_verdict:
        failures.append(f"{name} receipt has unexpected verdict")
    return failures


def normalized_sha(value: object) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def text_sha256(path_value: object) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    try:
        path = Path(text)
        if not path.is_file():
            return ""
        return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    except (OSError, UnicodeDecodeError):
        return ""


def windows_visual_audit_intake_request_path(published_root: Path | None = None) -> Path:
    return (published_root or PUBLISHED_ROOT) / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"


def windows_visual_audit_auto_import_path(published_root: Path | None = None) -> Path:
    return (published_root or PUBLISHED_ROOT) / WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT_NAME


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


def refresh_windows_watcher_state(watcher_status_command: str, watcher_path: Path) -> tuple[dict[str, Any], str]:
    command_text = str(watcher_status_command or "").strip()
    if command_text:
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


def refresh_windows_auto_import_state(auto_import_command: str, auto_import_path: Path) -> tuple[dict[str, Any], str]:
    command_text = str(auto_import_command or "").strip()
    if command_text:
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
    refresh_windows_runtime_receipts: bool = True,
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
        "operator_ask_text_path": operator_ask_text_path,
        "operator_ask_text_exists": path_exists(operator_ask_text_path),
        "operator_ask_metadata_path": operator_ask_metadata_path,
        "operator_ask_metadata_exists": path_exists(operator_ask_metadata_path),
        "operator_ask_send_command": str(operator_draft.get("send_command") or "").strip(),
        "operator_ask_receipt_name": operator_ask_receipt_name,
        "operator_ask_message_preview": str(operator_draft.get("message_preview") or "").strip(),
        "operator_ask_message_sha256": text_sha256(operator_ask_text_path),
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
        "post_import_verify_note": str(artifact_intake.get("post_import_verify_note") or "").strip(),
        "post_import_commands": list(payload.get("post_import_gates"))
        if isinstance(payload.get("post_import_gates"), list)
        else [],
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
    if refresh_windows_runtime_receipts:
        auto_import_payload, auto_import_load_status = refresh_windows_auto_import_state(
            str(artifacts.get("auto_import_command") or "").strip(),
            auto_import_path,
        )
        watcher_payload, watcher_load_status = refresh_windows_watcher_state(
            str(artifacts.get("watcher_status_command") or "").strip(),
            watcher_path,
        )
    else:
        auto_import_payload, auto_import_load_status = load_json_with_status(auto_import_path)
        watcher_payload, watcher_load_status = load_json_with_status(watcher_path)
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


def windows_visual_audit_intake_request_receipt_verifier(path: Path) -> dict[str, Any]:
    try:
        _ok, result = verify_windows_visual_intake_request_receipt(path, require_pass=False)
        return dict(result) if isinstance(result, dict) else {}
    except Exception as exc:
        return {
            "status": "fail",
            "issues": [f"windows_visual_audit_intake_request_verifier_failed:{type(exc).__name__}"],
            "path": str(path),
            "require_pass": False,
            "operator_action_still_required": False,
            "recovery_pack_pass": False,
        }



def google_oauth_operator_evidence_missing_failure(payload: dict[str, Any]) -> str | None:
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


def google_oauth_operator_ask_resend_failure(payload: dict[str, Any]) -> str | None:
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


def windows_visual_audit_digest_mismatch_failure(payload: dict[str, Any]) -> str | None:
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


def windows_operator_recovery_pack_failure(payload: dict[str, Any]) -> str | None:
    receipt_verifier = payload.get("receipt_verifier")
    receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
    if str(receipt_verifier.get("status") or "").strip().lower() == "pass":
        return None
    issues = normalized_string_list(receipt_verifier.get("issues"))
    if issues:
        return "windows installer operator recovery pack is broken: " + ", ".join(issues)
    if receipt_verifier:
        return "windows installer operator recovery pack is broken"
    return None


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


def mirror_windows_runtime_artifacts(target: dict[str, Any]) -> None:
    request_artifacts = (
        target.get("operator_request_artifacts")
        if isinstance(target.get("operator_request_artifacts"), dict)
        else {}
    )
    for key in WINDOWS_RUNTIME_ARTIFACT_FIELDS:
        if key in request_artifacts:
            target[key] = request_artifacts[key]


def gate(
    name: str,
    path: Path,
    payload: dict[str, Any] | None = None,
    *,
    accepted_statuses: set[str] | None = None,
    load_status: str | None = None,
) -> dict[str, Any]:
    if payload is None and load_status is None:
        loaded, inferred_load_status = load_json_with_status(path)
    else:
        loaded = payload if payload is not None else {}
        inferred_load_status = load_status or ("loaded" if loaded else "invalid" if path.is_file() else "missing")
    source_status = str(loaded.get("status") or "").strip()
    reported_status = source_status or ("invalid" if inferred_load_status == "invalid" else "missing")
    status = source_status.lower()
    accepted = accepted_statuses or {"pass", "passed", "ready"}
    result = {
        "path": str(path),
        "exists": path.is_file(),
        "load_status": inferred_load_status,
        "status": reported_status,
        "raw_status": reported_status,
        "verdict": loaded.get("verdict"),
        "generated_at_utc": loaded.get("generated_at_utc") or loaded.get("generatedAtUtc") or loaded.get("generatedAt") or loaded.get("generated_at"),
        "pass": inferred_load_status == "loaded" and path.is_file() and status in accepted,
    }
    if inferred_load_status == "invalid":
        result["failures"] = [f"{name} receipt is malformed: {path}"]
    failures = loaded.get("failures")
    if isinstance(failures, list):
        result["failures"] = [
            str(item).strip()
            for item in failures
            if str(item).strip()
        ]
    failed_gates = loaded.get("failed_gates")
    if isinstance(failed_gates, list):
        result["failed_gates"] = [
            str(item).strip()
            for item in failed_gates
            if str(item).strip()
        ]
    if result["pass"] and (result.get("failures") or result.get("failed_gates")):
        result["pass"] = False
        result["status"] = "fail"
    next_actions = loaded.get("nextActions") or loaded.get("next_actions")
    if isinstance(next_actions, list):
        result["nextActions"] = [
            str(item).strip()
            for item in next_actions
            if str(item).strip()
        ]
    operator_request_artifacts = loaded.get("operator_request_artifacts")
    if isinstance(operator_request_artifacts, dict):
        result["operator_request_artifacts"] = operator_request_artifacts
    receipt_verifier = loaded.get("receipt_verifier")
    if isinstance(receipt_verifier, dict):
        result["receipt_verifier"] = receipt_verifier
    return result


def google_oauth_linking_receipt_verifier(path: Path) -> dict[str, Any]:
    try:
        _ok, result = verify_google_oauth_linking_proof_receipt(path, require_pass=False)
        return dict(result) if isinstance(result, dict) else {}
    except Exception as exc:
        return {
            "status": "fail",
            "issues": [f"google_oauth_linking_proof_verifier_failed:{type(exc).__name__}"],
            "path": str(path),
            "require_pass": False,
        }


def ea_operator_readiness_receipt_verifier(path: Path) -> dict[str, Any]:
    try:
        verified, _passed = verify_ea_operator_readiness_receipt(path)
        return dict(verified) if isinstance(verified, dict) else {}
    except Exception as exc:
        return {
            "status": "fail",
            "failures": [f"ea_operator_readiness_verifier_failed:{type(exc).__name__}"],
            "path": str(path),
        }


def mymedia_public_surface_receipt_verifier(path: Path) -> dict[str, Any]:
    try:
        _passed, result = verify_mymedia_public_surface_receipt(path, require_pass=False)
        return dict(result) if isinstance(result, dict) else {}
    except Exception as exc:
        return {
            "status": "fail",
            "issues": [f"mymedia_public_surface_verifier_failed:{type(exc).__name__}"],
            "path": str(path),
            "require_pass": False,
        }


def host_workload_runtime_health_receipt_verifier(path: Path) -> dict[str, Any]:
    try:
        verified, _passed = verify_host_workload_runtime_health_receipt(path)
        return dict(verified) if isinstance(verified, dict) else {}
    except Exception as exc:
        return {
            "status": "fail",
            "failures": [f"host_workload_runtime_health_verifier_failed:{type(exc).__name__}"],
            "path": str(path),
        }


def qbittorrent_staging_hygiene_receipt_verifier(path: Path) -> dict[str, Any]:
    try:
        verified, _passed = verify_qbittorrent_staging_hygiene_receipt(path)
        return dict(verified) if isinstance(verified, dict) else {}
    except Exception as exc:
        return {
            "status": "fail",
            "failures": [f"qbittorrent_staging_hygiene_verifier_failed:{type(exc).__name__}"],
            "path": str(path),
        }


def google_oauth_release_truth_effective_pass(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    failures = normalized_string_list(payload.get("failures"))
    failed_gates = normalized_string_list(payload.get("failed_gates"))
    if normalized_token(payload.get("status")) in PASS_STATES and not failures and not failed_gates:
        return True

    operator_evidence = (
        payload.get("operator_end_to_end_evidence")
        if isinstance(payload.get("operator_end_to_end_evidence"), dict)
        else {}
    )
    operator_request_artifacts = (
        payload.get("operator_request_artifacts")
        if isinstance(payload.get("operator_request_artifacts"), dict)
        else {}
    )
    quick_probe = (
        payload.get("quick_handoff_probe")
        if isinstance(payload.get("quick_handoff_probe"), dict)
        else {}
    )
    signed_in_probe = (
        payload.get("signed_in_link_handoff")
        if isinstance(payload.get("signed_in_link_handoff"), dict)
        else {}
    )
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


def release_blocking_check_failed(name: str, data: dict[str, Any]) -> bool:
    if name == "windows_installer_visual_audit" and IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        return False
    if data.get("pass"):
        return False
    if name == "google_oauth_linking_proof" and google_oauth_release_truth_effective_pass(data):
        return False
    return True


def recover_flagship_product_readiness_release_blocking(checks: dict[str, Any]) -> None:
    flagship = checks.get("flagship_product_readiness")
    if not isinstance(flagship, dict):
        return
    summary = flagship.get("summary")
    if not isinstance(summary, dict):
        return
    if flagship.get("source_receipt") != "gate":
        return
    if not flagship_product_readiness_structural_pass(summary):
        return
    if not flagship_product_readiness_launch_blockers_recoverable(summary):
        return
    independent_blockers = sorted(
        name
        for name, data in checks.items()
        if name != "flagship_product_readiness"
        and isinstance(data, dict)
        and data.get("release_blocking", True) is not False
        and not bool(data.get("pass"))
    )
    if not independent_blockers:
        release_ready_gate = checks.get("release_ready")
        if not (
            isinstance(release_ready_gate, dict)
            and release_ready_gate.get("self_check_skipped") is True
        ):
            return
        independent_blockers = ["release_ready:self_check_skipped"]
    flagship["pass"] = True
    flagship["status"] = "pass"
    flagship["release_blocking_recovered"] = True
    flagship["recovered_because_of_checks"] = independent_blockers
    flagship["recovered_launch_blockers"] = normalized_string_list(
        summary.get("launch_critical_nested_blockers")
    )
    flagship.pop("failures", None)
    summary["structural_pass"] = True
    summary["recovered_for_release_blocking"] = True
    summary["recovered_because_of_checks"] = independent_blockers


def build_payload(
    *,
    release_ready_self_check: bool = False,
    public_edge_live_role_alias_routes: dict[str, Any] | None = None,
    refresh_windows_runtime_receipts: bool = True,
) -> dict[str, Any]:
    public_release_snapshot = load_json(PUBLIC_RELEASE_SNAPSHOT_PATH)
    release_channel_path = REGISTRY_ROOT / "RELEASE_CHANNEL.generated.json"
    release_channel = load_json(release_channel_path)
    mirror_path = PUBLISHED_ROOT / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json"
    mirror = load_json(mirror_path)
    ruleset_path = PUBLISHED_ROOT / "RULESET_READINESS.generated.json"
    ruleset = load_json(ruleset_path)
    raw_flagship_product_readiness_path = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    raw_flagship_product_readiness, raw_flagship_product_readiness_load_status = load_json_with_status(raw_flagship_product_readiness_path)
    flagship_product_readiness_gate_path = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
    refresh_flagship_product_readiness_gate(flagship_product_readiness_gate_path)
    flagship_product_readiness_gate, flagship_product_readiness_gate_load_status = load_json_with_status(flagship_product_readiness_gate_path)
    flagship_product_readiness_path = (
        flagship_product_readiness_gate_path
        if flagship_product_readiness_gate_path.is_file()
        else raw_flagship_product_readiness_path
    )
    flagship_product_readiness = (
        flagship_product_readiness_gate
        if flagship_product_readiness_gate_path.is_file()
        else raw_flagship_product_readiness
    )
    flagship_product_readiness_load_status = (
        flagship_product_readiness_gate_load_status
        if flagship_product_readiness_gate_path.is_file()
        else raw_flagship_product_readiness_load_status
    )
    public_route_proof_path = PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
    public_route_proof = load_json(public_route_proof_path)
    public_edge_postdeploy_path = PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    public_edge_postdeploy = normalize_public_edge_postdeploy_payload(load_json(public_edge_postdeploy_path))
    public_edge_preflight_path = PUBLISHED_ROOT / "PUBLIC_EDGE_DEPLOY_PREFLIGHT.generated.json"
    public_edge_preflight = load_json(public_edge_preflight_path)
    public_edge_overlay_publish_path = PUBLISHED_ROOT / "PUBLIC_EDGE_PORTAL_OVERLAY_PUBLISH.generated.json"
    public_edge_overlay_publish = load_json(public_edge_overlay_publish_path)
    public_edge_overlay_verify_path = PUBLISHED_ROOT / "PUBLIC_EDGE_PORTAL_OVERLAY_VERIFY.generated.json"
    public_edge_overlay_verify = load_json(public_edge_overlay_verify_path)
    public_edge_local_overlay_parity_path = PUBLISHED_ROOT / "LIVE_SURFACE_PARITY.local-overlay.generated.json"
    public_edge_local_overlay_parity = load_json(public_edge_local_overlay_parity_path)
    windows_installer_visual_audit_path = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
    windows_installer_visual_audit = load_json(windows_installer_visual_audit_path)
    windows_visual_audit_intake_request_receipt_path = windows_visual_audit_intake_request_path()
    windows_visual_audit_intake_request = load_json(windows_visual_audit_intake_request_receipt_path)
    ui_frame_path = COMPLETION_ROOT / "UI_FRAME_INTEGRITY.generated.json"
    ui_frame = load_json(ui_frame_path)
    design_path = PUBLISHED_ROOT / "DESIGN_QUALITY_GATE.generated.json"
    design = load_json(design_path)
    copy_path = PUBLISHED_ROOT / "PUBLIC_COPY_LEAK_GATE.generated.json"
    copy_gate = load_json(copy_path)
    blazor_execution_horizon_bridge_path = PUBLISHED_ROOT / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json"
    blazor_execution_horizon_bridge = load_json(blazor_execution_horizon_bridge_path)
    blazor_play_surface_horizon_path = first_candidate_path(WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES)
    blazor_play_surface_horizon = (
        load_json(blazor_play_surface_horizon_path)
        if isinstance(blazor_play_surface_horizon_path, Path)
        else {}
    )
    participate_billing_honesty_path = PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json"
    participate_billing_honesty = load_json(participate_billing_honesty_path)
    account_handoff_runtime_config_path = PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json"
    account_handoff_runtime_config = load_json(account_handoff_runtime_config_path)
    release_ready_path = PUBLISHED_ROOT / "RELEASE_READY.generated.json"
    release_ready = load_json(release_ready_path)
    root_release_blockers = load_json(ROOT_RELEASE_BLOCKERS_PATH)
    final_gold_path = PUBLISHED_ROOT / "FINAL_GOLD_JANITOR.generated.json"
    final_gold = load_json(final_gold_path)
    oauth_path = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    oauth = load_json(oauth_path)
    if oauth_path.is_file() and isinstance(oauth, dict) and oauth:
        oauth["receipt_verifier"] = google_oauth_linking_receipt_verifier(oauth_path)
        operator_request_artifacts = oauth.get("operator_request_artifacts")
        if isinstance(operator_request_artifacts, dict):
            oauth["operator_request_artifacts"] = enrich_operator_ask_delivery_details(operator_request_artifacts)
    ea_operator_readiness_path = PUBLISHED_ROOT / "EA_OPERATOR_READINESS.generated.json"
    ea_operator_readiness = load_json(ea_operator_readiness_path)
    ea_operator_readiness_verifier = (
        ea_operator_readiness_receipt_verifier(ea_operator_readiness_path)
        if ea_operator_readiness_path.is_file()
        else {}
    )
    host_workload_runtime_health_path = PUBLISHED_ROOT / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json"
    host_workload_runtime_health = load_json(host_workload_runtime_health_path)
    host_workload_runtime_health_verifier = (
        host_workload_runtime_health_receipt_verifier(host_workload_runtime_health_path)
        if host_workload_runtime_health_path.is_file()
        else {}
    )
    qbittorrent_staging_hygiene_path = PUBLISHED_ROOT / "QBITTORRENT_STAGING_HYGIENE.generated.json"
    qbittorrent_staging_hygiene = load_json(qbittorrent_staging_hygiene_path)
    qbittorrent_staging_hygiene_verifier = (
        qbittorrent_staging_hygiene_receipt_verifier(qbittorrent_staging_hygiene_path)
        if qbittorrent_staging_hygiene_path.is_file()
        else {}
    )
    mymedia_public_surface_path = PUBLISHED_ROOT / "MYMEDIA_PUBLIC_SURFACE.generated.json"
    mymedia_public_surface = load_json(mymedia_public_surface_path)
    mymedia_public_surface_verifier = (
        mymedia_public_surface_receipt_verifier(mymedia_public_surface_path)
        if mymedia_public_surface_path.is_file()
        else {}
    )
    windows_visual_audit_intake_request_verifier = (
        windows_visual_audit_intake_request_receipt_verifier(windows_visual_audit_intake_request_receipt_path)
        if windows_visual_audit_intake_request_receipt_path.is_file()
        else {}
    )
    teable_important_work_path = PUBLISHED_ROOT / "TEABLE_IMPORTANT_WORK.generated.json"
    teable_important_work = load_json(teable_important_work_path)
    portable_receipts_audit_path = PUBLISHED_ROOT / "PORTABLE_RECEIPTS_AUDIT.generated.json"
    portable_receipts_audit = load_json(portable_receipts_audit_path)
    supply_chain_path = supply_chain_release_gate_path()
    supply_chain_release_gate = load_json(supply_chain_path)
    public_edge_observability_path = (
        PUBLISHED_ROOT / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json"
    )
    public_edge_observability_release_gate = load_json(public_edge_observability_path)

    checks = {
        "release_channel": gate("release_channel", release_channel_path, release_channel, accepted_statuses={"published", "pass", "passed", "ready"}),
        "external_distribution_mirror_proof": gate("external_distribution_mirror_proof", mirror_path, mirror),
        "ruleset_readiness": gate("ruleset_readiness", ruleset_path, ruleset),
        "flagship_product_readiness": gate(
            "flagship_product_readiness",
            flagship_product_readiness_path,
            flagship_product_readiness,
            load_status=flagship_product_readiness_load_status,
        ),
        "public_route_proof": gate("public_route_proof", public_route_proof_path, public_route_proof),
        "public_edge_postdeploy_gate": gate("public_edge_postdeploy_gate", public_edge_postdeploy_path, public_edge_postdeploy),
        "windows_installer_visual_audit": gate("windows_installer_visual_audit", windows_installer_visual_audit_path, windows_installer_visual_audit),
        "ui_frame_integrity": gate("ui_frame_integrity", ui_frame_path, ui_frame),
        "design_quality_gate": gate("design_quality_gate", design_path, design),
        "blazor_execution_horizon_bridge": gate(
            "blazor_execution_horizon_bridge",
            blazor_execution_horizon_bridge_path,
            blazor_execution_horizon_bridge,
        ),
        "public_copy_leak_gate": gate("public_copy_leak_gate", copy_path, copy_gate),
        "participate_billing_honesty": gate("participate_billing_honesty", participate_billing_honesty_path, participate_billing_honesty),
        "account_handoff_runtime_config": gate("account_handoff_runtime_config", account_handoff_runtime_config_path, account_handoff_runtime_config),
        "release_ready": gate("release_ready", release_ready_path, release_ready),
        "final_gold_janitor": gate("final_gold_janitor", final_gold_path, final_gold),
        "google_oauth_linking_proof": gate("google_oauth_linking_proof", oauth_path, oauth),
        "ea_operator_readiness": gate("ea_operator_readiness", ea_operator_readiness_path, ea_operator_readiness),
        "host_workload_runtime_health": gate(
            "host_workload_runtime_health",
            host_workload_runtime_health_path,
            host_workload_runtime_health,
        ),
        "qbittorrent_staging_hygiene": gate(
            "qbittorrent_staging_hygiene",
            qbittorrent_staging_hygiene_path,
            qbittorrent_staging_hygiene,
        ),
        "mymedia_public_surface": gate("mymedia_public_surface", mymedia_public_surface_path, mymedia_public_surface),
        "teable_important_work": gate("teable_important_work", teable_important_work_path, teable_important_work),
        "portable_receipts_audit": gate(
            "portable_receipts_audit",
            portable_receipts_audit_path,
            portable_receipts_audit,
        ),
        "supply_chain_release_gate": gate(
            "supply_chain_release_gate",
            supply_chain_path,
            supply_chain_release_gate,
        ),
        "public_edge_observability_release_gate": gate(
            "public_edge_observability_release_gate",
            public_edge_observability_path,
            public_edge_observability_release_gate,
        ),
    }
    checks["flagship_product_readiness"]["source_receipt"] = (
        "gate" if flagship_product_readiness_path == flagship_product_readiness_gate_path else "raw"
    )
    checks["flagship_product_readiness"]["raw_readiness_path"] = str(raw_flagship_product_readiness_path)

    # Final-gold reads this dashboard while producing its own receipt, so it remains context-only here
    # to avoid a self-referential release gate.
    checks["final_gold_janitor"]["release_blocking"] = False
    checks["blazor_execution_horizon_bridge"]["release_blocking"] = False
    checks["ea_operator_readiness"]["release_blocking"] = False
    checks["host_workload_runtime_health"]["release_blocking"] = False
    checks["qbittorrent_staging_hygiene"]["release_blocking"] = False
    checks["mymedia_public_surface"]["release_blocking"] = False
    if IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING:
        checks["windows_installer_visual_audit"]["release_blocking"] = False
    if isinstance(blazor_execution_horizon_bridge, dict) and blazor_execution_horizon_bridge:
        bridge_proofs = (
            blazor_execution_horizon_bridge.get("proofs")
            if isinstance(blazor_execution_horizon_bridge.get("proofs"), dict)
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
            "verdict": str(blazor_execution_horizon_bridge.get("verdict") or "").strip(),
            "hub_mobile_pwa_public_projection_status": str(hub_mobile.get("status") or "").strip(),
            "blazor_hosted_pwa_public_edge_status": str(hosted_pwa.get("status") or "").strip(),
            "near_term_smoke_status": str(hosted_execution.get("near_term_smoke_status") or "").strip(),
            "mid_term_full_matrix_status": str(hosted_execution.get("mid_term_full_matrix_status") or "").strip(),
            "mid_term_full_required_workflow_family_count": int(hosted_execution.get("mid_term_full_required_workflow_family_count") or 0),
            "mid_term_full_covered_workflow_family_count": int(hosted_execution.get("mid_term_full_covered_workflow_family_count") or 0),
            "long_term_full_browser_parity_status": str(hosted_execution.get("long_term_full_browser_parity_status") or "").strip(),
            "notes": normalized_string_list(blazor_execution_horizon_bridge.get("notes")),
        }
        if isinstance(blazor_play_surface_horizon_path, Path):
            bridge_summary["play_surface_horizon_path"] = str(blazor_play_surface_horizon_path)
        if isinstance(blazor_play_surface_horizon, dict) and blazor_play_surface_horizon:
            bridge_summary["play_surface_horizon"] = blazor_play_surface_horizon_summary(blazor_play_surface_horizon)
        checks["blazor_execution_horizon_bridge"]["summary"] = bridge_summary
    if isinstance(ea_operator_readiness, dict) and ea_operator_readiness:
        ea_next_actions = [
            dict(item)
            for item in ea_operator_readiness.get("next_actions") or []
            if isinstance(item, dict)
        ]
        checks["ea_operator_readiness"]["receipt_verifier"] = ea_operator_readiness_verifier
        checks["ea_operator_readiness"]["operator_ready"] = bool(ea_operator_readiness.get("operator_ready"))
        checks["ea_operator_readiness"]["operator_status"] = str(
            ea_operator_readiness.get("operator_status") or checks["ea_operator_readiness"].get("status") or "unknown"
        ).strip() or "unknown"
        checks["ea_operator_readiness"]["runtime_status"] = str(
            ea_operator_readiness.get("runtime_status")
            or (
                "blocked"
                if int(ea_operator_readiness.get("probe_failed_count") or 0) > 0
                or int(ea_operator_readiness.get("blocked_count") or 0) > 0
                else "degraded"
                if int(ea_operator_readiness.get("attention_required_count") or 0) > 0
                or not bool(ea_operator_readiness.get("operator_ready"))
                else "ready"
            )
        ).strip() or "unknown"
        checks["ea_operator_readiness"]["runtime_ready"] = bool(
            ea_operator_readiness.get("runtime_ready")
        ) if "runtime_ready" in ea_operator_readiness else checks["ea_operator_readiness"]["runtime_status"] == "ready"
        checks["ea_operator_readiness"]["blocking_count"] = int(
            ea_operator_readiness.get("blocking_count") or 0
        )
        checks["ea_operator_readiness"]["advisory_count"] = int(
            ea_operator_readiness.get("advisory_count") or 0
        )
        checks["ea_operator_readiness"]["blocking_findings"] = normalized_string_list(
            ea_operator_readiness.get("blocking_findings")
        )
        checks["ea_operator_readiness"]["advisory_findings"] = normalized_string_list(
            ea_operator_readiness.get("advisory_findings")
        )
        checks["ea_operator_readiness"]["attention_required_count"] = int(
            ea_operator_readiness.get("attention_required_count") or 0
        )
        checks["ea_operator_readiness"]["blocked_count"] = int(ea_operator_readiness.get("blocked_count") or 0)
        checks["ea_operator_readiness"]["next_action_component_keys"] = normalized_string_list(
            ea_operator_readiness.get("next_action_component_keys")
        )
        checks["ea_operator_readiness"]["supplemental_attention_count"] = int(
            ea_operator_readiness.get("supplemental_attention_count") or 0
        )
        checks["ea_operator_readiness"]["supplemental_blocked_count"] = int(
            ea_operator_readiness.get("supplemental_blocked_count") or 0
        )
        checks["ea_operator_readiness"]["supplemental_probe_failed_count"] = int(
            ea_operator_readiness.get("supplemental_probe_failed_count") or 0
        )
        checks["ea_operator_readiness"]["supplemental_attention_component_keys"] = normalized_string_list(
            ea_operator_readiness.get("supplemental_attention_component_keys")
        )
        checks["ea_operator_readiness"]["supplemental_blocked_component_keys"] = normalized_string_list(
            ea_operator_readiness.get("supplemental_blocked_component_keys")
        )
        checks["ea_operator_readiness"]["supplemental_probe_failed_component_keys"] = normalized_string_list(
            ea_operator_readiness.get("supplemental_probe_failed_component_keys")
        )
        checks["ea_operator_readiness"]["supplemental_next_action_component_keys"] = normalized_string_list(
            ea_operator_readiness.get("supplemental_next_action_component_keys")
        )
        checks["ea_operator_readiness"]["advisory_action_component_keys"] = normalized_string_list(
            ea_operator_readiness.get("advisory_action_component_keys")
        )
        checks["ea_operator_readiness"]["nextActions"] = [
            f"{str(item.get('component_key') or '').strip()}: {str(item.get('action') or '').strip()}"
            for item in ea_next_actions
            if str(item.get("component_key") or "").strip() and str(item.get("action") or "").strip()
        ]
        ea_advisory_actions = [
            dict(item)
            for item in ea_operator_readiness.get("advisory_actions") or []
            if isinstance(item, dict)
        ]
        checks["ea_operator_readiness"]["advisoryActions"] = [
            f"{str(item.get('component_key') or '').strip()}: {str(item.get('action') or '').strip()}"
            for item in ea_advisory_actions
            if str(item.get("component_key") or "").strip() and str(item.get("action") or "").strip()
        ]
        structural_pass = str(ea_operator_readiness_verifier.get("status") or "").strip().lower() == "pass"
        checks["ea_operator_readiness"]["structural_pass"] = structural_pass
        checks["ea_operator_readiness"]["status"] = checks["ea_operator_readiness"]["operator_status"]
        checks["ea_operator_readiness"]["pass"] = structural_pass and bool(
            checks["ea_operator_readiness"]["runtime_ready"]
        )
        if not structural_pass:
            checks["ea_operator_readiness"]["failures"] = normalized_string_list(
                ea_operator_readiness_verifier.get("failures")
            )
        elif not checks["ea_operator_readiness"]["pass"]:
            checks["ea_operator_readiness"]["failures"] = (
                checks["ea_operator_readiness"]["blocking_findings"]
                + checks["ea_operator_readiness"]["advisory_findings"]
            )
    else:
        checks["ea_operator_readiness"]["status"] = "missing"
        checks["ea_operator_readiness"]["pass"] = False
        checks["ea_operator_readiness"]["failures"] = ["ea_operator_readiness receipt is missing"]
    if isinstance(host_workload_runtime_health, dict) and host_workload_runtime_health:
        checks["host_workload_runtime_health"]["receipt_verifier"] = host_workload_runtime_health_verifier
        checks["host_workload_runtime_health"]["runtime_ready"] = bool(
            host_workload_runtime_health.get("runtime_ready")
        )
        checks["host_workload_runtime_health"]["runtime_status"] = str(
            host_workload_runtime_health.get("runtime_status")
            or checks["host_workload_runtime_health"].get("status")
            or "unknown"
        )
        checks["host_workload_runtime_health"]["blocking_count"] = int(
            host_workload_runtime_health.get("blocking_count") or 0
        )
        checks["host_workload_runtime_health"]["advisory_count"] = int(
            host_workload_runtime_health.get("advisory_count") or 0
        )
        checks["host_workload_runtime_health"]["blocking_findings"] = normalized_string_list(
            host_workload_runtime_health.get("blocking_findings")
        )
        checks["host_workload_runtime_health"]["advisory_findings"] = normalized_string_list(
            host_workload_runtime_health.get("advisory_findings")
        )
        checks["host_workload_runtime_health"]["next_action_component_keys"] = normalized_string_list(
            host_workload_runtime_health.get("next_action_component_keys")
        )
        checks["host_workload_runtime_health"]["advisory_action_component_keys"] = normalized_string_list(
            host_workload_runtime_health.get("advisory_action_component_keys")
        )
        checks["host_workload_runtime_health"]["runtime_observation"] = (
            host_workload_runtime_health.get("runtime_observation")
            if isinstance(host_workload_runtime_health.get("runtime_observation"), dict)
            else {}
        )
        structural_pass = str(host_workload_runtime_health_verifier.get("status") or "").strip().lower() == "pass"
        checks["host_workload_runtime_health"]["structural_pass"] = structural_pass
        checks["host_workload_runtime_health"]["status"] = checks["host_workload_runtime_health"]["runtime_status"]
        checks["host_workload_runtime_health"]["pass"] = structural_pass and bool(
            checks["host_workload_runtime_health"]["runtime_ready"]
        )
        if not structural_pass:
            checks["host_workload_runtime_health"]["failures"] = normalized_string_list(
                host_workload_runtime_health_verifier.get("failures")
            )
        elif not checks["host_workload_runtime_health"]["pass"]:
            checks["host_workload_runtime_health"]["failures"] = (
                checks["host_workload_runtime_health"]["blocking_findings"]
                + checks["host_workload_runtime_health"]["advisory_findings"]
            )
    else:
        checks["host_workload_runtime_health"]["status"] = "missing"
        checks["host_workload_runtime_health"]["pass"] = False
        checks["host_workload_runtime_health"]["failures"] = ["host_workload_runtime_health receipt is missing"]
    if isinstance(qbittorrent_staging_hygiene, dict) and qbittorrent_staging_hygiene:
        checks["qbittorrent_staging_hygiene"]["receipt_verifier"] = qbittorrent_staging_hygiene_verifier
        checks["qbittorrent_staging_hygiene"]["runtime_ready"] = bool(
            qbittorrent_staging_hygiene.get("runtime_ready")
        )
        checks["qbittorrent_staging_hygiene"]["runtime_status"] = str(
            qbittorrent_staging_hygiene.get("runtime_status")
            or checks["qbittorrent_staging_hygiene"].get("status")
            or "unknown"
        ).strip() or "unknown"
        checks["qbittorrent_staging_hygiene"]["blocking_count"] = int(
            qbittorrent_staging_hygiene.get("blocking_count") or 0
        )
        checks["qbittorrent_staging_hygiene"]["advisory_count"] = int(
            qbittorrent_staging_hygiene.get("advisory_count") or 0
        )
        checks["qbittorrent_staging_hygiene"]["blocking_findings"] = normalized_string_list(
            qbittorrent_staging_hygiene.get("blocking_findings")
        )
        checks["qbittorrent_staging_hygiene"]["advisory_findings"] = normalized_string_list(
            qbittorrent_staging_hygiene.get("advisory_findings")
        )
        checks["qbittorrent_staging_hygiene"]["next_action_component_keys"] = normalized_string_list(
            qbittorrent_staging_hygiene.get("next_action_component_keys")
        )
        checks["qbittorrent_staging_hygiene"]["advisory_action_component_keys"] = normalized_string_list(
            qbittorrent_staging_hygiene.get("advisory_action_component_keys")
        )
        checks["qbittorrent_staging_hygiene"]["runtime_observation"] = (
            qbittorrent_staging_hygiene.get("runtime_observation")
            if isinstance(qbittorrent_staging_hygiene.get("runtime_observation"), dict)
            else {}
        )
        structural_pass = str(qbittorrent_staging_hygiene_verifier.get("status") or "").strip().lower() == "pass"
        checks["qbittorrent_staging_hygiene"]["structural_pass"] = structural_pass
        checks["qbittorrent_staging_hygiene"]["status"] = checks["qbittorrent_staging_hygiene"]["runtime_status"]
        checks["qbittorrent_staging_hygiene"]["pass"] = structural_pass and bool(
            checks["qbittorrent_staging_hygiene"]["runtime_ready"]
        )
        if not structural_pass:
            checks["qbittorrent_staging_hygiene"]["failures"] = normalized_string_list(
                qbittorrent_staging_hygiene_verifier.get("failures")
            )
        elif not checks["qbittorrent_staging_hygiene"]["pass"]:
            checks["qbittorrent_staging_hygiene"]["failures"] = (
                checks["qbittorrent_staging_hygiene"]["blocking_findings"]
                + checks["qbittorrent_staging_hygiene"]["advisory_findings"]
            )
    else:
        checks["qbittorrent_staging_hygiene"]["status"] = "missing"
        checks["qbittorrent_staging_hygiene"]["pass"] = False
        checks["qbittorrent_staging_hygiene"]["failures"] = ["qbittorrent_staging_hygiene receipt is missing"]
    if isinstance(mymedia_public_surface, dict) and mymedia_public_surface:
        checks["mymedia_public_surface"]["receipt_verifier"] = mymedia_public_surface_verifier
        checks["mymedia_public_surface"]["runtime_status"] = str(
            mymedia_public_surface.get("runtime_status")
            or ("ready" if bool(mymedia_public_surface.get("public_surface_ready")) else "blocked")
        ).strip() or "unknown"
        checks["mymedia_public_surface"]["runtime_ready"] = bool(
            mymedia_public_surface.get("runtime_ready")
        ) if "runtime_ready" in mymedia_public_surface else bool(mymedia_public_surface.get("public_surface_ready"))
        checks["mymedia_public_surface"]["blocking_count"] = int(
            mymedia_public_surface.get("blocking_count") or 0
        )
        checks["mymedia_public_surface"]["advisory_count"] = int(
            mymedia_public_surface.get("advisory_count") or 0
        )
        checks["mymedia_public_surface"]["blocking_findings"] = normalized_string_list(
            mymedia_public_surface.get("blocking_findings")
        )
        checks["mymedia_public_surface"]["advisory_findings"] = normalized_string_list(
            mymedia_public_surface.get("advisory_findings")
        )
        checks["mymedia_public_surface"]["public_surface_ready"] = bool(
            mymedia_public_surface.get("public_surface_ready")
        )
        checks["mymedia_public_surface"]["public_surface_status"] = str(
            mymedia_public_surface.get("public_surface_status")
            or checks["mymedia_public_surface"].get("status")
            or "unknown"
        ).strip() or "unknown"
        checks["mymedia_public_surface"]["public_surface_url"] = str(
            mymedia_public_surface.get("public_surface_url") or ""
        ).strip()
        checks["mymedia_public_surface"]["public_surface_http_status_code"] = int(
            mymedia_public_surface.get("public_surface_http_status_code") or 0
        )
        checks["mymedia_public_surface"]["public_surface_access_protected"] = bool(
            mymedia_public_surface.get("public_surface_access_protected")
        )
        checks["mymedia_public_surface"]["public_surface_cloudflare_blocked"] = bool(
            mymedia_public_surface.get("public_surface_cloudflare_blocked")
        )
        checks["mymedia_public_surface"]["mymedia_status"] = str(
            mymedia_public_surface.get("mymedia_status") or "unknown"
        ).strip() or "unknown"
        structural_pass = str(mymedia_public_surface_verifier.get("status") or "").strip().lower() == "pass"
        checks["mymedia_public_surface"]["structural_pass"] = structural_pass
        checks["mymedia_public_surface"]["status"] = checks["mymedia_public_surface"]["public_surface_status"]
        checks["mymedia_public_surface"]["pass"] = structural_pass and bool(
            checks["mymedia_public_surface"]["runtime_ready"]
        )
        if not structural_pass:
            checks["mymedia_public_surface"]["failures"] = normalized_string_list(
                mymedia_public_surface_verifier.get("issues")
            )
        elif not checks["mymedia_public_surface"]["pass"]:
            checks["mymedia_public_surface"]["failures"] = (
                checks["mymedia_public_surface"]["blocking_findings"]
                + checks["mymedia_public_surface"]["advisory_findings"]
            )
    else:
        checks["mymedia_public_surface"]["status"] = "missing"
        checks["mymedia_public_surface"]["pass"] = False
        checks["mymedia_public_surface"]["failures"] = ["mymedia_public_surface receipt is missing"]
    if windows_visual_audit_intake_request_receipt_path.is_file() and isinstance(windows_visual_audit_intake_request, dict):
        checks["windows_installer_visual_audit"]["operator_request_artifacts"] = windows_operator_request_artifacts(
            windows_visual_audit_intake_request_receipt_path,
            windows_visual_audit_intake_request,
            refresh_windows_runtime_receipts=refresh_windows_runtime_receipts,
        )
        if windows_visual_audit_intake_request_verifier:
            checks["windows_installer_visual_audit"]["receipt_verifier"] = windows_visual_audit_intake_request_verifier
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["pass"] = bool(
                windows_visual_audit_intake_request_verifier.get("recovery_pack_pass")
            )
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["failures"] = normalized_string_list(
                windows_visual_audit_intake_request_verifier.get("issues")
            )
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["receipt_verifier_status"] = str(
                windows_visual_audit_intake_request_verifier.get("status") or ""
            ).strip()
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["request_effective_status"] = str(
                windows_visual_audit_intake_request_verifier.get("effective_status") or ""
            ).strip()
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["operator_action_still_required"] = bool(
                windows_visual_audit_intake_request_verifier.get("operator_action_still_required")
            )
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["current_windows_visual_audit_status"] = str(
                windows_visual_audit_intake_request_verifier.get("current_windows_visual_audit_status") or ""
            ).strip()
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["current_windows_visual_audit_effective_pass"] = bool(
                windows_visual_audit_intake_request_verifier.get("current_windows_visual_audit_effective_pass")
            )
            checks["windows_installer_visual_audit"]["operator_request_artifacts"]["current_windows_visual_audit_issues"] = normalized_string_list(
                windows_visual_audit_intake_request_verifier.get("current_windows_visual_audit_issues")
            )
            checks["windows_installer_visual_audit"]["operator_request_artifacts"] = enrich_operator_ask_delivery_details(
                checks["windows_installer_visual_audit"]["operator_request_artifacts"]
            )
    if release_ready_self_check:
        checks["release_ready"].update(
            {
                "pass": True,
                "status": "self_check_skipped",
                "release_blocking": False,
                "self_check_skipped": True,
                "reason": (
                    "Skipped only while the release-ready verifier is producing a new release_ready "
                    "receipt, so the dashboard checks current dependencies instead of the previous "
                    "release_ready result."
                ),
            }
        )

    providers = {
        provider: data.get("status")
        for provider, data in (mirror.get("providers") or {}).items()
        if isinstance(data, dict)
    }
    frame_base_url = public_safe_base_url(ui_frame.get("base_url")) or public_safe_base_url(public_route_proof.get("base_url"))
    rulesets = {
        ruleset_name: {
            "status": data.get("status"),
            "workflow_parity_status": data.get("workflow_parity_status"),
            "human_side_gold_assumption": data.get("human_side_gold_assumption"),
        }
        for ruleset_name, data in (ruleset.get("rulesets") or {}).items()
        if isinstance(data, dict)
    }
    frame_summary = ui_frame.get("summary") if isinstance(ui_frame.get("summary"), dict) else {}
    route_summary = public_route_proof.get("summary") if isinstance(public_route_proof.get("summary"), dict) else {}
    try:
        route_count = int(route_summary.get("route_count") or 0)
        route_failed_count = int(route_summary.get("failed_count") or 0)
        negative_path_failed_count = int(route_summary.get("negative_path_failed_count") or 0)
    except (TypeError, ValueError):
        route_count = 0
        route_failed_count = 0
        negative_path_failed_count = 0
    checks["public_route_proof"]["summary"] = {
        "route_count": route_count,
        "failed_count": route_failed_count,
        "negative_path_failed_count": negative_path_failed_count,
    }
    checks["public_route_proof"]["pass"] = bool(
        checks["public_route_proof"]["pass"]
        and route_count > 0
        and route_failed_count == 0
        and negative_path_failed_count == 0
    )
    workspace_portal_release_channel_checks, workspace_portal_release_channel_failures = (
        workspace_portal_release_channel_observations(release_channel)
    )
    release_channel_semantic_failures_list = (
        release_channel_semantic_failures(release_channel)
        + workspace_portal_release_channel_failures
    )
    release_channel_summary = {
        "status": release_channel.get("status"),
        "version": release_channel.get("version"),
        "published_at": release_channel.get("publishedAt") or release_channel.get("published_at"),
        "channel": release_channel.get("channel") or release_channel.get("channelId"),
        "rollout_state": release_channel.get("rolloutState"),
        "supportability_state": release_channel.get("supportabilityState"),
        "workspace_portal_release_channels_checked": workspace_portal_release_channel_checks,
        "workspace_portal_release_channel_mismatches": workspace_portal_release_channel_failures,
        "semantic_failures": release_channel_semantic_failures_list,
    }
    checks["release_channel"]["summary"] = release_channel_summary
    checks["release_channel"].update(
        {
            "version": release_channel_summary["version"],
            "published_at": release_channel_summary["published_at"],
            "channel": release_channel_summary["channel"],
            "rollout_state": release_channel_summary["rollout_state"],
            "supportability_state": release_channel_summary["supportability_state"],
            "workspace_portal_release_channels_checked": workspace_portal_release_channel_checks,
            "workspace_portal_release_channel_mismatches": workspace_portal_release_channel_failures,
            "semantic_failures": release_channel_semantic_failures_list,
        }
    )
    if release_channel_semantic_failures_list:
        checks["release_channel"]["pass"] = False
        checks["release_channel"]["status"] = "fail"
        checks["release_channel"].setdefault("failures", [])
        checks["release_channel"]["failures"].extend(release_channel_semantic_failures_list)
    if flagship_product_readiness:
        readiness_summary_payload = flagship_product_readiness.get("summary") if isinstance(flagship_product_readiness.get("summary"), dict) else {}
        is_readiness_gate = flagship_product_readiness.get("contract_name") == "chummer.flagship_product_readiness_gate.v1"
        completion = flagship_product_readiness.get("completion_audit") if isinstance(flagship_product_readiness.get("completion_audit"), dict) else {}
        readiness = flagship_product_readiness.get("flagship_readiness_audit") if isinstance(flagship_product_readiness.get("flagship_readiness_audit"), dict) else {}
        readiness_fields = readiness_summary_payload if is_readiness_gate else readiness
        coverage_gaps = [
            str(item).strip()
            for item in readiness_fields.get("coverage_gap_keys", [])
            if str(item).strip()
        ] if isinstance(readiness_fields.get("coverage_gap_keys"), list) else []
        scoped_gaps = [
            str(item).strip()
            for item in readiness_fields.get("scoped_coverage_gap_keys", [])
            if str(item).strip()
        ] if isinstance(readiness_fields.get("scoped_coverage_gap_keys"), list) else []
        launch_critical_nested_blockers = [
            str(item).strip()
            for item in readiness_summary_payload.get("launch_critical_nested_blockers", [])
            if str(item).strip()
        ] if isinstance(readiness_summary_payload.get("launch_critical_nested_blockers"), list) else []
        try:
            missing_count = int(readiness_summary_payload.get("missing_count") or 0)
            scoped_missing_count = int(readiness_summary_payload.get("scoped_missing_count") or 0)
            ready_count = int(readiness_summary_payload.get("ready_count") or 0)
        except (TypeError, ValueError):
            missing_count = 1
            scoped_missing_count = 1
            ready_count = 0
        flagship_summary = {
            "contract_name": (
                readiness_summary_payload.get("contract_name")
                if is_readiness_gate
                else flagship_product_readiness.get("contract_name")
            ),
            "status": flagship_product_readiness.get("status"),
            "source_receipt": "gate" if is_readiness_gate else "raw",
            "verdict": flagship_product_readiness.get("verdict"),
            "gate_contract_name": flagship_product_readiness.get("contract_name") if is_readiness_gate else None,
            "gate_path": str(flagship_product_readiness_gate_path) if is_readiness_gate else None,
            "raw_readiness_path": str(raw_flagship_product_readiness_path),
            "readiness_load_status": (
                readiness_summary_payload.get("readiness_load_status")
                if is_readiness_gate
                else None
            ),
            "source_receipt_load_status": checks["flagship_product_readiness"].get("load_status"),
            "completion_audit_status": (
                readiness_summary_payload.get("completion_audit_status")
                if is_readiness_gate
                else completion.get("status")
            ),
            "flagship_readiness_audit_status": (
                readiness_summary_payload.get("flagship_readiness_audit_status")
                if is_readiness_gate
                else readiness.get("status")
            ),
            "reason": (
                readiness_summary_payload.get("reason")
                if is_readiness_gate
                else readiness.get("reason") or completion.get("reason")
            ),
            "ready_count": ready_count,
            "missing_count": missing_count,
            "scoped_missing_count": scoped_missing_count,
            "coverage_gap_keys": coverage_gaps,
            "scoped_coverage_gap_keys": scoped_gaps,
            "launch_critical_nested_blockers": launch_critical_nested_blockers,
            "launch_critical_nested_blocker_count": len(launch_critical_nested_blockers),
        }
        structural_flagship_pass = flagship_product_readiness_structural_pass(flagship_summary)
        flagship_summary["structural_pass"] = structural_flagship_pass
        flagship_summary["recovered_for_release_blocking"] = False
        flagship_semantic_failures = flagship_product_readiness_gate_semantic_failures(flagship_summary)
        checks["flagship_product_readiness"]["verdict"] = flagship_product_readiness.get("verdict")
        checks["flagship_product_readiness"]["summary"] = flagship_summary
        checks["flagship_product_readiness"]["semanticFailures"] = flagship_semantic_failures
        checks["flagship_product_readiness"]["source_receipt"] = "gate" if is_readiness_gate else "raw"
        checks["flagship_product_readiness"]["raw_readiness_path"] = str(raw_flagship_product_readiness_path)
        flagship_pass = (
            structural_flagship_pass
            and checks["flagship_product_readiness"]["pass"]
            and not launch_critical_nested_blockers
        )
        if not flagship_pass:
            checks["flagship_product_readiness"]["pass"] = False
            checks["flagship_product_readiness"]["status"] = "fail"
            checks["flagship_product_readiness"].setdefault("failures", [])
            checks["flagship_product_readiness"]["failures"].append("Flagship product readiness is not pass")
            checks["flagship_product_readiness"]["failures"].extend(launch_critical_nested_blockers)
            checks["flagship_product_readiness"]["failures"].extend(flagship_semantic_failures)
    if public_edge_postdeploy:
        public_edge_contract_name = str(public_edge_postdeploy.get("contractName") or public_edge_postdeploy.get("contract_name") or "").strip()
        public_edge_release_truth = public_edge_release_truth_state(public_release_snapshot, public_edge_postdeploy_path)
        public_edge_release_truth_runtime_observation = (
            public_edge_release_truth.get("runtime_observation")
            if isinstance(public_edge_release_truth.get("runtime_observation"), dict)
            else {}
        )
        public_edge_overlay_publish_verification = (
            public_edge_overlay_publish.get("verification")
            if isinstance(public_edge_overlay_publish.get("verification"), dict)
            else {}
        )
        public_edge_overlay_landing_browser_redirect = (
            public_edge_overlay_publish_verification.get("landingBrowserRedirect")
            if isinstance(public_edge_overlay_publish_verification.get("landingBrowserRedirect"), dict)
            else {}
        )
        public_edge_overlay_local_live_surface_parity = (
            public_edge_overlay_publish_verification.get("localLiveSurfaceParity")
            if isinstance(public_edge_overlay_publish_verification.get("localLiveSurfaceParity"), dict)
            else {}
        )
        if not public_edge_overlay_local_live_surface_parity and isinstance(public_edge_local_overlay_parity, dict):
            public_edge_overlay_local_live_surface_parity = {
                "status": public_edge_local_overlay_parity.get("status"),
                "failureCount": len(normalized_string_list(public_edge_local_overlay_parity.get("failures"))),
                "failures": public_edge_local_overlay_parity.get("failures"),
                "verdict": public_edge_local_overlay_parity.get("verdict"),
                "receiptPath": str(public_edge_local_overlay_parity_path)
                if public_edge_local_overlay_parity_path.is_file()
                else "",
            }
        public_edge_release_truth_runtime_failure_lines = public_edge_release_truth_runtime_failures(public_edge_release_truth)
        public_edge_receipt_failures = public_edge_postdeploy_receipt_failures(public_edge_postdeploy)
        public_edge_non_preflight_receipt_failures = public_edge_postdeploy_non_preflight_receipt_failures(public_edge_postdeploy)
        public_edge_release_channel_alignment_failures = public_edge_postdeploy_release_channel_alignment_failures(
            public_edge_postdeploy,
            release_channel,
        )
        missing_public_edge_fields = sorted(
            field
            for field in PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS
            if field not in public_edge_postdeploy
        )
        checks["public_edge_postdeploy_gate"]["summary"] = {
            "contract_name": public_edge_contract_name,
            "core_child_contracts": public_edge_postdeploy.get("coreChildContracts"),
            "preflight_status": public_edge_postdeploy.get("preflightStatus"),
            "preflight_active_lock_count": public_edge_postdeploy.get("preflightActiveLockCount"),
            "preflight_blocking_lock_count": public_edge_postdeploy.get("preflightBlockingLockCount"),
            "preflight_foreign_lock_count": (
                public_edge_preflight.get("foreignLockCount")
                if "foreignLockCount" in public_edge_preflight
                else public_edge_postdeploy.get("preflightForeignLockCount")
            ),
            "preflight_ignored_foreign_lock_count": (
                public_edge_preflight.get("ignoredForeignLockCount")
                if "ignoredForeignLockCount" in public_edge_preflight
                else public_edge_postdeploy.get("preflightIgnoredForeignLockCount")
            ),
            "preflight_foreign_locks_ignored": (
                public_edge_preflight.get("foreignLocksIgnored")
                if "foreignLocksIgnored" in public_edge_preflight
                else public_edge_postdeploy.get("preflightForeignLocksIgnored")
            ),
            "preflight_allow_foreign_build_locks": (
                public_edge_preflight.get("allowForeignBuildLocks")
                if "allowForeignBuildLocks" in public_edge_preflight
                else public_edge_postdeploy.get("preflightAllowForeignBuildLocks")
            ),
            "preflight_stale_looking_lock_count": public_edge_postdeploy.get("preflightStaleLookingLockCount"),
            "preflight_stale_foreign_lock_count": public_edge_postdeploy.get("preflightStaleForeignLockCount"),
            "preflight_stale_foreign_locks_ignored": public_edge_postdeploy.get("preflightStaleForeignLocksIgnored"),
            "preflight_allow_stale_foreign_build_locks": (
                public_edge_preflight.get("allowStaleForeignBuildLocks")
                if "allowStaleForeignBuildLocks" in public_edge_preflight
                else public_edge_postdeploy.get("preflightAllowStaleForeignBuildLocks")
            ),
            "preflight_auto_ignored_stale_foreign_lock_count": public_edge_preflight.get(
                "autoIgnoredStaleForeignLockCount"
            ),
            "preflight_auto_ignore_stale_foreign_lock_seconds": public_edge_preflight.get(
                "autoIgnoreStaleForeignLockSeconds"
            ),
            "preflight_overlay_root": public_edge_postdeploy.get("preflightOverlayRoot"),
            "preflight_overlay_source_fingerprint_matches_current_source": public_edge_postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"
            ),
            "preflight_overlay_source_fingerprint_recorded_aggregate_sha256": public_edge_postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256"
            ),
            "preflight_overlay_source_fingerprint_expected_aggregate_sha256": public_edge_postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256"
            ),
            "preflight_overlay_source_fingerprint_missing_keys": public_edge_postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintMissingKeys"
            ),
            "preflight_overlay_source_fingerprint_mismatched_keys": public_edge_postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"
            ),
            "downloads_status": public_edge_postdeploy.get("downloadsStatus"),
            "downloads_has_marker": public_edge_postdeploy.get("downloadsHasMarker"),
            "status_redirect_has_marker": public_edge_postdeploy.get("statusRedirectHasMarker"),
            "visible_version": public_edge_postdeploy.get("visibleVersion"),
            "status_redirect_version": public_edge_postdeploy.get("statusRedirectVersion"),
            "expected_release_version": public_edge_postdeploy.get("expectedReleaseVersion"),
            "visible_version_matches_release_channel": public_edge_postdeploy.get("visibleVersionMatchesReleaseChannel"),
            "status_redirect_version_matches_release_channel": public_edge_postdeploy.get("statusRedirectVersionMatchesReleaseChannel"),
            "expected_release_status": public_edge_postdeploy.get("expectedReleaseStatus"),
            "expected_release_channel": public_edge_postdeploy.get("expectedReleaseChannel"),
            "expected_release_supportability_state": public_edge_postdeploy.get("expectedReleaseSupportabilityState"),
            "expected_release_rollout_state": public_edge_postdeploy.get("expectedReleaseRolloutState"),
            "release_manifest_http_status": public_edge_postdeploy.get("releaseManifestHttpStatus"),
            "release_manifest_status": public_edge_postdeploy.get("releaseManifestStatus"),
            "release_manifest_status_matches_release_channel": public_edge_postdeploy.get("releaseManifestStatusMatchesReleaseChannel"),
            "release_manifest_channel": public_edge_postdeploy.get("releaseManifestChannel"),
            "release_manifest_channel_matches_release_channel": public_edge_postdeploy.get("releaseManifestChannelMatchesReleaseChannel"),
            "release_manifest_version": public_edge_postdeploy.get("releaseManifestVersion"),
            "release_manifest_version_matches_release_channel": public_edge_postdeploy.get("releaseManifestVersionMatchesReleaseChannel"),
            "release_manifest_supportability_state": public_edge_postdeploy.get("releaseManifestSupportabilityState"),
            "release_manifest_supportability_matches_release_channel": public_edge_postdeploy.get("releaseManifestSupportabilityMatchesReleaseChannel"),
            "release_manifest_rollout_state": public_edge_postdeploy.get("releaseManifestRolloutState"),
            "release_manifest_rollout_matches_release_channel": public_edge_postdeploy.get("releaseManifestRolloutMatchesReleaseChannel"),
            "release_channel_alignment_failures": public_edge_release_channel_alignment_failures,
            "current_release_channel_version": release_channel_summary["version"],
            "current_release_channel_channel": release_channel_summary["channel"],
            "current_release_channel_supportability_state": release_channel_summary["supportability_state"],
            "current_release_channel_rollout_state": release_channel_summary["rollout_state"],
            "pwa_static_status": public_edge_postdeploy.get("pwaStaticStatus"),
            "pwa_manifest_count": public_edge_postdeploy.get("pwaManifestCount"),
            "role_pwa_manifest_count": public_edge_postdeploy.get("rolePwaManifestCount"),
            "role_pwa_manifests": public_edge_postdeploy.get("rolePwaManifests"),
            "pwa_asset_count": public_edge_postdeploy.get("pwaAssetCount"),
            "ledger_stream_non_cacheable": public_edge_postdeploy.get("ledgerStreamNonCacheable"),
            "ledger_stream_precached": public_edge_postdeploy.get("ledgerStreamPrecached"),
            "mobile_ledger_status": public_edge_postdeploy.get("mobileLedgerStatus"),
            "mobile_ledger_payload_status": public_edge_postdeploy.get("mobileLedgerPayloadStatus"),
            "mobile_ledger_cache_control": public_edge_postdeploy.get("mobileLedgerCacheControl"),
            "mobile_ledger_vary": public_edge_postdeploy.get("mobileLedgerVary"),
            "ready_mobile_handoff_status": public_edge_postdeploy.get("readyMobileHandoffStatus"),
            "ready_mobile_handoff_tool_ids": public_edge_postdeploy.get("readyMobileHandoffToolIds"),
            "ready_mobile_handoff_packet_roles": public_edge_postdeploy.get("readyMobileHandoffPacketRoles"),
            "ready_mobile_handoff_frontdoor_launch_route": public_edge_postdeploy.get("readyMobileHandoffFrontdoorLaunchRoute"),
            "ready_mobile_handoff_role_routes": public_edge_postdeploy.get("readyMobileHandoffRoleRoutes"),
            "downloads_status_browser_status": public_edge_postdeploy.get("downloadsStatusBrowserStatus"),
            "downloads_status_browser_artifact_contract": public_edge_postdeploy.get("downloadsStatusBrowserArtifactContract"),
            "mobile_pwa_viewport_status": public_edge_postdeploy.get("mobilePwaViewportStatus"),
            "mobile_pwa_viewport_artifact_contract": public_edge_postdeploy.get("mobilePwaViewportArtifactContract"),
            "mobile_pwa_viewport_route_count": public_edge_postdeploy.get("mobilePwaViewportRouteCount"),
            "mobile_pwa_viewport_viewport_count": public_edge_postdeploy.get("mobilePwaViewportViewportCount"),
            "mobile_pwa_viewport_routes": public_edge_postdeploy.get("mobilePwaViewportRoutes"),
            "mobile_pwa_viewport_missing_routes": public_edge_postdeploy.get("mobilePwaViewportMissingRoutes"),
            "pwa_offline_cache_status": public_edge_postdeploy.get("pwaOfflineCacheStatus"),
            "pwa_offline_cache_artifact_contract": public_edge_postdeploy.get("pwaOfflineCacheArtifactContract"),
            "pwa_offline_cache_cache_version": public_edge_postdeploy.get("pwaOfflineCacheCacheVersion"),
            "pwa_offline_cache_navigation_policy": public_edge_postdeploy.get("pwaOfflineCacheNavigationPolicy"),
            "pwa_offline_cache_private_state_scope": public_edge_postdeploy.get("pwaOfflineCachePrivateStateScope"),
            "pwa_offline_cache_static_paths": public_edge_postdeploy.get("pwaOfflineCacheStaticPaths"),
            "pwa_offline_cache_offline_role_fallbacks": public_edge_postdeploy.get("pwaOfflineCacheOfflineRoleFallbacks"),
            "pwa_offline_cache_query_bearing_requests_cached": public_edge_postdeploy.get("pwaOfflineCacheQueryBearingRequestsCached"),
            "pwa_offline_cache_private_navigation_cached": public_edge_postdeploy.get("pwaOfflineCachePrivateNavigationCached"),
            "pwa_offline_cache_private_api_cached": public_edge_postdeploy.get("pwaOfflineCachePrivateApiCached"),
            "pwa_offline_cache_personalized_ledger_cached": public_edge_postdeploy.get("pwaOfflineCachePersonalizedLedgerCached"),
            "pwa_offline_cache_legacy_private_cache_prefixes_purged": public_edge_postdeploy.get("pwaOfflineCacheLegacyPrivateCachePrefixesPurged"),
            "pwa_offline_cache_unrelated_cache_preserved": public_edge_postdeploy.get("pwaOfflineCacheUnrelatedCachePreserved"),
            "role_alias_route_status": public_edge_postdeploy.get("roleAliasRouteStatus"),
            "role_alias_route_contract": public_edge_postdeploy.get("roleAliasRouteContract"),
            "role_alias_route_results": public_edge_postdeploy.get("roleAliasRouteResults"),
            "role_alias_route_drift": public_edge_postdeploy.get("roleAliasRouteDrift"),
            "release_truth_status": public_edge_release_truth.get("status"),
            "release_truth_verdict": public_edge_release_truth.get("verdict"),
            "release_truth_generated_at": public_edge_release_truth.get("generated_at"),
            "release_truth_runtime_override_applied": public_edge_release_truth.get("runtime_override_applied"),
            "release_truth_runtime_override_reason": public_edge_release_truth.get("runtime_override_reason"),
            "release_truth_runtime_observation_status": public_edge_release_truth_runtime_observation.get("status"),
            "release_truth_runtime_overlay_root": public_edge_release_truth_runtime_observation.get("overlay_root"),
            "release_truth_runtime_active_lock_count": public_edge_release_truth_runtime_observation.get("active_lock_count"),
            "release_truth_runtime_foreign_lock_count": public_edge_release_truth_runtime_observation.get("foreign_lock_count"),
            "release_truth_runtime_stale_foreign_lock_count": public_edge_release_truth_runtime_observation.get("stale_foreign_lock_count"),
            "release_truth_runtime_blocking_findings": normalized_string_list(
                public_edge_release_truth_runtime_observation.get("blocking_findings")
            ),
            "local_overlay_publish_status": public_edge_overlay_publish.get("status"),
            "local_overlay_activation_status": public_edge_overlay_publish.get("activationStatus"),
            "local_overlay_reuse_staging": public_edge_overlay_publish.get("reuseStaging"),
            "local_overlay_verify_receipt_status": (
                public_edge_overlay_publish_verification.get("receiptStatus")
                or public_edge_overlay_verify.get("status")
            ),
            "local_overlay_verify_receipt_path": (
                str(public_edge_overlay_publish_verification.get("receiptPath") or "").strip()
                or (str(public_edge_overlay_verify_path) if public_edge_overlay_verify_path.is_file() else "")
            ),
            "local_overlay_landing_marker_status": public_edge_overlay_publish_verification.get("landingMarkerStatus"),
            "local_overlay_landing_missing_markers": normalized_string_list(
                public_edge_overlay_publish_verification.get("landingMissingMarkers")
            ),
            "local_overlay_landing_browser_redirect_status": public_edge_overlay_landing_browser_redirect.get("status"),
            "local_overlay_landing_browser_redirect_path_matches": public_edge_overlay_landing_browser_redirect.get(
                "pathMatches"
            ),
            "local_overlay_landing_browser_redirect_hash_matches": public_edge_overlay_landing_browser_redirect.get(
                "hashMatches"
            ),
            "local_overlay_landing_browser_redirect_final_url": public_edge_overlay_landing_browser_redirect.get(
                "finalUrl"
            ),
            "local_overlay_local_live_surface_parity_status": public_edge_overlay_local_live_surface_parity.get(
                "status"
            ),
            "local_overlay_local_live_surface_parity_failure_count": int_value(
                public_edge_overlay_local_live_surface_parity.get("failureCount")
            )
            or len(
                normalized_string_list(public_edge_overlay_local_live_surface_parity.get("failures"))
            ),
            "local_overlay_local_live_surface_parity_failures": normalized_string_list(
                public_edge_overlay_local_live_surface_parity.get("failures")
            ),
            "local_overlay_local_live_surface_parity_verdict": public_edge_overlay_local_live_surface_parity.get(
                "verdict"
            ),
            "local_overlay_local_live_surface_parity_receipt_path": (
                str(public_edge_overlay_local_live_surface_parity.get("receiptPath") or "").strip()
                or (str(public_edge_local_overlay_parity_path) if public_edge_local_overlay_parity_path.is_file() else "")
            ),
            "live_role_alias_route_status": (
                public_edge_live_role_alias_routes.get("status")
                if isinstance(public_edge_live_role_alias_routes, dict)
                else None
            ),
            "live_role_alias_route_checked_at_utc": (
                public_edge_live_role_alias_routes.get("checkedAtUtc")
                if isinstance(public_edge_live_role_alias_routes, dict)
                else None
            ),
            "live_role_alias_route_results": (
                public_edge_live_role_alias_routes.get("results")
                if isinstance(public_edge_live_role_alias_routes, dict)
                else None
            ),
            "live_role_alias_route_drift": (
                public_edge_live_role_alias_routes.get("drift")
                if isinstance(public_edge_live_role_alias_routes, dict)
                else None
            ),
            "participate_iframe_shell_status": public_edge_postdeploy.get("participateIframeShellStatus"),
            "participate_iframe_route_count": public_edge_postdeploy.get("participateIframeRouteCount"),
            "participate_iframe_route_iframe_count": public_edge_postdeploy.get("participateIframeRouteIframeCount"),
            "participate_iframe_route_offline_fallback_count": public_edge_postdeploy.get("participateIframeRouteOfflineFallbackCount"),
            "frontdoor_navigation_status": public_edge_postdeploy.get("frontdoorNavigationStatus"),
            "frontdoor_navigation_mobile_artifact_contract": public_edge_postdeploy.get("frontdoorNavigationMobileArtifactContract"),
            "frontdoor_navigation_ledger_artifact_contract": public_edge_postdeploy.get("frontdoorNavigationLedgerArtifactContract"),
            "frontdoor_navigation_anchor_artifact_contract": public_edge_postdeploy.get("frontdoorNavigationAnchorArtifactContract"),
            "frontdoor_navigation_gated_targets": public_edge_postdeploy.get("frontdoorNavigationGatedTargets"),
            "frontdoor_navigation_public_targets": public_edge_postdeploy.get("frontdoorNavigationPublicTargets"),
            "frontdoor_navigation_play_route": public_edge_postdeploy.get("frontdoorNavigationPlayRoute"),
            "frontdoor_navigation_play_sign_in_route": public_edge_postdeploy.get("frontdoorNavigationPlaySignInRoute"),
            "frontdoor_navigation_direct_player_route": public_edge_postdeploy.get("frontdoorNavigationDirectPlayerRoute"),
            "frontdoor_navigation_direct_player_http_status": public_edge_postdeploy.get("frontdoorNavigationDirectPlayerHttpStatus"),
            "frontdoor_navigation_final_url": public_edge_postdeploy.get("frontdoorNavigationFinalUrl"),
            "frontdoor_navigation_private_identity_redacted": public_edge_postdeploy.get("frontdoorNavigationPrivateIdentityRedacted"),
            "frontdoor_navigation_visible_player_url_private_identity_absent": public_edge_postdeploy.get("frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent"),
            "frontdoor_navigation_player_session_context_present": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionContextPresent"),
            "frontdoor_navigation_player_device_context_present": public_edge_postdeploy.get("frontdoorNavigationPlayerDeviceContextPresent"),
            "frontdoor_navigation_live_turn_companion_shell": public_edge_postdeploy.get("frontdoorNavigationLiveTurnCompanionShell"),
            "frontdoor_navigation_pwa_manifest_path": public_edge_postdeploy.get("frontdoorNavigationPwaManifestPath"),
            "frontdoor_navigation_pwa_role": public_edge_postdeploy.get("frontdoorNavigationPwaRole"),
            "frontdoor_navigation_blazor_shell": public_edge_postdeploy.get("frontdoorNavigationBlazorShell"),
            "frontdoor_navigation_rybbit_configured": public_edge_postdeploy.get("frontdoorNavigationRybbitConfigured"),
            "frontdoor_navigation_rybbit_tag": public_edge_postdeploy.get("frontdoorNavigationRybbitTag"),
            "frontdoor_navigation_rybbit_route": public_edge_postdeploy.get("frontdoorNavigationRybbitRoute"),
            "frontdoor_navigation_rybbit_mode": public_edge_postdeploy.get("frontdoorNavigationRybbitMode"),
            "frontdoor_navigation_rybbit_role": public_edge_postdeploy.get("frontdoorNavigationRybbitRole"),
            "frontdoor_navigation_rybbit_site_id_present": public_edge_postdeploy.get("frontdoorNavigationRybbitSiteIdPresent"),
            "frontdoor_navigation_rybbit_script_url_present": public_edge_postdeploy.get("frontdoorNavigationRybbitScriptUrlPresent"),
            "frontdoor_navigation_rybbit_script_url_allowed": public_edge_postdeploy.get("frontdoorNavigationRybbitScriptUrlAllowed"),
            "frontdoor_navigation_rybbit_skip_patterns": public_edge_postdeploy.get("frontdoorNavigationRybbitSkipPatterns"),
            "frontdoor_navigation_rybbit_mask_patterns": public_edge_postdeploy.get("frontdoorNavigationRybbitMaskPatterns"),
            "frontdoor_navigation_rybbit_skip_mobile_paths": public_edge_postdeploy.get("frontdoorNavigationRybbitSkipMobilePaths"),
            "frontdoor_navigation_rybbit_mask_mobile_paths": public_edge_postdeploy.get("frontdoorNavigationRybbitMaskMobilePaths"),
            "frontdoor_navigation_rybbit_masks_private_play_routes": public_edge_postdeploy.get("frontdoorNavigationRybbitMasksPrivatePlayRoutes"),
            "frontdoor_navigation_rybbit_replay_block_selector": public_edge_postdeploy.get("frontdoorNavigationRybbitReplayBlockSelector"),
            "frontdoor_navigation_rybbit_replay_blocks_turn_root": public_edge_postdeploy.get("frontdoorNavigationRybbitReplayBlocksTurnRoot"),
            "frontdoor_navigation_player_session_handoff_url": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffUrl"),
            "frontdoor_navigation_player_session_handoff_status": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffStatus"),
            "frontdoor_navigation_player_session_handoff_link_text": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffLinkText"),
            "frontdoor_navigation_player_session_handoff_preserves_session": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffPreservesSession"),
            "frontdoor_navigation_player_session_handoff_preserves_role": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffPreservesRole"),
            "frontdoor_navigation_player_session_handoff_strips_device": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffStripsDevice"),
            "frontdoor_navigation_player_session_handoff_sender_device_id_present": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent"),
            "frontdoor_navigation_player_session_handoff_private_identity_redacted": public_edge_postdeploy.get("frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted"),
            "frontdoor_navigation_gm_route": public_edge_postdeploy.get("frontdoorNavigationGmRoute"),
            "frontdoor_navigation_gm_route_session_id_present": public_edge_postdeploy.get("frontdoorNavigationGmRouteSessionIdPresent"),
            "frontdoor_navigation_gm_route_private_identity_redacted": public_edge_postdeploy.get("frontdoorNavigationGmRoutePrivateIdentityRedacted"),
            "frontdoor_navigation_gm_http_status": public_edge_postdeploy.get("frontdoorNavigationGmHttpStatus"),
            "frontdoor_navigation_gm_final_url": public_edge_postdeploy.get("frontdoorNavigationGmFinalUrl"),
            "frontdoor_navigation_visible_gm_url_private_identity_absent": public_edge_postdeploy.get("frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent"),
            "frontdoor_navigation_gm_session_context_present": public_edge_postdeploy.get("frontdoorNavigationGmSessionContextPresent"),
            "frontdoor_navigation_gm_device_context_present": public_edge_postdeploy.get("frontdoorNavigationGmDeviceContextPresent"),
            "frontdoor_navigation_gm_live_turn_companion_shell": public_edge_postdeploy.get("frontdoorNavigationGmLiveTurnCompanionShell"),
            "frontdoor_navigation_gm_pwa_manifest_path": public_edge_postdeploy.get("frontdoorNavigationGmPwaManifestPath"),
            "frontdoor_navigation_gm_pwa_role": public_edge_postdeploy.get("frontdoorNavigationGmPwaRole"),
            "frontdoor_navigation_gm_blazor_shell": public_edge_postdeploy.get("frontdoorNavigationGmBlazorShell"),
            "frontdoor_navigation_gm_rybbit_configured": public_edge_postdeploy.get("frontdoorNavigationGmRybbitConfigured"),
            "frontdoor_navigation_gm_rybbit_tag": public_edge_postdeploy.get("frontdoorNavigationGmRybbitTag"),
            "frontdoor_navigation_gm_rybbit_route": public_edge_postdeploy.get("frontdoorNavigationGmRybbitRoute"),
            "frontdoor_navigation_gm_rybbit_mode": public_edge_postdeploy.get("frontdoorNavigationGmRybbitMode"),
            "frontdoor_navigation_gm_rybbit_role": public_edge_postdeploy.get("frontdoorNavigationGmRybbitRole"),
            "frontdoor_navigation_gm_rybbit_site_id_present": public_edge_postdeploy.get("frontdoorNavigationGmRybbitSiteIdPresent"),
            "frontdoor_navigation_gm_rybbit_script_url_present": public_edge_postdeploy.get("frontdoorNavigationGmRybbitScriptUrlPresent"),
            "frontdoor_navigation_gm_rybbit_script_url_allowed": public_edge_postdeploy.get("frontdoorNavigationGmRybbitScriptUrlAllowed"),
            "frontdoor_navigation_gm_rybbit_skip_patterns": public_edge_postdeploy.get("frontdoorNavigationGmRybbitSkipPatterns"),
            "frontdoor_navigation_gm_rybbit_mask_patterns": public_edge_postdeploy.get("frontdoorNavigationGmRybbitMaskPatterns"),
            "frontdoor_navigation_gm_rybbit_skip_mobile_paths": public_edge_postdeploy.get("frontdoorNavigationGmRybbitSkipMobilePaths"),
            "frontdoor_navigation_gm_rybbit_mask_mobile_paths": public_edge_postdeploy.get("frontdoorNavigationGmRybbitMaskMobilePaths"),
            "frontdoor_navigation_gm_rybbit_masks_private_play_routes": public_edge_postdeploy.get("frontdoorNavigationGmRybbitMasksPrivatePlayRoutes"),
            "frontdoor_navigation_gm_rybbit_replay_block_selector": public_edge_postdeploy.get("frontdoorNavigationGmRybbitReplayBlockSelector"),
            "frontdoor_navigation_gm_rybbit_replay_blocks_turn_root": public_edge_postdeploy.get("frontdoorNavigationGmRybbitReplayBlocksTurnRoot"),
            "frontdoor_navigation_gm_session_handoff_url": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffUrl"),
            "frontdoor_navigation_gm_session_handoff_status": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffStatus"),
            "frontdoor_navigation_gm_session_handoff_link_text": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffLinkText"),
            "frontdoor_navigation_gm_session_handoff_preserves_session": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffPreservesSession"),
            "frontdoor_navigation_gm_session_handoff_preserves_role": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffPreservesRole"),
            "frontdoor_navigation_gm_session_handoff_strips_device": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffStripsDevice"),
            "frontdoor_navigation_gm_session_handoff_sender_device_id_present": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent"),
            "frontdoor_navigation_gm_session_handoff_private_identity_redacted": public_edge_postdeploy.get("frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted"),
            "frontdoor_navigation_ledger_primary": public_edge_postdeploy.get("frontdoorNavigationLedgerPrimary"),
            "frontdoor_navigation_anchor_entry_url": public_edge_postdeploy.get("frontdoorNavigationAnchorEntryUrl"),
            "frontdoor_navigation_anchor_final_url": public_edge_postdeploy.get("frontdoorNavigationAnchorFinalUrl"),
            "frontdoor_navigation_anchor_final_path": public_edge_postdeploy.get("frontdoorNavigationAnchorFinalPath"),
            "frontdoor_navigation_anchor_final_hash": public_edge_postdeploy.get("frontdoorNavigationAnchorFinalHash"),
            "frontdoor_navigation_anchor_pwa_manifest_path": public_edge_postdeploy.get("frontdoorNavigationAnchorPwaManifestPath"),
            "frontdoor_navigation_anchor_pwa_role": public_edge_postdeploy.get("frontdoorNavigationAnchorPwaRole"),
            "frontdoor_navigation_anchor_blazor_shell": public_edge_postdeploy.get("frontdoorNavigationAnchorBlazorShell"),
            "frontdoor_navigation_anchor_private_identity_redacted": public_edge_postdeploy.get("frontdoorNavigationAnchorPrivateIdentityRedacted"),
            "frontdoor_navigation_anchor_visible_url_private_identity_absent": public_edge_postdeploy.get("frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent"),
            "frontdoor_navigation_anchor_session_context_present": public_edge_postdeploy.get("frontdoorNavigationAnchorSessionContextPresent"),
            "frontdoor_navigation_anchor_device_context_present": public_edge_postdeploy.get("frontdoorNavigationAnchorDeviceContextPresent"),
            "frontdoor_navigation_anchor_failure": public_edge_postdeploy.get("frontdoorNavigationAnchorFailure"),
            "receipt_failures": public_edge_receipt_failures,
            "non_preflight_receipt_failures": public_edge_non_preflight_receipt_failures,
            "missing_required_fields": missing_public_edge_fields,
        }
        if missing_public_edge_fields:
            checks["public_edge_postdeploy_gate"]["pass"] = False
            checks["public_edge_postdeploy_gate"]["status"] = "fail"
            checks["public_edge_postdeploy_gate"].setdefault("failures", [])
            checks["public_edge_postdeploy_gate"]["failures"].append(
                "missing postdeploy fields: " + ", ".join(missing_public_edge_fields)
            )
        semantic_failures = public_edge_postdeploy_semantic_failures(public_edge_postdeploy)
        frontdoor_homepage_lane_disclosure_missing = public_edge_postdeploy_homepage_lane_disclosure_missing(
            public_edge_postdeploy
        )
        live_role_alias_failures = public_edge_live_role_alias_failures(public_edge_live_role_alias_routes)
        live_role_alias_timeout_recovered = (
            bool(live_role_alias_failures)
            and public_edge_live_role_alias_timeout_only(public_edge_live_role_alias_routes)
            and public_edge_receipt_role_alias_routes_proven(public_edge_postdeploy)
        )
        if live_role_alias_timeout_recovered:
            checks["public_edge_postdeploy_gate"]["summary"]["live_role_alias_timeout_recovered"] = True
            checks["public_edge_postdeploy_gate"]["summary"]["live_role_alias_timeout_recovery_reason"] = (
                "Recovered timeout-only live alias probe failure from the canonical public-edge receipt."
            )
        else:
            semantic_failures.extend(live_role_alias_failures)
        semantic_failures.extend(public_edge_release_channel_alignment_failures)
        if semantic_failures:
            checks["public_edge_postdeploy_gate"]["pass"] = False
            checks["public_edge_postdeploy_gate"]["status"] = "fail"
            if frontdoor_homepage_lane_disclosure_missing:
                checks["public_edge_postdeploy_gate"]["failures"] = []
            checks["public_edge_postdeploy_gate"].setdefault("failures", [])
            checks["public_edge_postdeploy_gate"]["failures"].extend(semantic_failures)
            checks["public_edge_postdeploy_gate"]["summary"]["semantic_failures"] = semantic_failures
        if public_edge_non_preflight_receipt_failures and not frontdoor_homepage_lane_disclosure_missing:
            checks["public_edge_postdeploy_gate"]["pass"] = False
            checks["public_edge_postdeploy_gate"]["status"] = "fail"
            checks["public_edge_postdeploy_gate"].setdefault("failures", [])
            checks["public_edge_postdeploy_gate"]["failures"].extend(public_edge_non_preflight_receipt_failures)
        if public_edge_release_truth_runtime_failure_lines:
            checks["public_edge_postdeploy_gate"]["pass"] = False
            checks["public_edge_postdeploy_gate"]["status"] = "fail"
            for failure in public_edge_release_truth_runtime_failure_lines:
                append_unique_failure(checks["public_edge_postdeploy_gate"], failure)
        if public_edge_contract_name != PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME:
            checks["public_edge_postdeploy_gate"]["pass"] = False
            checks["public_edge_postdeploy_gate"]["status"] = "fail"
            checks["public_edge_postdeploy_gate"].setdefault("failures", [])
            checks["public_edge_postdeploy_gate"]["failures"].append(
                "unexpected public-edge postdeploy contract"
            )
        if (
            public_edge_contract_name == PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME
            and not missing_public_edge_fields
            and not semantic_failures
            and not public_edge_non_preflight_receipt_failures
            and not public_edge_release_truth_runtime_failure_lines
        ):
            checks["public_edge_postdeploy_gate"]["pass"] = True
            checks["public_edge_postdeploy_gate"]["status"] = "pass"
            checks["public_edge_postdeploy_gate"]["release_blocking_recovered_from_preflight"] = (
                normalized_token(public_edge_postdeploy.get("preflightStatus")) != "pass"
                or int_value(public_edge_postdeploy.get("preflightBlockingLockCount")) != 0
            )
            checks["public_edge_postdeploy_gate"].pop("failures", None)
    if teable_important_work:
        sync = teable_important_work.get("sync") if isinstance(teable_important_work.get("sync"), dict) else {}
        rows = teable_important_work.get("rows") if isinstance(teable_important_work.get("rows"), list) else []
        try:
            row_count = int(teable_important_work.get("row_count") or 0)
            synced_count = int(sync.get("synced_count") or 0)
            failed_count = int(sync.get("failed_count") or 0)
        except (TypeError, ValueError):
            row_count = 0
            synced_count = 0
            failed_count = 1
        teable_summary = {
            "contract_name": teable_important_work.get("contract_name"),
            "row_count": row_count,
            "rows_count": len(rows),
            "table_name": teable_important_work.get("table_name"),
            "sync_state": sync.get("state"),
            "sync_attempted": sync.get("attempted") is True,
            "synced_count": synced_count,
            "failed_count": failed_count,
            "created_count": sync.get("created_count"),
            "updated_count": sync.get("updated_count"),
        }
        checks["teable_important_work"]["summary"] = teable_summary
        teable_pass = (
            teable_summary["contract_name"] == "chummer.teable_important_work.v1"
            and row_count > 0
            and teable_summary["rows_count"] == row_count
            and teable_summary["sync_state"] == "passed"
            and teable_summary["sync_attempted"]
            and synced_count == row_count
            and failed_count == 0
        )
        if teable_pass:
            checks["teable_important_work"]["pass"] = True
            checks["teable_important_work"]["status"] = "pass"
            checks["teable_important_work"].pop("failures", None)
        else:
            checks["teable_important_work"]["pass"] = False
            checks["teable_important_work"]["status"] = "fail"
            checks["teable_important_work"].setdefault("failures", [])
            checks["teable_important_work"]["failures"].append("Teable important work sync is not pass")
    for key in ("artifact", "startupReceipt", "visualAuditSource"):
        if isinstance(windows_installer_visual_audit.get(key), dict):
            checks["windows_installer_visual_audit"][key] = windows_installer_visual_audit[key]
    if windows_installer_visual_audit:
        mirror_windows_runtime_artifacts(checks["windows_installer_visual_audit"])
        windows_semantic_failures = windows_installer_visual_audit_semantic_failures(windows_installer_visual_audit)
        checks["windows_installer_visual_audit"]["semanticFailures"] = windows_semantic_failures
        if windows_semantic_failures:
            checks["windows_installer_visual_audit"]["pass"] = False
            checks["windows_installer_visual_audit"]["status"] = "fail"
            for failure in windows_semantic_failures:
                append_unique_failure(checks["windows_installer_visual_audit"], failure)
        windows_digest_mismatch = windows_visual_audit_digest_mismatch_failure(windows_installer_visual_audit)
        if windows_digest_mismatch:
            checks["windows_installer_visual_audit"]["digestMismatchFailure"] = windows_digest_mismatch
            append_unique_failure(checks["windows_installer_visual_audit"], windows_digest_mismatch)
        windows_recovery_pack_failure = windows_operator_recovery_pack_failure(checks["windows_installer_visual_audit"])
        if windows_recovery_pack_failure and not checks["windows_installer_visual_audit"]["pass"]:
            checks["windows_installer_visual_audit"]["operatorRequestFailure"] = windows_recovery_pack_failure
            append_unique_failure(checks["windows_installer_visual_audit"], windows_recovery_pack_failure)
        windows_missing_artifact_failure = windows_operator_missing_artifact_failure(
            checks["windows_installer_visual_audit"]
        )
        if windows_missing_artifact_failure and not checks["windows_installer_visual_audit"]["pass"]:
            checks["windows_installer_visual_audit"]["operatorArtifactMissingFailure"] = windows_missing_artifact_failure
            append_unique_failure(checks["windows_installer_visual_audit"], windows_missing_artifact_failure)
        windows_operator_ask_resend = windows_operator_ask_resend_failure(
            checks["windows_installer_visual_audit"]
        )
        if windows_operator_ask_resend and not checks["windows_installer_visual_audit"]["pass"]:
            checks["windows_installer_visual_audit"]["operatorAskResendAdvisory"] = windows_operator_ask_resend
            append_unique_advisory_action(checks["windows_installer_visual_audit"], windows_operator_ask_resend)
        windows_stage_hint_advisory = windows_stage_visual_proof_hint_advisory(
            checks["windows_installer_visual_audit"]
        )
        if windows_stage_hint_advisory and not checks["windows_installer_visual_audit"]["pass"]:
            checks["windows_installer_visual_audit"]["stageVisualProofHintAdvisory"] = windows_stage_hint_advisory
            append_unique_advisory_action(checks["windows_installer_visual_audit"], windows_stage_hint_advisory)
    if oauth:
        checks["google_oauth_linking_proof"]["quick_handoff_probe"] = oauth.get("quick_handoff_probe", {})
        checks["google_oauth_linking_proof"]["signed_in_link_handoff"] = oauth.get("signed_in_link_handoff", {})
        checks["google_oauth_linking_proof"]["operator_end_to_end_evidence"] = oauth.get(
            "operator_end_to_end_evidence", {}
        )
        google_operator_failure = google_oauth_operator_evidence_missing_failure(oauth)
        if google_operator_failure:
            checks["google_oauth_linking_proof"]["operatorEvidenceMissingFailure"] = google_operator_failure
            append_unique_failure(checks["google_oauth_linking_proof"], google_operator_failure)
        google_operator_ask_resend = google_oauth_operator_ask_resend_failure(
            checks["google_oauth_linking_proof"]
        )
        if google_operator_ask_resend:
            checks["google_oauth_linking_proof"]["operatorAskResendAdvisory"] = google_operator_ask_resend
            append_unique_advisory_action(checks["google_oauth_linking_proof"], google_operator_ask_resend)
        google_gate = checks["google_oauth_linking_proof"]
        if not google_gate.get("pass") and google_oauth_release_truth_effective_pass(google_gate):
            google_gate["release_truth_effective_pass"] = True
            google_gate["release_truth_effective_pass_reason"] = (
                "auth_signin_automation_paused_by_user_request"
                if normalized_string_list(google_gate.get("failures"))
                and all(
                    item.startswith("auth_signin_automation_paused:")
                    for item in normalized_string_list(google_gate.get("failures"))
                )
                else "operator_evidence_green_signed_in_preflight_only_failure"
            )
            google_gate["fresh_within_hours"] = RELEASE_BLOCKING_MAX_AGE_HOURS
            google_gate["fresh"] = generated_at_is_fresh(
                str(google_gate.get("generated_at_utc") or "")
            )
            google_gate["release_blocking"] = False
    release_ready_windows_artifacts = release_ready_windows_blocking_artifacts(release_ready)
    if release_ready_windows_artifacts:
        blocking_gate_artifacts = release_ready.get("blocking_gate_artifacts")
        if isinstance(blocking_gate_artifacts, dict):
            checks["release_ready"]["blocking_gate_artifacts"] = blocking_gate_artifacts
        checks["windows_installer_visual_audit"]["release_ready_blocking_artifacts"] = release_ready_windows_artifacts
        for key, value in release_ready_windows_artifacts.items():
            if key.startswith("stage_"):
                checks["windows_installer_visual_audit"][key] = value
    snapshot_truth_audit = release_ready_snapshot_truth_audit(
        release_ready,
        PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH,
    )
    if snapshot_truth_audit:
        checks["release_ready"]["public_release_snapshot_readonly_audit"] = snapshot_truth_audit
    if release_ready and not release_ready_self_check:
        release_ready_semantic_failures = release_ready_receipt_semantic_failures(release_ready)
        checks["release_ready"]["semanticFailures"] = release_ready_semantic_failures
        if release_ready_semantic_failures:
            checks["release_ready"]["pass"] = False
            checks["release_ready"]["status"] = "fail"
            append_unique_failure(checks["release_ready"], "release_ready semantic proof failed")
            for failure in release_ready_semantic_failures:
                append_unique_failure(checks["release_ready"], failure)
    if design:
        design_semantic_failures = expected_verdict_receipt_semantic_failures(
            "design_quality_gate",
            design,
            DESIGN_READY_VERDICT,
        )
        checks["design_quality_gate"]["semanticFailures"] = design_semantic_failures
        if design_semantic_failures:
            checks["design_quality_gate"]["pass"] = False
            checks["design_quality_gate"]["status"] = "fail"
            append_unique_failure(checks["design_quality_gate"], "design_quality_gate semantic proof failed")
            for failure in design_semantic_failures:
                append_unique_failure(checks["design_quality_gate"], failure)
    if ui_frame:
        ui_frame_semantic_failures = expected_verdict_receipt_semantic_failures(
            "ui_frame_integrity",
            ui_frame,
            READY_VERDICT,
        )
        checks["ui_frame_integrity"]["semanticFailures"] = ui_frame_semantic_failures
        if ui_frame_semantic_failures:
            checks["ui_frame_integrity"]["pass"] = False
            checks["ui_frame_integrity"]["status"] = "fail"
            append_unique_failure(checks["ui_frame_integrity"], "ui_frame_integrity semantic proof failed")
            for failure in ui_frame_semantic_failures:
                append_unique_failure(checks["ui_frame_integrity"], failure)
    if participate_billing_honesty:
        participate_semantic_failures = expected_verdict_receipt_semantic_failures(
            "participate_billing_honesty",
            participate_billing_honesty,
            READY_VERDICT,
        )
        checks["participate_billing_honesty"]["semanticFailures"] = participate_semantic_failures
        if participate_semantic_failures:
            checks["participate_billing_honesty"]["pass"] = False
            checks["participate_billing_honesty"]["status"] = "fail"
            append_unique_failure(
                checks["participate_billing_honesty"],
                "participate_billing_honesty semantic proof failed",
            )
            for failure in participate_semantic_failures:
                append_unique_failure(checks["participate_billing_honesty"], failure)
    if account_handoff_runtime_config:
        account_handoff_semantic_failures = expected_verdict_receipt_semantic_failures(
            "account_handoff_runtime_config",
            account_handoff_runtime_config,
            READY_VERDICT,
        )
        checks["account_handoff_runtime_config"]["semanticFailures"] = account_handoff_semantic_failures
        if account_handoff_semantic_failures:
            checks["account_handoff_runtime_config"]["pass"] = False
            checks["account_handoff_runtime_config"]["status"] = "fail"
            append_unique_failure(
                checks["account_handoff_runtime_config"],
                "account_handoff_runtime_config semantic proof failed",
            )
            for failure in account_handoff_semantic_failures:
                append_unique_failure(checks["account_handoff_runtime_config"], failure)

    portable_failure_counts = (
        portable_receipts_audit.get("failure_counts")
        if isinstance(portable_receipts_audit.get("failure_counts"), dict)
        else {}
    )
    checks["portable_receipts_audit"]["summary"] = {
        "contract_name": portable_receipts_audit.get("contract_name"),
        "scanned_artifact_count": portable_receipts_audit.get("scanned_artifact_count"),
        "machine_specific_path_failure_count": portable_failure_counts.get(
            "machine_specific_paths"
        ),
        "artifact_integrity_failure_count": portable_failure_counts.get(
            "artifact_integrity"
        ),
        "machine_specific_path_hits": normalized_string_list(
            portable_receipts_audit.get("machine_specific_path_hits")
        ),
        "artifact_integrity_hits": normalized_string_list(
            portable_receipts_audit.get("artifact_integrity_hits")
        ),
        "unreadable_artifacts": normalized_string_list(
            portable_receipts_audit.get("unreadable_artifacts")
        ),
    }
    apply_direct_release_gate_semantics(
        "portable_receipts_audit",
        checks["portable_receipts_audit"],
        portable_receipts_audit_semantic_failures(portable_receipts_audit),
    )

    supply_checks = (
        supply_chain_release_gate.get("checks")
        if isinstance(supply_chain_release_gate.get("checks"), dict)
        else {}
    )
    checks["supply_chain_release_gate"]["summary"] = {
        "contract_name": supply_chain_release_gate.get("contract_name"),
        "pass_marker": supply_chain_release_gate.get("pass"),
        "verdict": supply_chain_release_gate.get("verdict"),
        "blockers": normalized_string_list(supply_chain_release_gate.get("blockers")),
        "check_statuses": {
            check_id: str(
                (supply_checks.get(check_id) or {}).get("status")
                if isinstance(supply_checks.get(check_id), dict)
                else "missing"
            ).strip()
            for check_id in sorted(SUPPLY_CHAIN_REQUIRED_CHECKS)
        },
    }
    apply_direct_release_gate_semantics(
        "supply_chain_release_gate",
        checks["supply_chain_release_gate"],
        supply_chain_release_gate_semantic_failures(supply_chain_release_gate),
    )

    observability_checks = (
        public_edge_observability_release_gate.get("checks")
        if isinstance(public_edge_observability_release_gate.get("checks"), list)
        else []
    )
    observability_failed_check_ids = [
        str(item.get("id") or "").strip()
        for item in observability_checks
        if isinstance(item, dict)
        and str(item.get("id") or "").strip()
        and normalized_token(item.get("status")) != "pass"
    ]
    observability_release_candidate = (
        public_edge_observability_release_gate.get("release_candidate")
        if isinstance(public_edge_observability_release_gate.get("release_candidate"), dict)
        else {}
    )
    observability_operator_intake = (
        public_edge_observability_release_gate.get("operator_intake")
        if isinstance(public_edge_observability_release_gate.get("operator_intake"), dict)
        else {}
    )
    checks["public_edge_observability_release_gate"]["summary"] = {
        "contract_name": public_edge_observability_release_gate.get("contract_name"),
        "verdict": public_edge_observability_release_gate.get("verdict"),
        "failure_count": public_edge_observability_release_gate.get("failure_count"),
        "failed_check_ids": observability_failed_check_ids,
        "release_candidate_version": observability_release_candidate.get("version"),
        "release_candidate_channel": observability_release_candidate.get("channel"),
        "operator_intake_state": observability_operator_intake.get("state"),
        "external_evidence_required": observability_operator_intake.get(
            "external_evidence_required"
        ),
    }
    observability_operator_dependencies = normalized_string_list(
        public_edge_observability_release_gate.get("operator_dependencies")
    )
    if observability_operator_dependencies:
        checks["public_edge_observability_release_gate"][
            "nextActions"
        ] = observability_operator_dependencies
    apply_direct_release_gate_semantics(
        "public_edge_observability_release_gate",
        checks["public_edge_observability_release_gate"],
        public_edge_observability_release_gate_semantic_failures(
            public_edge_observability_release_gate
        ),
    )

    recover_flagship_product_readiness_release_blocking(checks)

    for name in sorted(_effective_freshness_required_checks()):
        data = checks.get(name)
        if not isinstance(data, dict) or data.get("release_blocking") is False:
            continue
        generated_at = data.get("generated_at_utc")
        fresh = generated_at_is_fresh(generated_at)
        data["fresh_within_hours"] = RELEASE_BLOCKING_MAX_AGE_HOURS
        data["fresh"] = fresh
        if not fresh:
            data["pass"] = False
            data["status"] = "fail"
            data.setdefault("failures", [])
            data["failures"].append(
                f"{name} generated_at is missing or stale for operator dashboard"
            )

    for name in sorted(CONTEXT_FRESHNESS_CHECKS):
        data = checks.get(name)
        if not isinstance(data, dict):
            continue
        generated_at = data.get("generated_at_utc")
        fresh = generated_at_is_fresh(generated_at)
        data["fresh_within_hours"] = RELEASE_BLOCKING_MAX_AGE_HOURS
        data["fresh"] = fresh
        if not fresh:
            data["pass"] = False
            data.setdefault("failures", [])
            data["failures"].append(
                f"{name} generated_at is missing or stale for operator dashboard"
            )

    required_names = sorted(_effective_required_checks(checks))
    failed_release_blocking_checks = sorted(
        name for name in required_names if release_blocking_check_failed(name, checks[name])
    )
    failures = list(failed_release_blocking_checks)
    for key_name, detail_field in (
        ("google_oauth_linking_proof", "operatorEvidenceMissingFailure"),
        ("windows_installer_visual_audit", "operatorRequestFailure"),
        ("windows_installer_visual_audit", "operatorArtifactMissingFailure"),
        ("windows_installer_visual_audit", "digestMismatchFailure"),
    ):
        data = checks.get(key_name)
        if isinstance(data, dict) and release_blocking_check_failed(key_name, data):
            detail = str(data.get(detail_field) or "").strip()
            if detail and detail not in failures:
                failures.append(detail)
    root_blockers, local_surface_status = release_root_blocker_families(checks, root_release_blockers)
    root_context = root_release_truth_context(root_release_blockers)

    return {
        "contract_name": "chummer.operator_release_dashboard",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "OPERABLE_RELEASE_READY" if not failures else "OPERABLE_RELEASE_BLOCKED",
        "summary": {
            "release_blocking_check_count": len(required_names),
            "failed_release_blocking_check_count": len(failed_release_blocking_checks),
            "failed_release_blocking_checks": failed_release_blocking_checks,
            "failure_count": len(failures),
            "root_blocker_count": len(root_blockers),
            "root_blocker_ids": [str(item.get("id") or "").strip() for item in root_blockers if isinstance(item, dict)],
            "local_surface_all_passing": bool(local_surface_status.get("all_passing")),
        },
        "release": {
            "version": release_channel.get("version"),
            "published_at": release_channel.get("publishedAt") or release_channel.get("published_at"),
            "channel": release_channel.get("channel") or release_channel.get("channelId"),
            "rollout_state": release_channel.get("rolloutState"),
            "supportability_state": release_channel.get("supportabilityState"),
            "known_issue_summary": customer_safe_release_text(release_channel.get("knownIssueSummary")),
        },
        "mirrors": {
            "external_required": mirror.get("external_required"),
            "required_providers": mirror.get("required_providers"),
            "providers": providers,
        },
        "rulesets": rulesets,
        "ui": {
            "frame_base_url": frame_base_url,
            "frame_checked_pages": frame_summary.get("checked_pages"),
            "frame_failure_count": frame_summary.get("failure_count"),
            "design_verdict": design.get("verdict"),
        },
        "account_handoffs": {
            "billing_mode": ((account_handoff_runtime_config.get("billing") or {}) if isinstance(account_handoff_runtime_config.get("billing"), dict) else {}).get("mode"),
            "release_upload_mode": ((account_handoff_runtime_config.get("release_upload") or {}) if isinstance(account_handoff_runtime_config.get("release_upload"), dict) else {}).get("mode"),
        },
        "release_blocking_checks": sorted(required_names),
        "failed_release_blocking_checks": failed_release_blocking_checks,
        "release_blocking_failures": failures,
        "root_blockers": root_blockers,
        "local_surface_status": local_surface_status,
        "checks": checks,
        "failures": failures,
        "root_blocker_ids": root_context["root_blocker_ids"],
        "root_blockers_generated_at": root_context["root_blockers_generated_at"],
        "stable_promotion_command": root_context["stable_promotion_command"],
        "post_promotion_verify_command": root_context["post_promotion_verify_command"],
        "root_release_truth_source": root_context["root_release_truth_source"],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    mirrors = payload.get("mirrors") if isinstance(payload.get("mirrors"), dict) else {}
    rulesets = payload.get("rulesets") if isinstance(payload.get("rulesets"), dict) else {}
    root_blockers = payload.get("root_blockers") if isinstance(payload.get("root_blockers"), list) else []
    local_surface_status = (
        payload.get("local_surface_status")
        if isinstance(payload.get("local_surface_status"), dict)
        else {}
    )
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    account_handoffs = payload.get("account_handoffs") if isinstance(payload.get("account_handoffs"), dict) else {}
    lines = [
        f"# {payload.get('verdict')}",
        "",
        f"- Generated: {payload.get('generated_at_utc')}",
        f"- Version: `{release.get('version')}`",
        f"- Channel: `{release.get('channel')}`",
        f"- Published: `{release.get('published_at')}`",
        f"- Supportability: `{release.get('supportability_state')}`",
        f"- Rollout: `{release.get('rollout_state')}`",
        f"- Mirrors: {', '.join(f'{name}={status}' for name, status in sorted((mirrors.get('providers') or {}).items()))}",
        f"- Billing mode: `{account_handoffs.get('billing_mode')}`",
        f"- Release-upload mode: `{account_handoffs.get('release_upload_mode')}`",
        "",
        "## Root Blockers",
    ]
    if root_blockers:
        for blocker in root_blockers:
            if not isinstance(blocker, dict):
                continue
            lines.append(
                f"- `{blocker.get('id')}`: {blocker.get('summary')}"
            )
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
        "## Rulesets",
    ])
    for name, data in sorted(rulesets.items()):
        if isinstance(data, dict):
            lines.append(f"- `{name}`: status `{data.get('status')}`, workflow parity `{data.get('workflow_parity_status')}`, assumption `{data.get('human_side_gold_assumption')}`")
    lines.extend(["", "## Checks"])
    for name, data in sorted(checks.items()):
        if isinstance(data, dict):
            release_blocking = bool(data.get("release_blocking", True))
            rendered_failures = False
            if data.get("pass"):
                mark = "PASS"
            elif release_blocking:
                mark = "FAIL"
            else:
                mark = "INFO"
            suffix = "" if release_blocking else " (operator context, not release-blocking)"
            lines.append(f"- {mark} `{name}`: `{data.get('status')}`{suffix}")
            if data.get("raw_status") and data.get("raw_status") != data.get("status"):
                lines.append(f"  - raw status: `{data.get('raw_status')}`")
            if name == "release_channel" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - release: "
                    f"version={summary.get('version')} "
                    f"channel={summary.get('channel')} "
                    f"supportability={summary.get('supportability_state')} "
                    f"rollout={summary.get('rollout_state')}"
                )
                if data.get("failures"):
                    lines.append(f"  - failures: {', '.join(str(item) for item in data['failures'])}")
                    rendered_failures = True
            if name == "public_route_proof" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - routes: "
                    f"count={summary.get('route_count')} "
                    f"failed={summary.get('failed_count')} "
                    f"negative_path_failed={summary.get('negative_path_failed_count')}"
                )
            if name == "portable_receipts_audit" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - portable receipts: "
                    f"scanned={summary.get('scanned_artifact_count')} "
                    f"machine_specific_paths={summary.get('machine_specific_path_failure_count')} "
                    f"artifact_integrity={summary.get('artifact_integrity_failure_count')}"
                )
                if summary.get("machine_specific_path_hits"):
                    lines.append(
                        "  - machine-specific path hits: "
                        + ", ".join(str(item) for item in summary["machine_specific_path_hits"])
                    )
                if summary.get("artifact_integrity_hits"):
                    lines.append(
                        "  - artifact-integrity hits: "
                        + ", ".join(str(item) for item in summary["artifact_integrity_hits"])
                    )
            if name == "supply_chain_release_gate" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - supply chain: "
                    f"verdict={summary.get('verdict') or 'missing'} "
                    f"pass_marker={summary.get('pass_marker')} "
                    f"checks={summary.get('check_statuses')} "
                    f"blockers={summary.get('blockers')}"
                )
            if (
                name == "public_edge_observability_release_gate"
                and isinstance(data.get("summary"), dict)
            ):
                summary = data["summary"]
                lines.append(
                    "  - public-edge observability: "
                    f"verdict={summary.get('verdict') or 'missing'} "
                    f"failures={summary.get('failure_count')} "
                    f"failed_checks={summary.get('failed_check_ids')} "
                    f"release={summary.get('release_candidate_version') or 'missing'} "
                    f"channel={summary.get('release_candidate_channel') or 'missing'} "
                    f"intake={summary.get('operator_intake_state') or 'missing'} "
                    f"external_evidence_required={summary.get('external_evidence_required')}"
                )
            if name == "blazor_execution_horizon_bridge" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
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
                play_surface = summary.get("play_surface_horizon")
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
            if name == "public_edge_postdeploy_gate" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - edge: "
                    f"preflight={summary.get('preflight_status')} "
                    f"blocking_locks={summary.get('preflight_blocking_lock_count')} "
                    f"active_locks={summary.get('preflight_active_lock_count')} "
                    f"stale_locks={summary.get('preflight_stale_looking_lock_count')} "
                    f"stale_foreign={summary.get('preflight_stale_foreign_lock_count')} "
                    f"ignored={summary.get('preflight_stale_foreign_locks_ignored')} "
                    f"overlay_root={summary.get('preflight_overlay_root')} "
                    f"overlay_source_match={summary.get('preflight_overlay_source_fingerprint_matches_current_source')} "
                    f"overlay_missing={summary.get('preflight_overlay_source_fingerprint_missing_keys')} "
                    f"overlay_mismatched={summary.get('preflight_overlay_source_fingerprint_mismatched_keys')} "
                    f"downloads={summary.get('downloads_status')} "
                    f"downloads_marker={summary.get('downloads_has_marker')} "
                    f"status_marker={summary.get('status_redirect_has_marker')} "
                    f"visible_version={summary.get('visible_version')} "
                    f"status_version={summary.get('status_redirect_version')} "
                    f"expected_version={summary.get('expected_release_version')} "
                    f"version_match={summary.get('visible_version_matches_release_channel')} "
                    f"status_version_match={summary.get('status_redirect_version_matches_release_channel')} "
                    f"release_manifest_supportability={summary.get('release_manifest_supportability_state')} "
                    f"expected_supportability={summary.get('expected_release_supportability_state')} "
                    f"supportability_match={summary.get('release_manifest_supportability_matches_release_channel')} "
                    f"release_manifest_rollout={summary.get('release_manifest_rollout_state')} "
                    f"expected_rollout={summary.get('expected_release_rollout_state')} "
                    f"rollout_match={summary.get('release_manifest_rollout_matches_release_channel')}"
                )
                lines.append(
                    "  - preflight lock policy: "
                    f"foreign_locks={summary.get('preflight_foreign_lock_count')} "
                    f"ignored_foreign_locks={summary.get('preflight_ignored_foreign_lock_count')} "
                    f"foreign_locks_ignored={summary.get('preflight_foreign_locks_ignored')} "
                    f"allow_foreign_build_locks={summary.get('preflight_allow_foreign_build_locks')} "
                    f"allow_stale_foreign_build_locks={summary.get('preflight_allow_stale_foreign_build_locks')} "
                    f"auto_ignored_stale_foreign_locks={summary.get('preflight_auto_ignored_stale_foreign_lock_count')} "
                    f"auto_ignore_stale_foreign_lock_seconds={summary.get('preflight_auto_ignore_stale_foreign_lock_seconds')}"
                )
                lines.append(
                    "  - participate iframe shell: "
                    f"status={summary.get('participate_iframe_shell_status')} "
                    f"routes={summary.get('participate_iframe_route_count')} "
                    f"iframe_routes={summary.get('participate_iframe_route_iframe_count')} "
                    f"fallback_routes={summary.get('participate_iframe_route_offline_fallback_count')}"
                )
                lines.append(
                    "  - mobile PWA viewport: "
                    f"status={summary.get('mobile_pwa_viewport_status')} "
                    f"routes={summary.get('mobile_pwa_viewport_route_count')} "
                    f"viewports={summary.get('mobile_pwa_viewport_viewport_count')} "
                    f"missing_routes={summary.get('mobile_pwa_viewport_missing_routes')}"
                )
                lines.append(
                    "  - role PWA manifests: "
                    f"count={summary.get('role_pwa_manifest_count')} "
                    f"manifests={summary.get('role_pwa_manifests')}"
                )
                lines.append(
                    "  - ready mobile handoff: "
                    f"status={summary.get('ready_mobile_handoff_status')} "
                    f"tools={summary.get('ready_mobile_handoff_tool_ids')} "
                    f"packet_roles={summary.get('ready_mobile_handoff_packet_roles')} "
                    f"frontdoor_launch_route={summary.get('ready_mobile_handoff_frontdoor_launch_route')} "
                    f"role_routes={summary.get('ready_mobile_handoff_role_routes')}"
                )
                lines.append(
                    "  - mobile PWA offline cache: "
                    f"status={summary.get('pwa_offline_cache_status')} "
                    f"version={summary.get('pwa_offline_cache_cache_version')} "
                    f"navigation={summary.get('pwa_offline_cache_navigation_policy')} "
                    f"private_state={summary.get('pwa_offline_cache_private_state_scope')} "
                    f"static_paths={summary.get('pwa_offline_cache_static_paths')} "
                    f"role_fallbacks={summary.get('pwa_offline_cache_offline_role_fallbacks')} "
                    f"private_navigation_cached={summary.get('pwa_offline_cache_private_navigation_cached')} "
                    f"private_api_cached={summary.get('pwa_offline_cache_private_api_cached')} "
                    f"personalized_ledger_cached={summary.get('pwa_offline_cache_personalized_ledger_cached')}"
                )
                lines.append(
                    "  - public role aliases: "
                    f"status={summary.get('role_alias_route_status')} "
                    f"results={summary.get('role_alias_route_results')} "
                    f"drift={summary.get('role_alias_route_drift')}"
                )
                lines.append(
                    "  - local overlay staging: "
                    f"publish_status={summary.get('local_overlay_publish_status')} "
                    f"activation_status={summary.get('local_overlay_activation_status')} "
                    f"reuse_staging={summary.get('local_overlay_reuse_staging')} "
                    f"verify_receipt_status={summary.get('local_overlay_verify_receipt_status')} "
                    f"landing_marker_status={summary.get('local_overlay_landing_marker_status')} "
                    f"landing_redirect_status={summary.get('local_overlay_landing_browser_redirect_status')} "
                    f"path_match={summary.get('local_overlay_landing_browser_redirect_path_matches')} "
                    f"hash_match={summary.get('local_overlay_landing_browser_redirect_hash_matches')} "
                    f"local_live_surface_parity={summary.get('local_overlay_local_live_surface_parity_status')} "
                    f"local_live_surface_parity_failures={summary.get('local_overlay_local_live_surface_parity_failure_count')}"
                )
                if summary.get("local_overlay_local_live_surface_parity_failures"):
                    lines.append(
                        "  - local overlay parity failures: "
                        + ", ".join(str(item) for item in summary["local_overlay_local_live_surface_parity_failures"])
                    )
                if summary.get("live_role_alias_route_status") is not None:
                    lines.append(
                        "  - live public role aliases: "
                        f"status={summary.get('live_role_alias_route_status')} "
                        f"checked_at={summary.get('live_role_alias_route_checked_at_utc')} "
                        f"results={summary.get('live_role_alias_route_results')} "
                        f"drift={summary.get('live_role_alias_route_drift')}"
                    )
                if (
                    summary.get("release_truth_verdict") is not None
                    or summary.get("release_truth_runtime_observation_status") is not None
                ):
                    lines.append(
                        "  - live release truth: "
                        f"verdict={summary.get('release_truth_verdict')} "
                        f"status={summary.get('release_truth_status')} "
                        f"runtime_override={summary.get('release_truth_runtime_override_applied')} "
                        f"runtime_status={summary.get('release_truth_runtime_observation_status')} "
                        f"runtime_active_locks={summary.get('release_truth_runtime_active_lock_count')} "
                        f"runtime_foreign_locks={summary.get('release_truth_runtime_foreign_lock_count')} "
                        f"runtime_stale_foreign_locks={summary.get('release_truth_runtime_stale_foreign_lock_count')} "
                        f"blocking_findings={summary.get('release_truth_runtime_blocking_findings')}"
                    )
                lines.append(
                    "  - front-door navigation: "
                    f"status={summary.get('frontdoor_navigation_status')} "
                    f"gated_targets={summary.get('frontdoor_navigation_gated_targets')} "
                    f"public_targets={summary.get('frontdoor_navigation_public_targets')} "
                    f"play_route={summary.get('frontdoor_navigation_play_route')} "
                    f"play_sign_in_route={summary.get('frontdoor_navigation_play_sign_in_route')} "
                    f"direct_player_route={summary.get('frontdoor_navigation_direct_player_route')} "
                    f"ledger_primary={summary.get('frontdoor_navigation_ledger_primary')}"
                )
                lines.append(
                    "  - front-door mobile launch: "
                    f"player_http={summary.get('frontdoor_navigation_direct_player_http_status')} "
                    f"player_role={summary.get('frontdoor_navigation_pwa_role')} "
                    f"player_manifest={summary.get('frontdoor_navigation_pwa_manifest_path')} "
                    f"player_blazor={summary.get('frontdoor_navigation_blazor_shell')} "
                    f"player_rybbit={summary.get('frontdoor_navigation_rybbit_configured')} "
                    f"player_rybbit_skip_mobile={summary.get('frontdoor_navigation_rybbit_skip_mobile_paths')} "
                    f"player_rybbit_mask_api={summary.get('frontdoor_navigation_rybbit_masks_private_play_routes')} "
                    f"player_rybbit_replay_block={summary.get('frontdoor_navigation_rybbit_replay_blocks_turn_root')} "
                    f"gm_http={summary.get('frontdoor_navigation_gm_http_status')} "
                    f"gm_role={summary.get('frontdoor_navigation_gm_pwa_role')} "
                    f"gm_manifest={summary.get('frontdoor_navigation_gm_pwa_manifest_path')} "
                    f"gm_blazor={summary.get('frontdoor_navigation_gm_blazor_shell')} "
                    f"gm_rybbit={summary.get('frontdoor_navigation_gm_rybbit_configured')} "
                    f"gm_rybbit_skip_mobile={summary.get('frontdoor_navigation_gm_rybbit_skip_mobile_paths')} "
                    f"gm_rybbit_mask_api={summary.get('frontdoor_navigation_gm_rybbit_masks_private_play_routes')} "
                    f"gm_rybbit_replay_block={summary.get('frontdoor_navigation_gm_rybbit_replay_blocks_turn_root')}"
                )
                lines.append(
                    "  - front-door session handoff: "
                    f"player_preserves_session={summary.get('frontdoor_navigation_player_session_handoff_preserves_session')} "
                    f"player_preserves_role={summary.get('frontdoor_navigation_player_session_handoff_preserves_role')} "
                    f"player_strips_device={summary.get('frontdoor_navigation_player_session_handoff_strips_device')} "
                    f"player_identity_redacted={summary.get('frontdoor_navigation_player_session_handoff_private_identity_redacted')} "
                    f"gm_preserves_session={summary.get('frontdoor_navigation_gm_session_handoff_preserves_session')} "
                    f"gm_preserves_role={summary.get('frontdoor_navigation_gm_session_handoff_preserves_role')} "
                    f"gm_strips_device={summary.get('frontdoor_navigation_gm_session_handoff_strips_device')} "
                    f"gm_identity_redacted={summary.get('frontdoor_navigation_gm_session_handoff_private_identity_redacted')}"
                )
                if summary.get("missing_required_fields"):
                    lines.append(f"  - missing postdeploy fields: {', '.join(str(item) for item in summary['missing_required_fields'])}")
                if data.get("failures"):
                    lines.append(f"  - failures: {', '.join(str(item) for item in data['failures'])}")
                    rendered_failures = True
            if name == "teable_important_work" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - teable: "
                    f"state={summary.get('sync_state')} "
                    f"attempted={summary.get('sync_attempted')} "
                    f"rows={summary.get('synced_count')}/{summary.get('row_count')} "
                    f"failed={summary.get('failed_count')} "
                    f"table={summary.get('table_name')}"
                )
            if name == "flagship_product_readiness" and isinstance(data.get("summary"), dict):
                summary = data["summary"]
                lines.append(
                    "  - flagship readiness: "
                    f"source={data.get('source_receipt')} "
                    f"verdict={summary.get('verdict') or 'missing'} "
                    f"audit={summary.get('flagship_readiness_audit_status')} "
                    f"completion={summary.get('completion_audit_status')} "
                    f"ready={summary.get('ready_count')} "
                    f"missing={summary.get('missing_count')} "
                    f"scoped_missing={summary.get('scoped_missing_count')} "
                    f"coverage_gaps={summary.get('coverage_gap_keys')}"
                )
                if summary.get("recovered_for_release_blocking"):
                    lines.append(
                        "  - release-blocking recovered via: "
                        + ", ".join(str(item) for item in summary.get("recovered_because_of_checks") or [])
                    )
                if summary.get("launch_critical_nested_blockers"):
                    lines.append(
                        "  - launch blockers: "
                        + ", ".join(str(item) for item in summary["launch_critical_nested_blockers"])
                    )
                if summary.get("reason"):
                    lines.append(f"  - readiness reason: {summary.get('reason')}")
            if name == "google_oauth_linking_proof":
                request_artifacts = data.get("operator_request_artifacts")
                request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
                receipt_verifier = data.get("receipt_verifier")
                receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
                required_operator_evidence_path = str(request_artifacts.get("required_operator_evidence_path") or "").strip()
                request_receipt_path = str(request_artifacts.get("request_receipt_path") or "").strip()
                operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or "").strip()
                operator_ask_metadata_path = str(request_artifacts.get("operator_ask_metadata_path") or "").strip()
                operator_evidence_template_path = str(request_artifacts.get("operator_evidence_template_path") or "").strip()
                preferred_drop_path = str(request_artifacts.get("preferred_drop_path") or "").strip()
                operator_ask_send_command = str(request_artifacts.get("operator_ask_send_command") or "").strip()
                import_command = str(request_artifacts.get("import_command") or "").strip()
                auto_import_watch_command = str(request_artifacts.get("auto_import_watch_command") or "").strip()
                post_import_verify_command = str(request_artifacts.get("post_import_verify_command") or "").strip()
                post_import_verify_note = str(request_artifacts.get("post_import_verify_note") or "").strip()
                post_import_commands = normalized_string_list(request_artifacts.get("post_import_commands"))
                operator_ask_delivery_status = str(request_artifacts.get("operator_ask_delivery_status") or "").strip()
                operator_ask_delivery_receipt_path = str(request_artifacts.get("operator_ask_delivery_receipt_path") or "").strip()
                operator_ask_delivery_comparable = request_artifacts.get("operator_ask_delivery_current_text_comparable")
                operator_ask_delivery_matches_current = request_artifacts.get("operator_ask_delivery_matches_current_text")
                operator_ask_resend_command = str(request_artifacts.get("operator_ask_resend_command") or "").strip()
                show_google_action_commands = normalized_token(
                    request_artifacts.get("request_effective_status")
                    or request_artifacts.get("request_status")
                ) != "not_required"
                if required_operator_evidence_path or request_receipt_path or operator_ask_text_path or preferred_drop_path:
                    lines.append(
                        "  - google oauth operator evidence: "
                        f"required_path={required_operator_evidence_path or 'missing'} "
                        f"request_receipt={request_receipt_path or 'missing'} "
                        f"ask_text={operator_ask_text_path or 'missing'} "
                        f"preferred_drop={preferred_drop_path or 'missing'}"
                    )
                if operator_ask_metadata_path or operator_evidence_template_path:
                    lines.append(
                        "  - google oauth operator packet: "
                        f"ask_meta={operator_ask_metadata_path or 'missing'} "
                        f"template={operator_evidence_template_path or 'missing'}"
                    )
                if show_google_action_commands and operator_ask_send_command:
                    lines.append(f"  - google oauth operator ask send: {operator_ask_send_command}")
                if show_google_action_commands and (import_command or auto_import_watch_command):
                    lines.append(
                        "  - google oauth operator intake: "
                        f"import={import_command or 'missing'} "
                        f"watch={auto_import_watch_command or 'missing'}"
                    )
                if show_google_action_commands and (import_command or post_import_verify_command or post_import_verify_note):
                    lines.append(
                        "  - google oauth intake verify: "
                        f"primary={post_import_verify_command or 'missing'} "
                        f"steps={len(post_import_commands)} "
                        f"note={post_import_verify_note or 'import --verify reruns the intake-request post-import gate chain'}"
                    )
                if operator_ask_delivery_status or operator_ask_delivery_receipt_path or operator_ask_delivery_comparable:
                    current_text_matches = (
                        str(bool(operator_ask_delivery_matches_current)).lower()
                        if operator_ask_delivery_comparable is True
                        else "not_comparable"
                    )
                    lines.append(
                        "  - google oauth operator ask delivery: "
                        f"status={operator_ask_delivery_status or 'missing'} "
                        f"receipt={operator_ask_delivery_receipt_path or 'missing'} "
                        f"current_text_matches_delivery={current_text_matches}"
                    )
                if show_google_action_commands and operator_ask_resend_command:
                    lines.append(f"  - google oauth operator ask resend: {operator_ask_resend_command}")
                if receipt_verifier:
                    lines.append(
                        "  - google oauth proof verifier: "
                        f"structural_status={receipt_verifier.get('status') or 'unknown'} "
                        f"operator_evidence_pass={str(bool(receipt_verifier.get('operator_evidence_pass'))).lower()} "
                        f"recovery_pack={str(bool(receipt_verifier.get('operator_request_artifacts_pass'))).lower()}"
                    )
                    verifier_issues = normalized_string_list(receipt_verifier.get("issues"))
                    if verifier_issues:
                        lines.append("  - google oauth proof verifier issues: " + ", ".join(verifier_issues))
            if name == "ea_operator_readiness":
                next_action_component_keys = normalized_string_list(data.get("next_action_component_keys"))
                advisory_action_component_keys = normalized_string_list(data.get("advisory_action_component_keys"))
                supplemental_next_action_component_keys = normalized_string_list(
                    data.get("supplemental_next_action_component_keys")
                )
                receipt_verifier = data.get("receipt_verifier")
                receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
                lines.append(
                    "  - ea operator readiness: "
                    f"ready={str(bool(data.get('operator_ready'))).lower()} "
                    f"runtime_status={data.get('runtime_status') or 'unknown'} "
                    f"attention={int_value(data.get('attention_required_count'))} "
                    f"blocked={int_value(data.get('blocked_count'))} "
                    f"next={','.join(next_action_component_keys) if next_action_component_keys else 'none'} "
                    f"supplemental={','.join(supplemental_next_action_component_keys) if supplemental_next_action_component_keys else 'none'} "
                    f"advisory={','.join(advisory_action_component_keys) if advisory_action_component_keys else 'none'}"
                )
                if receipt_verifier:
                    lines.append(
                        "  - ea operator receipt verifier: "
                        f"structural_status={receipt_verifier.get('status') or 'unknown'} "
                        f"operator_status={data.get('operator_status') or 'unknown'} "
                        f"runtime_status={data.get('runtime_status') or 'unknown'}"
                    )
            if name == "host_workload_runtime_health":
                next_action_component_keys = normalized_string_list(data.get("next_action_component_keys"))
                advisory_action_component_keys = normalized_string_list(data.get("advisory_action_component_keys"))
                observation = data.get("runtime_observation")
                observation = observation if isinstance(observation, dict) else {}
                mirror = observation.get("plex_internxt_mirror")
                mirror = mirror if isinstance(mirror, dict) else {}
                receipt_verifier = data.get("receipt_verifier")
                receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
                mirror_eta_seconds = mirror.get("eta_seconds")
                mirror_eta_summary = (
                    str(int(mirror_eta_seconds))
                    if isinstance(mirror_eta_seconds, int)
                    else (
                        f"suppressed:{str(mirror.get('eta_suppressed_reason') or '').strip()}"
                        if str(mirror.get("eta_suppressed_reason") or "").strip()
                        else "unknown"
                    )
                )
                lines.append(
                    "  - host workload runtime: "
                    f"ready={str(bool(data.get('runtime_ready'))).lower()} "
                    f"status={data.get('runtime_status') or 'unknown'} "
                    f"blocking={','.join(normalized_string_list(data.get('blocking_findings'))) or 'none'} "
                    f"advisory={','.join(normalized_string_list(data.get('advisory_findings'))) or 'none'} "
                    f"qbit_write_probe={str(bool(observation.get('qbittorrent_write_probe_ok'))).lower()} "
                    f"qbit_fast_resume_rejected={int_value(observation.get('qbittorrent_fast_resume_rejected_count'))} "
                    f"cache_mode={observation.get('pcloud_cache_mode') or 'unknown'} "
                    f"internxt_cache_bytes={int_value(observation.get('internxt_cache_bytes_used'))} "
                    f"mirror={mirror.get('status') or 'unknown'} "
                    f"mirror_phase={mirror.get('phase') or 'unknown'} "
                    f"mirror_progress={int_value(mirror.get('overall_current'))}/{int_value(mirror.get('overall_total'))} "
                    f"mirror_eta_seconds={mirror_eta_summary} "
                    f"next={','.join(next_action_component_keys) if next_action_component_keys else 'none'} "
                    f"advisory_components={','.join(advisory_action_component_keys) if advisory_action_component_keys else 'none'}"
                )
                if receipt_verifier:
                    lines.append(
                        "  - host workload runtime verifier: "
                        f"structural_status={receipt_verifier.get('status') or 'unknown'} "
                        f"runtime_status={data.get('runtime_status') or 'unknown'}"
                    )
            if name == "qbittorrent_staging_hygiene":
                observation = data.get("runtime_observation")
                observation = observation if isinstance(observation, dict) else {}
                receipt_verifier = data.get("receipt_verifier")
                receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
                lines.append(
                    "  - qbittorrent staging hygiene: "
                    f"ready={str(bool(data.get('runtime_ready'))).lower()} "
                    f"status={data.get('runtime_status') or 'unknown'} "
                    f"orphan_partials={int_value(observation.get('orphan_partial_file_count'))} "
                    f"orphan_partial_gib={observation.get('orphan_partial_gib') or 0} "
                    f"dead_meta={int_value(observation.get('dead_meta_candidate_count'))} "
                    f"dead_stalled={int_value(observation.get('dead_stalled_candidate_count'))} "
                    f"dead_checking={int_value(observation.get('dead_checking_candidate_count'))} "
                    f"requeued_meta={int_value(observation.get('dead_meta_requeue_count'))} "
                    f"requeued_stalled={int_value(observation.get('dead_stalled_requeue_count'))} "
                    f"requeued_checking={int_value(observation.get('dead_checking_requeue_count'))} "
                    f"advisory={','.join(normalized_string_list(data.get('advisory_findings'))) or 'none'}"
                )
                if receipt_verifier:
                    lines.append(
                        "  - qbittorrent staging hygiene verifier: "
                        f"structural_status={receipt_verifier.get('status') or 'unknown'} "
                        f"runtime_status={data.get('runtime_status') or 'unknown'}"
                    )
            if name == "mymedia_public_surface":
                receipt_verifier = data.get("receipt_verifier")
                receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
                lines.append(
                    "  - mymedia public surface: "
                    f"ready={str(bool(data.get('public_surface_ready'))).lower()} "
                    f"status={data.get('public_surface_status') or 'unknown'} "
                    f"runtime_status={data.get('runtime_status') or 'unknown'} "
                    f"http={int_value(data.get('public_surface_http_status_code'))} "
                    f"access_protected={str(bool(data.get('public_surface_access_protected'))).lower()} "
                    f"cloudflare_blocked={str(bool(data.get('public_surface_cloudflare_blocked'))).lower()} "
                    f"url={data.get('public_surface_url') or 'missing'}"
                )
                if receipt_verifier:
                    lines.append(
                        "  - mymedia public surface verifier: "
                        f"structural_status={receipt_verifier.get('status') or 'unknown'} "
                        f"mymedia_status={data.get('mymedia_status') or 'unknown'} "
                        f"runtime_status={data.get('runtime_status') or 'unknown'}"
                    )
            if name == "windows_installer_visual_audit":
                artifact = data.get("artifact")
                artifact = artifact if isinstance(artifact, dict) else {}
                visual = data.get("visualAuditSource")
                visual = visual if isinstance(visual, dict) else {}
                startup = data.get("startupReceipt")
                startup = startup if isinstance(startup, dict) else {}
                receipt_verifier = data.get("receipt_verifier")
                receipt_verifier = receipt_verifier if isinstance(receipt_verifier, dict) else {}
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
                request_artifacts = data.get("operator_request_artifacts")
                request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}
                request_receipt_path = str(request_artifacts.get("request_receipt_path") or "").strip()
                operator_ask_text_path = str(request_artifacts.get("operator_ask_text_path") or "").strip()
                operator_ask_metadata_path = str(request_artifacts.get("operator_ask_metadata_path") or "").strip()
                preferred_drop_path = str(request_artifacts.get("preferred_drop_path") or "").strip()
                preferred_extracted_visual_dir = str(
                    request_artifacts.get("preferred_extracted_visual_dir") or ""
                ).strip()
                operator_ask_send_command = str(request_artifacts.get("operator_ask_send_command") or "").strip()
                discover_command = str(request_artifacts.get("discover_command") or "").strip()
                discover_visual_source_command = str(
                    request_artifacts.get("discover_visual_source_command") or ""
                ).strip()
                auto_import_command = str(request_artifacts.get("auto_import_command") or "").strip()
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
                post_import_verify_command = str(request_artifacts.get("post_import_verify_command") or "").strip()
                post_import_verify_note = str(request_artifacts.get("post_import_verify_note") or "").strip()
                post_import_commands = normalized_string_list(request_artifacts.get("post_import_commands"))
                operator_ask_delivery_status = str(request_artifacts.get("operator_ask_delivery_status") or "").strip()
                operator_ask_delivery_receipt_path = str(request_artifacts.get("operator_ask_delivery_receipt_path") or "").strip()
                operator_ask_delivery_comparable = request_artifacts.get("operator_ask_delivery_current_text_comparable")
                operator_ask_delivery_matches_current = request_artifacts.get("operator_ask_delivery_matches_current_text")
                operator_ask_resend_command = str(request_artifacts.get("operator_ask_resend_command") or "").strip()
                if (
                    request_receipt_path
                    or operator_ask_text_path
                    or operator_ask_metadata_path
                    or preferred_drop_path
                    or preferred_extracted_visual_dir
                ):
                    lines.append(
                        "  - windows visual proof request: "
                        f"request_receipt={request_receipt_path or 'missing'} "
                        f"ask_text={operator_ask_text_path or 'missing'} "
                        f"ask_meta={operator_ask_metadata_path or 'missing'} "
                        f"preferred_drop={preferred_drop_path or 'missing'} "
                        f"fallback_dir={preferred_extracted_visual_dir or 'missing'}"
                    )
                if discover_command or discover_visual_source_command:
                    lines.append(
                        "  - windows proof discovery: "
                        f"bundle={discover_command or 'missing'} "
                        f"visual_source={discover_visual_source_command or 'missing'}"
                    )
                stage_release_handoff_path = str(data.get("stage_release_build_handoff_path") or "").strip()
                stage_release_handoff_status = str(data.get("stage_release_build_handoff_status") or "").strip()
                stage_visual_handoff_path = str(data.get("stage_windows_visual_proof_handoff_path") or "").strip()
                stage_visual_handoff_status = str(data.get("stage_windows_visual_proof_handoff_status") or "").strip()
                stage_visual_handoff_summary = str(data.get("stage_windows_visual_proof_handoff_summary") or "").strip()
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
                if import_command or auto_import_command or auto_import_watch_command:
                    lines.append(
                        "  - windows proof intake: "
                        f"import={import_command or 'missing'} "
                        f"auto={auto_import_command or 'missing'} "
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
                if import_command or post_import_verify_command or post_import_verify_note:
                    lines.append(
                        "  - windows intake verify: "
                        f"primary={post_import_verify_command or 'missing'} "
                        f"steps={len(post_import_commands)} "
                        f"note={post_import_verify_note or 'import --verify reruns the intake-request post-import gate chain'}"
                    )
                if operator_ask_delivery_status or operator_ask_delivery_receipt_path or operator_ask_delivery_comparable:
                    current_text_matches = (
                        str(bool(operator_ask_delivery_matches_current)).lower()
                        if operator_ask_delivery_comparable is True
                        else "not_comparable"
                    )
                    lines.append(
                        "  - windows operator ask delivery: "
                        f"status={operator_ask_delivery_status or 'missing'} "
                        f"receipt={operator_ask_delivery_receipt_path or 'missing'} "
                        f"current_text_matches_delivery={current_text_matches}"
                    )
                if operator_ask_resend_command:
                    lines.append(f"  - windows operator ask resend: {operator_ask_resend_command}")
                if receipt_verifier:
                    lines.append(
                        "  - windows proof verifier: "
                        f"structural_status={receipt_verifier.get('status') or 'unknown'} "
                        f"operator_action_still_required={str(bool(receipt_verifier.get('operator_action_still_required'))).lower()} "
                        f"recovery_pack={str(bool(receipt_verifier.get('recovery_pack_pass'))).lower()}"
                    )
                    verifier_issues = normalized_string_list(receipt_verifier.get("issues"))
                    if verifier_issues:
                        lines.append("  - windows proof verifier issues: " + ", ".join(verifier_issues))
            if data.get("failures") and not rendered_failures:
                lines.append(f"  - failures: {', '.join(str(item) for item in data['failures'])}")
            if data.get("failed_gates"):
                lines.append(f"  - failed gates: {', '.join(str(item) for item in data['failed_gates'])}")
        if name == "release_ready" and isinstance(data.get("public_release_snapshot_readonly_audit"), dict):
            snapshot_audit = data["public_release_snapshot_readonly_audit"]
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
            if data.get("fresh_within_hours") is not None:
                lines.append(
                    f"  - freshness: generated_at={data.get('generated_at_utc')} "
                    f"fresh={data.get('fresh')} max_age_hours={data.get('fresh_within_hours')}"
                )
            if data.get("nextActions"):
                lines.append("  - next actions:")
                lines.extend(f"    - {item}" for item in data["nextActions"])
            if data.get("advisoryActions"):
                lines.append("  - advisory actions:")
                lines.extend(f"    - {item}" for item in data["advisoryActions"])
        if data.get("fresh_within_hours") is not None and name != "release_ready":
            lines.append(
                f"  - freshness: generated_at={data.get('generated_at_utc')} "
                f"fresh={data.get('fresh')} max_age_hours={data.get('fresh_within_hours')}"
            )
        if data.get("nextActions") and name != "release_ready":
            lines.append("  - next actions:")
            lines.extend(f"    - {item}" for item in data["nextActions"])
        if data.get("advisoryActions") and name != "release_ready":
            lines.append("  - advisory actions:")
            lines.extend(f"    - {item}" for item in data["advisoryActions"])
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- `{failure}`" for failure in failures)
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the Chummer operator release dashboard.")
    parser.add_argument(
        "--release-ready-self-check",
        action="store_true",
        help=(
            "Skip the previous release_ready receipt as a release-blocking input while the "
            "release-ready verifier is computing a fresh one."
        ),
    )
    parser.add_argument(
        "--skip-live-public-edge-probe",
        action="store_true",
        help="Do not probe live public role aliases while materializing the dashboard.",
    )
    parser.add_argument(
        "--skip-windows-runtime-refresh",
        action="store_true",
        help=(
            "Reuse the current Windows auto-import and watcher receipts instead of refreshing them "
            "while materializing the operator release dashboard."
        ),
    )
    parser.add_argument(
        "--public-edge-base-url",
        default=PUBLIC_EDGE_LIVE_ALIAS_BASE_URL,
        help="Base URL used for the live public-edge role alias probe.",
    )
    parser.add_argument(
        "--public-edge-timeout-seconds",
        type=float,
        default=PUBLIC_EDGE_LIVE_ALIAS_TIMEOUT_SECONDS,
        help="Per-route timeout for the live public-edge role alias probe.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    live_role_alias_routes = None
    if not args.skip_live_public_edge_probe:
        live_role_alias_routes = probe_public_edge_live_role_alias_routes(
            base_url=args.public_edge_base_url,
            timeout_seconds=args.public_edge_timeout_seconds,
        )
    payload = build_payload(
        release_ready_self_check=args.release_ready_self_check,
        public_edge_live_role_alias_routes=live_role_alias_routes,
        refresh_windows_runtime_receipts=not args.skip_windows_runtime_refresh,
    )
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload), encoding="utf-8")
    print(f"operator_release_dashboard:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
