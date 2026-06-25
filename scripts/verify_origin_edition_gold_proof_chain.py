#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_verify_paths import gold_proof_chain_from_env


CONTRACT_NAME = "chummer.origin_edition.gold_proof_chain.v1"
EXPECTED_STAGE_NAMES = [
    "deployed_browser_probe",
    "deployed_operator_handoff",
    "gold_gap_audit",
    "runsite_integration_proof",
    "completion_matrix",
    "requirement_coverage",
]
FORBIDDEN_VALUE_MARKERS = [
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=",
    "Bearer ",
    "secret-token",
    "owner-session-token",
    "super-secret",
]


def load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def verify(path: Path, *, require_gold: bool = False) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not path.is_file():
        return False, [f"missing proof-chain receipt: {path}"]
    text = path.read_text(encoding="utf-8")
    payload = load_json(path)
    if payload.get("contractName") != CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    status = str(payload.get("status") or "").lower()
    if not str(payload.get("updated_at") or "").strip():
        issues.append("updated_at_missing")
    if not str(payload.get("next_action") or "").strip():
        issues.append("next_action_missing")
    blocking_reason = str(payload.get("blocking_reason") or "")
    if status == "pass" and blocking_reason:
        issues.append("pass_chain_has_blocking_reason")
    if status == "blocked" and not blocking_reason:
        issues.append("blocked_chain_missing_blocking_reason")
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    if not isinstance(progress.get("totalStages"), int):
        issues.append("progress_total_stages_missing")
    if not isinstance(progress.get("passedStages"), int):
        issues.append("progress_passed_stages_missing")
    if not isinstance(progress.get("blockedStages"), list):
        issues.append("progress_blocked_stages_missing")
    stages = payload.get("stages") if isinstance(payload.get("stages"), list) else []
    stage_names = [stage.get("name") for stage in stages if isinstance(stage, dict)]
    if stage_names != EXPECTED_STAGE_NAMES:
        issues.append(f"stage_order_mismatch:{stage_names}")
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        name = str(stage.get("name") or "")
        if not str(stage.get("path") or "").strip():
            issues.append(f"stage_path_missing:{name}")
        sha = str(stage.get("sha256") or "")
        if len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha.lower()):
            issues.append(f"stage_sha256_invalid:{name}")
    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    for key in ("rawCredentialExposed", "rawSessionTokenExposed", "envValuesExposed", "deploymentPerformed"):
        if privacy.get(key) is not False:
            issues.append(f"privacy_flag_not_false:{key}")
    env_file = payload.get("envFile") if isinstance(payload.get("envFile"), dict) else {}
    if env_file.get("valuesStoredInReceipt") is not False:
        issues.append("env_file_values_stored")
    for marker in FORBIDDEN_VALUE_MARKERS:
        if marker in text:
            issues.append(f"forbidden_secret_marker:{marker}")

    if require_gold:
        if status != "pass":
            issues.append("proof_chain_not_pass")
        if payload.get("goalCompletionClaimAllowed") is not True:
            issues.append("goal_completion_not_allowed")
        if payload.get("blockedStages") != []:
            issues.append("gold_chain_has_blocked_stages")
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            name = str(stage.get("name") or "")
            if str(stage.get("status") or "").lower() != "pass":
                issues.append(f"gold_stage_not_pass:{name}")
            blockers = stage.get("blockers") if isinstance(stage.get("blockers"), list) else []
            if blockers:
                issues.append(f"gold_stage_has_blockers:{name}")
            blocked_rows = stage.get("blockedRows") if isinstance(stage.get("blockedRows"), list) else []
            if blocked_rows:
                issues.append(f"gold_stage_has_blocked_rows:{name}")
            blocked_hard_gates = stage.get("blockedHardGates") if isinstance(stage.get("blockedHardGates"), list) else []
            if blocked_hard_gates:
                issues.append(f"gold_stage_has_blocked_hard_gates:{name}")
            blocked_requirements = stage.get("blockedRequirements") if isinstance(stage.get("blockedRequirements"), list) else []
            if blocked_requirements:
                issues.append(f"gold_stage_has_blocked_requirements:{name}")
    else:
        if status not in {"pass", "blocked"}:
            issues.append("unexpected_proof_chain_status")
        if status == "blocked":
            blocked_stages = payload.get("blockedStages") if isinstance(payload.get("blockedStages"), list) else []
            if "deployed_browser_probe" not in blocked_stages:
                issues.append("blocked_without_deployed_browser_probe")
            deployed_probe = next((stage for stage in stages if isinstance(stage, dict) and stage.get("name") == "deployed_browser_probe"), {})
            deployed_blockers = deployed_probe.get("blockers") if isinstance(deployed_probe.get("blockers"), list) else []
            if "owner_playback_e2e_verified" not in deployed_blockers:
                issues.append("deployed_probe_missing_owner_playback_blocker")
            handoff = next((stage for stage in stages if isinstance(stage, dict) and stage.get("name") == "deployed_operator_handoff"), {})
            handoff_blockers = handoff.get("blockers") if isinstance(handoff.get("blockers"), list) else []
            if "deployed_browser_probe_flag_missing:owner_playback_e2e_verified" not in handoff_blockers:
                issues.append("handoff_missing_owner_playback_blocker")
            runsite = next((stage for stage in stages if isinstance(stage, dict) and stage.get("name") == "runsite_integration_proof"), {})
            if str(runsite.get("status") or "").lower() != "pass":
                issues.append("runsite_integration_proof_not_pass")
            completion = next((stage for stage in stages if isinstance(stage, dict) and stage.get("name") == "completion_matrix"), {})
            blocked_rows = completion.get("blockedRows") if isinstance(completion.get("blockedRows"), list) else []
            if "deployed_user_login_read_listen_watch" not in blocked_rows:
                issues.append("completion_matrix_missing_deployed_user_blocker")
            blocked_hard_gates = completion.get("blockedHardGates") if isinstance(completion.get("blockedHardGates"), list) else []
            if "gold_audit_completion_claim_allowed" not in blocked_hard_gates:
                issues.append("completion_matrix_missing_gold_audit_hard_gate")
            coverage = next((stage for stage in stages if isinstance(stage, dict) and stage.get("name") == "requirement_coverage"), {})
            coverage_blocked = coverage.get("blockedRequirements") if isinstance(coverage.get("blockedRequirements"), list) else []
            if coverage_blocked != ["deployed_owner_read_listen_watch_canon"]:
                issues.append("requirement_coverage_unexpected_blocked_requirements")
            if payload.get("goalCompletionClaimAllowed") is not False:
                issues.append("blocked_chain_claims_completion")
    return not issues, issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Origin Edition Gold proof-chain receipt.")
    parser.add_argument(
        "--proof-chain",
        type=Path,
        default=gold_proof_chain_from_env(),
    )
    parser.add_argument("--require-gold", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ok, issues = verify(args.proof_chain, require_gold=args.require_gold)
    if not ok:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("origin edition gold proof chain verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
