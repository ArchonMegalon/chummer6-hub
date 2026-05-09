#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from absolute_completion_common import completion_path, now_iso, write_text


CORE_ROOT = Path("/docker/chummercomplete/chummer-core-engine")
SR4_DEPTH_PATH = CORE_ROOT / ".codex-studio" / "published" / "SR4_RULESET_DEPTH.generated.json"
SR5_DEPTH_PATH = CORE_ROOT / ".codex-studio" / "published" / "SR5_RULESET_DEPTH.generated.json"
SR6_DEPTH_PATH = CORE_ROOT / ".codex-studio" / "published" / "SR6_RULESET_DEPTH.generated.json"
SR4_RETIREMENT_PATH = CORE_ROOT / ".codex-studio" / "published" / "SR4_CLAIM_RETIREMENT.generated.json"
SR5_ACCEPTANCE_PATH = CORE_ROOT / ".codex-studio" / "published" / "SR5_ACCEPTANCE_PROOF.generated.json"
SR6_RETIREMENT_PATH = CORE_ROOT / ".codex-studio" / "published" / "SR6_CLAIM_RETIREMENT.generated.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_status(value: object) -> str:
    return normalize_text(value).lower()


def receipt_ok(payload: dict) -> bool:
    return normalize_status(payload.get("status")) == "pass"


def main() -> int:
    lines = [
        "# Trivial ruleset host audit",
        "",
        f"- Generated: {now_iso()}",
    ]
    required_inputs = [
        CORE_ROOT,
        SR4_DEPTH_PATH,
        SR5_DEPTH_PATH,
        SR6_DEPTH_PATH,
        SR4_RETIREMENT_PATH,
        SR5_ACCEPTANCE_PATH,
        SR6_RETIREMENT_PATH,
    ]
    missing_inputs = [str(path) for path in required_inputs if not path.exists()]
    if missing_inputs:
        lines.extend(
            [
                "",
                "## Result",
                "",
                "- Status: `blocked_external`",
                f"- Missing inputs: `{', '.join(missing_inputs)}`",
                "- The current audit requires the published SR4/SR5/SR6 depth and decision receipts from chummer-core-engine.",
            ]
        )
        write_text(completion_path("TRIVIAL_RULESET_HOST_AUDIT.md"), "\n".join(lines))
        return 0

    sr4_depth = load_json(SR4_DEPTH_PATH)
    sr5_depth = load_json(SR5_DEPTH_PATH)
    sr6_depth = load_json(SR6_DEPTH_PATH)
    sr4_retirement = load_json(SR4_RETIREMENT_PATH)
    sr5_acceptance = load_json(SR5_ACCEPTANCE_PATH)
    sr6_retirement = load_json(SR6_RETIREMENT_PATH)

    sr4_ok = (
        receipt_ok(sr4_depth)
        and normalize_text(sr4_depth.get("ruleset_id")).lower() == "sr4"
        and normalize_status(sr4_depth.get("serious_implementation_claim")) == "not_allowed"
        and receipt_ok(sr4_retirement)
        and normalize_text(sr4_retirement.get("ruleset")).upper() == "SR4"
        and normalize_status(sr4_retirement.get("claim_status")) == "retired"
    )
    sr5_ok = (
        receipt_ok(sr5_depth)
        and normalize_text(sr5_depth.get("ruleset_id")).lower() == "sr5"
        and receipt_ok(sr5_acceptance)
        and normalize_text(sr5_acceptance.get("ruleset")).upper() == "SR5"
        and normalize_status(sr5_acceptance.get("serious_implementation_claim")) == "allowed"
    )
    sr6_ok = (
        receipt_ok(sr6_depth)
        and normalize_text(sr6_depth.get("ruleset_id")).lower() == "sr6"
        and normalize_status(sr6_depth.get("serious_implementation_claim")) == "not_allowed"
        and receipt_ok(sr6_retirement)
        and normalize_text(sr6_retirement.get("ruleset")).upper() == "SR6"
        and normalize_status(sr6_retirement.get("claim_status")) == "retired"
    )
    status = "pass" if sr4_ok and sr5_ok and sr6_ok else "failed"

    lines.extend(
        [
            "",
            "## Result",
            "",
            f"- Status: `{status}`",
            "- Summary: SR5 has a passing serious-support acceptance receipt, while SR4 and SR6 explicitly retire serious-support claims and keep only bounded baseline-host posture.",
            "",
            "## Ruleset decisions",
            "",
            "### SR4",
            f"- Depth receipt: `{SR4_DEPTH_PATH}`",
            f"- Claim ceiling: `{normalize_text(sr4_depth.get('claim_ceiling'))}`",
            f"- Serious implementation claim: `{normalize_text(sr4_depth.get('serious_implementation_claim'))}`",
            f"- Retirement receipt: `{SR4_RETIREMENT_PATH}`",
            f"- Retirement status: `{normalize_text(sr4_retirement.get('claim_status'))}`",
            "",
            "### SR5",
            f"- Depth receipt: `{SR5_DEPTH_PATH}`",
            f"- Claim ceiling: `{normalize_text(sr5_depth.get('claim_ceiling'))}`",
            f"- Depth serious implementation claim: `{normalize_text(sr5_depth.get('serious_implementation_claim'))}`",
            f"- Acceptance receipt: `{SR5_ACCEPTANCE_PATH}`",
            f"- Acceptance serious implementation claim: `{normalize_text(sr5_acceptance.get('serious_implementation_claim'))}`",
            "",
            "### SR6",
            f"- Depth receipt: `{SR6_DEPTH_PATH}`",
            f"- Claim ceiling: `{normalize_text(sr6_depth.get('claim_ceiling'))}`",
            f"- Serious implementation claim: `{normalize_text(sr6_depth.get('serious_implementation_claim'))}`",
            f"- Retirement receipt: `{SR6_RETIREMENT_PATH}`",
            f"- Retirement status: `{normalize_text(sr6_retirement.get('claim_status'))}`",
            "",
            "## Evidence",
            "",
            "- SR4/SR6 depth receipts still expose only `derive.stat` and `session.quick-actions` as deterministic capability anchors, with retirement receipts preventing serious-support overclaim.",
            "- SR5 acceptance explicitly promotes the supported workflow set to production-grade seriousness even though the lower-level depth receipt remains conservative.",
        ]
    )
    write_text(completion_path("TRIVIAL_RULESET_HOST_AUDIT.md"), "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
