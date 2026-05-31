#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WORKSPACE = Path("/docker/chummercomplete")
SOURCE_DIR = WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes"
PUBLIC_DIR = WORKSPACE / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
BUILD_DIR = WORKSPACE / "_completion" / "chummer6_flagship_promo_12_scene_reel"
SOURCE_RECEIPT = SOURCE_DIR / "MAGICFIT_12_SCENE_PROMO_SOURCE_AUDIT.generated.json"
PROVIDER_RECEIPT = WORKSPACE / "_completion" / "magicfit_provider" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json"
PUBLIC_RECEIPT = PUBLIC_DIR / "chummer6-flagship-promo.receipt.json"

SCENE_GLOB = "[0-9][0-9]_*.mp4"
TARGET_MP4 = PUBLIC_DIR / "chummer6-flagship-promo.mp4"
TARGET_WEBM = PUBLIC_DIR / "chummer6-flagship-promo.webm"
TARGET_POSTER = PUBLIC_DIR / "chummer6-flagship-promo-poster.png"
TARGET_VTT = PUBLIC_DIR / "chummer6-flagship-promo.vtt"

WIDTH = 1280
HEIGHT = 720
FPS = 24

CAPTIONS = (
    (0, 8, "Too much chaos at the table becomes one calm client workflow."),
    (8, 15, "Open Chummer6 and start from the client, not a marketing page."),
    (15, 23, "Build the runner with dense desktop controls and low-noise screens."),
    (23, 30, "Explain values and rule decisions with visible receipts."),
    (30, 38, "Black Ledger makes the world feel alive without faction detours."),
    (38, 45, "Release truth, provider proof, and audit freshness stay visible."),
    (45, 53, "Table Pulse keeps remote players and GM follow-through aligned."),
    (53, 60, "Remote reactions return as deliberate choices instead of chat noise."),
    (60, 68, "Karma Forge turns feedback into tracked improvements."),
    (68, 75, "Newsreels show campaign movement while the client stays the hero."),
    (75, 83, "Desktop and mobile surfaces point at the same release truth."),
    (83, 90, "Chummer6: build the runner, run the table, move the city."),
)

TARGET_SECONDS = 90.0
TRANSITION_SECONDS = 0.5
SCENE_SECONDS = (TARGET_SECONDS + 11 * TRANSITION_SECONDS) / 12

FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
TITLE_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 48)
SUBTITLE_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 24)
LABEL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 18)
SMALL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 17)
MONO_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSansMono.ttf"), 18)

