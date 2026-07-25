#!/usr/bin/env python3
"""Authoritatively prepare, execute, and receipt RunServicesSmoke."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().with_name("campaign_os_local_proof_v3.py")
MODULE_SPEC = importlib.util.spec_from_file_location("campaign_os_local_proof_v3", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("unable to load Campaign OS proof contract")
CONTRACT = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = CONTRACT
MODULE_SPEC.loader.exec_module(CONTRACT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the materializer-owned Campaign OS smoke proof lane."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "run",
        help="write running, prepare the fixed closure, execute it, and verify checkpoints",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return 2
    root = Path(__file__).resolve().parents[1]
    receipt = root / CONTRACT.DEFAULT_RECEIPT_PATH
    try:
        payload = CONTRACT.run_owned_smoke(root, receipt)
    except CONTRACT.ProofContractError as exc:
        print(
            f"campaign_os_local_proof_v3:running:{exc.reason_code}",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError):
        print("campaign_os_local_proof_v3:running:execution_error", file=sys.stderr)
        return 1
    print(f"campaign_os_local_proof_v3:passed:{payload['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
