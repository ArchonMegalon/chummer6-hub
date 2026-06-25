#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_verify_paths import (
    gold_final_verdict_from_env,
    gold_proof_chain_from_env,
    gold_requirement_coverage_from_env,
)


READY_VERDICT = "ORIGIN_EDITION_GOLD_READY"
BLOCKED_VERDICT = "ORIGIN_EDITION_GOLD_BLOCKED"
FORBIDDEN_VALUE_MARKERS = [
    "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=",
    "Bearer ",
    "Cookie:",
    "secret-token",
    "owner-session-token",
    "super-secret",
    "rangersofB5",
    "api:",
]


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def expected_verdict(proof_chain: dict[str, Any], coverage: dict[str, Any]) -> tuple[str, bool, list[str]]:
    blocked_requirements = coverage.get("blockedRequirements")
    if not isinstance(blocked_requirements, list):
        blocked_requirements = []
    blocked = [str(item) for item in blocked_requirements]
    ready = (
        proof_chain.get("status") == "pass"
        and proof_chain.get("goalCompletionClaimAllowed") is True
        and coverage.get("status") == "pass"
        and coverage.get("goalCompletionClaimAllowed") is True
        and not blocked
    )
    return (READY_VERDICT if ready else BLOCKED_VERDICT), ready, blocked


def verify(verdict_path: Path, proof_chain_path: Path, coverage_path: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not verdict_path.is_file():
        return False, [f"missing_final_verdict:{verdict_path}"]
    if not proof_chain_path.is_file():
        issues.append(f"missing_proof_chain:{proof_chain_path}")
    if not coverage_path.is_file():
        issues.append(f"missing_requirement_coverage:{coverage_path}")
    if issues:
        return False, issues

    text = verdict_path.read_text(encoding="utf-8")
    proof_chain = read_json(proof_chain_path)
    coverage = read_json(coverage_path)
    verdict, ready, blocked_requirements = expected_verdict(proof_chain, coverage)

    if f"Verdict: `{verdict}`" not in text:
        issues.append(f"verdict_text_mismatch:{verdict}")
    completion_text = "true" if ready else "false"
    if f"Goal completion claim allowed: `{completion_text}`" not in text:
        issues.append(f"goal_completion_text_mismatch:{completion_text}")
    wrong_verdict = BLOCKED_VERDICT if verdict == READY_VERDICT else READY_VERDICT
    if f"Verdict: `{wrong_verdict}`" in text:
        issues.append(f"contradictory_verdict_present:{wrong_verdict}")
    next_action = str(proof_chain.get("next_action") or "").strip()
    if next_action and next_action not in text:
        issues.append("next_action_missing")
    blocking_reason = str(proof_chain.get("blocking_reason") or "").strip()
    if blocking_reason and blocking_reason not in text:
        issues.append("blocking_reason_missing")
    for requirement in blocked_requirements:
        if f"`{requirement}`" not in text:
            issues.append(f"blocked_requirement_missing:{requirement}")
    if not blocked_requirements and "- None." not in text:
        issues.append("missing_no_blocked_requirements_marker")

    privacy = proof_chain.get("privacy") if isinstance(proof_chain.get("privacy"), dict) else {}
    for key in ("rawCredentialExposed", "rawSessionTokenExposed", "envValuesExposed", "deploymentPerformed"):
        if privacy.get(key) is not False:
            issues.append(f"privacy_flag_not_false:{key}")
        if f"`{key}`: `false`" not in text:
            issues.append(f"privacy_line_missing:{key}")

    for marker in FORBIDDEN_VALUE_MARKERS:
        if marker in text:
            issues.append(f"forbidden_secret_marker:{marker}")

    return not issues, issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the operator-readable Origin Edition Gold final verdict.")
    parser.add_argument(
        "--verdict",
        type=Path,
        default=gold_final_verdict_from_env(),
    )
    parser.add_argument(
        "--proof-chain",
        type=Path,
        default=gold_proof_chain_from_env(),
    )
    parser.add_argument(
        "--requirement-coverage",
        type=Path,
        default=gold_requirement_coverage_from_env(),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ok, issues = verify(args.verdict, args.proof_chain, args.requirement_coverage)
    if not ok:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("origin edition gold final verdict verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
