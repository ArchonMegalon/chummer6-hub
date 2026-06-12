#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
CORE_ENGINE_ROOT = Path(os.environ.get("CHUMMER_CORE_ENGINE_ROOT", "/docker/chummercomplete/chummer-core-engine"))
OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
DEFAULT_MIN_RULEFACTS = int(os.environ.get("CHUMMER_RULE_AUTHORITY_MIN_RULEFACTS", "100"))
FULL_COMPLETION_PATH = CORE_ENGINE_ROOT / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"
OPERATOR_GOLD_PATH = CORE_ENGINE_ROOT / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"

READY_VERDICTS = {
    "sr4": "SR4_RULE_AUTHORITY_READY",
    "sr5": "SR5_RULE_AUTHORITY_READY",
    "sr6": "SR6_RULE_AUTHORITY_READY",
}

def registry_paths() -> dict[str, Path]:
    return {
        "sr4": CORE_ENGINE_ROOT / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json",
        "sr5": CORE_ENGINE_ROOT / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json",
        "sr6": CORE_ENGINE_ROOT / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json",
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed when committed public ruleset registries are below minimum coverage.")
    parser.add_argument("--min-rulefacts", type=int, default=DEFAULT_MIN_RULEFACTS)
    args = parser.parse_args()

    completion_payload = load_json(FULL_COMPLETION_PATH)
    operator_gold_payload = load_json(OPERATOR_GOLD_PATH)
    completion_rulesets = completion_payload.get("rulesets") if isinstance(completion_payload.get("rulesets"), dict) else {}
    completion_blockers = {
        item.get("ruleset"): item
        for item in completion_payload.get("blockers", [])
        if isinstance(item, dict) and item.get("ruleset")
    }
    operator_rulesets = {
        item.get("ruleset"): item
        for item in operator_gold_payload.get("rulesets", [])
        if isinstance(item, dict) and item.get("ruleset")
    }

    rulesets: dict[str, Any] = {}
    failures: list[str] = []
    for ruleset, path in registry_paths().items():
        payload = load_json(path)
        count = int(payload.get("rulefact_count") or 0)
        verdict = str(payload.get("final_verdict") or "")
        expected_verdict = READY_VERDICTS[ruleset]
        completion_entry = completion_rulesets.get(ruleset, {}) if isinstance(completion_rulesets, dict) else {}
        blocker_entry = completion_blockers.get(ruleset, {}) if isinstance(completion_blockers, dict) else {}
        operator_entry = operator_rulesets.get(ruleset, {}) if isinstance(operator_rulesets, dict) else {}
        matrix_path = Path(str(blocker_entry.get("blocker_receipts", {}).get("verification_matrix_run", "")))
        matrix_payload = load_json(matrix_path) if matrix_path.is_file() else {}
        ready_by_verdict = verdict == expected_verdict
        ready_by_completion = bool(completion_entry.get("rule_authority_ready"))
        ready_by_operator = operator_entry.get("status") == "pass" and operator_entry.get("verdict") == expected_verdict
        matrix_has_unexpected_failures = bool(matrix_payload.get("unexpected_failed_gates"))
        status = (
            "pass"
            if count >= args.min_rulefacts
            and ready_by_verdict
            and ready_by_completion
            and ready_by_operator
            and not matrix_has_unexpected_failures
            else "fail"
        )
        if count < args.min_rulefacts:
            failures.append(f"{ruleset} rulefact_count {count} is below minimum {args.min_rulefacts}")
        if not ready_by_verdict:
            failures.append(f"{ruleset} final_verdict is not ready")
        if not ready_by_completion:
            failures.append(f"{ruleset} full product rule authority completion is not ready")
        if not ready_by_operator:
            failures.append(f"{ruleset} operator promoted rule authority gold is not ready")
        if matrix_has_unexpected_failures:
            failures.append(f"{ruleset} verification matrix has unexpected failed gates")
        rulesets[ruleset] = {
            "path": str(path),
            "rulefact_count": count,
            "final_verdict": verdict,
            "expected_ready_verdict": expected_verdict,
            "full_completion_rule_authority_ready": ready_by_completion,
            "operator_gold_status": operator_entry.get("status"),
            "operator_gold_verdict": operator_entry.get("verdict"),
            "blocker_receipts": blocker_entry.get("blocker_receipts", {}),
            "row_level_mapping_status": blocker_entry.get("row_level_mapping_status"),
            "errata_posture_status": blocker_entry.get("errata_posture_status"),
            "human_review_status": blocker_entry.get("human_review_status"),
            "verification_matrix_status": matrix_payload.get("status"),
            "verification_matrix_failed_gates": matrix_payload.get("failed_gates", []),
            "verification_matrix_unexpected_failed_gates": matrix_payload.get("unexpected_failed_gates", []),
            "verification_matrix_expected_ready_blockers": matrix_payload.get("expected_ready_blockers", []),
            "remaining_gates": blocker_entry.get("remaining_gates", []),
            "status": status,
        }

    result = {
        "contract_name": "chummer.rule_authority_minimum_coverage",
        "generated_at_utc": completion_payload.get("generated_at_utc") or operator_gold_payload.get("generated_at_utc") or "",
        "minimum_rulefacts_required": args.min_rulefacts,
        "full_completion_path": str(FULL_COMPLETION_PATH),
        "operator_gold_path": str(OPERATOR_GOLD_PATH),
        "status": "pass" if not failures else "fail",
        "rulesets": rulesets,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if failures:
        print(json.dumps({
            "status": "fail",
            "failures": failures,
            "output_path": str(OUTPUT_PATH),
            "rulesets": {
                ruleset: {
                    "rulefact_count": payload["rulefact_count"],
                    "final_verdict": payload["final_verdict"],
                    "full_completion_rule_authority_ready": payload["full_completion_rule_authority_ready"],
                    "operator_gold_status": payload["operator_gold_status"],
                    "operator_gold_verdict": payload["operator_gold_verdict"],
                    "remaining_gates": payload["remaining_gates"],
                    "verification_matrix_status": payload["verification_matrix_status"],
                    "verification_matrix_unexpected_failed_gates": payload["verification_matrix_unexpected_failed_gates"],
                }
                for ruleset, payload in rulesets.items()
                if payload["status"] != "pass"
            },
        }, indent=2), file=sys.stderr)
        raise SystemExit("rules authority minimum coverage failed")
    print("rule_authority_minimum_coverage:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
