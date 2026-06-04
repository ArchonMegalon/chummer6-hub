#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path("/docker/chummercomplete")
OUT_ROOT = ROOT / "_completion" / "black_ledger_magicfit_newsreels"
DEFAULT_BASE = "https://chummer.run"
NEGATIVE = (
    "flat vector, static poster, slideshow, generic corporate SaaS, dead faces, broken hands, unreadable text, "
    "official Shadowrun logos, sourcebook art, sourcebook page layout, real brand logos, watermark, empty newsroom, "
    "cartoon metahumans, no visible cyberware, no AR overlays, comic panel, lego toy, plastic miniature, low-energy acting"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MagicFit scene manifests for Black Ledger Turn 1/Turn 2 newsroom videos.")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--turn", type=int, action="append", default=[1, 2], help="Turn to include; may be repeated.")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(base_url: str, turn: int) -> dict:
    response = requests.get(f"{base_url.rstrip('/')}/ledger/turns/{turn}/newsreel.json", timeout=60)
    response.raise_for_status()
    return response.json()


def scene(asset_id: str, number: int, title: str, duration: int, prompt: str, line: str, voice_role: str) -> dict:
    return {
        "id": f"{asset_id}_{number:02}_{title.lower().replace(' ', '_')}",
        "scene_number": number,
        "title": title,
        "timecode": "",
        "duration_seconds": duration,
        "on_screen_text": "",
        "prompt": prompt,
        "negative_prompt": NEGATIVE,
        "narration": line,
        "voice_role": voice_role,
    }


def clean_line(value: object, fallback: str) -> str:
    text = str(value or fallback).strip()
    return text.replace("MysAd", "awakened").replace("public-safe", "public").replace("proof", "signal")


def build_asset(turn: int, payload: dict) -> dict:
    asset_id = f"emerald_sprawl_turn_{turn}_newsreel"
    world_name = str(payload["worldName"])
    transition = str(payload["transitionLabel"])
    lead = str(payload["newsreelLead"])
    state = str(payload["stateSummary"])
    action_beats = payload.get("actionBeats") or []
    featured_beats = [beat for beat in action_beats if str(beat.get("actorKind") or "").lower() != "anchor"]
    if not featured_beats:
        featured_beats = action_beats
    first = featured_beats[0] if featured_beats else {}
    second = featured_beats[1] if len(featured_beats) > 1 else first
    third = featured_beats[2] if len(featured_beats) > 2 else second

    opening_line = (
        f"In Emerald Sprawl, turn {turn} does not arrive as a recap. It hits like a district pulse, "
        f"and everyone watching can feel which corner of the city just lost its balance."
    )
    if turn == 2:
        opening_line = (
            "Emerald Sprawl is no longer bracing for impact. "
            "Now the city is answering back, and every answer redraws who still looks in control."
        )

    field_line = (
        f"We have a developing situation in {first.get('actorLabel', 'the district')}. "
        f"{clean_line(first.get('actionSummary'), first.get('consequenceLine', 'Pressure is moving in public now.'))}"
    )
    desk_line = (
        f"Behind the desk, the next move is already visible. "
        f"{second.get('actorLabel', 'The board')}: "
        f"{clean_line(second.get('commandIntent'), second.get('actionSummary', 'the board is forcing the next hard decision'))}"
    )
    fallout_line = (
        f"{clean_line(third.get('consequenceLine'), third.get('stakes', state))} "
        f"The city remembers the crews that move first and the districts that fail to recover."
    )
    close_line = (
        f"Tonight the city closes on this reality: {state} "
        "Tomorrow the board opens again, and the next faction that hesitates will be seen."
    )

    scenes = [
        scene(
            asset_id,
            1,
            "Anchor Open",
            7,
            "Photoreal cinematic cyberpunk newsroom, seasoned metahuman anchor at a premium desk, visible cyberware, AR lower thirds, world pressure wall behind them, slow push-in, grounded performance, premium broadcast lighting, live-action feeling, 16:9. "
            f"Turn {turn} headline for {world_name}; transition posture {transition}.",
            opening_line,
            "anchor",
        ),
        scene(
            asset_id,
            2,
            "Field Pressure",
            7,
            "Photoreal rainy Seattle street report, ork field reporter speaking into camera, visible tusks and cyberware, civilians and drones moving through a pressure zone, AR district heat overlay, cinematic handheld camera, premium live-action scene, 16:9. "
            f"Visual hook: {first.get('visualHook', 'pressure moves in public')}.",
            field_line,
            "ork_reporter",
        ),
        scene(
            asset_id,
            3,
            "Command Desk",
            7,
            "Photoreal command desk with Black Ledger geoscape, metahuman operator and anchor reviewing pressure arcs, subtle AR overlays, visible cyberware, premium newsroom strategy wall, strategic camera orbit, 16:9. "
            f"Show {second.get('actorLabel', 'world desk')} as the next visible mover.",
            desk_line,
            "narrator",
        ),
        scene(
            asset_id,
            4,
            "Consequence Close",
            7,
            "Photoreal consequence montage, faction operatives, district responders, witness traffic, and city-state fallout all visible in one grounded cyberpunk scene, premium lighting, metahuman cast, camera movement obvious, 16:9. "
            f"State summary: {state}",
            fallout_line,
            "narrator",
        ),
        scene(
            asset_id,
            5,
            "Validation Close",
            6,
            "Photoreal newsroom closing shot, anchor half-turned toward a producer wall with route map, captions rail, and city overlays, cinematic but restrained, AR stamps and validation traces, 16:9.",
            close_line,
            "anchor",
        ),
    ]
    total = sum(item["duration_seconds"] for item in scenes)
    return {
        "lane": "black_ledger_turn_newsreels",
        "asset_id": asset_id,
        "title": f"{world_name} Turn {turn} Newsreel",
        "horizon": "BLACK LEDGER",
        "source_file": payload["validationJsonHref"],
        "duration_seconds": total,
        "turn": turn,
        "screenplay_summary": "Anchor open, ork field dispatch, command reaction, consequence montage, anchor close.",
        "narrator_posture": "Slow cinematic narration with a distinct ork field reporter insert over MagicFit-rendered clips.",
        "scenes": scenes,
    }


def main() -> int:
    args = parse_args()
    turns = sorted(set(args.turn))
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    assets = [build_asset(turn, fetch(args.base_url, turn)) for turn in turns]
    manifest = {
        "contract_name": "black_ledger_turn_magicfit_newsreels",
        "generated_at_utc": now_iso(),
        "provider": "MagicFit",
        "render_method": "per_scene_magicfit_then_composite_with_narration",
        "asset_count": len(assets),
        "scene_count": sum(len(asset["scenes"]) for asset in assets),
        "claim_boundary": "This manifest defines the MagicFit render plan. Public route claims should change only after rendered clips are composited and published.",
        "assets": assets,
    }
    out = OUT_ROOT / "BLACK_LEDGER_TURN_MAGICFIT_RENDER_MANIFEST.generated.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "manifest": str(out), "asset_count": len(assets)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    def clean_line(value: object, fallback: str) -> str:
        text = str(value or fallback).strip()
        return text.replace("MysAd", "awakened").replace("public-safe", "public").replace("proof", "signal")
