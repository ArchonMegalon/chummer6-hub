#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
REGISTRY_PUBLISHED_ROOT = ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
DEFAULT_READINESS = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
DEFAULT_SUMMARY_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
DEFAULT_MATERIALIZER = Path("/docker/fleet/scripts/materialize_flagship_product_readiness.py")
DEFAULT_RELEASE_CHANNEL = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"
DEFAULT_WORKSPACE_PORTAL_RELEASE_CHANNEL = (
    RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
)
DEFAULT_RELEASE_BLOCKERS = ROOT / "RELEASE_BLOCKERS.generated.json"
DEFAULT_GOOGLE_OAUTH_LINKING_PROOF = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
DEFAULT_PRIVACY_LAUNCH_GATE = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PRIVACY_LAUNCH_GATE.json"
DEFAULT_HOSTED_BUILD_OPERATOR_DECISIONS = (
    ROOT
    / "chummer-presentation"
    / ".codex-studio"
    / "published"
    / "HOSTED_BUILD_V002_OPERATOR_DECISION_GATE.generated.json"
)
HOSTED_BUILD_OPERATOR_DECISIONS_VERIFIER = (
    ROOT
    / "chummer-presentation"
    / "scripts"
    / "verify_hosted_build_v002_operator_decisions.py"
)
STRICT_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PRIVACY_LAUNCH_GATE_CONTRACT_NAME = "chummer.privacy_launch_gate"
PRIVACY_LAUNCH_GATE_CONTRACT_VERSION = 1
PRIVACY_LAUNCH_GATE_SCOPE = "flagship_launch_and_release_supportability"
HOSTED_BUILD_OPERATOR_DECISIONS_CONTRACT_NAME = (
    "chummer.hosted_build_v002_operator_decision_gate"
)
HOSTED_BUILD_OPERATOR_DECISIONS_CONTRACT_VERSION = 1
HOSTED_BUILD_OPERATOR_DECISIONS_SCOPE = (
    "hosted_build_workspace_lifecycle_and_quota_v002"
)
HOSTED_BUILD_OPERATOR_DECISION_IDS = [
    "quota_policy",
    "logical_bytes",
    "recreation_and_undo",
    "offline_compatibility",
    "tombstone_privacy_policy",
    "stable_owner_identity",
    "writer_epoch",
    "delete_replay_and_rpo",
    "provider_and_topology",
    "enforcement_boundary",
    "migration_posture",
    "capacity_and_retention",
]
HOSTED_BUILD_REQUIRED_BLOCKED_CLAIMS = {
    "flagship_launch",
    "public_release_supportability",
    "hosted_build_v002_authoring",
    "hosted_build_v002_migration",
    "hosted_build_production_launch",
}
HOSTED_BUILD_DECISION_DOES_NOT_AUTHORIZE = [
    "hosted_build_v002_authoring",
    "hosted_build_v002_application",
    "quota_enforcement",
    "tombstone_deletion",
    "hosted_build_production_launch",
    "public_recovery_or_retention_claims",
]
HOSTED_BUILD_IMPLEMENTATION_GATE_REQUIRED_REASON = (
    "Hosted Build V002 decision freeze does not authorize authoring, application, "
    "quota enforcement, tombstone deletion, production launch, or public recovery/retention claims; "
    "a separate versioned implementation and exact-release proof gate is required."
)
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PASS_STATES = {"pass", "passed", "ready"}
RELEASE_READY_CONTRACT_NAME = "chummer.release_ready"
RELEASE_READY_VERDICT = "RELEASE_READY"
READY_VERDICT = "FLAGSHIP_PRODUCT_READY"
NOT_READY_VERDICT = "NOT_FLAGSHIP_PRODUCT_READY"
GOLD_READY_VERDICT = "gold_ready"
GOLD_SUPPORTABILITY_STATE = "gold_supported"
FLAGSHIP_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
FLAGSHIP_PUBLIC_STABLE_ROLLOUT_STATE = "public_stable"
BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "public_release_review_required",
    "desktop_polish_needed",
    "revoked",
}
RECOVERABLE_RELEASE_WRAPPER_BLOCKERS = {
    "final gold janitor state is 'fail'",
    "final gold janitor verdict is 'NOT_GOLD'",
    "live-backed gold claim is not allowed",
}
ROOT_RELEASE_BLOCKERS_MAX_AGE = timedelta(hours=24)
ROOT_RELEASE_BLOCKERS_MAX_FUTURE_SKEW = timedelta(minutes=5)
WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX = (
    "workspace portal release channel artifact "
)


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


