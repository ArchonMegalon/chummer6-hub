#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WORKSPACE = Path("/docker/chummercomplete")
PUBLIC_DIR = WORKSPACE / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
BUILD_DIR = WORKSPACE / "_completion" / "every_wonder_horizon_promo"

ASSET_ID = "every-wonder-horizon-promo"
TARGET_MP4 = PUBLIC_DIR / f"{ASSET_ID}.mp4"
TARGET_WEBM = PUBLIC_DIR / f"{ASSET_ID}.webm"
TARGET_POSTER = PUBLIC_DIR / f"{ASSET_ID}-poster.png"
TARGET_VTT = PUBLIC_DIR / f"{ASSET_ID}.vtt"
TARGET_RECEIPT = PUBLIC_DIR / f"{ASSET_ID}.receipt.json"

WIDTH = 1280
HEIGHT = 720
FPS = 24
TARGET_SECONDS = 90.0
TRANSITION_SECONDS = 0.5
SCENE_DURATIONS = (6.0, 6.0, 7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 8.0, 10.0, 10.0, 8.0)
SCENE_SECONDS = (TARGET_SECONDS + 11 * TRANSITION_SECONDS) / 12

FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
TITLE_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 54)
SUBTITLE_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 25)
LABEL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 20)
SMALL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 18)
MONO_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSansMono.ttf"), 18)


PRODUCTION_TITLE = "Chummer6 Horizons - The Table Remembers"
GLOBAL_MAGICFIT_PROMPT = (
    "Cinematic cyberpunk tabletop product promo, rain-soaked neon sprawl, warm table light, "
    "AR campaign interface, dice and character sheets on a dark table, tactical UI overlays, "
    "readable horizon cards, polished product trailer, subtle handheld camera, no official game logos, "
    "no real brand logos, 16:9, 90 seconds."
)
NEGATIVE_PROMPT = (
    "No official Shadowrun logos, no real corporate logos, no unreadable tiny text, no gore, no messy UI, "
    "no cartoon style, no exaggerated fantasy magic, no random weapon closeups, no ungrounded superhero visuals, "
    "no voyeuristic surveillance framing, no real-world targeting UI, no player scoring dashboard."
)
PROOF_CONSTRAINTS = (
    "90 second minimum final duration with audio and video streams",
    "exactly 12 distinct timed scenes",
    "captions contain one segment per scene",
    "horizons are future lanes, not current feature promises",
    "MagicFit render claim requires provider and scene receipts; otherwise label first-party motion storyboard",
)