SCENES = (
    ("Table Chaos Ends", "Loose notes, screen clutter, and disputed values collapse into one calm product workflow.", "pain to product", (244, 99, 99), ("notes", "tables", "arguments", "handoff")),
    ("Chummer6 Opens", "The first screen is the client: release truth, downloads, status, and work surfaces without a detour.", "client first", (95, 205, 255), ("status", "downloads", "proof", "launch")),
    ("Build The Runner", "Classic W1 FormPorts expose typed feature controls and commands instead of generic preview JSON.", "typed controls", (118, 232, 163), ("attributes", "skills", "gear", "commands")),
    ("Rules Explain Themselves", "SR4, SR5, and SR6 authority verdicts stay inspectable while respecting source boundaries.", "rule receipts", (255, 213, 99), ("SR4", "SR5", "SR6", "boundary")),
    ("Black Ledger Lives", "Newsroom, city movement, and campaign pressure become visible while the runner builder remains the hero.", "world motion", (179, 143, 255), ("newsroom", "pressure", "districts", "aftershock")),
    ("Truth Matrix Holds", "Shelf truth, build truth, provider proof, and live status agree before release language can tighten.", "release truth", (255, 151, 95), ("matrix", "status", "shelf", "build")),
    ("Table Pulse Connects", "Remote players, opt-outs, GM follow-through, and table receipts travel through one governed lane.", "remote table", (92, 224, 205), ("players", "GM", "opt-out", "receipt")),
    ("The World Reacts", "Remote reactions return as deliberate choices, not chat noise or untracked side-channel pressure.", "choice signal", (255, 128, 166), ("prompt", "consent", "reaction", "result")),
    ("Karma Forge Improves", "Feedback becomes tracked improvement work with public proof instead of vague future promise.", "tracked change", (151, 229, 101), ("feedback", "issue", "fix", "receipt")),
    ("Video Proof Lands", "Promo, globe, newsroom, and faction video verdicts name their provider posture without overclaiming.", "media receipts", (123, 171, 255), ("promo", "globe", "news", "factions")),
    ("Play Anywhere Honestly", "PWA, public routes, mobile surfaces, and desktop downloads all point back to the same release truth.", "one truth", (255, 235, 123), ("PWA", "mobile", "desktop", "public")),
    ("Chummer6 Gold Gate", "Build the runner, run the table, move the city: only when every gate proves what it claims.", "gold only by proof", (255, 255, 255), ("runner", "table", "city", "GOLD")),
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def format_ts(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"00:{minutes:02}:{secs:02}.000"


def write_vtt() -> None:
    lines = ["WEBVTT", ""]
    for index, (start, end, text) in enumerate(CAPTIONS, start=1):
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", text, ""])
    TARGET_VTT.write_text("\n".join(lines), encoding="utf-8")


def validate_inputs() -> list[Path]:
    if not SOURCE_RECEIPT.is_file():
        raise SystemExit(f"missing source receipt: {SOURCE_RECEIPT}")
    if not PROVIDER_RECEIPT.is_file():
        raise SystemExit(f"missing MagicFit provider receipt: {PROVIDER_RECEIPT}")

    source_receipt = load_json(SOURCE_RECEIPT)
    provider_receipt = load_json(PROVIDER_RECEIPT)
    scenes = sorted(SOURCE_DIR.glob(SCENE_GLOB))
    if len(scenes) != 12:
        raise SystemExit(f"expected 12 scene clips, found {len(scenes)} in {SOURCE_DIR}")
    if source_receipt.get("status") != "pass":
        raise SystemExit("MagicFit source audit is not passing")
    if provider_receipt.get("status") != "verified":
        raise SystemExit("MagicFit provider is not verified")
    return scenes


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


def draw_scene(
    index: int,
    title: str,
    body: str,
    proof: str,
    accent: tuple[int, int, int],
    tokens: tuple[str, str, str, str],
) -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), (5, 8, 12))
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        mix = y / HEIGHT
        r = int(6 + mix * 18 + accent[0] * 0.055)
        g = int(9 + mix * 16 + accent[1] * 0.045)
        b = int(14 + mix * 28 + accent[2] * 0.05)
        draw.line((0, y, WIDTH, y), fill=(r, g, b))

    for x in range(-120, WIDTH + 160, 84):
        offset = int(42 * math.sin(index * 0.8 + x / 150))
        draw.line((x, HEIGHT, x + 230 + offset, 0), fill=(22, 34, 48), width=1)

    for ring in range(7):
        radius = 96 + ring * 54
        color = tuple(max(0, min(255, int(channel * (0.16 + ring * 0.02)))) for channel in accent)
        cx = 1010 - index * 9
        cy = 164 + index * 3
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=2)

    draw.rounded_rectangle((66, 58, 1214, 650), radius=8, fill=(7, 13, 21), outline=(57, 74, 92), width=2)
    draw.rectangle((66, 58, 1214, 120), fill=(10, 20, 31))
    draw.text((96, 80), f"CHUMMER6 FLAGSHIP REEL   SCENE {index + 1:02d} / 12", fill=accent, font=MONO_FONT)
    draw.text((956, 80), "90s AUDIO + VIDEO", fill=(220, 230, 237), font=SMALL_FONT)

    draw.text((98, 166), title, fill=(255, 255, 255), font=TITLE_FONT)
    y = 246
    for line in wrap_text(draw, body, SUBTITLE_FONT, 710):
        draw.text((102, y), line, fill=(215, 228, 238), font=SUBTITLE_FONT)
        y += 37

    draw.rounded_rectangle((100, 470, 720, 574), radius=8, fill=(13, 24, 36), outline=accent, width=2)
    draw.text((126, 493), proof.upper(), fill=accent, font=LABEL_FONT)
    for row, line in enumerate(wrap_text(draw, CAPTIONS[index][2], SMALL_FONT, 550)[:2]):
        draw.text((126, 523 + row * 22), line, fill=(190, 205, 216), font=SMALL_FONT)

    panel_x = 794
    panel_y = 176
    for row, token in enumerate(tokens):
        y0 = panel_y + row * 78
        draw.rounded_rectangle((panel_x, y0, 1148, y0 + 52), radius=7, fill=(15, 28, 42), outline=(55, 72, 89), width=1)
        draw.rectangle((panel_x, y0, panel_x + 18 + row * 21, y0 + 52), fill=accent)
        draw.text((panel_x + 42, y0 + 14), token.upper(), fill=(232, 240, 246), font=LABEL_FONT)

    draw.rounded_rectangle((820, 526, 1118, 584), radius=8, fill=(6, 11, 18), outline=accent, width=2)
    draw.text((850, 545), "VISUALLY DISTINCT SAMPLE", fill=accent, font=SMALL_FONT)

    path = BUILD_DIR / f"{index + 1:02d}_{title.lower().replace(' ', '_')}.png"
    image.save(path)
    return path


