#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


def sh(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def read_live_store(container: str) -> dict:
    return json.loads(sh("docker", "exec", container, "/bin/sh", "-lc", "cat /app/state/community-store.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal-container", default="chummer6-hub-chummer-portal-1")
    parser.add_argument("--mailshot-proof", default="/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_ADVISORY_MAILSHOTS.generated.json")
    parser.add_argument("--backfill-proof", default="/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_ADVISORY_ALLEGIANCE_BACKFILL.generated.json")
    args = parser.parse_args()

    store = read_live_store(args.portal_container)
    onboarding = store.get("blackLedgerFactionOnboarding") or {}
    allegiances = onboarding.get("Allegiances") or {}
    charters = onboarding.get("Charters") or {}
    receipts = onboarding.get("MembershipReceipts") or []
    mailshot = json.loads(Path(args.mailshot_proof).read_text(encoding="utf-8"))
    backfill = json.loads(Path(args.backfill_proof).read_text(encoding="utf-8"))

    leader = (charters.get("ashline-circle") or {}).get("FounderAccountId")
    gmail_deliveries = [item for item in mailshot.get("deliveries", []) if "gmail.com" in item.get("recipient_email_masked", "")]
    result = {
        "status": "pass",
        "store_allegiances": len(allegiances),
        "store_charters": len(charters),
        "store_receipts": len(receipts),
        "ashline_circle_leader": leader,
        "mailshot_recipient_count": mailshot.get("recipient_count"),
        "mailshot_delivery_count": mailshot.get("delivery_count"),
        "gmail_delivery_count": len(gmail_deliveries),
        "backfill_mode": backfill.get("mode"),
        "backfill_added_allegiances": backfill.get("added_allegiances"),
    }

    failures: list[str] = []
    if len(allegiances) < 1:
        failures.append("missing_live_allegiances")
    if "ashline-circle" not in charters:
        failures.append("missing_ashline_circle_charter")
    if not leader:
        failures.append("missing_ashline_circle_leader")
    if mailshot.get("status") != "pass":
        failures.append("mailshot_proof_not_pass")
    if (mailshot.get("delivery_count") or 0) < 1:
        failures.append("mailshot_delivery_count_zero")
    if len(gmail_deliveries) < 1:
        failures.append("missing_gmail_target_in_mailshot")
    if backfill.get("status") != "pass":
        failures.append("backfill_proof_not_pass")

    if failures:
        result["status"] = "fail"
        result["failures"] = failures

    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
