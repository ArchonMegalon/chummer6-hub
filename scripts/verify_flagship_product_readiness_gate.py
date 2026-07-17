#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from public_edge_postdeploy_contract import release_channel_trust_invariant_failures


ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
REGISTRY_PUBLISHED_ROOT = ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
SHARED_RUN_SERVICES_ROOT = Path(
    os.environ.get("CHUMMER_SHARED_RUN_SERVICES_ROOT") or "/docker/chummercomplete/chummer.run-services"
)
DEFAULT_READINESS = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
DEFAULT_SUMMARY_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
DEFAULT_MATERIALIZER = Path("/docker/fleet/scripts/materialize_flagship_product_readiness.py")
DEFAULT_RELEASE_CHANNEL = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"
DEFAULT_GOOGLE_OAUTH_LINKING_PROOF = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
PASS_STATES = {"pass", "passed", "ready"}
GOLD_READY_VERDICT = "gold_ready"
GOLD_SUPPORTABILITY_STATE = "gold_supported"
FLAGSHIP_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
FLAGSHIP_PUBLIC_STABLE_ROLLOUT_STATE = "public_stable"
BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "desktop_polish_needed",
    "revoked",
}
RECOVERABLE_RELEASE_WRAPPER_BLOCKERS = {
    "final gold janitor state is 'fail'",
    "final gold janitor verdict is 'NOT_GOLD'",
    "live-backed gold claim is not allowed",
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "invalid"
    if not isinstance(payload, dict):
        return {}, "invalid"
    return payload, "loaded"


def unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def resolve_release_channel_path() -> Path:
    explicit = os.environ.get("CHUMMER_RELEASE_CHANNEL_PATH")
    candidates = unique_paths(
        [
            Path(explicit).expanduser() if explicit else DEFAULT_RELEASE_CHANNEL,
            DEFAULT_RELEASE_CHANNEL,
            SHARED_RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
            SHARED_RUN_SERVICES_ROOT / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
            RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
            RUN_SERVICES_ROOT / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def receipt_load_failure(
    label: str,
    path: Path,
    load_status: str,
    *,
    include_missing: bool = True,
) -> str | None:
    if load_status == "missing" and include_missing:
        return f"{label} receipt is missing: {path}"
    if load_status == "invalid":
        return f"{label} receipt is malformed: {path}"
    return None


def int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def norm(value: object) -> str:
    return str(value or "").strip().lower()


def normalized_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value).strip()
        if not candidate:
            continue
        folded = candidate.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result.append(candidate)
    return result


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def google_oauth_operator_evidence_missing_failure(payload: dict[str, Any]) -> str | None:
    operator_evidence = payload.get("operator_end_to_end_evidence")
    operator_evidence = operator_evidence if isinstance(operator_evidence, dict) else {}
    request_artifacts = payload.get("operator_request_artifacts")
    request_artifacts = request_artifacts if isinstance(request_artifacts, dict) else {}

    failure_reasons = normalized_strings(operator_evidence.get("failures"))
    if not failure_reasons:
        failure_reasons = normalized_strings(payload.get("failures"))

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


def append_reason_details(base_reason: str, details: Sequence[str]) -> str:
    normalized_base = str(base_reason or "").strip()
    normalized_details = [
        str(detail).strip().rstrip(".")
        for detail in details
        if str(detail).strip()
    ]
    if not normalized_base:
        return " ".join(f"{detail}." for detail in normalized_details).strip()
    if not normalized_base.endswith((".", "!", "?")):
        normalized_base += "."
    if not normalized_details:
        return normalized_base
    return normalized_base + " " + " ".join(f"{detail}." for detail in normalized_details)


def append_if_present_and_not_ready(
    blockers: list[str],
    evidence: dict[str, Any],
    key: str,
    label: str,
) -> None:
    if key not in evidence:
        return
    value = norm(evidence.get(key))
    if value not in PASS_STATES:
        blockers.append(f"{label} is {evidence.get(key)!r}")


def structural_ready_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    readiness_planes = payload.get("readiness_planes") if isinstance(payload.get("readiness_planes"), dict) else {}
    structural_ready = readiness_planes.get("structural_ready") if isinstance(readiness_planes.get("structural_ready"), dict) else {}
    evidence = structural_ready.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def supervisor_current_readiness_recovered(payload: dict[str, Any], evidence: dict[str, Any]) -> bool:
    structural_evidence = structural_ready_evidence(payload)
    return bool(
        evidence.get("supervisor_completion_status_recovered_from_current_readiness")
        or (
            structural_evidence.get("supervisor_recent_enough") is True
            and structural_evidence.get("supervisor_current_readiness_recovery") is True
        )
        or (
            evidence.get("supervisor_completion_status_recovered_from_active_shard_topology")
            and evidence.get("supervisor_recent_enough_recovered_from_active_shard_topology")
        )
    )


def launch_critical_nested_blockers(payload: dict[str, Any]) -> list[str]:
    coverage = payload.get("coverage_details") if isinstance(payload.get("coverage_details"), dict) else {}
    fleet_loop = coverage.get("fleet_and_operator_loop") if isinstance(coverage.get("fleet_and_operator_loop"), dict) else {}
    evidence = fleet_loop.get("evidence") if isinstance(fleet_loop.get("evidence"), dict) else {}
    blockers: list[str] = []
    if not evidence:
        return blockers

    append_if_present_and_not_ready(blockers, evidence, "final_gold_janitor_state", "final gold janitor state")
    if "final_gold_janitor_verdict" in evidence and norm(evidence.get("final_gold_janitor_verdict")) != GOLD_READY_VERDICT:
        blockers.append(f"final gold janitor verdict is {evidence.get('final_gold_janitor_verdict')!r}")
    if "live_backed_gold_claim_allowed" in evidence and evidence.get("live_backed_gold_claim_allowed") is not True:
        blockers.append("live-backed gold claim is not allowed")
    if not supervisor_current_readiness_recovered(payload, evidence):
        append_if_present_and_not_ready(blockers, evidence, "supervisor_completion_status", "supervisor completion status")
        if "supervisor_recent_enough" in evidence and evidence.get("supervisor_recent_enough") is not True:
            blockers.append("supervisor completion evidence is stale")
    if "source_live_recrawl_generated_at_stale" in evidence and evidence.get("source_live_recrawl_generated_at_stale") is True:
        blockers.append("source live recrawl evidence is stale")
    detailed_release_blockers = resolve_release_truth_launch_blockers(evidence)
    if not detailed_release_blockers:
        return blockers

    return normalized_strings(
        detailed_release_blockers
        + [
            blocker
            for blocker in blockers
            if blocker not in RECOVERABLE_RELEASE_WRAPPER_BLOCKERS
        ]
    )


def resolve_release_truth_launch_blockers(evidence: dict[str, Any]) -> list[str]:
    if not str(evidence.get("final_gold_janitor_path") or "").strip():
        return []

    current_release_truth_blockers = current_release_truth_launch_blockers()
    if current_release_truth_blockers:
        return current_release_truth_blockers

    release_ready_path = PUBLISHED_ROOT / "RELEASE_READY.generated.json"
    release_ready, release_ready_load_status = load_json(release_ready_path)
    if release_ready_load_status != "loaded":
        return []
    if not release_ready or normalized_token(release_ready.get("status")) in PASS_STATES:
        return []

    failed_gates = {
        item.casefold()
        for item in normalized_strings(release_ready.get("failed_gates"))
    }
    if (
        "release_channel" not in failed_gates
        and "google_oauth_linking_proof" not in failed_gates
        and "windows_installer_visual_audit" not in failed_gates
    ):
        return []

    details: list[str] = []
    for failure in normalized_strings(release_ready.get("failures")):
        if failure.startswith("FAIL release_channel:"):
            details.append(failure.split(":", 1)[1].strip())
            continue
        if failure.startswith("FAIL google_oauth_linking_proof:"):
            details.append(failure.split(":", 1)[1].strip())
            continue
        if failure.startswith("FAIL windows_installer_visual_audit:"):
            details.append(failure.split(":", 1)[1].strip())

    return normalized_strings(details)


def current_release_truth_launch_blockers() -> list[str]:
    details: list[str] = []
    resolved_release_channel_path = resolve_release_channel_path()
    release_channel, release_channel_load_status = load_json(resolved_release_channel_path)
    release_channel_load_failure = receipt_load_failure(
        "release channel",
        resolved_release_channel_path,
        release_channel_load_status,
        include_missing=False,
    )
    if release_channel_load_failure:
        details.append(release_channel_load_failure)
    elif release_channel:
        details.extend(current_release_channel_failures(release_channel))

    google_oauth_linking_proof, google_oauth_linking_proof_load_status = load_json(DEFAULT_GOOGLE_OAUTH_LINKING_PROOF)
    google_load_failure = receipt_load_failure(
        "google oauth linking proof",
        DEFAULT_GOOGLE_OAUTH_LINKING_PROOF,
        google_oauth_linking_proof_load_status,
        include_missing=False,
    )
    if google_load_failure:
        details.append(google_load_failure)
    elif google_oauth_linking_proof and normalized_token(google_oauth_linking_proof.get("status")) not in PASS_STATES:
        google_operator_failure = google_oauth_operator_evidence_missing_failure(google_oauth_linking_proof)
        google_resend_failure = google_oauth_operator_ask_resend_failure(google_oauth_linking_proof)
        if google_operator_failure:
            details.append(google_operator_failure)
        if google_resend_failure:
            details.append(google_resend_failure)
        if not google_operator_failure and not google_resend_failure:
            details.extend(
                receipt_failure_reasons(
                    google_oauth_linking_proof,
                    "google_oauth_linking_proof status is not pass",
                )
            )

    windows_installer_visual_audit, windows_installer_visual_audit_load_status = load_json(DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT)
    windows_load_failure = receipt_load_failure(
        "windows installer visual audit",
        DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT,
        windows_installer_visual_audit_load_status,
        include_missing=False,
    )
    if windows_load_failure:
        details.append(windows_load_failure)
    elif windows_installer_visual_audit and normalized_token(windows_installer_visual_audit.get("status")) not in PASS_STATES:
        details.extend(
            receipt_failure_reasons(
                windows_installer_visual_audit,
                "windows_installer_visual_audit status is not pass",
            )
        )

    return normalized_strings(details)


def current_release_channel_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    status = normalized_token(payload.get("status"))
    version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
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
    elif normalized_channel not in FLAGSHIP_STABLE_CHANNELS:
        failures.append(f"release channel channel is {normalized_channel}, not a flagship stable lane")
    if supportability_state != GOLD_SUPPORTABILITY_STATE:
        failures.append("release channel supportability is not gold_supported")
    if rollout_state in BLOCKING_ROLLOUT_STATES:
        failures.append(f"release channel rollout is blocking: {rollout_state}")
        failures.extend(release_channel_rollout_blocker_details(payload))
    elif rollout_state and rollout_state != FLAGSHIP_PUBLIC_STABLE_ROLLOUT_STATE:
        failures.append(f"release channel rollout is {rollout_state}, not public_stable")
    failures.extend(release_channel_trust_invariant_failures(payload))
    return normalized_strings(failures)


def release_channel_rollout_blocker_details(payload: dict[str, Any]) -> list[str]:
    coverage = payload.get("desktopTupleCoverage") if isinstance(payload.get("desktopTupleCoverage"), dict) else {}
    if not coverage:
        return []

    details: list[str] = []
    missing_platforms = normalized_strings(coverage.get("missingRequiredPlatforms"))
    if missing_platforms:
        details.append(
            "release channel is missing required desktop platforms: "
            + ", ".join(missing_platforms)
        )

    missing_pairs = normalized_strings(coverage.get("missingRequiredPlatformHeadPairs"))
    if missing_pairs:
        details.append(
            "release channel is missing required desktop platform/head coverage: "
            + ", ".join(missing_pairs)
        )

    missing_tuples = normalized_strings(coverage.get("missingRequiredPlatformHeadRidTuples"))
    if missing_tuples:
        details.append(
            "release channel is missing required desktop tuples: "
            + ", ".join(missing_tuples)
        )

    external_proof_requests = coverage.get("externalProofRequests")
    requested_tuples = normalized_strings(
        [
            str(item.get("tupleId") or "").strip()
            for item in external_proof_requests
            if isinstance(external_proof_requests, list) and isinstance(item, dict)
        ]
    )
    if requested_tuples:
        details.append(
            "release channel still requires external proof capture for tuples: "
            + ", ".join(requested_tuples)
        )

    return normalized_strings(details)


def receipt_failure_reasons(payload: dict[str, Any], fallback: str) -> list[str]:
    failures = payload.get("failures")
    if isinstance(failures, list):
        cleaned = [str(item).strip() for item in failures if str(item).strip()]
        if cleaned:
            return cleaned

    next_actions = payload.get("nextActions") or payload.get("next_actions")
    if isinstance(next_actions, list):
        cleaned = [str(item).strip() for item in next_actions if str(item).strip()]
        if cleaned:
            return cleaned

    summary = payload.get("summary")
    if isinstance(summary, dict):
        nested = summary.get("launch_critical_nested_blockers")
        if isinstance(nested, list):
            cleaned = [str(item).strip() for item in nested if str(item).strip()]
            if cleaned:
                return cleaned
        reason = str(summary.get("reason") or "").strip()
        if reason:
            return [reason]

    reason = str(payload.get("reason") or "").strip()
    if reason:
        return [reason]
    return [fallback]


def resolve_summary_reason(
    payload: dict[str, Any],
    completion: dict[str, Any],
    readiness: dict[str, Any],
    blockers: Sequence[str],
    coverage_gaps: Sequence[str],
    scoped_gaps: Sequence[str],
) -> str | None:
    normalized_blockers = normalized_strings(list(blockers))
    normalized_coverage_gaps = normalized_strings(list(coverage_gaps))
    normalized_scoped_gaps = normalized_strings(list(scoped_gaps))
    override = payload.get("gate_status_override") if isinstance(payload.get("gate_status_override"), dict) else {}
    override_effective_reason = str(override.get("effective_reason") or "").strip()
    if override_effective_reason:
        return override_effective_reason
    override_reason = str(override.get("reason") or "").strip()
    if override_reason and (
        norm(payload.get("status")) not in PASS_STATES
        or normalized_blockers
        or normalized_coverage_gaps
        or normalized_scoped_gaps
    ):
        details: list[str] = []
        if normalized_blockers:
            details.append("Launch blockers: " + ", ".join(normalized_blockers))
        if normalized_coverage_gaps:
            details.append("Coverage gaps: " + ", ".join(normalized_coverage_gaps))
        if normalized_scoped_gaps and normalized_scoped_gaps != normalized_coverage_gaps:
            details.append("Scoped coverage gaps: " + ", ".join(normalized_scoped_gaps))
        return append_reason_details(override_reason, details)

    raw_reason = str(readiness.get("reason") or completion.get("reason") or "").strip()
    if raw_reason:
        return raw_reason

    details = []
    if normalized_blockers:
        details.append("Launch blockers: " + ", ".join(normalized_blockers))
    if normalized_coverage_gaps:
        details.append("Coverage gaps: " + ", ".join(normalized_coverage_gaps))
    if normalized_scoped_gaps and normalized_scoped_gaps != normalized_coverage_gaps:
        details.append("Scoped coverage gaps: " + ", ".join(normalized_scoped_gaps))
    fallback_reason = append_reason_details("", details)
    return fallback_reason or None


def desktop_client_gap_subsumed_by_launch_blockers(payload: dict[str, Any], blockers: Sequence[str]) -> bool:
    coverage = payload.get("coverage_details") if isinstance(payload.get("coverage_details"), dict) else {}
    desktop_client = coverage.get("desktop_client") if isinstance(coverage.get("desktop_client"), dict) else {}
    evidence = desktop_client.get("evidence") if isinstance(desktop_client.get("evidence"), dict) else {}
    if not evidence:
        return False

    if norm(evidence.get("ui_executable_exit_gate_blocking_mode")) != "external_only":
        return False
    if norm(evidence.get("ui_windows_exit_gate_blocking_mode")) != "external_only":
        return False
    if evidence.get("ui_linux_exit_gate_effective_ready") is not True:
        return False
    if norm(evidence.get("ui_workflow_execution_gate_status")) not in PASS_STATES:
        return False
    if norm(evidence.get("ui_visual_familiarity_exit_gate_status")) not in PASS_STATES:
        return False
    if norm(evidence.get("ui_flagship_release_gate_status")) not in PASS_STATES:
        return False

    if "ui_user_journey_tester_audit_required" not in evidence:
        return False
    user_journey_audit_required = evidence.get("ui_user_journey_tester_audit_required")
    if user_journey_audit_required is not True and user_journey_audit_required is not False:
        return False
    if user_journey_audit_required is True:
        if norm(evidence.get("ui_user_journey_tester_audit_status")) not in PASS_STATES:
            return False
        if evidence.get("ui_user_journey_tester_audit_ready") is not True:
            return False

    unresolved_hosts = {
        norm(item)
        for item in evidence.get("ui_external_host_proof_blockers_unresolved_hosts", [])
        if str(item).strip()
    } if isinstance(evidence.get("ui_external_host_proof_blockers_unresolved_hosts"), list) else set()
    if unresolved_hosts != {"windows"}:
        return False

    normalized_blockers = {str(item).strip().casefold() for item in blockers if str(item).strip()}
    return any("windows installer visual audit" in blocker for blocker in normalized_blockers)


def normalized_coverage_gaps(
    payload: dict[str, Any],
    gaps: Sequence[str],
    blockers: Sequence[str],
) -> list[str]:
    normalized_gaps = normalized_strings(list(gaps))
    if "desktop_client" in {item.casefold() for item in normalized_gaps} and desktop_client_gap_subsumed_by_launch_blockers(payload, blockers):
        normalized_gaps = [
            item
            for item in normalized_gaps
            if item.casefold() != "desktop_client"
        ]
    return normalized_gaps


def summarize(
    payload: dict[str, Any],
    *,
    readiness_load_status: str = "loaded",
    readiness_path: Path | None = None,
) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    completion = payload.get("completion_audit") if isinstance(payload.get("completion_audit"), dict) else {}
    readiness = payload.get("flagship_readiness_audit") if isinstance(payload.get("flagship_readiness_audit"), dict) else {}
    raw_coverage_gaps = [
        str(item).strip()
        for item in readiness.get("coverage_gap_keys", [])
        if str(item).strip()
    ] if isinstance(readiness.get("coverage_gap_keys"), list) else []
    raw_scoped_gaps = [
        str(item).strip()
        for item in readiness.get("scoped_coverage_gap_keys", [])
        if str(item).strip()
    ] if isinstance(readiness.get("scoped_coverage_gap_keys"), list) else []
    launch_blockers = launch_critical_nested_blockers(payload)
    coverage_gaps = normalized_coverage_gaps(payload, raw_coverage_gaps, launch_blockers)
    scoped_gaps = normalized_coverage_gaps(payload, raw_scoped_gaps, launch_blockers)
    result = {
        "contract_name": payload.get("contract_name"),
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at") or payload.get("generated_at_utc") or payload.get("generatedAtUtc"),
        "readiness_load_status": readiness_load_status,
        "completion_audit_status": completion.get("status"),
        "flagship_readiness_audit_status": readiness.get("status"),
        "ready_count": int_value(summary.get("ready_count")),
        "missing_count": int_value(summary.get("missing_count")),
        "scoped_missing_count": int_value(summary.get("scoped_missing_count")),
        "warning_count": int_value(summary.get("warning_count")),
        "coverage_gap_keys": coverage_gaps,
        "scoped_coverage_gap_keys": scoped_gaps,
        "launch_critical_nested_blockers": launch_blockers,
    }
    load_failure = (
        receipt_load_failure("flagship readiness", readiness_path, readiness_load_status)
        if readiness_path is not None
        else None
    )
    result["reason"] = load_failure or resolve_summary_reason(
        payload,
        completion,
        readiness,
        result["launch_critical_nested_blockers"],
        coverage_gaps,
        scoped_gaps,
    )
    result["launch_critical_nested_blocker_count"] = len(result["launch_critical_nested_blockers"])
    result["pass"] = (
        readiness_load_status == "loaded"
        and result["contract_name"] == "fleet.flagship_product_readiness"
        and norm(result["status"]) in PASS_STATES
        and norm(result["completion_audit_status"]) in PASS_STATES
        and norm(result["flagship_readiness_audit_status"]) in PASS_STATES
        and result["missing_count"] == 0
        and result["scoped_missing_count"] == 0
        and not coverage_gaps
        and not scoped_gaps
        and not result["launch_critical_nested_blockers"]
    )
    return result


def fail_closed_readiness_payload(payload: dict[str, Any], summary: dict[str, Any], generated_at_utc: str) -> tuple[dict[str, Any], bool]:
    if summary["pass"]:
        return payload, False
    if not payload:
        return payload, False

    raw_status = payload.get("status")
    raw_scoped_status = payload.get("scoped_status")
    blockers = [
        str(item).strip()
        for item in summary.get("launch_critical_nested_blockers", [])
        if str(item).strip()
    ]
    coverage_gaps = [
        str(item).strip()
        for item in summary.get("coverage_gap_keys", [])
        if str(item).strip()
    ]
    scoped_gaps = [
        str(item).strip()
        for item in summary.get("scoped_coverage_gap_keys", [])
        if str(item).strip()
    ]
    if not blockers and not coverage_gaps and not scoped_gaps:
        return payload, False

    updated = dict(payload)
    updated["status"] = "fail"
    if "scoped_status" in updated:
        updated["scoped_status"] = "fail"
    updated["gate_status_override"] = {
        "contract_name": "chummer.flagship_product_readiness.fail_closed_override.v1",
        "applied_at_utc": generated_at_utc,
        "raw_status": raw_status,
        "raw_scoped_status": raw_scoped_status,
        "summary_pass": summary["pass"],
        "reason": "Launch-critical nested blockers or coverage gaps remain; raw materializer status is not sufficient for a flagship launch claim.",
        "launch_critical_nested_blockers": blockers,
        "coverage_gap_keys": coverage_gaps,
        "scoped_coverage_gap_keys": scoped_gaps,
    }
    completion = payload.get("completion_audit") if isinstance(payload.get("completion_audit"), dict) else {}
    readiness = payload.get("flagship_readiness_audit") if isinstance(payload.get("flagship_readiness_audit"), dict) else {}
    updated["gate_status_override"]["effective_reason"] = resolve_summary_reason(
        updated,
        completion,
        readiness,
        blockers,
        coverage_gaps,
        scoped_gaps,
    )
    return updated, True


def materialize(materializer: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(materializer), "--out", str(output), "--mirror-out", ""],
        cwd=RUN_SERVICES_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail closed on whole-product flagship readiness.")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--materializer", type=Path, default=DEFAULT_MATERIALIZER)
    parser.add_argument("--skip-materialize", action="store_true", help="Only validate the existing readiness receipt.")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_SUMMARY_OUTPUT,
        help="Path for the verifier summary JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    materializer_result: dict[str, Any] | None = None
    if not args.skip_materialize:
        completed = materialize(args.materializer, args.readiness)
        materializer_result = {
            "command": f"python3 {args.materializer} --out {args.readiness} --mirror-out ''",
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout.splitlines()[-20:],
            "stderr_tail": completed.stderr.splitlines()[-20:],
        }
        if completed.returncode != 0:
            print(json.dumps({"status": "fail", "materializer": materializer_result}, indent=2), file=sys.stderr)
            return 1

    generated_at_utc = now_iso()
    readiness_payload, readiness_load_status = load_json(args.readiness)
    summary = summarize(
        readiness_payload,
        readiness_load_status=readiness_load_status,
        readiness_path=args.readiness,
    )
    fail_closed_payload, readiness_updated = fail_closed_readiness_payload(readiness_payload, summary, generated_at_utc)
    if readiness_updated:
        args.readiness.write_text(json.dumps(fail_closed_payload, indent=2) + "\n", encoding="utf-8")
        summary = summarize(
            fail_closed_payload,
            readiness_load_status=readiness_load_status,
            readiness_path=args.readiness,
        )
    payload = {
        "contract_name": "chummer.flagship_product_readiness_gate.v1",
        "generated_at_utc": generated_at_utc,
        "status": "pass" if summary["pass"] else "fail",
        "readiness_path": str(args.readiness),
        "readiness_load_status": summary["readiness_load_status"],
        "readiness_receipt_fail_closed": readiness_updated,
        "pass": summary["pass"],
        "reason": summary["reason"],
        "coverage_gap_keys": summary["coverage_gap_keys"],
        "scoped_coverage_gap_keys": summary["scoped_coverage_gap_keys"],
        "launch_critical_nested_blockers": summary["launch_critical_nested_blockers"],
        "launch_critical_nested_blocker_count": summary["launch_critical_nested_blocker_count"],
        "summary": summary,
    }
    if materializer_result is not None:
        payload["materializer"] = materializer_result
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not summary["pass"]:
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return 1
    print("flagship_product_readiness:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
