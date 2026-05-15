#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from absolute_completion_common import now_iso, read_json, write_json


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
PRESENTATION_PUBLISHED = WORKSPACE_ROOT / "chummer-presentation" / ".codex-studio" / "published"
FLEET_PUBLISHED = WORKSPACE_ROOT.parent / "fleet" / ".codex-studio" / "published"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify SR4/SR5/SR6 readiness from current published receipts.")
    parser.add_argument(
        "--output",
        default="",
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


def classify() -> dict[str, object]:
    sr4 = receipt_status(PRESENTATION_PUBLISHED / "SR4_DESKTOP_WORKFLOW_PARITY.generated.json")
    sr6 = receipt_status(PRESENTATION_PUBLISHED / "SR6_DESKTOP_WORKFLOW_PARITY.generated.json")
    frontier = receipt_status(PRESENTATION_PUBLISHED / "SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json")
    sr5 = receipt_status(PRESENTATION_PUBLISHED / "UI_FLAGSHIP_RELEASE_GATE.generated.json")
    fleet_closeout = receipt_status(FLEET_PUBLISHED / "NEXT90_M136_FLEET_SR4_SR6_READINESS_CLOSEOUT.generated.json")

    rulesets = {
        "sr4": {
            "readiness": "full" if sr4 == "pass" and frontier == "pass" else "baseline",
            "workflow_parity_status": sr4,
            "frontier_status": frontier,
            "ui_orientation": dimension(sr4, frontier),
            "codec_import_export": "baseline",
            "deterministic_provider_depth": "verified" if sr4 == "pass" else "missing",
            "mechanics_corpus": "verified" if sr4 == "pass" else "missing",
            "explain_receipts": "verified" if sr4 == "pass" else "missing",
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
            "readiness": "full" if sr6 == "pass" and frontier == "pass" else "baseline",
            "workflow_parity_status": sr6,
            "frontier_status": frontier,
            "ui_orientation": dimension(sr6, frontier),
            "codec_import_export": "baseline",
            "deterministic_provider_depth": "verified" if sr6 == "pass" else "missing",
            "mechanics_corpus": "verified" if sr6 == "pass" else "missing",
            "explain_receipts": "verified" if sr6 == "pass" else "missing",
            "package_amend_support": "baseline",
            "release_posture": "governed_preview" if fleet_closeout == "pass" else "review_required",
        },
    }
    return {
        "contract_name": "chummer.ruleset_readiness",
        "generated_at_utc": now_iso(),
        "fleet_closeout_status": fleet_closeout,
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
        "status": "pass" if sr4 == "pass" and sr5 == "pass" and sr6 == "pass" and fleet_closeout == "pass" else "fail",
    }


def main() -> int:
    args = parse_args()
    payload = classify()
    if args.output:
        write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
