#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


WORKSPACE = Path("/docker/chummercomplete")
SOURCE_ROOT = WORKSPACE / "_completion" / "horizon_flagship_reels_20260602" / "videos"
BUILD_DIR = WORKSPACE / "_completion" / "origin_dossier_fallback_reel"
SOURCE_IMAGE = WORKSPACE / "Chummer6" / "assets" / "horizons" / "origin-dossier.png"
MAGICFIT_STATUS = WORKSPACE / "_completion" / "origin_dossier_horizon_20260618" / "ORIGIN_DOSSIER_MAGICFIT_RENDER_STATUS.generated.json"

ASSET_ID = "origin_dossier_90s_deepdive"
TARGET_MP4 = SOURCE_ROOT / f"{ASSET_ID}.mp4"
TARGET_VTT = SOURCE_ROOT / f"{ASSET_ID}.vtt"
TARGET_RECEIPT = BUILD_DIR / "ORIGIN_DOSSIER_FALLBACK_REEL.generated.json"

WIDTH = 1280
HEIGHT = 720
FPS = 24
TARGET_SECONDS = 90.0

FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
TITLE_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 54)
BODY_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 26)
LABEL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 20)
SMALL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 18)


SCENES: tuple[dict[str, str], ...] = (
    {
        "title": "Where The Sheet Stops",
        "body": "A runner can be legal and still feel unfinished. Origin Dossier starts with that gap.",
        "tag": "BUILD -> PERSON",
        "voiceover": "A runner can be legal and still feel unfinished. Origin Dossier starts where the sheet stops.",
    },
    {
        "title": "GM Steer Stays Visible",
        "body": "Clinic favors, restricted parts, debts, scars, and table constraints stay reviewable.",
        "tag": "VISIBLE CONTEXT",
        "voiceover": "The GM's steer stays visible. A clinic favor becomes pressure, not hidden gear.",
    },
    {
        "title": "Draft, Then Approve",
        "body": "Story is proposed as canon only after the player and GM review what it means.",
        "tag": "REVIEW FIRST",
        "voiceover": "The draft is not table truth until the player and GM approve what becomes canon.",
    },
    {
        "title": "Consequences, Not Decoration",
        "body": "Contacts, enemies, debts, secrets, beliefs, and scars become usable campaign memory.",
        "tag": "LIFE WITH CONSEQUENCES",
        "voiceover": "Contacts, enemies, debts, secrets, beliefs, and scars become campaign memory the table can use.",
    },
    {
        "title": "Media Is Downstream",
        "body": "Portraits, scenes, narration, video packets, and audiobook requests support the dossier.",
        "tag": "MEDIA SUPPORTS MEMORY",
        "voiceover": "Portraits, scenes, narration, video packets, and audiobook requests are downstream media.",
    },
    {
        "title": "Mechanics Stay In Chummer",
        "body": "A story exception never silently applies ware, nuyen, qualities, magic, or legality.",
        "tag": "NO SILENT RULES",
        "voiceover": "Mechanics stay in Chummer. Dossier prose never silently applies ware, money, qualities, magic, or legality.",
    },
    {
        "title": "ALICE Reads Approved Canon",
        "body": "ALICE can use the origin later, but it still cites Chummer-owned mechanics truth.",
        "tag": "ALICE WITH BOUNDARIES",
        "voiceover": "ALICE can read approved origin canon later, while rules and build truth remain separate.",
    },
    {
        "title": "Reject Media Safely",
        "body": "A bad portrait, scene, narration, or video can be rejected without harming the sheet.",
        "tag": "SAFE REJECTION",
        "voiceover": "A weak portrait, scene, narration, or video can be rejected without harming the runner.",
    },
    {
        "title": "The Table Remembers",
        "body": "The approved dossier gives the crew a person to bring into the next job.",
        "tag": "SHARED MEMORY",
        "voiceover": "The approved dossier gives the crew a person to bring into the next job.",
    },
    {
        "title": "Origin Dossier",
        "body": "Not a backstory pasted on top. A sourced dossier the table can trust.",
        "tag": "THE LIFE BEHIND THE STATS",
        "voiceover": "Not a backstory pasted on top. A sourced dossier the table can trust.",
    },
)


