#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Black Ledger command map tick replay endpoints and replay-safe deltas.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    parser.add_argument("--world", default="emerald-sprawl-prelude")
    parser.add_argument("--from-turn", type=int, default=0)
    parser.add_argument("--to-turn", type=int, default=1)
    return parser.parse_args()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run(base_url: str, world: str, from_turn: int, to_turn: int) -> int:
    failures: list[str] = []

    map_response = requests.get(f"{base_url}/api/v1/ledger/worlds/{world}/map/turns/{to_turn}", timeout=30)
    map_response.raise_for_status()
    delta_response = requests.get(
        f"{base_url}/api/v1/ledger/worlds/{world}/map/tick-delta/{from_turn}/{to_turn}",
        timeout=30,
    )
    delta_response.raise_for_status()

    map_payload = map_response.json()
    delta_payload = delta_response.json()

    require(map_payload.get("worldId") == world, "map worldId did not match requested world", failures)
    require(map_payload.get("currentTurn") == to_turn, "map currentTurn did not match requested turn", failures)
    require(bool(map_payload.get("regions")), "map regions were empty", failures)
    require(bool(map_payload.get("events")), "map events were empty", failures)
    require(bool(map_payload.get("replaySteps")), "map replaySteps were empty", failures)

    require(delta_payload.get("worldId") == world, "delta worldId did not match requested world", failures)
    require(delta_payload.get("fromTurn") == from_turn, "delta fromTurn did not match requested turn", failures)
    require(delta_payload.get("toTurn") == to_turn, "delta toTurn did not match requested turn", failures)
    require(bool(delta_payload.get("regionDeltas")), "tick delta regionDeltas were empty", failures)
    require(bool(delta_payload.get("dispatchIds")), "tick delta dispatchIds were empty", failures)

    region_ids = {item.get("regionId") for item in delta_payload.get("regionDeltas", []) if item.get("regionId")}
    map_region_ids = {item.get("regionId") for item in map_payload.get("regions", []) if item.get("regionId")}
    require(bool(region_ids & map_region_ids), "tick delta regions did not intersect map regions", failures)

    payload = {
        "contract_name": "chummer.black_ledger_command_map_tick_replay_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "world_id": world,
        "from_turn": from_turn,
        "to_turn": to_turn,
        "region_delta_count": len(delta_payload.get("regionDeltas", [])),
        "dispatch_count": len(delta_payload.get("dispatchIds", [])),
        "event_count": len(map_payload.get("events", [])),
        "replay_step_count": len(map_payload.get("replaySteps", [])),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_COMMAND_MAP_TICK_REPLAY.generated.json"), payload)

    lines = [
        "# Black Ledger Command Map Tick Replay",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- World: `{world}`",
        f"- Turn span: `{from_turn}` -> `{to_turn}`",
        f"- Status: `{payload['status']}`",
        f"- Region deltas: `{payload['region_delta_count']}`",
        f"- Dispatch ids: `{payload['dispatch_count']}`",
        f"- Replay steps: `{payload['replay_step_count']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in failures)
    else:
        lines.extend(["", "Tick replay APIs expose replay-safe map state and delta receipts."])
    write_text(completion_path("BLACK_LEDGER_COMMAND_MAP_TICK_REPLAY.md"), "\n".join(lines))
    return 0 if not failures else 1


def run_source(world: str, from_turn: int, to_turn: int) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    service = (repo_root / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerPublicStatsService.cs").read_text(encoding="utf-8")
    controller = (repo_root / "Chummer.Run.Api" / "Controllers" / "LedgerController.cs").read_text(encoding="utf-8")

    failures: list[str] = []
    require("LoadCommandMapDocument" in service, "service missing LoadCommandMapDocument", failures)
    require("LoadTickDelta" in service, "service missing LoadTickDelta", failures)
    require('[HttpGet("worlds/{worldId}/map/turns/{turn}")]' in controller, "controller missing turn map route", failures)
    require('[HttpGet("worlds/{worldId}/map/tick-delta/{fromTurn:int}/{toTurn:int}")]' in controller, "controller missing tick delta route", failures)

    payload = {
        "contract_name": "chummer.black_ledger_command_map_tick_replay_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": "source-only",
        "world_id": world,
        "from_turn": from_turn,
        "to_turn": to_turn,
        "region_delta_count": None,
        "dispatch_count": None,
        "event_count": None,
        "replay_step_count": None,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_COMMAND_MAP_TICK_REPLAY.generated.json"), payload)
    write_text(
        completion_path("BLACK_LEDGER_COMMAND_MAP_TICK_REPLAY.md"),
        "\n".join(
            [
                "# Black Ledger Command Map Tick Replay",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Base URL: {payload['base_url']}",
                f"- World: `{world}`",
                f"- Turn span: `{from_turn}` -> `{to_turn}`",
                f"- Status: `{payload['status']}`",
            ] + (["", "## Failures", *[f"- {item}" for item in failures]] if failures else ["", "Source contracts for replay and delta routes are present."])
        ),
    )
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"), args.world, args.from_turn, args.to_turn)

    try:
        with LocalHubApp() as app:
            return run(app.base_url, args.world, args.from_turn, args.to_turn)
    except Exception:
        return run_source(args.world, args.from_turn, args.to_turn)


if __name__ == "__main__":
    raise SystemExit(main())
