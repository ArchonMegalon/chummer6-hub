#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests import RequestException


DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_RECIPIENT = "the.girscheles@gmail.com"
DEFAULT_FACTIONS = [
    "ashline-circle",
    "barrens-free-wardens",
    "ghostline-network",
    "glass-tower-compact",
    "neon-docks-union",
    "rust-market-syndicate",
]
PORTAL_CONTAINER = "chummer6-hub-chummer-portal-1"
MOCK_CONTAINER = "chummer6-hub-support-progress-mock-1"
OUTPUT_ROOT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one Black Ledger leader digest email per faction.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--recipient", default=DEFAULT_RECIPIENT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def docker_env(container: str) -> dict[str, str]:
    output = subprocess.check_output(
        ["docker", "inspect", container, "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
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
        ["docker", "inspect", MOCK_CONTAINER, "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        text=True,
    ).strip()
    if not output:
        raise RuntimeError("support-progress-mock IP not found")
    return f"http://{output}:8080"


def fetch_json(url: str) -> Any:
    response = requests.get(url, timeout=30, headers={"User-Agent": "Chummer Individual Leader Digest/1.0"})
    response.raise_for_status()
    return response.json()


def build_payloads(base_url: str) -> list[dict[str, Any]]:
    base = base_url.rstrip("/")
    newsreel = fetch_json(f"{base}/ledger/turns/1/newsreel.json")
    payloads: list[dict[str, Any]] = []
    for faction_id in DEFAULT_FACTIONS:
        promo = fetch_json(f"{base}/ledger/factions/{faction_id}/promo.json")
        promo_json_href = promo.get("json_href")
        if not promo_json_href:
            promo_html_href = str(promo["html_href"])
            promo_json_href = promo_html_href if promo_html_href.endswith(".json") else f"{promo_html_href}.json"
        subject = f"[Chummer] {promo['publicName']} leader digest"
        body = "\n".join(
            [
                f"{promo['publicName']} leader digest for validation.",
                "",
                f"Transition: {newsreel['transitionLabel']}",
                f"Headline: {newsreel['inboxHeadline']}",
                f"Faction hook: {promo['campaign_hook']}",
                f"Audience promise: {promo['audience_promise']}",
                "",
                f"World packet: {base}/account/ledger/worldtick/validation",
                f"Leader validation: {base}{promo['validation_href']}",
                f"Promo rail: {base}{promo['html_href']}",
                f"Promo JSON: {base}{promo_json_href}",
                "",
                "Review posture:",
                "- Cross-check the leader brief against the turn packet.",
                "- Keep promo language subordinate to the same public-safe turn truth.",
                "- Do not publish private campaign labels or sourcebook text.",
            ]
        )
        payloads.append(
            {
                "faction_id": faction_id,
                "public_name": promo["publicName"],
                "subject": subject,
                "body": body,
                "transition": newsreel["transitionLabel"],
                "headline": newsreel["inboxHeadline"],
                "leader_validation_href": f"{base}{promo['validation_href']}",
                "promo_href": f"{base}{promo['html_href']}",
                "promo_json_href": f"{base}{promo_json_href}",
                "campaign_hook": promo["campaign_hook"],
                "audience_promise": promo["audience_promise"],
            }
        )
    return payloads


def send_dispatch(recipient: str, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    portal_env = docker_env(PORTAL_CONTAINER)
    dispatch_base_url = support_progress_base_url()
    api_token = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN", "").strip() or "local-support-progress-token"
    principal_id = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID", "").strip() or "support-progress-principal"
    binding_id = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID", "").strip() or "binding-support-progress"
    idempotency_key = f"black-ledger-leader-digest-{payload['faction_id']}-turn1"
    request_payload = {
        "tool_name": "connector.dispatch",
        "action_kind": "delivery.send",
        "payload_json": {
            "principal_id": principal_id,
            "binding_id": binding_id,
            "channel": "email",
            "recipient": recipient,
            "subject": payload["subject"],
            "content": payload["body"],
            "metadata": {
                "purpose": "black_ledger_individual_leader_digest",
                "dry_run": dry_run,
                "faction_id": payload["faction_id"],
                "transition": payload["transition"],
            },
            "idempotency_key": idempotency_key,
        },
    }
    if dry_run:
        return {
            "status": "dry_run",
            "faction_id": payload["faction_id"],
            "payload": request_payload,
            "dispatch_base_url": dispatch_base_url,
            "idempotency_key": idempotency_key,
        }

    response_payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.post(
                f"{dispatch_base_url}/v1/tools/execute",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-ea-principal-id": principal_id,
                    "Idempotency-Key": idempotency_key,
                    "User-Agent": "Chummer Individual Leader Digest/1.0",
                },
                data=json.dumps(request_payload),
                timeout=30,
            )
            response.raise_for_status()
            response_payload = response.json()
            break
        except RequestException as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))

    if response_payload is None:
        raise RuntimeError(f"leader digest dispatch failed without response payload: {last_error}")

    return {
        "status": "queued",
        "faction_id": payload["faction_id"],
        "dispatch_base_url": dispatch_base_url,
        "payload": request_payload,
        "response": response_payload,
        "delivery_id": response_payload.get("target_ref") or response_payload.get("output_json", {}).get("delivery_id"),
        "idempotency_key": idempotency_key,
    }


def write_receipt(recipient: str, payloads: list[dict[str, Any]], deliveries: list[dict[str, Any]], dry_run: bool) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    receipt = {
        "contract_name": "black_ledger_individual_leader_digests",
        "generated_at_utc": now_iso(),
        "status": "pass" if all(item.get("status") in {"queued", "dry_run"} for item in deliveries) else "fail",
        "recipient": recipient,
        "dry_run": dry_run,
        "delivery_count": len(deliveries),
        "deliveries": deliveries,
        "content": [
            {
                "faction_id": payload["faction_id"],
                "public_name": payload["public_name"],
                "subject": payload["subject"],
                "leader_validation_href": payload["leader_validation_href"],
                "promo_href": payload["promo_href"],
            }
            for payload in payloads
        ],
    }
    (OUTPUT_ROOT / "BLACK_LEDGER_INDIVIDUAL_LEADER_DIGESTS.generated.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    payloads = build_payloads(args.base_url)
    deliveries = []
    for payload in payloads:
        deliveries.append(send_dispatch(args.recipient, payload, dry_run=args.dry_run))
        if not args.dry_run:
            time.sleep(0.5)
    write_receipt(args.recipient, payloads, deliveries, args.dry_run)
    print(json.dumps({"status": "ok", "recipient": args.recipient, "delivery_count": len(deliveries)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