def evaluate_privacy_launch_gate(
    payload: dict[str, Any],
    load_status: str,
    path: Path,
) -> dict[str, Any]:
    failures: list[str] = []
    load_failure = receipt_load_failure("privacy launch gate", path, load_status)
    if load_failure:
        failures.append(load_failure)

    contract_name = str(payload.get("contractName") or "").strip()
    contract_version = int_value(payload.get("contractVersion"))
    status = norm(payload.get("status"))
    review_required = payload.get("reviewRequired")
    scope = str(payload.get("scope") or "").strip()
    blocked_claims = normalized_strings(payload.get("blockedClaims"))
    reason = str(payload.get("reason") or "").strip()
    if load_status == "loaded":
        if contract_name != PRIVACY_LAUNCH_GATE_CONTRACT_NAME:
            failures.append(
                f"privacy launch gate contractName must be {PRIVACY_LAUNCH_GATE_CONTRACT_NAME!r}"
            )
        if contract_version != PRIVACY_LAUNCH_GATE_CONTRACT_VERSION:
            failures.append(
                f"privacy launch gate contractVersion must be {PRIVACY_LAUNCH_GATE_CONTRACT_VERSION}"
            )
        if not isinstance(review_required, bool):
            failures.append("privacy launch gate reviewRequired must be boolean")
        if scope != PRIVACY_LAUNCH_GATE_SCOPE:
            failures.append(
                f"privacy launch gate scope must be {PRIVACY_LAUNCH_GATE_SCOPE!r}"
            )
        if not reason:
            failures.append("privacy launch gate reason is required")

        if review_required is True:
            if status != "review_required":
                failures.append(
                    "privacy launch gate reviewRequired=true must use status='review_required'"
                )
            required_claims = {
                "flagship_launch",
                "public_release_supportability",
            }
            missing_claims = sorted(required_claims - set(blocked_claims))
            if missing_claims:
                failures.append(
                    "privacy launch gate is missing blockedClaims: "
                    + ", ".join(missing_claims)
                )
        elif review_required is False and status not in PASS_STATES | {"documented", "clear"}:
            failures.append(
                "privacy launch gate reviewRequired=false must use a documented, clear, or passing status"
            )

    blockers = normalized_strings(failures)
    if not blockers and review_required is True:
        blockers = [reason]

    return {
        "contract_name": contract_name or None,
        "contract_version": contract_version or None,
        "path": str(path),
        "load_status": load_status,
        "status": status or None,
        "review_required": review_required if isinstance(review_required, bool) else None,
        "scope": scope or None,
        "blocked_claims": blocked_claims,
        "reason": reason or None,
        "blockers": blockers,
        "pass": not blockers,
    }


