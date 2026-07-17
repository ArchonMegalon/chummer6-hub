#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from black_ledger_sendr_policy import build_engagement_batch, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a review-gated Sendr engagement batch receipt.")
    parser.add_argument("--campaign-id", required=True, help="Sendr campaign id or stable local campaign id.")
    parser.add_argument("--campaign-type", default="", help="Optional campaign type, for example SPONSOR_OUTREACH.")
    parser.add_argument("--event-batch", required=True, dest="event_batch_id", help="Stable event batch id.")
    parser.add_argument("--events", required=True, help="Sanitized event JSON path; use {'events': [...]} or [...].")
    parser.add_argument("--dry-run", action="store_true", help="Required until webhook ingestion is human-reviewed.")
    parser.add_argument("--output", default="", help="Optional receipt output path.")
    return parser.parse_args()


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "batch"


def load_events(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("events")
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain an events list or an object with an events list")
    return payload


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("materialize_sendr_engagement_batch_receipt requires --dry-run; live webhook ingestion is not implemented")

    events = load_events(Path(args.events))
    receipt = build_engagement_batch(
        campaign_id=args.campaign_id,
        event_batch_id=args.event_batch_id,
        events=events,
        dry_run=args.dry_run,
        campaign_type=args.campaign_type,
    )
    output = Path(args.output) if args.output else Path(".codex-studio/published") / f"black_ledger_sendr_engagement_{safe_slug(args.event_batch_id)}.generated.json"
    if not output.is_absolute():
        output = Path.cwd() / output
    write_json(output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["validation"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
