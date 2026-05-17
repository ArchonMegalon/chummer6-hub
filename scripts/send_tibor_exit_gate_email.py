#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


WORLD_ID = "emerald-sprawl-prelude"
DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_RECIPIENT = "tibor.girschele@gmail.com"
OUTPUT_ROOT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect")
PORTAL_CONTAINER = "chummer6-hub-chummer-portal-1"
MOCK_CONTAINER = "chummer6-hub-support-progress-mock-1"
CONNECTOR_TOOL = "connector.dispatch"
DELIVERY_ACTION = "delivery.send"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send the Tibor Black Ledger exit-gate email.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--recipient", default=DEFAULT_RECIPIENT)
    parser.add_argument("--world", default=WORLD_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def docker_env(container: str) -> dict[str, str]:
    output = subprocess.check_output(
        [
            "docker",
            "inspect",
            container,
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
        ],
        text=True,
    )
    env: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def support_progress_base_url() -> str:
    output = subprocess.check_output(
        [
            "docker",
            "inspect",
            MOCK_CONTAINER,
            "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
        ],
        text=True,
    ).strip()
    if not output:
        raise RuntimeError("support-progress-mock IP not found")
    return f"http://{output}:8080"


def fetch_json(url: str) -> Any:
    response = requests.get(url, timeout=30, headers={"User-Agent": "Chummer Exit Gate/1.0"})
    response.raise_for_status()
    return response.json()


def build_email_body(base_url: str, world: str) -> tuple[str, dict[str, Any]]:
    world_payload = fetch_json(f"{base_url.rstrip('/')}/api/v1/ledger/worlds/{world}")
    delta_payload = fetch_json(f"{base_url.rstrip('/')}/api/v1/ledger/worlds/{world}/map/tick-delta/0/1")
    factions = fetch_json(f"{base_url.rstrip('/')}/api/v1/ledger/factions")

    faction_lines: list[str] = []
    faction_payloads: list[dict[str, str]] = []
    for faction in factions:
        href = f"{base_url.rstrip('/')}/ledger/factions/{faction['href'].rstrip('/').split('/')[-1]}/promo"
        faction_payloads.append(
            {
                "faction_id": faction["factionId"],
                "public_name": faction["publicName"],
                "summary": faction["summary"],
                "promo_href": href,
            }
        )
        faction_lines.append(f"- {faction['publicName']}: {faction['summary']} — {href}")

    subject = "[Chummer] Black Ledger Turn 1 newsreel + faction promo rail"
    body = "\n".join(
        [
            "Black Ledger exit gate for Tibor.",
            "",
            f"World: {world_payload['publicName']}",
            f"Turn headline: {world_payload['turnHeadline']}",
            f"Newsreel summary: {delta_payload['summary']}",
            f"Ledger route: {base_url.rstrip('/')}/ledger",
            f"Turn 1 page: {base_url.rstrip('/')}/ledger/turns/1",
            f"Replay route: {base_url.rstrip('/')}/ledger/map?replay=turn-1",
            "",
            "Faction promo/storyboard rail:",
            *faction_lines,
            "",
            "Public safety posture:",
            "- Fictional public-safe seed only.",
            "- Faction videos are live via first-party storyboard fallback.",
            "- External provider remains unclaimed until verified.",
        ]
    )
    payload = {
        "world": {
            "world_id": world_payload["worldId"],
            "public_name": world_payload["publicName"],
            "turn_headline": world_payload["turnHeadline"],
            "summary": delta_payload["summary"],
        },
        "routes": {
            "ledger": f"{base_url.rstrip('/')}/ledger",
            "turn_1": f"{base_url.rstrip('/')}/ledger/turns/1",
            "replay": f"{base_url.rstrip('/')}/ledger/map?replay=turn-1",
        },
        "factions": faction_payloads,
        "subject": subject,
        "body": body,
    }
    return body, payload


def send_dispatch(recipient: str, body: str, metadata: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    portal_env = docker_env(PORTAL_CONTAINER)
    base_url = support_progress_base_url()
    api_token = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN", "").strip() or "local-support-progress-token"
    principal_id = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID", "").strip() or "support-progress-principal"
    binding_id = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID", "").strip() or "binding-support-progress"
    idempotency_key = f"tibor-exit-gate-{metadata['world']['world_id']}-turn1"

    request_payload = {
        "tool_name": CONNECTOR_TOOL,
        "action_kind": DELIVERY_ACTION,
        "payload_json": {
            "principal_id": principal_id,
            "binding_id": binding_id,
            "channel": "email",
            "recipient": recipient,
            "subject": metadata["subject"],
            "content": body,
            "metadata": {
                "purpose": "black_ledger_exit_gate",
                "world_id": metadata["world"]["world_id"],
                "turn_headline": metadata["world"]["turn_headline"],
                "recipient": recipient,
                "dry_run": dry_run,
            },
            "idempotency_key": idempotency_key,
        },
    }

    if dry_run:
        return {
            "status": "dry_run",
            "dispatch_base_url": base_url,
            "payload": request_payload,
            "principal_id": principal_id,
            "binding_id": binding_id,
            "idempotency_key": idempotency_key,
        }

    response = requests.post(
        f"{base_url}/v1/tools/execute",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-ea-principal-id": principal_id,
            "Idempotency-Key": idempotency_key,
            "User-Agent": "Chummer Exit Gate/1.0",
        },
        data=json.dumps(request_payload),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "status": "queued",
        "dispatch_base_url": base_url,
        "payload": request_payload,
        "response": payload,
        "principal_id": principal_id,
        "binding_id": binding_id,
        "idempotency_key": idempotency_key,
        "delivery_id": payload.get("target_ref")
        or payload.get("output_json", {}).get("delivery_id"),
    }


def write_receipts(result: dict[str, Any], recipient: str, metadata: dict[str, Any], dry_run: bool) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    status = "pass" if result.get("status") in {"queued", "dry_run"} else "fail"
    receipt = {
        "contract_name": "tibor_black_ledger_exit_gate_email",
        "generated_at_utc": now_iso(),
        "status": status,
        "recipient": recipient,
        "dry_run": dry_run,
        "delivery": result,
        "content": {
            "subject": metadata["subject"],
            "world": metadata["world"],
            "routes": metadata["routes"],
            "faction_count": len(metadata["factions"]),
        },
    }
    (OUTPUT_ROOT / "TIBOR_EXIT_GATE_EMAIL.generated.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Tibor Exit Gate Email",
        "",
        f"- Generated: `{receipt['generated_at_utc']}`",
        f"- Recipient: `{recipient}`",
        f"- Dry run: `{dry_run}`",
        f"- Status: `{status}`",
        f"- Dispatch status: `{result.get('status')}`",
        f"- Delivery id: `{result.get('delivery_id', 'n/a')}`",
        f"- Turn: `{metadata['world']['turn_headline']}`",
        f"- Ledger: `{metadata['routes']['ledger']}`",
        f"- Turn 1: `{metadata['routes']['turn_1']}`",
        f"- Replay: `{metadata['routes']['replay']}`",
        f"- Faction promo links: `{len(metadata['factions'])}`",
    ]
    (OUTPUT_ROOT / "TIBOR_EXIT_GATE_EMAIL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    body, metadata = build_email_body(args.base_url, args.world)
    result = send_dispatch(args.recipient, body, metadata, dry_run=args.dry_run)
    write_receipts(result, args.recipient, metadata, args.dry_run)
    print(json.dumps({"status": result.get("status"), "recipient": args.recipient, "delivery_id": result.get("delivery_id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
