#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub

FACTIONS = [
    "glass-tower-compact",
    "rust-market-syndicate",
    "ashline-circle",
    "neon-docks-union",
    "ghostline-network",
    "barrens-free-wardens",
]
OUT_DIR = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="MagicFit")
    parser.add_argument("--fallback", default="storyboard")
    parser.add_argument("--base-url", default="")
    return parser.parse_args()


def evaluate(base: str, args: argparse.Namespace) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    receipts = []
    overall = "pass"
    provider_verified = str(args.provider or "").strip().lower() == "magicfit"
    for faction in FACTIONS:
        r = requests.get(f"{base}/ledger/factions/{faction}/promo.json", timeout=30)
        payload = r.json() if r.ok else {}
        storyboard_frames = payload.get("storyboard_frames")
        provider_status = str(payload.get("provider_status") or "")
        render_mode = str(payload.get("render_mode") or "")
        screenplay_scenes = payload.get("screenplay_scenes")
        public_receipt = Path(f"/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/ledger/factions/{faction}-promo.receipt.json")
        require_magicfit_route = provider_verified and public_receipt.is_file()
        status = "pass" if (
            r.status_code == 200
            and (
                (provider_status == "VERIFIED_PROVIDER" and render_mode == "magicfit_cinematic_faction_promo_with_narration")
                if require_magicfit_route
                else provider_status in {"VERIFIED_PROVIDER", "FIRST_PARTY_VIDEO"}
                and render_mode in {"magicfit_cinematic_faction_promo_with_narration", "first_party_motion_video"}
            )
            and isinstance(storyboard_frames, list)
            and len(storyboard_frames) >= 3
            and isinstance(screenplay_scenes, list)
            and len(screenplay_scenes) >= 3
            and all(
                isinstance(frame, dict)
                and str(frame.get("visual_hook") or "").strip()
                and str(frame.get("action_beat") or "").strip()
                and str(frame.get("proof_payoff") or "").strip()
                for frame in storyboard_frames
            )
        ) else "fail"
        if status != "pass":
            overall = "fail"
        receipt = {
            "generated_at_utc": now_iso(),
            "faction": faction,
            "provider": args.provider,
            "fallback": args.fallback,
            "status": status,
            "route": f"/ledger/factions/{faction}/promo.json",
            "provider_status": provider_status,
            "render_mode": render_mode,
            "magicfit_route_required": require_magicfit_route,
            "formats": payload.get("formats"),
            "storyboard_frame_count": len(storyboard_frames) if isinstance(storyboard_frames, list) else 0,
            "screenplay_scene_count": len(screenplay_scenes) if isinstance(screenplay_scenes, list) else 0,
        }
        receipts.append(receipt)
        out = OUT_DIR / f"{faction.replace('-', '_').upper()}_VIDEO_RECEIPT.generated.json"
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    summary = OUT_DIR / "FACTION_VIDEO_BRIEFS.generated.json"
    summary.write_text(json.dumps({"generated_at_utc": now_iso(), "status": overall, "receipts": receipts}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": overall, "count": len(receipts)}))
    return 0 if overall == "pass" else 1


def main() -> int:
    args = parse_args()
    if args.base_url.strip():
        return evaluate(args.base_url.rstrip("/"), args)

    with TokenIdentityStub(access_token="promo-render-gate-token", subject_id="subject.promo.render", display_name="Promo Render Gate", email="promo-render-gate@chummer.run") as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            return evaluate(app.base_url.rstrip("/"), args)


if __name__ == "__main__":
    raise SystemExit(main())
