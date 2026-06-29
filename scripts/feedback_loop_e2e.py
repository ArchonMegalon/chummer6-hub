#!/usr/bin/env python3
from __future__ import annotations

import argparse

from absolute_completion_common import RUN_SERVICES_ROOT, completion_path, now_iso, write_json


FEEDBACK_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Partizipate.cshtml"
ACCOUNT_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Accounts" / "Account.cshtml"
DRY_RUN_RECEIPT = completion_path("FEEDBACK_EA_FLEET_DRY_RUN.generated.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the V5 feedback-to-engagement closeout loop receipts and dashboard projection hooks.")
    parser.add_argument("--stub-delivery", action="store_true", help="Require the existing dry-run closeout receipt instead of a live delivery.")
    parser.add_argument("--with-impact-receipt", action="store_true", help="Require the account participation dashboard impact journal hook.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    feedback_view = FEEDBACK_VIEW.read_text(encoding="utf-8")
    account_view = ACCOUNT_VIEW.read_text(encoding="utf-8")

    if 'aria-label="Participate board"' not in feedback_view:
        failures.append("participate view lost first-party board landmark")
    if "data-chummer-participate-frame" not in feedback_view:
        failures.append("participate view lost the same-origin board frame hook")
    if "Board offline right now. Use Contact for the Chummer5 Discord server." not in feedback_view:
        failures.append("participate view lost first-party fallback wording")
    if args.stub_delivery and not DRY_RUN_RECEIPT.is_file():
        failures.append(f"missing dry-run receipt: {DRY_RUN_RECEIPT}")
    if args.with_impact_receipt and "Impact journal" not in account_view:
        failures.append("account participation dashboard missing impact journal")

    payload = {
        "contract_name": "chummer.feedback_loop_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "stub_delivery_required": args.stub_delivery,
        "impact_receipt_required": args.with_impact_receipt,
        "dry_run_receipt_path": str(DRY_RUN_RECEIPT),
        "dashboard_route": "/account/participation",
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("FEEDBACK_LOOP_E2E_RESULTS.generated.json"), payload)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
