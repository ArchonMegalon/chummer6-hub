#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests


DEFAULT_OUTPUT_ROOT = Path("/docker/chummercomplete/_completion/pregold_ux_pwa_black_ledger")
FACTIONS = [
    "glass-tower-compact",
    "rust-market-syndicate",
    "ashline-circle",
    "neon-docks-union",
    "ghostline-network",
    "barrens-free-wardens",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify faction video provider posture and fallback safety.")
    parser.add_argument("--provider", default="advertisemind")
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def find_ltd_inventory() -> Path | None:
    candidates = [
        Path("/docker/chummercomplete/executive-assistant/LTDs.md"),
        Path("/docker/chummercomplete/executive-assistant/ltds.md"),
        Path("/docker/chummercomplete/chummer.run-services/ltds.md"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    inventory = find_ltd_inventory()
    provider_verified = False
    if inventory is not None:
      provider_verified = args.provider.lower() in inventory.read_text(encoding="utf-8").lower()

    session = requests.Session()
    routes: list[dict[str, Any]] = []
    for faction in FACTIONS:
        page = session.get(f"{args.base_url}/ledger/factions/{faction}/promo", timeout=30)
        json_response = session.get(f"{args.base_url}/ledger/factions/{faction}/promo.json", timeout=30)
        vtt_response = session.get(f"{args.base_url}/ledger/factions/{faction}/promo.vtt", timeout=30)
        payload = json_response.json()
        routes.append(
            {
                "faction": faction,
                "page_status": page.status_code,
                "json_status": json_response.status_code,
                "vtt_status": vtt_response.status_code,
                "provider_status": payload.get("provider_status"),
                "render_mode": payload.get("render_mode"),
                "contains_provider_branding": args.provider.lower() in page.text.lower(),
            }
        )

    provider_status = "VERIFIED" if provider_verified else "NEEDS_PROVIDER_VERIFICATION"
    fallback_ok = all(
        row["page_status"] == 200
        and row["json_status"] == 200
        and row["vtt_status"] == 200
        and row["provider_status"] == "NEEDS_PROVIDER_VERIFICATION"
        and row["render_mode"] == "fallback_static_storyboard"
        and not row["contains_provider_branding"]
        for row in routes
    )
    status = "pass" if ((provider_verified or args.allow_fallback) and fallback_ok) else "fail"

    write_json(
        output_root / "FACTION_VIDEO_PROVIDER_VERIFICATION.generated.json",
        {
            "generated_at_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "status": "pass" if (provider_verified or args.allow_fallback) else "fail",
            "provider": args.provider,
            "provider_status": provider_status,
            "inventory_path": str(inventory) if inventory else None,
            "inventory_contains_provider": provider_verified,
            "approved_render_mode": "fallback_static_storyboard",
        },
    )
    write_json(
        output_root / "FACTION_VIDEO_PUBLIC_SAFETY.generated.json",
        {
            "generated_at_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "status": "pass" if fallback_ok else "fail",
            "provider": args.provider,
            "routes": routes,
        },
    )
    write_text(
        output_root / "FINAL_FACTION_VIDEO_VERDICT.md",
        "\n".join(
            [
                "# Final faction video verdict",
                "",
                f"- Provider posture: `{provider_status}`",
                f"- Fallback storyboard safety: `{'pass' if fallback_ok else 'fail'}`",
                f"- Verdict: `{'READY_VIA_FALLBACK' if status == 'pass' else 'NOT_READY'}`",
            ]
        ),
    )
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