SCENES = (
    {
        "id": "opener_table_remembers",
        "horizon": "Chummer6 Horizons",
        "title": "The Table Remembers",
        "body": "A dark table links runners, rules, places, briefings, and city state into one evidence-backed campaign interface.",
        "proof": "Future lanes, not feature promises",
        "voiceover": "A run does not end when the dice stop. Chummer6 carries builds, rules, places, briefings, and world state with proof.",
        "onscreen": "Chummer6 Horizons / Future lanes, not feature promises",
        "magicfit_visual": "Dark tabletop with dice, character sheets, laptop, and city map; neon AR lines connect runner, GM, rules, and campaign state.",
        "accent": (82, 204, 255),
    },
    {
        "id": "proof_boundary",
        "horizon": "Release Truth",
        "title": "Proof Before Promise",
        "body": "The promo names horizons as direction. Live release truth, downloads, status, and receipts stay the authority.",
        "proof": "Current proof outranks trailer energy",
        "voiceover": "These are horizon lanes, not claims that unfinished work is shipped. Current proof stays in charge.",
        "onscreen": "Proof boundary / Direction, not shelf truth",
        "magicfit_visual": "Trailer card pauses over live-proof receipts, download truth, status checkmarks, and a visible future-claim boundary.",
        "accent": (255, 197, 92),
    },
    {
        "id": "nexus_pan",
        "horizon": "NEXUS-PAN",
        "title": "Shared State Survives Device Churn",
        "body": "A reconnecting player sees laptop, tablet, and phone converge while conflict turns into recovered state.",
        "proof": "Reconnects and conflicts stay visible",
        "voiceover": "NEXUS-PAN keeps the session calm when devices drift: reconnects, status, conflicts, and recovery you can understand.",
        "onscreen": "NEXUS-PAN / Shared state survives device churn",
        "magicfit_visual": "Player reconnects mid-session; multiple devices synchronize; red conflict warning resolves to green recovered state.",
        "accent": (123, 220, 255),
    },
    {
        "id": "alice",
        "horizon": "ALICE",
        "title": "Build Mentor With Receipts",
        "body": "Two runner builds compare tradeoffs for gear budget, role fit, legality, and survivability before table pressure hits.",
        "proof": "Build advice must cite its reasons",
        "voiceover": "ALICE checks builds before they break at the table: what is legal, what is fragile, and what really fits the role.",
        "onscreen": "ALICE / Build mentor with receipts",
        "magicfit_visual": "Two holographic runner build cards compare legality, role fit, budget, survivability, and cited receipt markers.",
        "accent": (190, 150, 255),
    },
    {
        "id": "karma_forge",
        "horizon": "KARMA FORGE",
        "title": "Change The Table. Keep The Trust.",
        "body": "A house-rule package shows a diff, affected runners, dependency posture, and rollback before anything becomes table truth.",
        "proof": "House rules need history and rollback",
        "voiceover": "KARMA FORGE turns house rules into controlled packages: no pinned-message chaos, just changes with history and impact.",
        "onscreen": "KARMA FORGE / Change the table. Keep the trust.",
        "magicfit_visual": "GM activates a house-rule package; UI shows changed categories, affected runners, dependency warning, and rollback available.",
        "accent": (255, 128, 128),
    },
    {
        "id": "jackpoint",
        "horizon": "JACKPOINT",
        "title": "Briefings And Dossiers Without Making Things Up",
        "body": "Confirmed campaign truth becomes dossiers, recaps, and player-safe briefings with source path and spoiler posture.",
        "proof": "Recaps stay source-bound",
        "voiceover": "JACKPOINT turns campaign truth into briefings, dossiers, and recaps: polished, spoiler-safe, and source-bound.",
        "onscreen": "JACKPOINT / Briefings and dossiers with source path",
        "magicfit_visual": "Post-run evidence board, dossier pages, recap cards, audio waveform, and player-safe versus GM-only spoiler toggle.",
        "accent": (174, 190, 255),
    },
    {
        "id": "runsite",
        "horizon": "RUNSITE",
        "title": "Mission Spaces, Made Legible",
        "body": "Mission locations expose maps, routes, hotspots, cameras, escape paths, and separate player and GM layers.",
        "proof": "Location truth has bounded layers",
        "voiceover": "RUNSITE makes dangerous places readable before they get loud: maps, routes, hotspots, and separate player and GM views.",
        "onscreen": "RUNSITE / Mission spaces, made legible",
        "magicfit_visual": "Explorable safehouse blueprint with hotspots, camera cones, escape routes, hidden doors, and astral layer as GM-only overlay.",
        "accent": (104, 232, 174),
    },
    {
        "id": "runbook_press",
        "horizon": "RUNBOOK PRESS",
        "title": "Living Campaign Truth Becomes Books",
        "body": "Confirmed material flows into primers, district guides, GM appendices, and web or PDF exports without losing provenance.",
        "proof": "Books come from confirmed material",
        "voiceover": "RUNBOOK PRESS builds primers, handbooks, and campaign books from confirmed material instead of copy-paste from ten tools.",
        "onscreen": "RUNBOOK PRESS / Campaign truth becomes books",
        "magicfit_visual": "Campaign data assembles into a book layout: table of contents, district guide, GM appendix, PDF and web export cards.",
        "accent": (255, 221, 118),
    },
    {
        "id": "table_pulse",
        "horizon": "TABLE PULSE",
        "title": "Heat, Reactions, Aftermath - Bounded",
        "body": "Live pressure creates GM-controlled reaction packets while private after-action coaching remains consent-bounded.",
        "proof": "No player scoring dashboard",
        "voiceover": "TABLE PULSE separates live pressure from private aftermath: reactions in play, coaching after play, always bounded.",
        "onscreen": "TABLE PULSE / Heat, reactions, aftermath - bounded",
        "magicfit_visual": "World heat rises during a scene; GM receives a reaction packet; cut to private after-action packet, no player score.",
        "accent": (255, 156, 104),
    },
    {
        "id": "black_ledger",
        "horizon": "BLACK LEDGER",
        "title": "The City Remembers",
        "body": "Runs create consequences, faction pressure moves, district heat changes, and new jobs emerge from what happened.",
        "proof": "World motion follows receipts",
        "voiceover": "BLACK LEDGER lets the city remember. Runs create consequences, factions move, and new jobs grow from what actually happened.",
        "onscreen": "BLACK LEDGER / The city remembers",
        "magicfit_visual": "Neon city map with district heat, faction moves, open jobs; completed run changes a marker and starts a news ticker.",
        "accent": (112, 226, 190),
    },
    {
        "id": "community_hub",
        "horizon": "COMMUNITY HUB",
        "title": "Find The Table. Close The Loop.",
        "body": "Open runs, dossier preflight, rules posture, roster fit, scheduling, and closeout stay tied to Chummer truth.",
        "proof": "Community flow keeps product truth",
        "voiceover": "COMMUNITY HUB helps people reach the table: open runs, preflight, rules, roster, scheduling, and closeout without losing Chummer truth.",
        "onscreen": "COMMUNITY HUB / Find the table. Close the loop.",
        "magicfit_visual": "Player finds an open run, applies with runner dossier, preflight turns green, calendar handoff opens a neutral meeting door.",
        "accent": (132, 238, 132),
    },
    {
        "id": "finale_all_horizons",
        "horizon": "Chummer6 Horizons",
        "title": "Nine Horizons. One Boundary.",
        "body": "All horizon cards orbit the table as the table becomes a living city map, then returns to current proof.",
        "proof": "Build clearly. Run reliably. Carry the campaign forward.",
        "voiceover": "Nine horizons. One promise: keep the campaign explainable, from the first build to the world that remembers.",
        "onscreen": "Chummer6 Horizons / Build clearly. Run reliably. Carry the campaign forward.",
        "magicfit_visual": "All nine horizon cards orbit the tabletop; camera rises as table becomes a city map and resolves into Chummer6 interface.",
        "accent": (255, 238, 166),
    },
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def probe(path: Path) -> dict[str, object]:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def scene_timing() -> list[tuple[float, float]]:
    start = 0.0
    rows: list[tuple[float, float]] = []
    for duration in SCENE_DURATIONS:
        end = start + duration
        rows.append((start, end))
        start = end
    if abs(start - TARGET_SECONDS) > 0.001:
        raise SystemExit(f"scene durations must sum to {TARGET_SECONDS}; got {start}")
    return rows


def draw_scene(index: int, scene: dict[str, object]) -> Path:
    title = str(scene["title"])
    body = str(scene["body"])
    proof = str(scene["proof"])
    accent = tuple(scene["accent"])  # type: ignore[arg-type]
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), (6, 9, 14))
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        mix = y / HEIGHT
        r = int(7 + mix * 17 + accent[0] * 0.06)
        g = int(10 + mix * 15 + accent[1] * 0.04)
        b = int(16 + mix * 25 + accent[2] * 0.05)
        draw.line((0, y, WIDTH, y), fill=(r, g, b))

    for ring in range(9):
        radius = 120 + ring * 58
        color = tuple(max(0, min(255, int(channel * (0.18 + ring * 0.018)))) for channel in accent)
        draw.ellipse((WIDTH - 360 - radius, 90 - radius, WIDTH - 360 + radius, 90 + radius), outline=color, width=2)

    for x in range(-160, WIDTH + 160, 92):
        offset = int(34 * math.sin(index + x / 130))
        draw.line((x, HEIGHT, x + 280 + offset, 0), fill=(24, 38, 52), width=1)

    draw.rounded_rectangle((72, 76, 1208, 636), radius=8, fill=(7, 13, 22), outline=(58, 75, 91), width=2)
    draw.rectangle((72, 76, 1208, 132), fill=(10, 20, 32))
    draw.text((104, 94), f"SCENE {index + 1:02d} / 12", fill=accent, font=MONO_FONT)
    draw.text((940, 94), "FUTURE LANE / PROOF-BOUNDED", fill=(214, 226, 235), font=SMALL_FONT)

    draw.text((104, 164), str(scene["horizon"]), fill=accent, font=LABEL_FONT)
    title_y = 196
    title_lines = wrap_text(draw, title, TITLE_FONT, 650)
    for line in title_lines:
        draw.text((104, title_y), line, fill=(255, 255, 255), font=TITLE_FONT)
        title_y += 62
    y = title_y + 4
    for line in wrap_text(draw, body, SUBTITLE_FONT, 650):
        draw.text((108, y), line, fill=(213, 226, 238), font=SUBTITLE_FONT)
        y += 38

    draw.rounded_rectangle((106, 472, 742, 568), radius=8, fill=(13, 24, 35), outline=accent, width=2)
    draw.text((132, 496), proof, fill=accent, font=LABEL_FONT)
    y = 522
    for line in wrap_text(draw, "Bounded future claim; compare with live proof before release language tightens.", SMALL_FONT, 560):
        draw.text((132, y), line, fill=(190, 204, 214), font=SMALL_FONT)
        y += 22

    panel_x = 805
    for row, label in enumerate(("current proof", "readiness label", "next honest route", "receipt boundary")):
        y0 = 206 + row * 74
        draw.rounded_rectangle((panel_x, y0, 1134, y0 + 46), radius=7, fill=(15, 27, 40), outline=(54, 70, 86), width=1)
        draw.rectangle((panel_x, y0, panel_x + 10 + row * 16, y0 + 46), fill=accent)
        draw.text((panel_x + 30, y0 + 13), label.upper(), fill=(225, 235, 242), font=SMALL_FONT)

    path = BUILD_DIR / f"{index + 1:02d}_{str(scene['id'])}.png"
    image.save(path)
    return path


