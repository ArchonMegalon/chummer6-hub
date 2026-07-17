#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from black_ledger_sendr_policy import load_json, validate_suppression_sync, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Sendr engagement suppression sync is fail-closed.")
    parser.add_argument("--batch", required=True, help="Engagement batch receipt JSON path.")
    parser.add_argument("--output", default="", help="Optional validation receipt output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    batch = load_json(Path(args.batch))
    validation = validate_suppression_sync(batch)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = Path.cwd() / output
        write_json(output, validation)
    print(json.dumps(validation, indent=2, sort_keys=True))
    return 0 if validation["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
