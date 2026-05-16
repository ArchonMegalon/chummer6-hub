#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", default="emerald-sprawl-prelude")
    parser.add_argument("--turn", type=int, default=1)
    parser.add_argument("--base-url", default="")
    return parser.parse_args()


def run(base_url: str, world: str, turn: int) -> int:
    failures: list[str] = []
    map_response = requests.get(f"{base_url}/api/v1/ledger/worlds/{world}/map", timeout=30)
    turn_response = requests.get(f"{base_url}/api/v1/ledger/worlds/{world}/turns/{turn}", timeout=30)
    dispatch_response = requests.get(f"{base_url}/api/v1/ledger/worlds/{world}/dispatches?turn={turn}", timeout=30)

    if map_response.status_code != 200:
        failures.append("map route failed")
    if turn_response.status_code != 200:
        failures.append("turn route failed")
    if dispatch_response.status_code != 200:
        failures.append("dispatch route failed")

    if not failures:
        map_payload = map_response.json()
        turn_payload = turn_response.json()
        dispatch_payload = dispatch_response.json()
        if map_payload.get("worldId") != world:
            failures.append("map worldId mismatch")
        if turn_payload.get("turn") != turn:
            failures.append("turn payload mismatch")
        if not dispatch_payload:
            failures.append("dispatch payload empty")

    payload = {
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "base_url": base_url,
        "world": world,
        "turn": turn,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("..", "black_ledger_public_seed", "BLACK_LEDGER_PUBLIC_SEED_TICK_REPLAY.generated.json"), payload)
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"), args.world, args.turn)
    with LocalHubApp() as app:
        return run(app.base_url.rstrip("/"), args.world, args.turn)


if __name__ == "__main__":
    raise SystemExit(main())
