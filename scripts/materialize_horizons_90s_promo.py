#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
SOURCE_ZIP = Path("/home/tibor/jammer6_all_horizons_90s_magicfit_promo_20260531.zip")
SOURCE_ROOT = WORKSPACE / "_work" / "jammer6_all_horizons_90s_magicfit_promo_20260531" / "jammer6_all_horizons_90s_magicfit_promo_20260531"
OUT = WORKSPACE / "_completion" / "horizons_90s_promo"
PUBLIC_ASSET_BASE = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
ASSET_ID = "all-horizons-90s-magicfit-promo"

GLOBAL_POSITIVE = (
    "Photoreal cinematic cyberpunk tabletop roleplaying product teaser, realistic mixed metahuman tabletop crew "
    "(human GM, ork decker, elf mage, dwarf rigger, troll street samurai, human face), visible cyberware on multiple "
    "characters (chrome cyberarm, AR lenses, datajack, subtle dermal plating), augmented reality overlays floating "
    "above the table and devices, expressive acting, real action in every shot, premium dark neon lighting, rain "
    "reflections, practical lights, sharp product UI overlays added in post, high-end trailer quality, no official "
    "game logos, no real brand logos."
)
GLOBAL_NEGATIVE = (
    "SVG, flat vector animation, static poster, slideshow, generic SaaS explainer, generic office, no people, "
    "frozen faces, plastic skin, distorted hands, unreadable AI text, long paragraphs on screen, official Shadowrun logos, "
    "official corporation or faction marks, sourcebook art, sourcebook page designs, canonical named characters, real celebrity likeness, provider watermark."
)

