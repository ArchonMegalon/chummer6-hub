#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from absolute_completion_common import now_iso, read_json, write_json


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
PRESENTATION_PUBLISHED = WORKSPACE_ROOT / "chummer-presentation" / ".codex-studio" / "published"
CORE_PUBLISHED = WORKSPACE_ROOT / "chummer-core-engine" / ".codex-studio" / "published"
FLEET_PUBLISHED = WORKSPACE_ROOT.parent / "fleet" / ".codex-studio" / "published"
DEFAULT_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "RULESET_READINESS.generated.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify SR4/SR5/SR6 readiness from current published receipts.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Optional JSON output path for the readiness packet",
    )
    return parser.parse_args()


def receipt_status(path: Path) -> str:
    if not path.is_file():
        return "missing"
    payload = read_json(path)
    value = str(payload.get("status") or "").strip().lower()
    return "pass" if value in {"pass", "passed", "ready"} else "fail"


def dimension(primary: str, secondary: str = "pass") -> str:
    if primary != "pass":
        return "missing"
    return "verified" if secondary == "pass" else "baseline"


def rule_authority_human_approval() -> dict[str, object]:
    review_path = CORE_PUBLISHED / "CODEX_OPERATOR_RULE_AUTHORITY_REVIEW.generated.json"
    approval_path = CORE_PUBLISHED / "HUMAN_SIDE_RULE_AUTHORITY_GOLD_APPROVAL.generated.json"
    completion_path = CORE_PUBLISHED / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"

    if not review_path.is_file() or not approval_path.is_file() or not completion_path.is_file():
        return {
            "approved": False,
            "status": "missing",
            "reason": "core rule-authority human approval, operator review, or completion receipt is missing",
            "rulesets": [],
        }

    review = read_json(review_path)
    approval = read_json(approval_path)
    completion = read_json(completion_path)
    decision = review.get("readiness_decision") if isinstance(review.get("readiness_decision"), dict) else {}
    approved_rulesets = {
        str(item or "").strip().lower()
        for item in approval.get("rulesets", [])
        if str(item or "").strip()
    }

    approved = (
        str(approval.get("status") or "").strip().lower() in {"pass", "passed", "ready"}
        and str(completion.get("status") or "").strip().lower() in {"pass", "passed", "ready"}
        and bool(completion.get("readiness_token_allowed"))
        and bool(decision.get("full_product_rule_authority_ready"))
    )

    return {
        "approved": approved,
        "status": "pass" if approved else "fail",
        "reason": str(decision.get("reason") or "").strip(),
        "rulesets": sorted(approved_rulesets),
        "review_receipt": str(review_path),
        "approval_receipt": str(approval_path),
        "completion_receipt": str(completion_path),
    }


def rule_status(rule_authority: dict[str, object], ruleset: str) -> str:
    rulesets = rule_authority.get("rulesets")
    if bool(rule_authority.get("approved")) and isinstance(rulesets, list) and ruleset in rulesets:
        return "pass"
    return "fail"


def classify() -> dict[str, object]:
    sr4 = receipt_status(PRESENTATION_PUBLISHED / "SR4_DESKTOP_WORKFLOW_PARITY.generated.json")
    sr6 = receipt_status(PRESENTATION_PUBLISHED / "SR6_DESKTOP_WORKFLOW_PARITY.generated.json")
    ui_frontier = receipt_status(PRESENTATION_PUBLISHED / "SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json")
    aggregate_frontier = receipt_status(FLEET_PUBLISHED / "NEXT90_M136_FLEET_AGGREGATE_READINESS_PARITY_GATES.generated.json")
    frontier = "pass" if ui_frontier == "pass" or aggregate_frontier == "pass" else "fail"
    sr5 = receipt_status(PRESENTATION_PUBLISHED / "UI_FLAGSHIP_RELEASE_GATE.generated.json")
    fleet_closeout = receipt_status(FLEET_PUBLISHED / "NEXT90_M136_FLEET_SR4_SR6_READINESS_CLOSEOUT.generated.json")
    authority = rule_authority_human_approval()
    sr4_authority = rule_status(authority, "sr4")
    sr6_authority = rule_status(authority, "sr6")

    rulesets = {
        "sr4": {
            "readiness": "full" if (sr4 == "pass" or sr4_authority == "pass") and frontier == "pass" else "baseline",
            "workflow_parity_status": sr4,
            "rule_authority_status": sr4_authority,
            "frontier_status": frontier,
            "human_side_gold_assumption": sr4 != "pass" and sr4_authority == "pass",
            "ui_orientation": dimension(sr4, frontier) if sr4 == "pass" else "human_approved_gap",
            "codec_import_export": "baseline",
            "deterministic_provider_depth": "verified" if sr4 == "pass" or sr4_authority == "pass" else "missing",
            "mechanics_corpus": "verified" if sr4 == "pass" or sr4_authority == "pass" else "missing",
            "explain_receipts": "verified" if sr4 == "pass" or sr4_authority == "pass" else "missing",
            "package_amend_support": "baseline",
            "release_posture": "governed_preview" if fleet_closeout == "pass" else "review_required",
        },
        "sr5": {
            "readiness": "full" if sr5 == "pass" else "baseline",
            "flagship_ui_status": sr5,
            "ui_orientation": "verified" if sr5 == "pass" else "missing",
            "codec_import_export": "baseline",
            "deterministic_provider_depth": "verified" if sr5 == "pass" else "missing",
            "mechanics_corpus": "verified" if sr5 == "pass" else "missing",
            "explain_receipts": "verified" if sr5 == "pass" else "missing",
            "package_amend_support": "baseline",
            "release_posture": "governed_preview" if fleet_closeout == "pass" else "review_required",
        },
        "sr6": {
            "readiness": "full" if (sr6 == "pass" or sr6_authority == "pass") and frontier == "pass" else "baseline",
            "workflow_parity_status": sr6,
            "rule_authority_status": sr6_authority,
            "frontier_status": frontier,
            "human_side_gold_assumption": sr6 != "pass" and sr6_authority == "pass",
            "ui_orientation": dimension(sr6, frontier) if sr6 == "pass" else "human_approved_gap",
            "codec_import_export": "baseline",
            "deterministic_provider_depth": "verified" if sr6 == "pass" or sr6_authority == "pass" else "missing",
            "mechanics_corpus": "verified" if sr6 == "pass" or sr6_authority == "pass" else "missing",
            "explain_receipts": "verified" if sr6 == "pass" or sr6_authority == "pass" else "missing",
            "package_amend_support": "baseline",
            "release_posture": "governed_preview" if fleet_closeout == "pass" else "review_required",
        },
    }
    return {
        "contract_name": "chummer.ruleset_readiness",
        "generated_at_utc": now_iso(),
        "fleet_closeout_status": fleet_closeout,
        "frontier_receipts": {
            "ui_sr4_sr6_desktop_parity_frontier": ui_frontier,
            "fleet_aggregate_readiness_parity_gates": aggregate_frontier,
            "effective_frontier_status": frontier,
        },
        "rule_authority_human_approval": authority,
        "classifier_dimensions": [
            "ui_orientation",
            "codec_import_export",
            "deterministic_provider_depth",
            "mechanics_corpus",
            "explain_receipts",
            "package_amend_support",
            "release_posture",
        ],
        "rulesets": rulesets,
        "status": "pass" if (sr4 == "pass" or sr4_authority == "pass") and sr5 == "pass" and (sr6 == "pass" or sr6_authority == "pass") and frontier == "pass" and fleet_closeout == "pass" else "fail",
    }


def main() -> int:
    args = parse_args()
    payload = classify()
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
