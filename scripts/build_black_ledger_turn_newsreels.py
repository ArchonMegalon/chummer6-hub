#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json


FPS = 30
WIDTH = 1920
HEIGHT = 1080
DEFAULT_VOICE = "en-US-JennyNeural"
NEWSREEL_ROOT = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "newsreels"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render first-party Black Ledger turn newsreel videos with narration and score.")
    parser.add_argument("--turn", type=int, default=1, help="Turn number to render.")
    parser.add_argument("--base-url", default="", help="Optional running Chummer base URL. When omitted the script launches a temporary local app.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Edge TTS voice id.")
    parser.add_argument("--edge-python", default="", help="Optional Python executable that can import edge_tts.")
    return parser.parse_args()


def repo_font(name: str) -> Path:
    return Path("/usr/share/fonts/truetype/dejavu") / name


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred = repo_font("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    if preferred.is_file():
        return ImageFont.truetype(str(preferred), size=size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word]).strip()
        if candidate and draw.textlength(candidate, font=font) <= width:
            current.append(word)
            continue
        if current:
            lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ease(progress: float) -> float:
    progress = clamp(progress, 0.0, 1.0)
    return progress * progress * (3 - (2 * progress))


def build_script(payload: dict) -> tuple[str, list[tuple[float, float, str]]]:
    lead = payload["newsreelLead"].strip()
    bullets = [str(item).strip().rstrip(".") + "." for item in payload.get("newsreelBullets", [])[:4]]
    transition = str(payload["transitionLabel"]).strip()
    narrative = str(payload["transitionNarrative"]).strip()
    state_summary = str(payload["stateSummary"]).strip()
    world_name = str(payload["worldName"]).strip()
    lines = [
        f"Good evening. This is Black Ledger Network with the {transition} world calculation for {world_name}.",
        lead,
        *bullets,
        state_summary,
        "Validation stays receipt-backed, public-safe, and tied to the same city board you can inspect on the route.",
    ]

    timings: list[tuple[float, float, str]] = []
    cursor = 0.0
    scripted_lines: list[str] = []
    for line in lines:
        clean = " ".join(line.split())
        duration = max(1.8, min(4.2, len(clean) / 16.0))
        start = cursor
        cursor += duration
        timings.append((start, cursor, clean))
        scripted_lines.append(clean)
    full_script = " ".join(scripted_lines)
    if narrative and narrative not in full_script:
        full_script = f"{full_script} {narrative}"
    return full_script, timings


