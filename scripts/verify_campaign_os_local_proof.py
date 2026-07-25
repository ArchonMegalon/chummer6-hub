#!/usr/bin/env python3
"""Strict consumer-side validator for Campaign OS local proof v3."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


CONTRACT_MODULE_PATH = Path(__file__).resolve().with_name(
    "campaign_os_local_proof_v3.py"
)
CONTRACT_MODULE_SPEC = importlib.util.spec_from_file_location(
    "campaign_os_local_proof_v3",
    CONTRACT_MODULE_PATH,
)
if CONTRACT_MODULE_SPEC is None or CONTRACT_MODULE_SPEC.loader is None:
    raise RuntimeError("unable to load Campaign OS local proof v3 contract module")
CONTRACT_MODULE = importlib.util.module_from_spec(CONTRACT_MODULE_SPEC)
sys.modules[CONTRACT_MODULE_SPEC.name] = CONTRACT_MODULE
CONTRACT_MODULE_SPEC.loader.exec_module(CONTRACT_MODULE)

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT = Path(
    ".codex-studio/published/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json"
)


def _environment_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return -1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a current executed Campaign OS local proof v3 receipt."
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--proof", type=Path, default=None)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=_environment_int(
            "CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_MAX_AGE_SECONDS",
            CONTRACT_MODULE.DEFAULT_MAX_AGE_SECONDS,
        ),
    )
    parser.add_argument(
        "--future-skew-seconds",
        type=int,
        default=_environment_int(
            "CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_FUTURE_SKEW_SECONDS",
            CONTRACT_MODULE.DEFAULT_FUTURE_SKEW_SECONDS,
        ),
    )
    parser.add_argument("--expected-run-id", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configured_root = os.environ.get("CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_ROOT")
    root = (args.root or (Path(configured_root) if configured_root else DEFAULT_ROOT)).resolve()
    configured_proof = os.environ.get("CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_OUT")
    proof = args.proof or (
        Path(configured_proof) if configured_proof else root / DEFAULT_RECEIPT
    )
    try:
        result = CONTRACT_MODULE.validate_passed_receipt(
            root,
            proof,
            max_age_seconds=args.max_age_seconds,
            future_skew_seconds=args.future_skew_seconds,
            expected_run_id=args.expected_run_id,
        )
    except OSError:
        print("campaign_os_local_proof_v3:invalid:filesystem_error", file=sys.stderr)
        return 1
    if not result.valid:
        print(
            f"campaign_os_local_proof_v3:invalid:{result.reason_code}",
            file=sys.stderr,
        )
        return 1
    print("campaign_os_local_proof_v3:valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
