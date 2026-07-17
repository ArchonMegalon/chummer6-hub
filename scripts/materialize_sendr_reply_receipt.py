#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from black_ledger_sendr_policy import build_engagement_batch, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a sanitized Sendr reply review receipt.")
    parser.add_argument("--campaign-id", required=True, help="Sendr campaign id or stable local campaign id.")
    parser.add_argument("--campaign-type", default="", help="Optional campaign type, for example SPONSOR_OUTREACH.")
    parser.add_argument("--event-batch", required=True, dest="event_batch_id", help="Stable reply batch id.")
    parser.add_argument("--contact-hash", required=True, help="Hashed contact id; never pass a raw email address.")
    parser.add_argument("--occurred-at", required=True, help="Reply timestamp.")
    parser.add_argument("--preview", default="", help="Short sanitized reply preview; raw body storage is forbidden.")
    parser.add_argument("--negative", action="store_true", help="Treat the reply as a negative reply requiring suppression review.")
    parser.add_argument("--dry-run", action="store_true", help="Required until webhook ingestion is human-reviewed.")
    parser.add_argument("--output", default="", help="Optional receipt output path.")
    return parser.parse_args()


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "reply"


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("materialize_sendr_reply_receipt requires --dry-run; live reply ingestion is not implemented")

    receipt = build_engagement_batch(
        campaign_id=args.campaign_id,
        event_batch_id=args.event_batch_id,
        dry_run=args.dry_run,
        campaign_type=args.campaign_type,
        events=[
            {
                "event_type": "negative_reply" if args.negative else "reply_received",
                "contact_hash": args.contact_hash,
                "occurred_at": args.occurred_at,
                "preview": args.preview,
                "human_review_required": True,
                "raw_body_stored": False,
            }
        ],
    )
    output = Path(args.output) if args.output else Path(".codex-studio/published") / f"black_ledger_sendr_reply_{safe_slug(args.event_batch_id)}.generated.json"
    if not output.is_absolute():
        output = Path.cwd() / output
    write_json(output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["validation"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