NARRATION = (
    "Origin Dossier starts where the sheet stops. "
    "A runner can be legal and still feel unfinished. The player has attributes, gear, chrome, maybe magic, "
    "but no debt, no scar, no reason the crew should care. "
    "Origin Dossier turns approved table context into a life with consequences. The GM's steer stays visible. "
    "A clinic favor becomes pressure. A restricted part becomes a story exception to review, not hidden gear. "
    "The player and GM approve what becomes canon. Then the bundle can carry portraits, scene ideas, narration, "
    "audiobook requests, and video packets downstream. "
    "ALICE may read that approved canon later, but it never treats story as rules permission. Mechanics stay in Chummer. "
    "The media helps the table remember who this runner is. It can be rejected without harming the sheet. "
    "That is the promise: not a backstory pasted on top, but a sourced dossier the table can trust."
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(*command: str, capture: bool = False) -> str:
    completed = subprocess.run(command, check=True, text=True, capture_output=capture)
    return completed.stdout if capture else ""


def probe(path: Path) -> dict[str, Any]:
    return json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
            capture=True,
        )
    )


def duration(path: Path) -> float:
    return float((probe(path).get("format") or {}).get("duration") or 0.0)


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
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


def base_image() -> Image.Image:
    source = Image.open(SOURCE_IMAGE).convert("RGB")
    source_ratio = source.width / source.height
    target_ratio = WIDTH / HEIGHT
    if source_ratio > target_ratio:
        new_width = int(source.height * target_ratio)
        left = (source.width - new_width) // 2
        source = source.crop((left, 0, left + new_width, source.height))
    else:
        new_height = int(source.width / target_ratio)
        top = (source.height - new_height) // 2
        source = source.crop((0, top, source.width, top + new_height))
    return source.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def draw_slide(index: int, scene: dict[str, str], base: Image.Image) -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    image = ImageEnhance.Color(base).enhance(0.78)
    image = ImageEnhance.Contrast(image).enhance(0.88)
    background = image.filter(ImageFilter.GaussianBlur(9))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (4, 8, 12, 108))
    background = Image.alpha_composite(background.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(background)

    copper = (202, 129, 64)
    cyan = (92, 206, 226)
    ink = (7, 12, 18, 214)
    panel = (9, 16, 24, 230)
    x_shift = int(22 * math.sin(index * 0.9))

    draw.rounded_rectangle((70, 78, 760, 610), radius=8, fill=panel, outline=(71, 87, 98), width=2)
    draw.rectangle((70, 78, 760, 132), fill=ink)
    draw.text((104, 96), f"ORIGIN DOSSIER / {index + 1:02d}", fill=copper, font=LABEL_FONT)
    draw.text((104, 154), scene["tag"], fill=cyan, font=SMALL_FONT)

    y = 190
    for line in wrap(draw, scene["title"], TITLE_FONT, 570):
        draw.text((104, y), line, fill=(248, 248, 242), font=TITLE_FONT)
        y += 62
    y += 16
    for line in wrap(draw, scene["body"], BODY_FONT, 575):
        draw.text((106, y), line, fill=(222, 228, 230), font=BODY_FONT)
        y += 38

    draw.rounded_rectangle((830 + x_shift, 118, 1194 + x_shift, 574), radius=8, fill=(10, 17, 25, 180), outline=(202, 129, 64), width=2)
    for row, label in enumerate(("approved canon", "source hash", "media packet", "rules boundary")):
        y0 = 166 + row * 82
        draw.rectangle((862 + x_shift, y0, 882 + x_shift, y0 + 44), fill=copper if row % 2 == 0 else cyan)
        draw.text((902 + x_shift, y0 + 12), label.upper(), fill=(238, 242, 244), font=SMALL_FONT)

    path = BUILD_DIR / f"{index + 1:02d}_{scene['tag'].lower().replace(' ', '_').replace('->', 'to')}.png"
    background.convert("RGB").save(path, quality=95)
    return path


def format_ts(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def write_vtt() -> None:
    lines = ["WEBVTT", ""]
    scene_seconds = TARGET_SECONDS / len(SCENES)
    for index, scene in enumerate(SCENES, start=1):
        start = (index - 1) * scene_seconds
        end = index * scene_seconds
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", scene["voiceover"], ""])
    TARGET_VTT.write_text("\n".join(lines), encoding="utf-8")


def render_narration() -> tuple[Path, str]:
    text_file = BUILD_DIR / "origin-dossier-narration.txt"
    raw = BUILD_DIR / "origin-dossier-flite.wav"
    final = BUILD_DIR / "origin-dossier-audio.wav"
    text_file.write_text(NARRATION, encoding="utf-8")
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"flite=textfile={text_file}:voice=slt",
        "-ar",
        "48000",
        "-ac",
        "1",
        str(raw),
    )
    raw_duration = duration(raw)
    target_vo = 84.0
    tempo = raw_duration / target_vo if raw_duration else 1.0
    tempo = max(0.58, min(1.12, tempo))
    bed = (
        "aevalsrc='0.028*sin(2*PI*45*t)+0.017*sin(2*PI*90*t)+"
        "0.009*sin(2*PI*(180+10*sin(2*PI*0.04*t))*t)':"
        f"s=48000:d={TARGET_SECONDS:.3f},"
        "highpass=f=35,lowpass=f=3400,volume=0.72,afade=t=in:st=0:d=1.2,afade=t=out:st=87:d=3[bed]"
    )
    filter_complex = (
        f"[0:a]atempo={tempo:.5f},afade=t=in:st=0:d=0.2,highpass=f=70,lowpass=f=8500,"
        "acompressor=threshold=-22dB:ratio=2.4:attack=20:release=250:makeup=2.0,"
        f"adelay=900|900,apad,atrim=0:{TARGET_SECONDS:.3f},volume=1.08[vo];"
        f"{bed};[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.92[a]"
    )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(raw),
        "-filter_complex",
        filter_complex,
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(final),
    )
    return final, f"ffmpeg-flite-slt-atempo-{tempo:.3f}"