def format_ts(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def write_vtt() -> None:
    lines = ["WEBVTT", ""]
    for index, ((start, end), scene) in enumerate(zip(scene_timing(), SCENES, strict=True), start=1):
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", str(scene["voiceover"]), ""])
    TARGET_VTT.write_text("\n".join(lines), encoding="utf-8")


def build_mp4(slides: list[Path]) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    for index, slide in enumerate(slides):
        duration = SCENE_DURATIONS[index]
        inputs.extend(["-loop", "1", "-t", f"{duration:.6f}", "-i", str(slide)])
        frames = int(round(duration * FPS))
        zoom_expr = "1+0.045*on/{frames}".format(frames=frames)
        pan_x = "(iw-iw/zoom)/2"
        pan_y = "(ih-ih/zoom)/2"
        filters.append(
            f"[{index}:v]scale=1440:810,zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p[v{index}]"
        )
    chain = "[v0]"
    elapsed = SCENE_DURATIONS[0]
    for index in range(1, len(slides)):
        out = f"[x{index}]"
        offset = elapsed - TRANSITION_SECONDS
        filters.append(
            f"{chain}[v{index}]xfade=transition=fade:duration={TRANSITION_SECONDS:.3f}:offset={offset:.6f}{out}"
        )
        chain = out
        elapsed += SCENE_DURATIONS[index] - TRANSITION_SECONDS
    filters.append(
        "aevalsrc='0.05*sin(2*PI*49*t)+0.028*sin(2*PI*98*t)+"
        "0.016*sin(2*PI*(196+14*sin(2*PI*0.05*t))*t)':"
        f"s=48000:d={TARGET_SECONDS:.3f},"
        "afade=t=in:st=0:d=1.2,afade=t=out:st=87.5:d=2.5[a]"
    )
    run(
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        chain,
        "-map",
        "[a]",
        "-t",
        f"{TARGET_SECONDS:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(TARGET_MP4),
    )


def validate_outputs() -> None:
    for path in (TARGET_MP4, TARGET_WEBM, TARGET_POSTER, TARGET_VTT, TARGET_RECEIPT):
        if not path.is_file():
            raise SystemExit(f"missing Every Wonder Horizon promo output: {path}")
    if not TARGET_VTT.read_text(encoding="utf-8").startswith("WEBVTT\n"):
        raise SystemExit("Every Wonder Horizon captions are not WEBVTT")
    caption_segments = sum(1 for line in TARGET_VTT.read_text(encoding="utf-8").splitlines() if "-->" in line)
    if caption_segments != 12:
        raise SystemExit(f"Every Wonder Horizon captions must contain 12 segments; got {caption_segments}")
    receipt = json.loads(TARGET_RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("status") != "published":
        raise SystemExit("Every Wonder Horizon receipt is not published")
    if receipt.get("asset_id") != ASSET_ID:
        raise SystemExit("Every Wonder Horizon receipt asset_id mismatch")
    if receipt.get("scene_count") != 12:
        raise SystemExit("Every Wonder Horizon receipt does not prove 12 scenes")
    if receipt.get("magicfit_claim_allowed") is not False:
        raise SystemExit("Every Wonder Horizon receipt must not claim MagicFit without provider proof")
    if receipt.get("horizon_claim_boundary") != "directional_future_shelf_not_current_release_truth":
        raise SystemExit("Every Wonder Horizon receipt is missing the future-claim boundary")
    scene_rows = receipt.get("production_scenes") or []
    if not isinstance(scene_rows, list) or len(scene_rows) != 12:
        raise SystemExit("Every Wonder Horizon receipt must retain the 12-scene production sheet")
    expected_scene_ids = [str(scene["id"]) for scene in SCENES]
    receipt_scene_ids = [str(scene.get("id") or "") for scene in scene_rows if isinstance(scene, dict)]
    if receipt_scene_ids != expected_scene_ids:
        raise SystemExit("Every Wonder Horizon receipt scene ids do not match the production sheet")
    production_sheet_path = Path(str(receipt.get("production_sheet") or ""))
    if not production_sheet_path.is_file():
        raise SystemExit("Every Wonder Horizon production sheet is missing")
    production_sheet = json.loads(production_sheet_path.read_text(encoding="utf-8"))
    if production_sheet.get("scene_count") != 12 or production_sheet.get("target_duration_seconds") != TARGET_SECONDS:
        raise SystemExit("Every Wonder Horizon production sheet has the wrong scene count or duration")
    if "No official Shadowrun logos" not in str(production_sheet.get("negative_prompt") or ""):
        raise SystemExit("Every Wonder Horizon production sheet is missing the IP-safety negative prompt")
    mp4 = probe(TARGET_MP4)
    streams = mp4.get("streams") or []
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise SystemExit("Every Wonder Horizon MP4 has no video stream")
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise SystemExit("Every Wonder Horizon MP4 has no audio stream")
    duration = float(dict(mp4.get("format") or {}).get("duration") or 0.0)
    if duration < TARGET_SECONDS - 0.5:
        raise SystemExit(f"Every Wonder Horizon MP4 too short: {duration:.3f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the Every Wonder Horizon 90-second promo.")
    parser.add_argument("--check", action="store_true", help="verify public outputs without rebuilding")
    args = parser.parse_args()

    if args.check:
        validate_outputs()
        print("EVERY_WONDER_HORIZON_PROMO_READY")
        return 0

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    slides = [draw_scene(index, scene) for index, scene in enumerate(SCENES)]
    build_mp4(slides)
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(TARGET_MP4),
        "-c:v",
        "libvpx-vp9",
        "-crf",
        "34",
        "-b:v",
        "0",
        "-c:a",
        "libopus",
        "-b:a",
        "112k",
        str(TARGET_WEBM),
    )
    # Use a clean authored frame for the poster. Sampling the encoded reel can land
    # inside an xfade and produce unreadable double exposure.
    Image.open(slides[0]).save(TARGET_POSTER)
    write_vtt()
    timings = scene_timing()
    production_scenes = [
        {
            "scene_number": index,
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "duration_seconds": round(end - start, 3),
            "id": str(scene["id"]),
            "horizon": str(scene["horizon"]),
            "title": str(scene["title"]),
            "voiceover": str(scene["voiceover"]),
            "on_screen_text": str(scene["onscreen"]),
            "magicfit_visual_prompt": str(scene["magicfit_visual"]),
        }
        for index, ((start, end), scene) in enumerate(zip(timings, SCENES, strict=True), start=1)
    ]
    production_sheet = {
        "title": PRODUCTION_TITLE,
        "asset_id": ASSET_ID,
        "target_duration_seconds": TARGET_SECONDS,
        "scene_count": len(SCENES),
        "global_magicfit_prompt": GLOBAL_MAGICFIT_PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "proof_constraints": list(PROOF_CONSTRAINTS),
        "scenes": production_scenes,
    }
    production_sheet_path = BUILD_DIR / "EVERY_WONDER_HORIZON_12_SCENE_PRODUCTION_SHEET.generated.json"
    production_sheet_path.write_text(json.dumps(production_sheet, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "generated_at_utc": utc_now(),
        "status": "published",
        "asset_id": ASSET_ID,
        "render_mode": "first_party_motion_storyboard_90s",
        "provider_claim": "none",
        "magicfit_claim_allowed": False,
        "magicfit_provider_required_before_claim": True,
        "horizon_claim_boundary": "directional_future_shelf_not_current_release_truth",
        "scene_count": len(SCENES),
        "duration_seconds": TARGET_SECONDS,
        "title": PRODUCTION_TITLE,
        "global_magicfit_prompt": GLOBAL_MAGICFIT_PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "proof_constraints": list(PROOF_CONSTRAINTS),
        "production_sheet": str(production_sheet_path),
        "production_scenes": production_scenes,
        "public_files": {
            "mp4": str(TARGET_MP4),
            "webm": str(TARGET_WEBM),
            "poster": str(TARGET_POSTER),
            "captions": str(TARGET_VTT),
        },
        "mp4_probe": probe(TARGET_MP4),
    }
    TARGET_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    validate_outputs()
    print(TARGET_RECEIPT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