def write_vtt(path: Path, timings: list[tuple[float, float, str]]) -> None:
    def fmt(seconds: float) -> str:
        milliseconds = int(round(seconds * 1000))
        hours, rem = divmod(milliseconds, 3_600_000)
        minutes, rem = divmod(rem, 60_000)
        secs, ms = divmod(rem, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"

    lines = ["WEBVTT", ""]
    for index, (start, end, text) in enumerate(timings, start=1):
        lines.append(str(index))
        lines.append(f"{fmt(start)} --> {fmt(end)}")
        lines.extend(textwrap.wrap(text, width=54))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def find_edge_python(explicit: str) -> str:
    candidates = [explicit.strip()] if explicit.strip() else []
    candidates.extend([
        "/tmp/black-ledger-newsreel-venv/bin/python",
        "/tmp/black-ledger-newsreel-venv/bin/python3",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("No Python executable with edge_tts available. Pass --edge-python.")


def render_narration(edge_python: str, voice: str, script_text: str, output_path: Path, work_root: Path) -> None:
    script_path = work_root / "newsreel-script.txt"
    script_path.write_text(script_text, encoding="utf-8")
    temp_code = work_root / "edge_tts_render.py"
    temp_code.write_text(
        """
import asyncio
import pathlib
import sys
import edge_tts

voice = sys.argv[1]
script_path = pathlib.Path(sys.argv[2])
output_path = pathlib.Path(sys.argv[3])

async def main() -> None:
    text = script_path.read_text(encoding="utf-8")
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(output_path))

asyncio.run(main())
""".strip()
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [edge_python, str(temp_code), voice, str(script_path), str(output_path)],
        check=True,
        cwd=str(RUN_SERVICES_ROOT),
    )


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def render_music(output_path: Path, duration: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=92:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=184:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=368:sample_rate=48000:duration={duration}",
            "-filter_complex",
            "[0:a]volume=0.08,lowpass=f=260,afade=t=in:st=0:d=1.6[a0];"
            "[1:a]volume=0.05,lowpass=f=540,afade=t=in:st=0:d=2.2[a1];"
            "[2:a]volume=0.025,highpass=f=120,afade=t=in:st=0:d=2.8[a2];"
            "[a0][a1][a2]amix=inputs=3:normalize=0,"
            "aecho=0.8:0.88:60:0.22,alimiter=limit=0.85[out]",
            "-map",
            "[out]",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
        cwd=str(RUN_SERVICES_ROOT),
    )


def build_background(frame: int, total_frames: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (6, 11, 21))
    progress = frame / max(1, total_frames - 1)
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        blend = y / max(1, HEIGHT - 1)
        red = int(8 + (20 * blend) + (12 * math.sin((progress * 5.2) + (y / 140))))
        green = int(16 + (20 * blend) + (8 * math.sin((progress * 4.1) + (y / 180))))
        blue = int(28 + (48 * blend))
        draw.line((0, y, WIDTH, y), fill=(max(0, red), max(0, green), min(255, blue)))

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((WIDTH - 620, -160, WIDTH + 120, 540), fill=(219, 51, 44, 44))
    gdraw.ellipse((-180, 160, 660, 920), fill=(66, 133, 244, 54))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")

    grid = ImageDraw.Draw(image)
    for x in range(0, WIDTH, 96):
        grid.line((x, 0, x, HEIGHT), fill=(28, 42, 68), width=1)
    for y in range(0, HEIGHT, 64):
        grid.line((0, y, WIDTH, y), fill=(18, 31, 54), width=1)
    return image


def draw_anchor(draw: ImageDraw.ImageDraw, x: int, y: int, pulse: float) -> None:
    suit = (31, 43, 68)
    shirt = (226, 231, 237)
    skin = (201, 160, 136)
    hair = (31, 23, 22)
    accent = (216, 58, 48)

    draw.rounded_rectangle((x - 210, y + 130, x + 210, y + 300), radius=24, fill=(8, 18, 32), outline=(68, 96, 140), width=2)
    draw.rounded_rectangle((x - 140, y + 20, x + 140, y + 220), radius=38, fill=suit)
    draw.polygon([(x - 88, y + 220), (x, y + 92), (x + 88, y + 220)], fill=shirt)
    draw.ellipse((x - 68, y - 68, x + 68, y + 74), fill=skin)
    draw.pieslice((x - 82, y - 92, x + 82, y + 42), start=180, end=360, fill=hair)
    draw.rectangle((x - 9, y + 90, x + 9, y + 176), fill=(41, 55, 84))
    draw.polygon([(x - 14, y + 176), (x + 14, y + 176), (x, y + 215)], fill=accent)
    mouth_width = 18 + int(8 * pulse)
    draw.rounded_rectangle((x - mouth_width, y + 22, x + mouth_width, y + 34), radius=5, fill=(128, 58, 58))
    draw.ellipse((x - 30, y - 6, x - 16, y + 8), fill=(33, 38, 46))
    draw.ellipse((x + 16, y - 6, x + 30, y + 8), fill=(33, 38, 46))
    draw.arc((x - 24, y + 38, x + 24, y + 58), start=10, end=170, fill=(142, 78, 66), width=2)


def draw_scene(
    frame: int,
    total_frames: int,
    payload: dict,
    timings: list[tuple[float, float, str]],
    poster_only: bool = False,
) -> Image.Image:
    image = build_background(frame, total_frames).convert("RGBA")
    draw = ImageDraw.Draw(image)
    title_font = load_font(72, bold=True)
    body_font = load_font(30)
    body_bold = load_font(32, bold=True)
    micro_font = load_font(22, bold=True)
    ticker_font = load_font(28, bold=True)

    current_time = frame / FPS
    duration = total_frames / FPS
    scene_len = duration / 4.0
    scene = min(3, int(current_time / max(0.001, scene_len)))
    local = (current_time - (scene * scene_len)) / max(scene_len, 0.001)
    motion = ease(local)
    pulse = 0.5 + 0.5 * math.sin(current_time * 6.0)

    draw.rounded_rectangle((48, 42, WIDTH - 48, HEIGHT - 58), radius=34, outline=(40, 64, 104), width=3, fill=(4, 9, 18, 110))
    draw.rounded_rectangle((74, 82, 712, 816), radius=28, fill=(10, 17, 31, 220), outline=(57, 92, 142), width=2)
    draw.rounded_rectangle((748, 82, WIDTH - 82, 816), radius=28, fill=(8, 14, 26, 230), outline=(57, 92, 142), width=2)
    draw.rounded_rectangle((82, 820, WIDTH - 82, HEIGHT - 86), radius=22, fill=(10, 18, 31, 235), outline=(69, 103, 154), width=2)

    live_alpha = 200 if int(current_time * 2) % 2 == 0 else 120
    draw.rounded_rectangle((90, 48, 196, 94), radius=16, fill=(184, 32, 28, live_alpha))
    draw.text((116, 57), "LIVE", fill=(255, 244, 244), font=body_bold)
    draw.text((230, 55), "BLACK LEDGER NETWORK", fill=(202, 225, 255), font=micro_font)
    draw.text((230, 84), payload["transitionLabel"].upper(), fill=(134, 173, 214), font=micro_font)

    anchor_y = 362 + int(8 * math.sin(current_time * 2.4))
    draw_anchor(draw, 390, anchor_y, pulse)

    bar_base_x = 184
    for index in range(16):
        bar_height = 18 + int((46 + (index % 3) * 6) * (0.3 + 0.7 * abs(math.sin((current_time * 5.2) + index))))
        draw.rounded_rectangle((bar_base_x + (index * 21), 694 - bar_height, bar_base_x + 12 + (index * 21), 694), radius=4, fill=(89, 205, 255))

    draw.text((112, 740), "ANCHOR DESK", fill=(117, 162, 212), font=micro_font)
    draw.text((112, 772), "MARA QUILL", fill=(246, 250, 255), font=body_bold)
    draw.text((112, 810), "Receipt-backed city pressure bulletin", fill=(164, 190, 221), font=body_font)

    headline = str(payload["inboxHeadline"])
    headline_x = 788 + int((1.0 - motion) * 22)
    draw.text((headline_x, 128), headline, fill=(245, 249, 255), font=title_font)

    scene_bodies = [
        [payload["newsreelLead"]],
        [str(item) for item in payload.get("newsreelBullets", [])[:2]],
        [str(item) for item in payload.get("newsreelBullets", [])[2:4]] + [str(payload["stateSummary"])],
        list(payload.get("validationChecks", [])[:3]),
    ]
    scene_labels = [
        "OPENING CALCULATION",
        "PRESSURE BOARD",
        "CITY CONSEQUENCES",
        "VALIDATION AND HANDOFF",
    ]

    draw.text((792, 230), scene_labels[scene], fill=(255, 111, 97), font=micro_font)
    card_y = 278
    for index, line in enumerate(scene_bodies[scene][:3]):
        block_top = card_y + (index * 146)
        draw.rounded_rectangle((792, block_top, WIDTH - 126, block_top + 122), radius=20, fill=(13, 25, 44, 228), outline=(61, 96, 144), width=2)
        wrapped = wrap(draw, line, body_font, WIDTH - 220 - 792)
        text_y = block_top + 18
        for wrapped_line in wrapped[:3]:
            draw.text((822, text_y), wrapped_line, fill=(228, 236, 248), font=body_font)
            text_y += 34
        if index == 0:
            draw.text((WIDTH - 292, block_top + 16), f"T+{int(current_time):02}", fill=(126, 166, 220), font=micro_font)

    tickers = list(payload.get("newsreelBullets", [])) + [str(payload["stateSummary"]), "Public-safe aggregate only", "No private campaign state"]
    ticker_text = "   //   ".join(tickers)
    ticker_width = int(draw.textlength(ticker_text, font=ticker_font))
    offset = int((current_time * 170) % max(1, ticker_width + 240))
    ticker_x = WIDTH - offset
    draw.text((ticker_x, 913), ticker_text, fill=(236, 242, 255), font=ticker_font)
    draw.text((98, 866), "WORLD TICK NEWSREEL", fill=(116, 162, 212), font=micro_font)

    if poster_only:
        return image.convert("RGB")

    frame_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(frame_overlay)
    intensity = int(42 * (1.0 - abs((local * 2.0) - 1.0)))
    overlay_draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(255, 255, 255, intensity if scene in (1, 3) else 0))
    image = Image.alpha_composite(image, frame_overlay)
    return image.convert("RGB")


def build_video_assets(payload: dict, output_root: Path, edge_python: str, voice: str) -> dict:
    output_root.mkdir(parents=True, exist_ok=True)
    slug = f"turn-{payload['toTurn']}-newsreel"
    mp4_path = output_root / f"{slug}.mp4"
    webm_path = output_root / f"{slug}.webm"
    poster_path = output_root / f"{slug}-poster.png"
    captions_path = output_root / f"{slug}.vtt"
    script_text, timings = build_script(payload)
    write_vtt(captions_path, timings)

    with tempfile.TemporaryDirectory(prefix="black-ledger-newsreel-frames-") as temp_dir:
        frames_root = Path(temp_dir)
        narration_path = frames_root / "narration.mp3"
        music_path = frames_root / "music.wav"
        render_narration(edge_python, voice, script_text, narration_path, frames_root)
        narration_duration = ffprobe_duration(narration_path)
        total_duration = max(16.0, narration_duration + 1.0)
        render_music(music_path, total_duration)
        total_frames = math.ceil(total_duration * FPS)
        poster_frame = min(total_frames - 1, FPS * 2)
        for frame in range(total_frames):
            image = draw_scene(frame, total_frames, payload, timings)
            image.save(frames_root / f"frame_{frame:04d}.png", optimize=True)
            if frame == poster_frame:
                image.save(poster_path, optimize=True)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(frames_root / "frame_%04d.png"),
                "-i",
                str(narration_path),
                "-i",
                str(music_path),
                "-filter_complex",
                "[2:a]volume=0.16[bed];"
                "[bed][1:a]sidechaincompress=threshold=0.015:ratio=8:attack=5:release=240[ducked];"
                "[1:a][ducked]amix=inputs=2:weights='1 1':normalize=0[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "libx264",
                "-profile:v",
                "high",
                "-level",
                "4.1",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                str(mp4_path),
            ],
            check=True,
            cwd=str(RUN_SERVICES_ROOT),
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(frames_root / "frame_%04d.png"),
                "-i",
                str(narration_path),
                "-i",
                str(music_path),
                "-filter_complex",
                "[2:a]volume=0.16[bed];"
                "[bed][1:a]sidechaincompress=threshold=0.015:ratio=8:attack=5:release=240[ducked];"
                "[1:a][ducked]amix=inputs=2:weights='1 1':normalize=0[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "libvpx-vp9",
                "-b:v",
                "0",
                "-crf",
                "30",
                "-row-mt",
                "1",
                "-tile-columns",
                "1",
                "-c:a",
                "libopus",
                "-b:a",
                "128k",
                "-shortest",
                str(webm_path),
            ],
            check=True,
            cwd=str(RUN_SERVICES_ROOT),
        )

    return {
        "slug": slug,
        "script_text": script_text,
        "timings": timings,
        "narration_duration_seconds": narration_duration,
        "duration_seconds": total_duration,
        "mp4_path": str(mp4_path),
        "webm_path": str(webm_path),
        "poster_path": str(poster_path),
        "captions_path": str(captions_path),
    }


