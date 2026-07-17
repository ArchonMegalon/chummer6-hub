#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from black_ledger_sendr_policy import build_packet, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a fail-closed Black Ledger Sendr campaign packet draft.")
    parser.add_argument("--type", required=True, dest="campaign_type", help="Campaign type such as SPONSOR_OUTREACH.")
    parser.add_argument("--packet", required=True, dest="packet_id", help="Stable campaign packet id.")
    parser.add_argument("--source", action="append", default=[], help="Approved public source file to hash into the packet.")
    parser.add_argument("--source-note", action="append", default=[], help="Approved public source note to hash into the packet.")
    parser.add_argument("--target-audience", default="TTRPG-adjacent sponsor, guest, creator, or community contacts")
    parser.add_argument("--owner", default="black_ledger_editorial")
    parser.add_argument("--max-contacts", type=int, default=None)
    parser.add_argument(
        "--output",
        default=".codex-studio/published/black_ledger_sendr_campaign_packet.generated.json",
        help="Output JSON path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path.cwd()
    packet = build_packet(
        packet_id=args.packet_id,
        campaign_type=args.campaign_type,
        source_paths=list(args.source),
        source_notes=list(args.source_note),
        root=root,
        owner=args.owner,
        target_audience=args.target_audience,
        max_contacts=args.max_contacts,
    )
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    write_json(output, packet)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