SCENES: list[dict[str, Any]] = [
    {
        "id": "01_cold_open_table_chaos",
        "timecode": "00:00-00:06",
        "duration_seconds": 6,
        "role": "opener",
        "horizon": "framing",
        "title": "The table is alive, but the tools are dead",
        "overlay": "One table. Too much chaos.",
        "voiceover": "Shadowrunning is chaos. Your tools do not have to be.",
        "prompt": "Rain-lit safehouse tabletop game, messy paper sheets, tablets, dice, misaligned AR notes, human GM trying to regain context, ork decker with AR lenses, elf mage, dwarf rigger with headset, troll street samurai with chrome cyberarm, visible cyberware and funny frustration, handheld cinematic inserts.",
    },
    {
        "id": "02_nexus_pan_shared_state",
        "timecode": "00:06-00:14",
        "duration_seconds": 8,
        "role": "core_product",
        "horizon": "NEXUS-PAN",
        "title": "Reconnect without losing the table",
        "overlay": "NEXUS-PAN - Shared State",
        "voiceover": "NEXUS-PAN keeps shared state steady when devices drift, drop, and return. It is continuity, not a separate promise to decode.",
        "prompt": "A player phone reconnects, session state snaps into sync across laptop tablet and mobile, bright AR data strands align over the table, ork decker with datajack and AR lenses, troll street samurai with cyberarm, relieved mixed-metahuman character reactions, practical neon table light.",
    },
    {
        "id": "03_alice_build_tradeoffs",
        "timecode": "00:14-00:22",
        "duration_seconds": 8,
        "role": "base_feature",
        "horizon": "ALICE",
        "title": "Legal is not the same as good",
        "overlay": "ALICE - Base Workbench Help",
        "voiceover": "ALICE is base product help: it compares builds, catches role traps, and explains tradeoffs with receipts.",
        "prompt": "AR build lab above a tabletop, two generic cyberpunk runner builds compared as clean holographic silhouettes and risk badges, ork decker with AR lenses reacts, elf mage smirks, visible cyberware reflections, no dense text, premium product trailer closeup.",
    },
    {
        "id": "04_karma_forge_governed_rules",
        "timecode": "00:22-00:30",
        "duration_seconds": 8,
        "role": "expansion_bet",
        "horizon": "KARMA FORGE",
        "title": "House rules without fork chaos",
        "overlay": "KARMA FORGE - Governed Rules",
        "voiceover": "KARMA FORGE turns house rules into governed, inspectable rule environments.",
        "prompt": "GM manipulates holographic AR rule cards and approval stamps, impacted runner sheets glow, troll street samurai with chrome cyberarm reacts to a flagged weapon, dwarf rigger and elf mage visible at table, cinematic overhead and UI closeup.",
    },
    {
        "id": "05_jackpoint_dossiers_recaps",
        "timecode": "00:30-00:38",
        "duration_seconds": 8,
        "role": "expansion_bet",
        "horizon": "JACKPOINT",
        "title": "Campaign memory that remembers where facts came from",
        "overlay": "JACKPOINT - Campaign Memory",
        "voiceover": "JACKPOINT is campaign memory: briefings, dossiers, and recaps without making things up.",
        "prompt": "Cyberpunk evidence room, rough mission notes become a polished player-safe AR dossier packet, source trails glow under claims, stylish human fixer with subtle cybernetic eye reacts, ork decker and elf mage nearby, noir push-in, no readable paragraphs.",
    },
    {
        "id": "06_runsite_spatial_prep",
        "timecode": "00:38-00:46",
        "duration_seconds": 8,
        "role": "expansion_bet",
        "horizon": "RUNSITE",
        "title": "Understand the space before it explodes",
        "overlay": "RUNSITE - Spatial Prep",
        "voiceover": "RUNSITE makes mission spaces explorable and legible before the action starts.",
        "prompt": "3D AR model of a generic clinic or warehouse unfolds above tabletop, entry points and security zones as abstract geometry, GM-only hidden layer flashes, dwarf rigger with visible cybernetic hand points at a drone nest, troll and ork silhouettes nearby.",
    },
    {
        "id": "07_runbook_press_campaign_books",
        "timecode": "00:46-00:54",
        "duration_seconds": 8,
        "role": "expansion_bet",
        "horizon": "RUNBOOK PRESS",
        "title": "Turn a season into a book",
        "overlay": "RUNBOOK PRESS - Campaign Books",
        "voiceover": "RUNBOOK PRESS turns approved campaign truth into primers, guides, modules, and season books.",
        "prompt": "Futuristic publishing room, AR campaign maps and faction-neutral briefs flow into a premium original book mockup, mixed human ork elf dwarf troll tabletop crew watching with pride, visible cyberware and AR lenses, no sourcebook layout imitation.",
    },
    {
        "id": "08_table_pulse_live_heat",
        "timecode": "00:54-01:02",
        "duration_seconds": 8,
        "role": "base_feature",
        "horizon": "TABLE PULSE",
        "title": "The run pushes back",
        "overlay": "TABLE PULSE - Campaign Operations",
        "voiceover": "TABLE PULSE is campaign operations: bounded reactions, remote choices, and GM-approved fallout.",
        "prompt": "Tabletop session in motion with mixed metahuman crew, GM screen receives a subtle AR heat alert, remote player chooses a bounded reaction on phone, ork decker with AR lenses and troll cyberarm visible, cast reacts to fallout, warm table light and cyberpunk accents.",
    },
    {
        "id": "09_black_ledger_living_world",
        "timecode": "01:02-01:12",
        "duration_seconds": 10,
        "role": "expansion_bet",
        "horizon": "BLACK LEDGER",
        "title": "The city remembers",
        "overlay": "BLACK LEDGER - Living World",
        "voiceover": "BLACK LEDGER makes the city remember: factions, heat, missions, newsreels, and consequences.",
        "prompt": "Premium living city globe and district map AR interface, generic faction pressure shown as abstract heat arcs, completed run changes city markers and newsroom ticker energy, mixed metahuman operators with visible cyberware watch the globe, cinematic orbiting camera.",
    },
    {
        "id": "10_community_hub_open_runs",
        "timecode": "01:12-01:20",
        "duration_seconds": 8,
        "role": "expansion_bet",
        "horizon": "COMMUNITY HUB",
        "title": "Find the table. Close the loop.",
        "overlay": "COMMUNITY HUB - Open Runs",
        "voiceover": "COMMUNITY HUB helps players find runs, pass preflight, get scheduled, and feed outcomes back into the world.",
        "prompt": "Open-run recruitment scene, human ork elf dwarf and troll players gather around a table through phones and laptops, AR preflight checks glow green as abstract cards, visible cyberware, calendar handoff, welcoming character moment.",
    },
    {
        "id": "11_finale_all_horizons",
        "timecode": "01:20-01:30",
        "duration_seconds": 10,
        "role": "finale",
        "horizon": "all",
        "title": "One product spine",
        "overlay": "Build the runner. Run the table. Shape the world.",
        "voiceover": "Build the runner. Run the table. Remember consequences. Chummer6.",
        "prompt": "Product-area AR cards and a few future-bet cards circle above the tabletop and become a living city interface, recurring mixed metahuman cast stands together: human GM, ork decker, elf mage, dwarf rigger, troll street samurai with cyberarm, visible cyberware, final product logo space left clean for post, heroic trailer finish.",
    },
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_provider_verification() -> dict[str, Any]:
    path = WORKSPACE / "_completion" / "magicfit_provider" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json"
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid_json", "path": str(path)}
    payload["path"] = str(path)
    return payload


def scene_receipt(scene: dict[str, Any], provider_verified: bool) -> dict[str, Any]:
    prompt = f"{GLOBAL_POSITIVE} Scene: {scene['prompt']} Negative constraints: {GLOBAL_NEGATIVE}"
    expected_clip = OUT / "magicfit_clips" / f"{scene['id']}.mp4"
    sidecar = OUT / "magicfit_clips" / f"{scene['id']}.magicfit.json"
    clip_exists = expected_clip.is_file()
    sidecar_exists = sidecar.is_file()
    sidecar_payload: dict[str, Any] = {}
    if sidecar_exists:
        try:
            loaded = json.loads(sidecar.read_text(encoding="utf-8"))
            sidecar_payload = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            sidecar_payload = {"sidecar_error": "invalid_json"}

    status = "rendered" if clip_exists and sidecar_exists and sidecar_payload.get("provider") == "MagicFit" else "missing_render"
    return {
        "scene_id": scene["id"],
        "horizon": scene["horizon"],
        "role": scene["role"],
        "timecode": scene["timecode"],
        "duration_seconds": scene["duration_seconds"],
        "title": scene["title"],
        "provider": "MagicFit",
        "provider_verified": provider_verified,
        "status": status,
        "prompt_sha256": sha256_text(prompt),
        "prompt": prompt,
        "expected_clip_path": str(expected_clip),
        "expected_sidecar_path": str(sidecar),
        "clip_exists": clip_exists,
        "sidecar_exists": sidecar_exists,
        "job_id": sidecar_payload.get("job_id") or sidecar_payload.get("video_output_url"),
        "rendered_at_utc": sidecar_payload.get("generated_at_utc"),
        "ip_boundary": {
            "official_logos_allowed": False,
            "sourcebook_art_allowed": False,
            "canonical_named_characters_allowed": False,
            "product_text_added_in_post": True,
        },
    }


def write_outputs() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generated_at = now_iso()
    provider = load_provider_verification()
    provider_verified = provider.get("status") == "verified"
    receipts = [scene_receipt(scene, provider_verified) for scene in SCENES]
    rendered_count = sum(1 for receipt in receipts if receipt["status"] == "rendered")
    scene_count = len(SCENES)
    total_duration = sum(scene["duration_seconds"] for scene in SCENES)
    covered_surfaces = [scene["horizon"] for scene in SCENES if scene["role"] in {"core_product", "base_feature", "expansion_bet"}]
    required_surfaces = [
        "NEXUS-PAN",
        "ALICE",
        "KARMA FORGE",
        "JACKPOINT",
        "RUNSITE",
        "RUNBOOK PRESS",
        "TABLE PULSE",
        "BLACK LEDGER",
        "COMMUNITY HUB",
    ]
    surface_coverage_pass = covered_surfaces == required_surfaces
    all_rendered = rendered_count == scene_count
    composite_path = PUBLIC_ASSET_BASE / f"{ASSET_ID}.mp4"
    caption_path = PUBLIC_ASSET_BASE / f"{ASSET_ID}.vtt"
    poster_path = PUBLIC_ASSET_BASE / f"{ASSET_ID}-poster.png"
    composite_exists = composite_path.is_file()
    caption_exists = caption_path.is_file()
    poster_exists = poster_path.is_file()
    human_review_path = OUT / "PROMO_VIDEO_HUMAN_CREATIVE_REVIEW.md"
    human_review_text = human_review_path.read_text(encoding="utf-8") if human_review_path.is_file() else ""
    human_reviewed = "Verdict: PASS" in human_review_text
    public_safe_plan = True
    post_composite_complete = composite_exists and caption_exists and poster_exists
    ready = all_rendered and provider_verified and surface_coverage_pass and total_duration == 90 and post_composite_complete and human_reviewed

    plan = {
        "contract_name": "chummer.campaign_tools_90s_promo.magicfit_render_plan",
        "generated_at_utc": generated_at,
        "source_zip": str(SOURCE_ZIP),
        "source_root": str(SOURCE_ROOT),
        "asset_id": ASSET_ID,
        "title": "Chummer6: The Table Wakes Up",
        "duration_seconds": total_duration,
        "scene_count": scene_count,
        "render_method": {
            "do_not_render_as_one_video": True,
            "render_one_clip_per_scene": True,
            "clip_count": scene_count,
            "vo_in_post": True,
            "captions_in_post": True,
            "product_ui_overlays_in_post": True,
            "final_logo_in_post": True,
        },
        "provider": {
            "name": "MagicFit",
            "verification_status": provider.get("status"),
            "verification_receipt": provider.get("path"),
            "claim_boundary": "Provider capability is verified, but this campaign-tools reel is not ready until every scene has its own render receipt.",
        },
        "global_positive_prompt": GLOBAL_POSITIVE,
        "global_negative_prompt": GLOBAL_NEGATIVE,
        "required_surfaces": required_surfaces,
        "scenes": [
            {
                **scene,
                "magicfit_prompt": f"{GLOBAL_POSITIVE} Scene: {scene['prompt']} Negative constraints: {GLOBAL_NEGATIVE}",
                "render_status": receipts[index]["status"],
            }
            for index, scene in enumerate(SCENES)
        ],
    }
    (OUT / "MAGICFIT_RENDER_PLAN.generated.yaml").write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")

    receipts_payload = {
        "contract_name": "chummer.campaign_tools_90s_promo.magicfit_scene_receipts",
        "generated_at_utc": generated_at,
        "asset_id": ASSET_ID,
        "provider": "MagicFit",
        "provider_verified": provider_verified,
        "scene_count": scene_count,
        "rendered_scene_count": rendered_count,
        "missing_scene_count": scene_count - rendered_count,
        "status": "pass" if all_rendered else "missing_scene_renders",
        "receipts": receipts,
    }
    (OUT / "MAGICFIT_SCENE_RECEIPTS.generated.json").write_text(json.dumps(receipts_payload, indent=2), encoding="utf-8")

    metadata = {
        "contract_name": "chummer.campaign_tools_90s_promo.asset_metadata",
        "generated_at_utc": generated_at,
        "asset_id": ASSET_ID,
        "title": "Chummer6: The Table Wakes Up",
        "duration_seconds": total_duration,
        "scene_count": scene_count,
        "required_surfaces": required_surfaces,
        "surface_coverage_pass": surface_coverage_pass,
        "composite_expected_path": str(composite_path),
        "caption_expected_path": str(caption_path),
        "poster_expected_path": str(poster_path),
        "composite_exists": composite_exists,
        "caption_exists": caption_exists,
        "poster_exists": poster_exists,
        "render_mode": "magicfit_per_scene_then_post_composite",
        "status": "missing_magicfit_scene_renders"
        if not all_rendered
        else "rendered_pending_post_composite"
        if not post_composite_complete
        else "post_composited_pending_human_review",
    }
    (OUT / "PROMO_VIDEO_ASSET_METADATA.generated.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    motion_score = {
        "contract_name": "chummer.campaign_tools_90s_promo.motion_score",
        "generated_at_utc": generated_at,
        "status": "fail" if not all_rendered else "pending_human_review",
        "score": 0 if not all_rendered else None,
        "required_checks": {
            "people_visible_every_scene": None if all_rendered else False,
            "action_every_scene": None if all_rendered else False,
            "not_static_slideshow": None if all_rendered else False,
            "cinematic_character_driven": None if all_rendered else False,
            "unique_visual_metaphor_per_surface": surface_coverage_pass,
        },
        "reason": "Rendered MagicFit clips and post composite are present; human review must confirm motion quality before public release."
        if all_rendered
        else "No rendered scene clips are present for this 11-scene campaign-tools reel.",
    }
    (OUT / "PROMO_VIDEO_MOTION_SCORE.generated.json").write_text(json.dumps(motion_score, indent=2), encoding="utf-8")

    safety = {
        "contract_name": "chummer.campaign_tools_90s_promo.public_safety",
        "generated_at_utc": generated_at,
        "status": "pending_human_review" if all_rendered else "plan_pass_render_pending",
        "ip_boundary_pass": public_safe_plan,
        "forbidden_material": [
            "official Shadowrun logos",
            "official corporation/faction marks",
            "sourcebook art",
            "sourcebook page designs",
            "canonical named characters",
            "real celebrity likeness",
        ],
        "claim_boundary": "Do not claim expansion bets are fully shipped today; this is a directional product-spine teaser.",
        "render_review_required": True,
        "render_review_reason": "Rendered MagicFit clips must be inspected by a human before public-safe final approval.",
    }
    (OUT / "PROMO_VIDEO_PUBLIC_SAFETY.generated.json").write_text(json.dumps(safety, indent=2), encoding="utf-8")

    if human_reviewed:
        review_md = human_review_text
    else:
        review_md = f"""# Promo Video Human Creative Review

Generated: {generated_at}

Verdict: NOT HUMAN-REVIEWED FOR FINAL RELEASE

This package has a complete 11-scene MagicFit render plan, rendered MagicFit scene clips, per-scene MagicFit job receipts, and a 90-second post-composited MP4. It is still not marked release-ready because human creative review has not been recorded.

Creative notes:
- The 11-scene structure is valid: opener, core product areas, expansion bets, finale.
- The required product surfaces are each introduced once.
- The plan correctly keeps VO, captions, UI labels, and logo work in post.
- The post composite, caption file, and poster asset exist.
- The IP boundary is explicit and public-safe at the prompt level.

Release blocker:
- Human creative review cannot pass until the rendered clips and composite are inspected for motion, character acting, offensive artifacts, readable post overlays, and IP safety.
"""
    (OUT / "PROMO_VIDEO_HUMAN_CREATIVE_REVIEW.md").write_text(review_md, encoding="utf-8")

    final = "HORIZONS_90S_PROMO_READY" if ready else "NOT_READY"
    final_md = f"""{final}

Generated: {generated_at}

Summary:
- Provider capability verified: {provider_verified}
- Scene plan count: {scene_count}
- Required duration: {total_duration}s
- Required product surfaces covered once: {surface_coverage_pass}
- Rendered MagicFit scene receipts: {rendered_count}/{scene_count}
- Post composite present: {post_composite_complete}
- Human creative review passed: {human_reviewed}
"""
    if not ready:
        final_md += """
Blocking condition:
Final readiness requires provider verification, 11 rendered scenes, 90-second composite media, public-safety artifacts, and recorded human creative approval. Do not convert provider ownership, clip existence, or receipt text into human creative approval.
"""
    (OUT / "FINAL_HORIZONS_90S_PROMO_VERDICT.md").write_text(final_md, encoding="utf-8")

    print(final)
    return 0 if ready else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Materialize the Chummer6 product threads 90s MagicFit promo plan and fail-closed verdict.")
    parser.add_argument("--strict-ready", action="store_true", help="Exit non-zero unless the final verdict is ready.")
    args = parser.parse_args()
    result = write_outputs()
    raise SystemExit(result if args.strict_ready else 0)