def build_video(slides: list[Path], audio: Path) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    scene_seconds = TARGET_SECONDS / len(slides)
    for index, slide in enumerate(slides):
        inputs.extend(["-loop", "1", "-t", f"{scene_seconds:.3f}", "-i", str(slide)])
        frames = int(round(scene_seconds * FPS))
        zoom_expr = f"1+0.030*on/{frames}"
        pan_x = "(iw-iw/zoom)/2"
        pan_y = "(ih-ih/zoom)/2"
        filters.append(
            f"[{index}:v]scale=1408:792,zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p[v{index}]"
        )
    video_inputs = "".join(f"[v{index}]" for index in range(len(slides)))
    filters.append(f"{video_inputs}concat=n={len(slides)}:v=1:a=0[v]")
    run(
        "ffmpeg",
        "-y",
        *inputs,
        "-i",
        str(audio),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        f"{len(slides)}:a:0",
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
        "192k",
        "-movflags",
        "+faststart",
        str(TARGET_MP4),
    )


def validate() -> dict[str, Any]:
    if not TARGET_MP4.is_file():
        raise SystemExit(f"missing output: {TARGET_MP4}")
    if not TARGET_VTT.is_file() or not TARGET_VTT.read_text(encoding="utf-8").startswith("WEBVTT\n"):
        raise SystemExit("missing or invalid Origin Dossier VTT")
    metadata = probe(TARGET_MP4)
    streams = metadata.get("streams") or []
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise SystemExit("Origin Dossier fallback has no video stream")
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise SystemExit("Origin Dossier fallback has no audio stream")
    length = float((metadata.get("format") or {}).get("duration") or 0.0)
    if length < 89.5:
        raise SystemExit(f"Origin Dossier fallback is too short: {length:.3f}s")
    return metadata


def main() -> int:
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    base = base_image()
    slides = [draw_slide(index, scene, base) for index, scene in enumerate(SCENES)]
    audio, audio_provider = render_narration()
    build_video(slides, audio)
    write_vtt()
    metadata = validate()
    magicfit_status = {}
    if MAGICFIT_STATUS.is_file():
        magicfit_status = json.loads(MAGICFIT_STATUS.read_text(encoding="utf-8"))
    receipt = {
        "contract_name": "chummer.origin_dossier_fallback_reel.v1",
        "generated_at_utc": now_iso(),
        "status": "published",
        "asset_id": ASSET_ID,
        "horizon_id": "origin-dossier",
        "surface_class": "core_product",
        "render_mode": "first_party_narrated_storyboard_90s",
        "provider_claim": "none",
        "magicfit_full_reel_claim_allowed": False,
        "magicfit_status": {
            "status": magicfit_status.get("status", "unknown"),
            "reason": (magicfit_status.get("full_reel") or {}).get("reason", ""),
            "proof_clip": (magicfit_status.get("proof_clip") or {}).get("file", ""),
        },
        "source_image": str(SOURCE_IMAGE),
        "public_source_mp4": str(TARGET_MP4),
        "source_vtt": str(TARGET_VTT),
        "audio_provider": audio_provider,
        "scene_count": len(SCENES),
        "target_duration_seconds": TARGET_SECONDS,
        "narration_word_count": len(NARRATION.split()),
        "scenes": list(SCENES),
        "mp4_probe": metadata,
    }
    TARGET_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(TARGET_RECEIPT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