def evaluate_hosted_build_operator_decisions(
    payload: dict[str, Any],
    load_status: str,
    path: Path,
    *,
    verify_material_bindings: bool = True,
) -> dict[str, Any]:
    """Validate the derived decision receipt without trusting editable status."""

    validation_failures: list[str] = []
    if load_status == "missing":
        validation_failures.append("receipt_missing")
    elif load_status == "invalid":
        validation_failures.append("receipt_malformed")

    contract_name = str(payload.get("contractName") or "").strip()
    contract_version = int_value(payload.get("contractVersion"))
    status = norm(payload.get("status"))
    review_required = payload.get("reviewRequired")
    decision_gate_passed = payload.get("decisionGatePassed")
    canonical_provenance = payload.get("canonicalProvenance")
    scope = str(payload.get("scope") or "").strip()
    candidate_release_identity = payload.get("candidateReleaseIdentity")
    decision_count = int_value(payload.get("decisionCount"))
    approved_ids = normalized_strings(payload.get("approvedDecisionIds"))
    unresolved_ids = normalized_strings(payload.get("unresolvedDecisionIds"))
    invalid_ids = normalized_strings(payload.get("invalidDecisionIds"))
    blocked_claims = normalized_strings(payload.get("blockedClaims"))
    does_not_authorize = normalized_strings(payload.get("doesNotAuthorize"))
    receipt_blockers = normalized_strings(payload.get("blockers"))
    validation_errors = normalized_strings(payload.get("validationErrors"))
    reason = str(payload.get("reason") or "").strip()
    generated_at_utc = payload.get("generatedAtUtc")
    generated_at: datetime | None = None
    if isinstance(generated_at_utc, str) and STRICT_UTC_PATTERN.fullmatch(
        generated_at_utc
    ):
        try:
            generated_at = datetime.strptime(
                generated_at_utc,
                "%Y-%m-%dT%H:%M:%SZ",
            ).replace(tzinfo=UTC)
        except ValueError:
            generated_at = None
    source_contract = (
        payload.get("sourceContract")
        if isinstance(payload.get("sourceContract"), dict)
        else {}
    )
    approval_key_registry = (
        payload.get("approvalKeyRegistry")
        if isinstance(payload.get("approvalKeyRegistry"), dict)
        else {}
    )
    packet = payload.get("packet") if isinstance(payload.get("packet"), dict) else {}

    if load_status == "loaded":
        if generated_at is None:
            validation_failures.append("generated_at_utc_invalid")
        elif generated_at > datetime.now(UTC) + timedelta(minutes=5):
            validation_failures.append("generated_at_utc_future")
        elif datetime.now(UTC) - generated_at > timedelta(hours=24):
            validation_failures.append("generated_at_utc_stale")
        if contract_name != HOSTED_BUILD_OPERATOR_DECISIONS_CONTRACT_NAME:
            validation_failures.append("contract_name_invalid")
        if contract_version != HOSTED_BUILD_OPERATOR_DECISIONS_CONTRACT_VERSION:
            validation_failures.append("contract_version_invalid")
        if scope != HOSTED_BUILD_OPERATOR_DECISIONS_SCOPE:
            validation_failures.append("scope_invalid")
        if not isinstance(review_required, bool):
            validation_failures.append("review_required_invalid")
        if not isinstance(decision_gate_passed, bool):
            validation_failures.append("decision_gate_passed_invalid")
        if canonical_provenance is not True:
            validation_failures.append("canonical_provenance_required")
        if candidate_release_identity is not None and (
            not isinstance(candidate_release_identity, str)
            or not candidate_release_identity.strip()
        ):
            validation_failures.append("candidate_release_identity_invalid")
        if does_not_authorize != HOSTED_BUILD_DECISION_DOES_NOT_AUTHORIZE:
            validation_failures.append("does_not_authorize_contract_invalid")
        if decision_count != len(HOSTED_BUILD_OPERATOR_DECISION_IDS):
            validation_failures.append("decision_count_invalid")
        if not reason:
            validation_failures.append("reason_missing")
        if source_contract.get("path") != "docs/HOSTED_BUILD_WORKSPACE_LIFECYCLE_AND_QUOTA_CONTRACT.md":
            validation_failures.append("source_contract_path_invalid")
        if not SHA256_PATTERN.fullmatch(str(source_contract.get("sha256") or "")):
            validation_failures.append("source_contract_digest_invalid")
        if approval_key_registry.get("path") != ".codex-design/product/HOSTED_BUILD_V002_APPROVAL_KEY_REGISTRY.json":
            validation_failures.append("approval_key_registry_path_invalid")
        if not SHA256_PATTERN.fullmatch(
            str(approval_key_registry.get("sha256") or "")
        ):
            validation_failures.append("approval_key_registry_digest_invalid")
        approval_registry_status = approval_key_registry.get("status")
        active_key_count = approval_key_registry.get("activeKeyCount")
        if approval_registry_status not in {"active", "unconfigured"}:
            validation_failures.append("approval_key_registry_status_invalid")
        if (
            not isinstance(active_key_count, int)
            or isinstance(active_key_count, bool)
            or active_key_count < 0
            or (approval_registry_status == "unconfigured" and active_key_count != 0)
            or (approval_registry_status == "active" and active_key_count == 0)
        ):
            validation_failures.append("approval_key_registry_count_invalid")
        if packet.get("path") != ".codex-design/product/HOSTED_BUILD_V002_OPERATOR_DECISIONS.json":
            validation_failures.append("packet_path_invalid")
        if not SHA256_PATTERN.fullmatch(str(packet.get("sha256") or "")):
            validation_failures.append("packet_digest_invalid")

        all_ids = approved_ids + unresolved_ids + invalid_ids
        if len(all_ids) != len(set(all_ids)):
            validation_failures.append("decision_ids_overlap_or_repeat")
        if any(
            decision_ids
            != [
                item
                for item in HOSTED_BUILD_OPERATOR_DECISION_IDS
                if item in decision_ids
            ]
            for decision_ids in (approved_ids, unresolved_ids, invalid_ids)
        ):
            validation_failures.append("decision_ids_out_of_order")
        if set(all_ids) != set(HOSTED_BUILD_OPERATOR_DECISION_IDS):
            validation_failures.append("decision_ids_incomplete_or_unknown")

        if status == "pass":
            if review_required is not False or decision_gate_passed is not True:
                validation_failures.append("pass_state_flags_invalid")
            if approved_ids != HOSTED_BUILD_OPERATOR_DECISION_IDS:
                validation_failures.append("pass_state_approvals_incomplete")
            if approval_key_registry.get("status") != "active":
                validation_failures.append("pass_state_approval_registry_not_active")
            if unresolved_ids or invalid_ids or blocked_claims or receipt_blockers or validation_errors:
                validation_failures.append("pass_state_contains_blockers")
        elif status == "review_required":
            if review_required is not True or decision_gate_passed is not False:
                validation_failures.append("review_state_flags_invalid")
            if not unresolved_ids or invalid_ids or validation_errors:
                validation_failures.append("review_state_decisions_invalid")
            missing_claims = sorted(
                HOSTED_BUILD_REQUIRED_BLOCKED_CLAIMS - set(blocked_claims)
            )
            if missing_claims:
                validation_failures.append("review_state_blocked_claims_incomplete")
            if receipt_blockers != ["hosted_build_v002_operator_decisions_unresolved"]:
                validation_failures.append("review_state_blocker_invalid")
        elif status == "invalid":
            if review_required is not True or decision_gate_passed is not False:
                validation_failures.append("invalid_state_flags_invalid")
            if not invalid_ids or not validation_errors:
                validation_failures.append("invalid_state_detail_missing")
        else:
            validation_failures.append("status_invalid")

        if verify_material_bindings:
            recomputed = recompute_hosted_build_operator_decision_receipt(payload)
            if recomputed is None:
                validation_failures.append("source_material_verification_unavailable")
            elif recomputed != payload:
                validation_failures.append("derived_receipt_material_mismatch")

    validation_failures = normalized_strings(validation_failures)
    if validation_failures:
        blockers = [
            "Hosted Build V002 operator decision gate receipt is missing, malformed, or internally inconsistent."
        ]
        passed = False
    elif review_required is True:
        blockers = [reason]
        passed = False
    elif does_not_authorize:
        blockers = [HOSTED_BUILD_IMPLEMENTATION_GATE_REQUIRED_REASON]
        passed = False
    else:
        blockers = []
        passed = status == "pass" and decision_gate_passed is True

    return {
        "contract_name": contract_name or None,
        "contract_version": contract_version or None,
        "path": str(path),
        "load_status": load_status,
        "status": status or None,
        "review_required": review_required if isinstance(review_required, bool) else None,
        "decision_gate_passed": (
            decision_gate_passed if isinstance(decision_gate_passed, bool) else None
        ),
        "canonical_provenance": (
            canonical_provenance if isinstance(canonical_provenance, bool) else None
        ),
        "scope": scope or None,
        "candidate_release_identity": candidate_release_identity,
        "decision_count": decision_count,
        "approved_decision_ids": approved_ids,
        "unresolved_decision_ids": unresolved_ids,
        "invalid_decision_ids": invalid_ids,
        "blocked_claims": blocked_claims,
        "does_not_authorize": does_not_authorize,
        "source_contract": source_contract,
        "approval_key_registry": approval_key_registry,
        "packet": packet,
        "validation_failures": validation_failures,
        "reason": reason or None,
        "blockers": blockers,
        "pass": passed,
    }


