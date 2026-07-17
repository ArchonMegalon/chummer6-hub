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

from black_ledger_sendr_policy import build_receipt, load_json, validate_packet, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a Sendr campaign receipt without sending anything.")
    parser.add_argument("--packet", required=True, help="Campaign packet JSON path.")
    parser.add_argument("--dry-run", action="store_true", help="Required until a human-reviewed Sendr setup lane exists.")
    parser.add_argument("--output", default="", help="Optional receipt output path.")
    return parser.parse_args()


def safe_packet_slug(packet_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", packet_id).strip("-") or "packet"


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("materialize_sendr_campaign_receipt requires --dry-run; direct Sendr setup is not implemented")

    packet = load_json(Path(args.packet))
    validation = validate_packet(packet)
    receipt = build_receipt(packet, validation, dry_run=args.dry_run)
    output = Path(args.output) if args.output else Path(".codex-studio/published") / f"black_ledger_sendr_campaign_{safe_packet_slug(str(packet.get('packet_id', 'packet')))}.generated.json"
    if not output.is_absolute():
        output = Path.cwd() / output
    write_json(output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if validation["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
