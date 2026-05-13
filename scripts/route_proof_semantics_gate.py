#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from absolute_completion_common import read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate route-proof semantics for flagship release truth.")
    parser.add_argument("proof", help="Path to CHUMMER_PUBLIC_ROUTE_PROOF.generated.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = read_json(Path(args.proof))
    summary = payload.get("summary") or {}
    errors: list[str] = []

    if not payload.get("strict_positive"):
        errors.append("strict_positive must be true")
    if not payload.get("seed_receipts"):
        errors.append("seed_receipts must be true")
    if int(summary.get("failed_count") or 0) != 0:
        errors.append("route proof contains failed positive routes")
    if int(summary.get("seeded_receipt_count") or 0) <= 0:
        errors.append("seeded_receipt_count must be greater than zero")
    if int(summary.get("negative_path_count") or 0) <= 0:
        errors.append("negative_path_count must be greater than zero")
    if int(summary.get("negative_path_failed_count") or 0) != 0:
        errors.append("all negative-path checks must pass")

    for item in payload.get("negative_paths") or []:
        if item.get("status_code") != 404:
            errors.append(f"negative path {item.get('sample_path')} did not return 404")
        if item.get("positive_proof"):
            errors.append(f"negative path {item.get('sample_path')} counted as positive proof")

    if errors:
        raise SystemExit("route_proof_semantics_gate failed: " + "; ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
