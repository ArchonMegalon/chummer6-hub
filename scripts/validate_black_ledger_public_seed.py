#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from absolute_completion_common import completion_path, now_iso, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("seed_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.seed_path)
    if not path.is_absolute():
        registry_root = Path(
            os.environ.get("CHUMMER_HUB_REGISTRY_ROOT")
            or Path(__file__).resolve().parents[2] / "chummer-hub-registry"
        )
        path = registry_root.joinpath(args.seed_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    failures: list[str] = []

    if payload.get("world_id") != "emerald-sprawl-prelude":
        failures.append("world_id mismatch")
    if payload.get("public_name") != "Emerald Sprawl: First Pressure":
        failures.append("public_name mismatch")
    if payload.get("lore_mode") != "public_seed":
        failures.append("lore_mode mismatch")
    if payload.get("current_turn") != 1:
        failures.append("current_turn mismatch")
    if len(payload.get("factions", [])) != 6:
        failures.append("faction count mismatch")
    if len(payload.get("districts", [])) != 8:
        failures.append("district count mismatch")
    if not any(item.get("turn") == 1 for item in payload.get("turns", [])):
        failures.append("missing turn 1")
    if payload.get("official_ip_names_present") is not False:
        failures.append("official_ip_names_present must be false")
    if payload.get("sourcebook_text_present") is not False:
        failures.append("sourcebook_text_present must be false")

    artifact = {
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "seed_path": str(path),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("..", "black_ledger_public_seed", "BLACK_LEDGER_PUBLIC_SEED_VALIDATION.generated.json"), artifact)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