def recompute_hosted_build_operator_decision_receipt(
    receipt: dict[str, Any],
) -> dict[str, Any] | None:
    """Re-run the presentation validator so an editable receipt cannot self-clear."""

    generated_at_utc = receipt.get("generatedAtUtc")
    if not isinstance(generated_at_utc, str):
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "chummer_hosted_build_v002_operator_decisions",
            HOSTED_BUILD_OPERATOR_DECISIONS_VERIFIER,
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        packet_payload, packet_bytes = module._load_packet(module.DEFAULT_PACKET)
        source_bytes = module._read_repo_file(
            module.WORKSPACE_ROOT,
            "chummer-presentation",
            module.SOURCE_CONTRACT_PATH,
            module.MAX_PACKET_BYTES,
        )
        approval_registry_bytes = module._read_repo_file(
            module.WORKSPACE_ROOT,
            "chummer-presentation",
            module.APPROVAL_KEY_REGISTRY_PATH,
            module.MAX_PACKET_BYTES,
        )
        approval_registry_payload = module._strict_json_loads(
            approval_registry_bytes
        )
        recomputed = module.evaluate_packet(
            packet_payload,
            packet_bytes=packet_bytes,
            source_bytes=source_bytes,
            approval_registry_payload=approval_registry_payload,
            approval_registry_bytes=approval_registry_bytes,
            workspace_root=module.WORKSPACE_ROOT,
            generated_at_utc=generated_at_utc,
        )
        return recomputed if isinstance(recomputed, dict) else None
    except Exception:
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


def recoverable_wrapper_blockers_only(summary: dict[str, Any]) -> bool:
    blockers = normalized_strings(summary.get("launch_critical_nested_blockers"))
    return (
        str(summary.get("contract_name") or "").strip() == "fleet.flagship_product_readiness"
        and norm(summary.get("status")) == "fail"
        and summary.get("readiness_load_status") == "loaded"
        and norm(summary.get("completion_audit_status")) in PASS_STATES
        and norm(summary.get("flagship_readiness_audit_status")) in PASS_STATES
        and summary.get("pass") is False
        and int_value(summary.get("missing_count")) == 0
        and int_value(summary.get("scoped_missing_count")) == 0
        and not normalized_strings(summary.get("coverage_gap_keys"))
        and not normalized_strings(summary.get("scoped_coverage_gap_keys"))
        and bool(blockers)
        and int_value(summary.get("launch_critical_nested_blocker_count")) == len(blockers)
        and all(blocker in RECOVERABLE_RELEASE_WRAPPER_BLOCKERS for blocker in blockers)
    )


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def release_ready_gate_failures(payload: dict[str, Any]) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        return {}
    if (
        normalized_token(payload.get("status")) in PASS_STATES
        and not normalized_strings(payload.get("failures"))
        and not normalized_strings(payload.get("failed_gates"))
    ):
        return {}

    failures_by_gate: dict[str, list[str]] = {}
    for failure in normalized_strings(payload.get("failures")):
        if not failure.startswith("FAIL "):
            continue
        gate_with_sep, _, detail = failure[5:].partition(":")
        gate_name = gate_with_sep.strip().casefold()
        detail = detail.strip()
        if not gate_name or not detail:
            continue
        failures_by_gate.setdefault(gate_name, []).append(detail)
    return {
        gate_name: normalized_strings(details)
        for gate_name, details in failures_by_gate.items()
        if details
    }


