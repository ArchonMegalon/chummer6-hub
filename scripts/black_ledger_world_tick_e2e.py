#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests
import yaml

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, WORKSPACE_ROOT, completion_path, now_iso, write_json, write_text


FORBIDDEN_PUBLIC_TERMS = (
    "productlift",
    "emailit",
    "deftform",
    "icanpreneur",
    "chummer_",
    "support_case",
    "private_campaign",
    "account_email",
    "operator_secret",
    "sourcebook_text",
)

ROOT_REQUIRED_PHRASES = (
    "Black Ledger preview",
    "Turn 1 already ran",
    "Open Black Ledger",
)

LEDGER_REQUIRED_PHRASES = (
    "Emerald Sprawl: First Pressure",
    "Last tick receipt",
    "Privacy boundary",
    "fictional, public-safe seed world",
)

TURN_TWO_REQUIRED_PHRASES = (
    "Turn 2 deterministic preview is ready",
    "Mode: deterministic_test",
    "Turn 2 deterministic preview",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the preseeded Black Ledger world loads, renders, and stays public-safe.")
    parser.add_argument("--world", default="emerald-sprawl-prelude", help="Black Ledger seed world id without extension.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def seed_path(world: str) -> Path:
    return WORKSPACE_ROOT / "chummer-hub-registry" / "black-ledger" / "worlds" / f"{world}.yaml"


def load_seed(world: str) -> dict:
    path = seed_path(world)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def scan_forbidden(text: str, failures: list[str], label: str) -> None:
    lowered = text.lower()
    for term in FORBIDDEN_PUBLIC_TERMS:
        if term in lowered:
            failures.append(f"{label} contains forbidden term: {term}")


def scan_forbidden_values(node: Any, failures: list[str], label: str) -> None:
    if isinstance(node, dict):
        for value in node.values():
            scan_forbidden_values(value, failures, label)
        return
    if isinstance(node, list):
        for value in node:
            scan_forbidden_values(value, failures, label)
        return
    if isinstance(node, str):
        scan_forbidden(node, failures, label)


def assert_required_phrases(body: str, phrases: tuple[str, ...], failures: list[str], label: str) -> None:
    for phrase in phrases:
        if phrase not in body:
            failures.append(f"{label} missing required phrase: {phrase}")


def run(base_url: str, world: str) -> int:
    failures: list[str] = []
    seed = load_seed(world)
    factions = seed.get("factions", [])
    districts = seed.get("districts") or seed.get("map", {}).get("districts", [])
    ai_personalities = {
        item.get("personality_id") or item.get("id")
        for item in seed.get("ai_personalities", [])
        if item.get("personality_id") or item.get("id")
    }
    turns = seed.get("turns", [])
    turn_zero = next((turn for turn in turns if turn.get("turn") == 0), None)
    turn_one = next((turn for turn in turns if turn.get("turn") == 1), None)

    if len(factions) < 6:
        failures.append(f"expected at least 6 factions, found {len(factions)}")
    if len(districts) < 8:
        failures.append(f"expected at least 8 districts, found {len(districts)}")
    if turn_zero is None:
        failures.append("turn 0 is missing")
    if turn_one is None:
        failures.append("turn 1 is missing")
    elif turn_one.get("receipt_id") != "ledger_tick_0001_preseeded":
        failures.append(f"unexpected turn 1 receipt id: {turn_one.get('receipt_id')}")
    elif not turn_one.get("effects"):
        failures.append("turn 1 effects are missing")

    for faction in factions:
        posts = faction.get("management_posts") or {}
        for post_key in ("faction_leader", "field_gm", "intel_provider"):
            holder = posts.get(post_key)
            if not holder:
                failures.append(f"{faction.get('id', 'unknown faction')} missing {post_key}")
            elif holder not in ai_personalities:
                failures.append(f"{faction.get('id', 'unknown faction')} references unknown AI holder {holder}")

    scan_forbidden_values(seed, failures, "seed values")

    root_response = requests.get(f"{base_url}/", timeout=30)
    root_response.raise_for_status()
    ledger_response = requests.get(f"{base_url}/ledger", timeout=30)
    ledger_response.raise_for_status()
    turn_two_response = requests.get(f"{base_url}/ledger?turn=2", timeout=30)
    turn_two_response.raise_for_status()
    newsreel_response = requests.get(f"{base_url}/ledger/turns/1/newsreel.json", timeout=30)
    newsreel_response.raise_for_status()
    newsreel_payload = newsreel_response.json()

    assert_required_phrases(root_response.text, ROOT_REQUIRED_PHRASES, failures, "/")
    assert_required_phrases(ledger_response.text, LEDGER_REQUIRED_PHRASES, failures, "/ledger")
    assert_required_phrases(turn_two_response.text, TURN_TWO_REQUIRED_PHRASES, failures, "/ledger?turn=2")
    scan_forbidden(root_response.text, failures, "/")
    scan_forbidden(ledger_response.text, failures, "/ledger")
    scan_forbidden(turn_two_response.text, failures, "/ledger?turn=2")
    scan_forbidden_values(newsreel_payload, failures, "/ledger/turns/1/newsreel.json")

    if newsreel_payload.get("fromTurn") != 0:
        failures.append(f"unexpected fromTurn in newsreel payload: {newsreel_payload.get('fromTurn')}")
    if newsreel_payload.get("toTurn") != 1:
        failures.append(f"unexpected toTurn in newsreel payload: {newsreel_payload.get('toTurn')}")
    if newsreel_payload.get("transitionLabel") != "Turn 0 -> Turn 1":
        failures.append(f"unexpected transitionLabel: {newsreel_payload.get('transitionLabel')}")
    if "Turn 0" not in str(newsreel_payload.get("transitionNarrative", "")):
        failures.append("newsreel transitionNarrative is missing Turn 0 framing")
    if not newsreel_payload.get("newsreelBullets"):
        failures.append("newsreelBullets are missing")

    payload = {
        "contract_name": "chummer.black_ledger_preseeded_world_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "world_id": seed.get("world_id", world),
        "base_url": base_url,
        "seed_path": str(seed_path(world)),
        "faction_count": len(factions),
        "district_count": len(districts),
        "turn_0_present": turn_zero is not None,
        "turn_1_receipt_id": None if turn_one is None else turn_one.get("receipt_id"),
        "turn_2_preview_checked": True,
        "newsreel_transition_checked": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_PRESEEDED_WORLD_E2E.generated.json"), payload)
    lines = [
        "# Black Ledger preseeded world E2E",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- World: `{payload['world_id']}`",
        f"- Base URL: {payload['base_url']}",
        f"- Factions: `{payload['faction_count']}`",
        f"- Districts: `{payload['district_count']}`",
        f"- Turn 1 receipt: `{payload['turn_1_receipt_id']}`",
        f"- Status: `{payload['status']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "The preseeded Black Ledger world loads, renders, and stays public-safe."])
    write_text(completion_path("BLACK_LEDGER_PRESEEDED_WORLD_E2E.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"), args.world)
    with LocalHubApp() as app:
        return run(app.base_url, args.world)


if __name__ == "__main__":
    raise SystemExit(main())