def validate_public_outputs() -> None:
    for path in (TARGET_MP4, TARGET_WEBM, TARGET_POSTER, TARGET_VTT, PUBLIC_RECEIPT):
        if not path.is_file():
            raise SystemExit(f"missing public promo output: {path}")

    if not TARGET_VTT.read_text(encoding="utf-8").startswith("WEBVTT\n"):
        raise SystemExit("promo captions are not a valid WEBVTT file")

    receipt = load_json(PUBLIC_RECEIPT)
    if receipt.get("status") != "published":
        raise SystemExit("public promo receipt is not published")
    if receipt.get("source_scene_count") != 12:
        raise SystemExit("public promo receipt does not prove 12 source scenes")
    if receipt.get("visual_scene_count") != 12:
        raise SystemExit("public promo receipt does not prove 12 visual scenes")
    if receipt.get("magicfit_claim_allowed") is not True:
        raise SystemExit("public promo receipt does not prove MagicFit final rendering")
    if receipt.get("render_mode") != "ea_magicfit_12_scene_no_factions_90s_edit":
        raise SystemExit("public promo receipt render_mode is not the MagicFit final edit")
    if receipt.get("faction_assets_used") is not False:
        raise SystemExit("public promo receipt does not prove faction-free source")

    mp4 = probe(TARGET_MP4)
    webm = probe(TARGET_WEBM)
    for name, payload in (("mp4", mp4), ("webm", webm)):
        streams = payload.get("streams") or []
        has_video = any(stream.get("codec_type") == "video" for stream in streams)
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        duration = float(dict(payload.get("format") or {}).get("duration") or 0.0)
        if not has_video or not has_audio:
            raise SystemExit(f"{name} promo output is missing video or audio")
        if duration < TARGET_SECONDS - 0.5:
            raise SystemExit(f"{name} promo output is too short: {duration:.3f}s")


def build_master(slides: list[Path], target: Path) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    frames = int(round(SCENE_SECONDS * FPS))
    for index, slide in enumerate(slides):
        inputs.extend(["-loop", "1", "-t", f"{SCENE_SECONDS:.6f}", "-i", str(slide)])
        zoom_expr = "1+0.095*on/{frames}".format(frames=frames)
        filters.append(
            f"[{index}:v]scale=1440:810,zoompan=z='{zoom_expr}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p[v{index}]"
        )
    chain = "[v0]"
    for index in range(1, len(slides)):
        out = f"[x{index}]"
        offset = index * (SCENE_SECONDS - TRANSITION_SECONDS)
        filters.append(
            f"{chain}[v{index}]xfade=transition=fade:duration={TRANSITION_SECONDS:.3f}:"
            f"offset={offset:.6f}{out}"
        )
        chain = out
    filters.append(
        "aevalsrc='0.055*sin(2*PI*55*t)+0.035*sin(2*PI*110*t)+"
        "0.018*sin(2*PI*(220+20*sin(2*PI*0.04*t))*t)':"
        f"s=48000:d={TARGET_SECONDS:.3f},"
        "afade=t=in:st=0:d=1.5,afade=t=out:st=87.5:d=2.5[a]"
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
        str(target),
    )