def load_payload(base_url: str, turn: int) -> dict:
    response = requests.get(f"{base_url.rstrip('/')}/ledger/turns/{turn}/newsreel.json", timeout=60)
    response.raise_for_status()
    return response.json()


def write_receipt(turn: int, base_url: str, render: dict, payload: dict) -> None:
    proof = {
        "status": "pass",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "turn": turn,
        "world_id": payload["worldId"],
        "headline": payload["inboxHeadline"],
        "duration_seconds": round(render["duration_seconds"], 2),
        "narration_duration_seconds": round(render["narration_duration_seconds"], 2),
        "mp4_path": render["mp4_path"],
        "webm_path": render["webm_path"],
        "poster_path": render["poster_path"],
        "captions_path": render["captions_path"],
        "voice": DEFAULT_VOICE,
    }
    write_json(completion_path("BLACK_LEDGER_TURN_NEWSREEL_RENDER.generated.json"), proof)


def run(base_url: str, turn: int, voice: str, edge_python: str) -> int:
    payload = load_payload(base_url, turn)
    render = build_video_assets(payload, NEWSREEL_ROOT, edge_python, voice)
    write_receipt(turn, base_url, render, payload)
    return 0


def main() -> int:
    args = parse_args()
    edge_python = find_edge_python(args.edge_python)
    if args.base_url:
        return run(args.base_url, args.turn, args.voice, edge_python)
    with LocalHubApp() as app:
        return run(app.base_url, args.turn, args.voice, edge_python)


if __name__ == "__main__":
    raise SystemExit(main())
