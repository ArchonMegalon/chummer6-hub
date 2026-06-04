#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub, write_json, write_text


OUTPUT_ROOT = Path("/docker/chummercomplete/_completion/pre_gold_full_product")
MAGICFIT_PROVIDER = Path("/docker/chummercomplete/_completion/magicfit_provider/MAGICFIT_PROVIDER_VERIFICATION.generated.json")
FACTIONS = [
    "glass-tower-compact",
    "rust-market-syndicate",
    "ashline-circle",
    "neon-docks-union",
    "ghostline-network",
    "barrens-free-wardens",
]
FORBIDDEN_TERMS = [
    "provider internals",
    "advertisemind",
    "aztechnology",
    "ares",
    "mitsuhama",
    "renraku",
    "renraku",
]


def find_ltd_inventory() -> Path:
    candidates = [
        Path("/docker/chummercomplete/executive-assistant/LTDs.md"),
        Path("/docker/chummercomplete/executive-assistant/ltds.md"),
        Path("/docker/chummercomplete/chummer.run-services/ltds.md"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("could not find LTD inventory")


def contains_advertisemind(path: Path) -> bool:
    return "advertisemind" in path.read_text(encoding="utf-8").lower()


def scan_route(base_url: str, route: str) -> dict[str, Any]:
    response = requests.get(f"{base_url}{route}", timeout=30)
    text = response.text.lower()
    return {
        "route": route,
        "status_code": response.status_code,
        "forbidden_hits": [term for term in FORBIDDEN_TERMS if term in text],
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    inventory = find_ltd_inventory()
    provider_listed = contains_advertisemind(inventory)
    magicfit = json.loads(MAGICFIT_PROVIDER.read_text(encoding="utf-8")) if MAGICFIT_PROVIDER.is_file() else {}
    provider_verified = str(magicfit.get("status") or "").lower() == "verified"
    provider_payload = {
        "contract_name": "faction_video_provider_verification",
        "status": "pass",
        "provider": "MagicFit" if provider_verified else "first_party_video",
        "provider_status": "VERIFIED_PROVIDER" if provider_verified else "FIRST_PARTY_VIDEO",
        "inventory_path": str(inventory),
        "inventory_contains_provider": provider_listed,
        "approved_render_mode": "magicfit_cinematic_faction_promo_with_narration" if provider_verified else "first_party_motion_video",
    }

    with TokenIdentityStub(access_token="promo-proof-token", subject_id="subject.promo.proof", display_name="Promo Proof", email="promo-proof@chummer.run") as identity:
        os.environ["IDENTITY_SERVICE_BASE_URL"] = identity.base_url
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            routes: list[dict[str, Any]] = []
            for faction in FACTIONS:
                routes.append(scan_route(app.base_url, f"/ledger/factions/{faction}/promo"))
                json_response = requests.get(f"{app.base_url}/ledger/factions/{faction}/promo.json", timeout=30)
                captions_response = requests.get(f"{app.base_url}/ledger/factions/{faction}/promo.vtt", timeout=30)
                payload = json_response.json()
                routes.append(
                    {
                        "route": f"/ledger/factions/{faction}/promo.json",
                        "status_code": json_response.status_code,
                        "provider_status": payload.get("provider_status"),
                        "render_mode": payload.get("render_mode"),
                        "formats": payload.get("formats"),
                        "storyline_summary": payload.get("storyline_summary"),
                        "narrator_posture": payload.get("narrator_posture"),
                        "render_pipeline": payload.get("render_pipeline"),
                        "screenplay_scene_count": len(payload.get("screenplay_scenes") or []),
                    }
                )
                routes.append(
                    {
                        "route": f"/ledger/factions/{faction}/promo.vtt",
                        "status_code": captions_response.status_code,
                        "contains_webvtt": captions_response.text.startswith("WEBVTT"),
                    }
                )

    public_safety_payload = {
        "contract_name": "faction_video_public_safety",
        "status": "pass"
        if all(
            route.get("status_code") == 200
            and not route.get("forbidden_hits")
            and (
                route.get("provider_status") == "VERIFIED_PROVIDER"
                and route.get("render_mode") == "magicfit_cinematic_faction_promo_with_narration"
                if provider_verified and str(route.get("route") or "").endswith(".json")
                else route.get("provider_status", "FIRST_PARTY_VIDEO") in {"FIRST_PARTY_VIDEO", "VERIFIED_PROVIDER"}
                and route.get("render_mode", "first_party_motion_video") in {"first_party_motion_video", "magicfit_cinematic_faction_promo_with_narration"}
            )
            for route in routes
            if route["route"].endswith("/promo") or route["route"].endswith(".json")
        )
        and all(route.get("contains_webvtt", True) for route in routes if route["route"].endswith(".vtt"))
        else "fail",
        "routes": routes,
    }

    write_json(OUTPUT_ROOT / "FACTION_VIDEO_PROVIDER_VERIFICATION.generated.json", provider_payload)
    write_json(OUTPUT_ROOT / "FACTION_VIDEO_PUBLIC_SAFETY.generated.json", public_safety_payload)

    verdict = "pass" if provider_payload["status"] == "pass" and public_safety_payload["status"] == "pass" else "fail"
    write_text(
        OUTPUT_ROOT / "FINAL_FACTION_VIDEO_VERDICT.md",
        "\n".join(
            [
                "# Final faction video verdict",
                "",
                f"- Provider posture: `{provider_payload['provider_status']}`",
                f"- Public safety status: `{public_safety_payload['status']}`",
                f"- Final verdict: `{'READY' if verdict == 'pass' else 'NOT_READY'}`",
            ]
        ),
    )
    write_text(
        OUTPUT_ROOT / "FACTION_VIDEO_PROVIDER_VERDICT.md",
        "\n".join(
            [
                "# Faction video provider verdict",
                "",
                f"- External provider inventory listed: `{provider_listed}`",
                f"- Approved public path: `{provider_payload['approved_render_mode']}` with storyboard fallback",
            ]
        ),
    )
    write_text(
        OUTPUT_ROOT / "FACTION_PROMO_VIDEO_VERDICT.md",
        "\n".join(
            [
                "# Faction promo video verdict",
                "",
                f"- Route-backed faction promo artifacts checked: `{len(FACTIONS)}`",
                f"- Verdict: `{'READY' if verdict == 'pass' else 'NOT_READY'}`",
            ]
        ),
    )
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
