#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from black_ledger_sendr_policy import load_json, validate_packet, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a Black Ledger Sendr campaign packet is fail-closed and review-gated.")
    parser.add_argument("--packet", required=True, help="Campaign packet JSON path.")
    parser.add_argument("--output", default="", help="Optional validation receipt output path.")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless sources and recipient records make the packet ready for setup review.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet_path = Path(args.packet)
    packet = load_json(packet_path)
    validation = validate_packet(packet)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = Path.cwd() / output
        write_json(output, validation)
    print(json.dumps(validation, indent=2, sort_keys=True))
    if validation["status"] != "pass":
        return 1
    if args.require_ready and not validation["ready_for_sendr_setup"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