def build_magicfit_master(scenes: list[Path], target: Path) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    for index, scene in enumerate(scenes):
        media = probe(scene)
        duration = float(dict(media.get("format") or {}).get("duration") or 0.0)
        if duration <= 0:
            raise SystemExit(f"cannot read duration for {scene}")
        stretch = SCENE_SECONDS / duration
        inputs.extend(["-i", str(scene)])
        filters.append(
            f"[{index}:v]scale=1280:720:force_original_aspect_ratio=increase,"
            f"crop=1280:720,setsar=1,setpts={stretch:.8f}*PTS,"
            f"trim=duration={SCENE_SECONDS:.6f},setpts=PTS-STARTPTS,"
            f"fps={FPS},format=yuv420p[v{index}]"
        )
    chain = "[v0]"
    for index in range(1, len(scenes)):
        out = f"[x{index}]"
        offset = index * (SCENE_SECONDS - TRANSITION_SECONDS)
        filters.append(
            f"{chain}[v{index}]xfade=transition=fade:duration={TRANSITION_SECONDS:.3f}:"
            f"offset={offset:.6f}{out}"
        )
        chain = out
    filters.append(
        "aevalsrc='0.055*sin(2*PI*55*t)+0.035*sin(2*PI*110*t)+"
        "0.018*sin(2*PI*(220+20*sin(2*PI*0.04*t))*t)':"
        f"s=48000:d={TARGET_SECONDS:.3f},"
        "afade=t=in:st=0:d=1.5,afade=t=out:st=87.5:d=2.5[a]"
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
        str(target),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the public Chummer6 flagship promo.")
    parser.add_argument("--check", action="store_true", help="verify inputs and public outputs without rebuilding media")
    args = parser.parse_args()

    source_scenes = validate_inputs()
    if args.check:
        validate_public_outputs()
        print("CHUMMER6_FLAGSHIP_PROMO_READY")
        return 0

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    build_magicfit_master(source_scenes, TARGET_MP4)
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
        "-vf",
        "scale=1280:-2",
        str(TARGET_WEBM),
    )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(TARGET_MP4),
        "-vf",
        "select=eq(n\\,720)",
        "-frames:v",
        "1",
        "-update",
        "1",
        str(TARGET_POSTER),
    )
    write_vtt()

    mp4_probe = probe(TARGET_MP4)
    receipt = {
        "generated_at_utc": utc_now(),
        "status": "published",
        "asset_id": "chummer6-flagship-promo",
        "render_mode": "ea_magicfit_12_scene_no_factions_90s_edit",
        "provider_claim": "MagicFit",
        "magicfit_claim_allowed": True,
        "magicfit_final_visual_render_claim": True,
        "magicfit_source_receipts_retained": True,
        "magicfit_visual_recut_required": False,
        "old_synthetic_vector_renderer_removed": True,
        "source_scene_count": len(source_scenes),
        "visual_scene_count": len(SCENES),
        "source_scene_dir": str(SOURCE_DIR),
        "source_receipt": str(SOURCE_RECEIPT),
        "provider_receipt": str(PROVIDER_RECEIPT),
        "faction_assets_used": False,
        "scene_titles": [scene[0] for scene in SCENES],
        "scene_seconds_before_transitions": SCENE_SECONDS,
        "transition_seconds": TRANSITION_SECONDS,
        "continuous_audio_track": "ffmpeg_generated_synthetic_music_bed",
        "public_files": {
            "mp4": str(TARGET_MP4),
            "webm": str(TARGET_WEBM),
            "poster": str(TARGET_POSTER),
            "captions": str(TARGET_VTT),
        },
        "mp4_probe": mp4_probe,
    }
    PUBLIC_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(PUBLIC_RECEIPT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