def release_ready_receipt_semantic_failures(payload: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return []

    failures: list[str] = []
    if str(payload.get("contract_name") or "").strip() != RELEASE_READY_CONTRACT_NAME:
        failures.append("release_ready receipt has unexpected contract")

    if normalized_token(payload.get("status")) not in PASS_STATES:
        return failures

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


def google_oauth_release_truth_effective_pass(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False

    failures = normalized_strings(payload.get("failures"))
    failed_gates = normalized_strings(payload.get("failed_gates"))
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


def windows_visual_audit_semantic_failures(payload: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return []

    failures: list[str] = []
    startup_receipt = payload.get("startupReceipt") if isinstance(payload.get("startupReceipt"), dict) else {}
    visual_source = payload.get("visualAuditSource") if isinstance(payload.get("visualAuditSource"), dict) else {}

    if payload.get("source_digest_matches_promoted") is False:
        failures.append("Windows installer visual audit source digest does not match promoted installer")
    if startup_receipt:
        if normalized_token(startup_receipt.get("status")) not in PASS_STATES:
            failures.append("Windows installer startup receipt is not pass")
        if startup_receipt.get("artifactDigestMatchesPromoted") is False:
            failures.append("Windows installer startup receipt digest does not match promoted installer")
    if visual_source:
        if normalized_token(visual_source.get("status")) not in PASS_STATES:
            failures.append("Windows installer visual audit source is not pass")
        if visual_source.get("artifactDigestMatchesPromoted") is False:
            failures.append("Windows installer visual audit source digest does not match promoted installer")

    return normalized_strings(failures)


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


def launch_critical_nested_blockers(
    payload: dict[str, Any],
    *,
    recompute_workspace_release_truth: bool = False,
) -> list[str]:
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
    detailed_release_blockers = resolve_release_truth_launch_blockers(
        evidence,
        recompute_workspace_release_truth=recompute_workspace_release_truth,
    )
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


def resolve_release_truth_launch_blockers(
    evidence: dict[str, Any],
    *,
    recompute_workspace_release_truth: bool = False,
) -> list[str]:
    if not str(evidence.get("final_gold_janitor_path") or "").strip():
        return []

    current_release_truth_blockers = (
        current_release_truth_launch_blockers(
            recompute_workspace_release_truth=True,
        )
        if recompute_workspace_release_truth
        else current_release_truth_launch_blockers()
    )
    if current_release_truth_blockers:
        return current_release_truth_blockers

    _release_channel_payload, release_channel_load_status = load_json(DEFAULT_RELEASE_CHANNEL)
    _google_payload, google_load_status = load_json(DEFAULT_GOOGLE_OAUTH_LINKING_PROOF)
    _windows_payload, windows_load_status = load_json(DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT)
    if (
        release_channel_load_status == "loaded"
        and google_load_status == "loaded"
        and windows_load_status == "loaded"
    ):
        return []

    release_ready_path = PUBLISHED_ROOT / "RELEASE_READY.generated.json"
    release_ready, release_ready_load_status = load_json(release_ready_path)
    if release_ready_load_status != "loaded":
        return []
    if not release_ready:
        return []
    semantic_failures = release_ready_receipt_semantic_failures(release_ready)
    if normalized_token(release_ready.get("status")) in PASS_STATES:
        return normalized_strings(semantic_failures)

    failed_gates = {
        item.casefold()
        for item in normalized_strings(release_ready.get("failed_gates"))
    }
    if (
        "release_channel" not in failed_gates
        and "google_oauth_linking_proof" not in failed_gates
        and "windows_installer_visual_audit" not in failed_gates
    ):
        return normalized_strings(semantic_failures)

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

    return normalized_strings([*semantic_failures, *details])


def current_release_truth_launch_blockers(
    *,
    recompute_workspace_release_truth: bool = False,
) -> list[str]:
    details: list[str] = []
    release_ready, release_ready_load_status = load_json(PUBLISHED_ROOT / "RELEASE_READY.generated.json")
    release_ready_by_gate = (
        release_ready_gate_failures(release_ready)
        if release_ready_load_status == "loaded"
        else {}
    )
    release_channel, release_channel_load_status = load_json(DEFAULT_RELEASE_CHANNEL)
    release_channel_load_failure = receipt_load_failure(
        "release channel",
        DEFAULT_RELEASE_CHANNEL,
        release_channel_load_status,
        include_missing=False,
    )
    if release_channel_load_failure:
        details.append(release_channel_load_failure)
    elif release_channel:
        release_channel_details = current_release_channel_failures(release_channel)
        if release_channel_details:
            embedded_release_channel_details = release_ready_by_gate.get(
                "release_channel", []
            )
            if recompute_workspace_release_truth:
                embedded_release_channel_details = [
                    detail
                    for detail in embedded_release_channel_details
                    if not detail.startswith(
                        WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX
                    )
                ]
            release_channel_details = normalized_strings(
                release_channel_details + embedded_release_channel_details
            )
        details.extend(release_channel_details)
        if recompute_workspace_release_truth:
            details.extend(
                workspace_portal_release_channel_drift_failures(
                    release_channel,
                    DEFAULT_WORKSPACE_PORTAL_RELEASE_CHANNEL,
                )
            )

    google_oauth_linking_proof, google_oauth_linking_proof_load_status = load_json(DEFAULT_GOOGLE_OAUTH_LINKING_PROOF)
    google_load_failure = receipt_load_failure(
        "google oauth linking proof",
        DEFAULT_GOOGLE_OAUTH_LINKING_PROOF,
        google_oauth_linking_proof_load_status,
        include_missing=False,
    )
    if google_load_failure:
        details.append(google_load_failure)
    elif google_oauth_linking_proof and not google_oauth_release_truth_effective_pass(google_oauth_linking_proof):
        google_details: list[str] = []
        google_operator_failure = google_oauth_operator_evidence_missing_failure(google_oauth_linking_proof)
        google_resend_failure = google_oauth_operator_ask_resend_failure(google_oauth_linking_proof)
        if google_operator_failure:
            google_details.append(google_operator_failure)
        if google_resend_failure:
            google_details.append(google_resend_failure)
        if not google_operator_failure and not google_resend_failure:
            google_details.extend(
                receipt_failure_reasons(
                    google_oauth_linking_proof,
                    "google_oauth_linking_proof status is not pass",
                )
            )
        google_details.extend(release_ready_by_gate.get("google_oauth_linking_proof", []))
        details.extend(normalized_strings(google_details))

    windows_installer_visual_audit, windows_installer_visual_audit_load_status = load_json(DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT)
    windows_load_failure = receipt_load_failure(
        "windows installer visual audit",
        DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT,
        windows_installer_visual_audit_load_status,
        include_missing=False,
    )
    if windows_load_failure:
        details.append(windows_load_failure)
    elif (
        windows_installer_visual_audit
        and (
            normalized_token(windows_installer_visual_audit.get("status")) not in PASS_STATES
            or bool(normalized_strings(windows_installer_visual_audit.get("failures")))
            or bool(normalized_strings(windows_installer_visual_audit.get("failed_gates")))
            or bool(windows_visual_audit_semantic_failures(windows_installer_visual_audit))
        )
    ):
        windows_details = list(windows_visual_audit_semantic_failures(windows_installer_visual_audit))
        if (
            normalized_token(windows_installer_visual_audit.get("status")) not in PASS_STATES
            or bool(normalized_strings(windows_installer_visual_audit.get("failures")))
            or bool(normalized_strings(windows_installer_visual_audit.get("failed_gates")))
        ):
            windows_details.extend(
                receipt_failure_reasons(
                    windows_installer_visual_audit,
                    "windows_installer_visual_audit status is not pass",
                )
            )
        windows_details.extend(release_ready_by_gate.get("windows_installer_visual_audit", []))
        details.extend(
            receipt_failure_reasons(
                {"failures": normalized_strings(windows_details)},
                "windows_installer_visual_audit status is not pass",
            )
        )

    return normalized_strings(details)


def release_channel_identity(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "status": normalized_token(payload.get("status")),
        "channel": normalized_token(payload.get("channelId") or payload.get("channel")),
        "version": str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
        "supportability": normalized_token(payload.get("supportabilityState")),
        "rollout": normalized_token(payload.get("rolloutState")),
    }


def release_channel_identity_text(identity: dict[str, str]) -> str:
    return (
        f"status={identity.get('status') or 'missing'}, "
        f"channel={identity.get('channel') or 'missing'}, "
        f"version={identity.get('version') or 'missing'}, "
        f"supportability={identity.get('supportability') or 'missing'}, "
        f"rollout={identity.get('rollout') or 'missing'}"
    )


def display_workspace_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def workspace_portal_release_channel_drift_failures(
    authoritative_payload: dict[str, Any],
    portal_path: Path,
) -> list[str]:
    portal_payload, portal_load_status = load_json(portal_path)
    display_path = display_workspace_path(portal_path)
    if portal_load_status == "missing":
        return [
            f"{WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX}{display_path} is missing"
        ]
    if portal_load_status == "invalid":
        return [
            f"{WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX}{display_path} is malformed"
        ]

    authoritative_identity = release_channel_identity(authoritative_payload)
    portal_identity = release_channel_identity(portal_payload)
    if portal_identity == authoritative_identity:
        return []
    return [
        f"{WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX}{display_path} "
        "disagrees with authoritative registry receipt "
        f"(local {release_channel_identity_text(portal_identity)}; "
        f"authoritative {release_channel_identity_text(authoritative_identity)})"
    ]


def parse_offset_aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def root_release_truth_failures(
    payload: dict[str, Any],
    load_status: str,
    path: Path,
    *,
    observed_at: datetime | None = None,
) -> list[str]:
    load_failure = receipt_load_failure("root RELEASE_BLOCKERS", path, load_status)
    if load_failure:
        return [load_failure]

    failures: list[str] = []
    generated_at_raw = payload.get("generated_at") or payload.get("generated_at_utc")
    generated_at = parse_offset_aware_timestamp(generated_at_raw)
    if generated_at is None:
        failures.append(
            f"root RELEASE_BLOCKERS generated_at is missing or malformed: {path}"
        )
    else:
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        age = now - generated_at
        if age < -ROOT_RELEASE_BLOCKERS_MAX_FUTURE_SKEW:
            failures.append(
                "root RELEASE_BLOCKERS generated_at is in the future "
                f"(generated_at={generated_at_raw}): {path}"
            )
        elif age > ROOT_RELEASE_BLOCKERS_MAX_AGE:
            failures.append(
                "root RELEASE_BLOCKERS receipt is stale "
                f"(generated_at={generated_at_raw}; "
                f"max_age_seconds={int(ROOT_RELEASE_BLOCKERS_MAX_AGE.total_seconds())}): {path}"
            )

    blockers = payload.get("root_blockers")
    if blockers is None:
        blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        failures.append(
            "root RELEASE_BLOCKERS receipt must contain root_blockers or blockers as a list: "
            f"{path}"
        )
    return normalized_strings(failures)


def current_release_truth_root_context() -> dict[str, Any]:
    payload, load_status = load_json(DEFAULT_RELEASE_BLOCKERS)
    truth_failures = root_release_truth_failures(
        payload,
        load_status,
        DEFAULT_RELEASE_BLOCKERS,
    )
    if load_status != "loaded":
        return {
            "root_blocker_ids": [],
            "root_blockers_generated_at": None,
            "root_release_truth_failures": truth_failures,
            "stable_promotion_command": None,
            "post_promotion_verify_command": None,
            "root_release_truth_source": str(DEFAULT_RELEASE_BLOCKERS),
        }

    blockers = payload.get("root_blockers")
    blockers = blockers if isinstance(blockers, list) else []
    if not blockers:
        blockers = payload.get("blockers")
        blockers = blockers if isinstance(blockers, list) else []
    blocker_ids = normalized_strings(
        [
            entry.get("blocker_id") or entry.get("id")
            for entry in blockers
            if isinstance(entry, dict)
        ]
    )
    posture = next(
        (
            entry
            for entry in blockers
            if isinstance(entry, dict)
            and str(entry.get("blocker_id") or entry.get("id") or "").strip() == "release_posture:non_flagship_channel"
        ),
        {},
    )
    return {
        "root_blocker_ids": blocker_ids,
        "root_blockers_generated_at": payload.get("generated_at"),
        "root_release_truth_failures": truth_failures,
        "stable_promotion_command": str(posture.get("stable_promotion_command") or "").strip() or None,
        "post_promotion_verify_command": str(posture.get("post_promotion_verify_command") or "").strip() or None,
        "root_release_truth_source": str(DEFAULT_RELEASE_BLOCKERS),
    }


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
    elif rollout_state and rollout_state != FLAGSHIP_PUBLIC_STABLE_ROLLOUT_STATE:
        failures.append(f"release channel rollout is {rollout_state}, not public_stable")
    return failures


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

    if evidence.get("ui_linux_exit_gate_effective_ready") is not True:
        return False
    if norm(evidence.get("ui_workflow_execution_gate_status")) not in PASS_STATES:
        return False
    if norm(evidence.get("ui_visual_familiarity_exit_gate_status")) not in PASS_STATES:
        return False
    if norm(evidence.get("ui_flagship_release_gate_status")) not in PASS_STATES:
        return False
    if evidence.get("ui_user_journey_tester_audit_required") is True:
        if norm(evidence.get("ui_user_journey_tester_audit_status")) not in PASS_STATES:
            return False
        if evidence.get("ui_user_journey_tester_audit_ready") is not True:
            return False

    unresolved_hosts = {
        norm(item)
        for item in evidence.get("ui_external_host_proof_blockers_unresolved_hosts", [])
        if str(item).strip()
    } if isinstance(evidence.get("ui_external_host_proof_blockers_unresolved_hosts"), list) else set()

    normalized_blockers = {str(item).strip().casefold() for item in blockers if str(item).strip()}
    if (
        norm(evidence.get("ui_executable_exit_gate_blocking_mode")) == "external_only"
        and norm(evidence.get("ui_windows_exit_gate_blocking_mode")) == "external_only"
        and unresolved_hosts == {"windows"}
    ):
        return any("windows installer visual audit" in blocker for blocker in normalized_blockers)

    effective_local_blockers = [
        str(item).strip()
        for item in evidence.get("ui_executable_exit_gate_effective_local_blocking_findings", [])
        if str(item).strip()
    ] if isinstance(evidence.get("ui_executable_exit_gate_effective_local_blocking_findings"), list) else []
    release_posture_only = bool(effective_local_blockers) and all(
        norm(item).startswith("release channel rolloutstate")
        or norm(item).startswith("release channel supportabilitystate")
        for item in effective_local_blockers
    )
    if (
        release_posture_only
        and evidence.get("ui_windows_exit_gate_effective_ready") is True
        and not unresolved_hosts
    ):
        has_rollout_blocker = any("release channel rollout is" in blocker for blocker in normalized_blockers)
        has_supportability_blocker = any("release channel supportability is" in blocker for blocker in normalized_blockers)
        return has_rollout_blocker and has_supportability_blocker

    release_channel_missing_inventory = any(
        normalized_strings(evidence.get(key))
        for key in (
            "release_channel_missing_required_platform_head_pairs",
            "release_channel_missing_required_platform_head_pairs_derived",
            "release_channel_missing_required_platforms_derived",
            "release_channel_missing_required_heads_derived",
        )
    )
    recoverable_wrapper_blockers = bool(normalized_blockers) and all(
        blocker in {item.casefold() for item in RECOVERABLE_RELEASE_WRAPPER_BLOCKERS}
        for blocker in normalized_blockers
    )
    if (
        recoverable_wrapper_blockers
        and evidence.get("ui_executable_exit_gate_effective_ready") is True
        and evidence.get("ui_windows_exit_gate_effective_ready") is True
        and not effective_local_blockers
        and not unresolved_hosts
        and evidence.get("release_channel_freshness_ok") is False
        and norm(evidence.get("release_channel_status")) == "published"
        and norm(evidence.get("release_channel_rollout_state")) == "public_stable"
        and norm(evidence.get("release_channel_supportability_state")) == "gold_supported"
        and norm(evidence.get("release_channel_release_proof_status")) in PASS_STATES
        and evidence.get("release_channel_tuple_coverage_incomplete") is False
        and evidence.get("release_channel_has_windows_public_installer") is True
        and evidence.get("release_channel_has_linux_public_installer") is True
        and not release_channel_missing_inventory
    ):
        return True

    return False


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


def normalized_missing_count(raw_count: int, raw_gaps: list[str], normalized_gaps: list[str]) -> int:
    removed_gap_count = max(
        0,
        len(normalized_strings(raw_gaps)) - len(normalized_strings(normalized_gaps)),
    )
    return max(0, raw_count - removed_gap_count)


def summarize(
    payload: dict[str, Any],
    *,
    readiness_load_status: str = "loaded",
    readiness_path: Path | None = None,
    privacy_launch_gate_payload: dict[str, Any] | None = None,
    privacy_launch_gate_load_status: str = "not_evaluated",
    privacy_launch_gate_path: Path | None = None,
    hosted_build_operator_decisions_payload: dict[str, Any] | None = None,
    hosted_build_operator_decisions_load_status: str = "not_evaluated",
    hosted_build_operator_decisions_path: Path | None = None,
    hosted_build_operator_decisions_verify_material_bindings: bool = True,
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
    release_truth_context = current_release_truth_root_context()
    privacy_gate = (
        evaluate_privacy_launch_gate(
            privacy_launch_gate_payload or {},
            privacy_launch_gate_load_status,
            privacy_launch_gate_path,
        )
        if privacy_launch_gate_path is not None
        else {
            "path": None,
            "load_status": "not_evaluated",
            "status": None,
            "review_required": None,
            "scope": None,
            "blocked_claims": [],
            "reason": None,
            "blockers": [],
            "pass": True,
        }
    )
    hosted_build_operator_decisions = (
        evaluate_hosted_build_operator_decisions(
            hosted_build_operator_decisions_payload or {},
            hosted_build_operator_decisions_load_status,
            hosted_build_operator_decisions_path,
            verify_material_bindings=hosted_build_operator_decisions_verify_material_bindings,
        )
        if hosted_build_operator_decisions_path is not None
        else {
            "path": None,
            "load_status": "not_evaluated",
            "status": None,
            "review_required": None,
            "decision_gate_passed": None,
            "canonical_provenance": None,
            "scope": None,
            "candidate_release_identity": None,
            "decision_count": 0,
            "approved_decision_ids": [],
            "unresolved_decision_ids": [],
            "invalid_decision_ids": [],
            "blocked_claims": [],
            "does_not_authorize": [],
            "source_contract": {},
            "approval_key_registry": {},
            "packet": {},
            "validation_failures": [],
            "reason": None,
            "blockers": [],
            "pass": True,
        }
    )
    verify_external_release_truth = readiness_path is not None
    root_release_truth_blockers = (
        list(release_truth_context["root_release_truth_failures"])
        if verify_external_release_truth
        else []
    )
    launch_blockers = normalized_strings(
        launch_critical_nested_blockers(
            payload,
            recompute_workspace_release_truth=verify_external_release_truth,
        )
        + root_release_truth_blockers
        + list(privacy_gate["blockers"])
        + list(hosted_build_operator_decisions["blockers"])
    )
    coverage_gaps = normalized_coverage_gaps(payload, raw_coverage_gaps, launch_blockers)
    scoped_gaps = normalized_coverage_gaps(payload, raw_scoped_gaps, launch_blockers)
    raw_missing_count = int_value(summary.get("missing_count"))
    raw_scoped_missing_count = int_value(summary.get("scoped_missing_count"))
    result = {
        "contract_name": payload.get("contract_name"),
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at") or payload.get("generated_at_utc") or payload.get("generatedAtUtc"),
        "readiness_load_status": readiness_load_status,
        "completion_audit_status": completion.get("status"),
        "flagship_readiness_audit_status": readiness.get("status"),
        "ready_count": int_value(summary.get("ready_count")),
        "missing_count": normalized_missing_count(raw_missing_count, raw_coverage_gaps, coverage_gaps),
        "scoped_missing_count": normalized_missing_count(
            raw_scoped_missing_count,
            raw_scoped_gaps,
            scoped_gaps,
        ),
        "warning_count": int_value(summary.get("warning_count")),
        "coverage_gap_keys": coverage_gaps,
        "scoped_coverage_gap_keys": scoped_gaps,
        "launch_critical_nested_blockers": launch_blockers,
        "root_blocker_ids": release_truth_context["root_blocker_ids"],
        "root_blockers_generated_at": release_truth_context["root_blockers_generated_at"],
        "root_release_truth_failures": release_truth_context[
            "root_release_truth_failures"
        ],
        "stable_promotion_command": release_truth_context["stable_promotion_command"],
        "post_promotion_verify_command": release_truth_context["post_promotion_verify_command"],
        "root_release_truth_source": release_truth_context["root_release_truth_source"],
        "privacy_launch_gate": privacy_gate,
        "hosted_build_operator_decisions": hosted_build_operator_decisions,
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
        and
        result["contract_name"] == "fleet.flagship_product_readiness"
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
        "--allow-recoverable-wrapper-blockers",
        action="store_true",
        help=(
            "Exit zero when the gate is fail-closed only because release-wrapper blockers remain, "
            "while still writing a fail summary receipt."
        ),
    )
    parser.add_argument(
        "--privacy-launch-gate",
        type=Path,
        default=DEFAULT_PRIVACY_LAUNCH_GATE,
        help="Offline privacy launch-gate contract used to block unsupported flagship claims.",
    )
    parser.add_argument(
        "--hosted-build-v002-decisions",
        type=Path,
        default=DEFAULT_HOSTED_BUILD_OPERATOR_DECISIONS,
        help=(
            "Derived Hosted Build V002 operator decision receipt. Missing, invalid, "
            "or unresolved decisions fail closed without modifying the public privacy contract."
        ),
    )
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
    privacy_launch_gate_payload, privacy_launch_gate_load_status = load_json(
        args.privacy_launch_gate
    )
    (
        hosted_build_operator_decisions_payload,
        hosted_build_operator_decisions_load_status,
    ) = load_json(args.hosted_build_v002_decisions)
    summary = summarize(
        readiness_payload,
        readiness_load_status=readiness_load_status,
        readiness_path=args.readiness,
        privacy_launch_gate_payload=privacy_launch_gate_payload,
        privacy_launch_gate_load_status=privacy_launch_gate_load_status,
        privacy_launch_gate_path=args.privacy_launch_gate,
        hosted_build_operator_decisions_payload=hosted_build_operator_decisions_payload,
        hosted_build_operator_decisions_load_status=hosted_build_operator_decisions_load_status,
        hosted_build_operator_decisions_path=args.hosted_build_v002_decisions,
    )
    fail_closed_payload, readiness_updated = fail_closed_readiness_payload(readiness_payload, summary, generated_at_utc)
    if readiness_updated:
        args.readiness.write_text(json.dumps(fail_closed_payload, indent=2) + "\n", encoding="utf-8")
        summary = summarize(
            fail_closed_payload,
            readiness_load_status=readiness_load_status,
            readiness_path=args.readiness,
            privacy_launch_gate_payload=privacy_launch_gate_payload,
            privacy_launch_gate_load_status=privacy_launch_gate_load_status,
            privacy_launch_gate_path=args.privacy_launch_gate,
            hosted_build_operator_decisions_payload=hosted_build_operator_decisions_payload,
            hosted_build_operator_decisions_load_status=hosted_build_operator_decisions_load_status,
            hosted_build_operator_decisions_path=args.hosted_build_v002_decisions,
        )
    payload = {
        "contract_name": "chummer.flagship_product_readiness_gate.v1",
        "generated_at_utc": generated_at_utc,
        "status": "pass" if summary["pass"] else "fail",
        "verdict": READY_VERDICT if summary["pass"] else NOT_READY_VERDICT,
        "readiness_path": str(args.readiness),
        "readiness_load_status": summary["readiness_load_status"],
        "readiness_receipt_fail_closed": readiness_updated,
        "pass": summary["pass"],
        "reason": summary["reason"],
        "coverage_gap_keys": summary["coverage_gap_keys"],
        "scoped_coverage_gap_keys": summary["scoped_coverage_gap_keys"],
        "launch_critical_nested_blockers": summary["launch_critical_nested_blockers"],
        "launch_critical_nested_blocker_count": summary["launch_critical_nested_blocker_count"],
        "root_blocker_ids": summary["root_blocker_ids"],
        "root_blockers_generated_at": summary["root_blockers_generated_at"],
        "root_release_truth_failures": summary["root_release_truth_failures"],
        "stable_promotion_command": summary["stable_promotion_command"],
        "post_promotion_verify_command": summary["post_promotion_verify_command"],
        "root_release_truth_source": summary["root_release_truth_source"],
        "privacy_launch_gate": summary["privacy_launch_gate"],
        "hosted_build_operator_decisions": summary["hosted_build_operator_decisions"],
        "summary": summary,
    }
    payload["recoverable_wrapper_blockers_only"] = recoverable_wrapper_blockers_only(summary)
    if materializer_result is not None:
        payload["materializer"] = materializer_result
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not summary["pass"]:
        if args.allow_recoverable_wrapper_blockers and payload["recoverable_wrapper_blockers_only"]:
            print("flagship_product_readiness:recoverable_wrapper_blockers")
            return 0
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return 1
    print("flagship_product_readiness:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
