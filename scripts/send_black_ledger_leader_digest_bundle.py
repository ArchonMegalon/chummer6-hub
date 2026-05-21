#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


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
FACTION_MEDIA_ROOT = Path("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/ledger/factions")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Black Ledger leader digest bundle email.")
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
    response = requests.get(url, timeout=30, headers={"User-Agent": "Chummer Leader Digest/1.0"})
    response.raise_for_status()
    return response.json()


def asset_version(slug: str) -> str:
    target = FACTION_MEDIA_ROOT / f"{slug}-promo.mp4"
    stamp = int(target.stat().st_mtime) if target.exists() else int(datetime.now(timezone.utc).timestamp())
    return str(stamp)


def build_email(base_url: str) -> tuple[str, dict[str, Any]]:
    base = base_url.rstrip("/")
    newsreel = fetch_json(f"{base}/ledger/turns/1/newsreel.json")
    sections: list[str] = [
        "Black Ledger leader digest bundle for validation.",
        "",
        f"Transition: {newsreel['transitionLabel']}",
        f"Headline: {newsreel['inboxHeadline']}",
        f"Newsreel: {newsreel['newsreelLead']}",
        f"World packet: {base}/account/ledger/worldtick/validation",
        "",
        "Faction leader + promo lanes:",
    ]
    factions: list[dict[str, Any]] = []
    for faction_id in DEFAULT_FACTIONS:
        promo = fetch_json(f"{base}/ledger/factions/{faction_id}/promo.json")
        version = asset_version(faction_id)
        entry = {
            "faction_id": faction_id,
            "public_name": promo["publicName"],
            "promo_href": f"{base}{promo['html_href']}?autoplay=1",
            "promo_json_href": f"{base}{promo['html_href']}.json" if not str(promo.get("html_href", "")).endswith(".json") else f"{base}{promo['html_href']}",
            "leader_validation_href": f"{base}{promo['validation_href']}",
            "video_mp4_href": f"{base}{promo['video_mp4_href']}?v={version}",
            "video_webm_href": f"{base}{promo['video_webm_href']}?v={version}",
            "poster_href": f"{base}{promo['poster_href']}?v={version}",
            "campaign_hook": promo["campaign_hook"],
            "audience_promise": promo["audience_promise"],
        }
        factions.append(entry)
        sections.extend(
            [
                f"- {entry['public_name']}",
                f"  Promo: {entry['promo_href']}",
                f"  MP4: {entry['video_mp4_href']}",
                f"  WebM: {entry['video_webm_href']}",
                f"  Poster: {entry['poster_href']}",
                f"  Leader validation: {entry['leader_validation_href']}",
                f"  Hook: {entry['campaign_hook']}",
                f"  Promise: {entry['audience_promise']}",
            ]
        )

    sections.extend(
        [
            "",
            "Review posture:",
            "- Every faction should now have a dedicated leader-validation lane.",
            "- Promo rails stay public-safe and must not outrun the turn packet.",
            "- Inbox/newsreel, validation packet, and leader brief should be reviewed together.",
        ]
    )

    subject = "[Chummer] Black Ledger leader digest bundle"
    body = "\n".join(sections)
    payload = {
        "subject": subject,
        "body": body,
        "newsreel": {
            "transition": newsreel["transitionLabel"],
            "headline": newsreel["inboxHeadline"],
        },
        "factions": factions,
    }
    return body, payload


def send_dispatch(recipient: str, body: str, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    portal_env = docker_env(PORTAL_CONTAINER)
    dispatch_base_url = support_progress_base_url()
    api_token = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN", "").strip() or "local-support-progress-token"
    principal_id = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID", "").strip() or "support-progress-principal"
    binding_id = portal_env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID", "").strip() or "binding-support-progress"
    version_token = max(
        int(Path(item["video_mp4_href"].split("?v=")[-1]).name) if "?v=" in item["video_mp4_href"] else 0
        for item in payload["factions"]
    )
    idempotency_key = f"black-ledger-leader-digest-bundle-turn1-v{version_token}-watchfix-{recipient.lower()}"
    request_payload = {
        "tool_name": "connector.dispatch",
        "action_kind": "delivery.send",
        "payload_json": {
            "principal_id": principal_id,
            "binding_id": binding_id,
            "channel": "email",
            "recipient": recipient,
            "subject": payload["subject"],
            "content": body,
            "metadata": {
                "purpose": "black_ledger_leader_digest_bundle",
                "dry_run": dry_run,
                "faction_count": len(payload["factions"]),
            },
            "idempotency_key": idempotency_key,
        },
    }
    if dry_run:
        return {
            "status": "dry_run",
            "payload": request_payload,
            "dispatch_base_url": dispatch_base_url,
            "idempotency_key": idempotency_key,
        }

    response = requests.post(
        f"{dispatch_base_url}/v1/tools/execute",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-ea-principal-id": principal_id,
            "Idempotency-Key": idempotency_key,
            "User-Agent": "Chummer Leader Digest/1.0",
        },
        data=json.dumps(request_payload),
        timeout=30,
    )
    response.raise_for_status()
    response_payload = response.json()
    return {
        "status": "queued",
        "dispatch_base_url": dispatch_base_url,
        "payload": request_payload,
        "response": response_payload,
        "delivery_id": response_payload.get("target_ref") or response_payload.get("output_json", {}).get("delivery_id"),
        "idempotency_key": idempotency_key,
    }


def write_receipt(result: dict[str, Any], recipient: str, payload: dict[str, Any], dry_run: bool) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    receipt = {
        "contract_name": "black_ledger_leader_digest_bundle",
        "generated_at_utc": now_iso(),
        "status": "pass" if result.get("status") in {"queued", "dry_run"} else "fail",
        "recipient": recipient,
        "dry_run": dry_run,
        "delivery": result,
        "content": {
            "subject": payload["subject"],
            "newsreel": payload["newsreel"],
            "faction_count": len(payload["factions"]),
        },
    }
    (OUTPUT_ROOT / "BLACK_LEDGER_LEADER_DIGEST_BUNDLE.generated.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    body, payload = build_email(args.base_url)
    result = send_dispatch(args.recipient, body, payload, dry_run=args.dry_run)
    write_receipt(result, args.recipient, payload, args.dry_run)
    print(json.dumps({"status": result.get("status"), "recipient": args.recipient, "delivery_id": result.get("delivery_id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
