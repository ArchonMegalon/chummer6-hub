#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _unmixr_tts import load_profile, provider_token, render_short_tts


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
SOURCE_ROOT = WORKSPACE / "_completion" / "horizon_flagship_reels_20260602" / "videos"
PUBLIC_ROOT = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "horizons"
BUILD_DIR = WORKSPACE / "_completion" / "origin_dossier_kestrel_trailer_20260619"
SOURCE_IMAGE = WORKSPACE / "Chummer6" / "assets" / "horizons" / "origin-dossier.png"
MAGICFIT_STATUS = WORKSPACE / "_completion" / "origin_dossier_horizon_20260618" / "ORIGIN_DOSSIER_MAGICFIT_RENDER_STATUS.generated.json"

ASSET_ID = "origin_dossier_90s_deepdive"
PUBLIC_NAME = "origin-dossier-the-name-she-chose-20260619"
LEGACY_PUBLIC_NAME = "origin-dossier-90s-deepdive"
SOURCE_MP4 = SOURCE_ROOT / f"{ASSET_ID}.mp4"
SOURCE_VTT = SOURCE_ROOT / f"{ASSET_ID}.vtt"
PUBLIC_MP4 = PUBLIC_ROOT / f"{PUBLIC_NAME}.mp4"
PUBLIC_WEBM = PUBLIC_ROOT / f"{PUBLIC_NAME}.webm"
PUBLIC_VTT = PUBLIC_ROOT / f"{PUBLIC_NAME}.vtt"
PUBLIC_POSTER = PUBLIC_ROOT / f"{PUBLIC_NAME}.poster.png"
LEGACY_PUBLIC_MP4 = PUBLIC_ROOT / f"{LEGACY_PUBLIC_NAME}.mp4"
LEGACY_PUBLIC_WEBM = PUBLIC_ROOT / f"{LEGACY_PUBLIC_NAME}.webm"
LEGACY_PUBLIC_VTT = PUBLIC_ROOT / f"{LEGACY_PUBLIC_NAME}.vtt"
LEGACY_PUBLIC_POSTER = PUBLIC_ROOT / f"{LEGACY_PUBLIC_NAME}.poster.png"
MANIFEST_PATH = PUBLIC_ROOT / "horizon-video-manifest.json"
TARGET_RECEIPT = BUILD_DIR / "ORIGIN_DOSSIER_KESTREL_TRAILER.generated.json"

WIDTH = 1920
HEIGHT = 804
FPS = 24
TARGET_SECONDS = 90.0

FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
TITLE_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 66)
BODY_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 31)
LABEL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 24)
SMALL_FONT = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 20)


SCENES: tuple[dict[str, Any], ...] = (
    {
        "title": "The name she chose",
        "age": "26",
        "tag": "ALIAS / KESTREL",
        "body": "A runner alone in a freight elevator. One copper bird. One name she will own.",
        "palette": ((10, 16, 22), (44, 64, 74), (197, 117, 54)),
        "motif": "elevator",
        "voiceover": "They call me Kestrel. That wasn’t my first name.",
    },
    {
        "title": "Birth",
        "age": "newborn",
        "tag": "KEEPSAKE / COPPER BIRD",
        "body": "A clinic light flickers. Her mother gives her the one thing the city cannot repossess.",
        "palette": ((35, 24, 18), (98, 70, 44), (214, 145, 73)),
        "motif": "clinic",
        "voiceover": (
            "I was born Mara Vale beneath a clinic light that flickered every six seconds. "
            "My mother gave me one thing the city could not repossess: a copper bird."
        ),
    },
    {
        "title": "Before the city changed",
        "age": "6",
        "tag": "BOND / MOTHER",
        "body": "For one warm minute, the world is market smoke, music, and a hand that never lets go.",
        "palette": ((28, 18, 13), (123, 74, 42), (86, 141, 100)),
        "motif": "market",
        "voiceover": "At six, the world was market smoke, music, and her hand in mine.",
    },
    {
        "title": "The taking",
        "age": "9",
        "tag": "ENEMY / NADIR SECURITY",
        "body": "Armored boots. A door closing. A child learning that a home can disappear before dawn.",
        "palette": ((9, 15, 22), (39, 58, 75), (171, 42, 42)),
        "motif": "raid",
        "voiceover": "At nine, corporate security took our home and my mother with it.",
    },
    {
        "title": "The first line crossed",
        "age": "13",
        "tag": "SKILL / INFILTRATION",
        "body": "Medicine stolen in the rain. A debt to a street clinic. A good reason, and still a line.",
        "palette": ((8, 24, 25), (29, 86, 85), (207, 130, 64)),
        "motif": "lock",
        "voiceover": (
            "At thirteen, I learned every lock is only a question. "
            "I stole medicine. I told myself that made me good."
        ),
    },
    {
        "title": "The consequence",
        "age": "16",
        "tag": "SECRET / NORTHLINE CRASH",
        "body": "The convoy stops. The target falls. Someone else pays for the certainty of a teenager.",
        "palette": ((16, 18, 19), (94, 96, 98), (188, 52, 42)),
        "motif": "convoy",
        "voiceover": (
            "At sixteen, I stopped a convoy. The crash took more than the target. "
            "I still don’t know their names."
        ),
    },
    {
        "title": "The rule",
        "age": "19",
        "tag": "CODE / NO ONE LEFT BEHIND",
        "body": "A crew runs. One teammate stays trapped. Mara turns back and loses the arm.",
        "palette": ((8, 10, 14), (36, 44, 55), (225, 225, 215)),
        "motif": "blast",
        "voiceover": (
            "At nineteen, my crew sold me out. I went back for the one they left behind. "
            "I lost the arm and found the rule I still live by. No one gets left behind."
        ),
    },
    {
        "title": "Rebuilt",
        "age": "20–26",
        "tag": "SCAR / LEFT ARM",
        "body": "Rook rebuilds her slowly: copper under ceramic, failure before control, a new name on paper.",
        "palette": ((22, 26, 30), (70, 80, 84), (193, 124, 58)),
        "motif": "cyberarm",
        "voiceover": (
            "A street doctor rebuilt me. I chose a new name. "
            "The city wrote the wounds. I chose what they meant."
        ),
    },
    {
        "title": "The dossier is alive",
        "age": "26",
        "tag": "CONTACTS / DEBTS / CONSEQUENCES",
        "body": "A message from Rook. A trace of her mother. A crew waiting for the decision.",
        "palette": ((8, 17, 24), (32, 60, 74), (198, 125, 62)),
        "motif": "dossier",
        "voiceover": (
            "Origin Dossier turns every scar, debt, promise, enemy, and secret into the runner at your table. "
            "Not a backstory. A life with consequences."
        ),
    },
)


NARRATION = " ".join(str(scene["voiceover"]) for scene in SCENES)


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
            "format=duration,size:stream=index,codec_type,codec_name,width,height",
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


def load_source_plate() -> Image.Image:
    if not SOURCE_IMAGE.is_file():
        return Image.new("RGB", (WIDTH, HEIGHT), (10, 14, 20))
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


def gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    height = size[1]
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, size[0], y), fill=color)
    return image


def draw_rain(draw: ImageDraw.ImageDraw, seed: int, color: tuple[int, int, int, int]) -> None:
    rng = random.Random(seed)
    for _ in range(180):
        x = rng.randint(-120, WIDTH + 120)
        y = rng.randint(-50, HEIGHT + 50)
        length = rng.randint(18, 66)
        draw.line((x, y, x + 12, y + length), fill=color, width=1)


def draw_copper_bird(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float = 1.0) -> None:
    cx, cy = center
    copper = (207, 126, 57, 235)
    dark = (8, 12, 16, 240)
    wing = [
        (cx - int(84 * scale), cy + int(12 * scale)),
        (cx - int(14 * scale), cy - int(36 * scale)),
        (cx + int(24 * scale), cy - int(4 * scale)),
        (cx - int(12 * scale), cy + int(28 * scale)),
    ]
    tail = [
        (cx - int(10 * scale), cy + int(26 * scale)),
        (cx + int(58 * scale), cy + int(54 * scale)),
        (cx + int(22 * scale), cy + int(10 * scale)),
    ]
    beak = [
        (cx + int(68 * scale), cy - int(6 * scale)),
        (cx + int(104 * scale), cy - int(20 * scale)),
        (cx + int(76 * scale), cy + int(12 * scale)),
    ]
    body = [
        (cx - int(18 * scale), cy - int(28 * scale)),
        (cx + int(72 * scale), cy - int(8 * scale)),
        (cx + int(26 * scale), cy + int(34 * scale)),
    ]
    draw.polygon(wing, fill=copper, outline=dark)
    draw.polygon(tail, fill=(160, 88, 40, 220), outline=dark)
    draw.polygon(body, fill=copper, outline=dark)
    draw.polygon(beak, fill=(225, 148, 80, 230), outline=dark)
    draw.ellipse((cx + int(39 * scale), cy - int(11 * scale), cx + int(48 * scale), cy - int(2 * scale)), fill=dark)


def draw_motif(draw: ImageDraw.ImageDraw, scene: dict[str, Any], index: int) -> None:
    motif = str(scene["motif"])
    accent = tuple(scene["palette"][2])
    soft = (*accent, 130)
    white = (236, 239, 235, 210)
    if motif == "elevator":
        for x in range(1060, 1640, 98):
            draw.rectangle((x, 80, x + 32, 710), fill=(230, 72, 54, 38))
        draw.line((1300, 76, 1300, 710), fill=(220, 226, 228, 68), width=3)
        draw_copper_bird(draw, (1450, 435), 1.1)
    elif motif == "clinic":
        draw.ellipse((1110, 138, 1510, 538), fill=(255, 230, 188, 18), outline=(255, 230, 188, 80), width=3)
        draw.rounded_rectangle((1210, 360, 1500, 430), radius=28, fill=(240, 229, 212, 58))
        draw_copper_bird(draw, (1390, 474), 0.72)
    elif motif == "market":
        for x in range(1010, 1730, 90):
            draw.line((x, 140, x + 60, 170), fill=(245, 185, 92, 110), width=2)
            draw.ellipse((x + 50, 160, x + 76, 186), fill=(238, 178, 88, 115))
        draw.arc((1140, 220, 1580, 660), start=202, end=338, fill=white, width=4)
    elif motif == "raid":
        draw.rectangle((1180, 148, 1400, 694), fill=(18, 25, 31, 180), outline=(180, 56, 48, 90), width=4)
        for y in range(210, 620, 92):
            draw.line((980, y, 1740, y + 116), fill=(187, 38, 38, 54), width=14)
        draw_copper_bird(draw, (1530, 610), 0.62)
    elif motif == "lock":
        draw.rounded_rectangle((1130, 184, 1568, 592), radius=18, fill=(11, 25, 27, 210), outline=soft, width=3)
        for i in range(9):
            x = 1194 + i * 42
            draw.line((x, 250, x + 32, 446), fill=(99, 214, 198, 80), width=2)
        draw.ellipse((1295, 332, 1405, 442), outline=(220, 156, 72, 190), width=7)
    elif motif == "convoy":
        draw.polygon(((930, 610), (1780, 452), (1840, 548), (1010, 716)), fill=(40, 42, 44, 230))
        for x in (1110, 1360, 1610):
            draw.rounded_rectangle((x, 390, x + 160, 470), radius=12, fill=(71, 76, 78, 230), outline=(220, 225, 224, 70))
            draw.ellipse((x + 24, 458, x + 70, 504), fill=(18, 20, 22))
            draw.ellipse((x + 112, 458, x + 158, 504), fill=(18, 20, 22))
        draw.line((930, 590, 1760, 438), fill=(255, 255, 255, 95), width=2)
    elif motif == "blast":
        for radius in range(80, 470, 38):
            alpha = max(14, 112 - radius // 5)
            draw.ellipse((1340 - radius, 384 - radius, 1340 + radius, 384 + radius), outline=(245, 245, 230, alpha), width=6)
        draw.line((910, 560, 1640, 230), fill=(255, 255, 255, 120), width=5)
        draw_copper_bird(draw, (1035, 578), 0.48)
    elif motif == "cyberarm":
        for x in range(1180, 1580, 64):
            draw.rounded_rectangle((x, 164, x + 34, 650), radius=16, fill=(44, 50, 56, 220), outline=(152, 163, 164, 80))
        draw.arc((1090, 210, 1710, 720), start=250, end=330, fill=soft, width=8)
        draw_copper_bird(draw, (1466, 414), 0.74)
    elif motif == "dossier":
        terms = ("CONTACT", "ENEMY", "DEBT", "SCAR", "SECRET", "PROMISE")
        for pos, term in enumerate(terms):
            x = 1030 + (pos % 2) * 330
            y = 158 + (pos // 2) * 118
            draw.rounded_rectangle((x, y, x + 270, y + 54), radius=6, fill=(8, 16, 23, 180), outline=soft, width=2)
            draw.text((x + 20, y + 15), term, fill=(238, 241, 237, 220), font=SMALL_FONT)
        draw_copper_bird(draw, (1435, 628), 0.8)


def draw_slide(index: int, scene: dict[str, Any], source_plate: Image.Image) -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    top, bottom, accent = scene["palette"]
    background = gradient((WIDTH, HEIGHT), top, bottom).convert("RGBA")
    plate = ImageEnhance.Color(source_plate).enhance(0.58).filter(ImageFilter.GaussianBlur(9)).convert("RGBA")
    plate.putalpha(74)
    background = Image.alpha_composite(background, plate)
    draw = ImageDraw.Draw(background)
    draw_rain(draw, 1729 + index, (230, 238, 240, 28))

    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(0, 0, 0, 46))
    draw.rectangle((0, HEIGHT - 120, WIDTH, HEIGHT), fill=(0, 0, 0, 54))
    draw_motif(draw, scene, index)

    panel = (7, 11, 15, 198)
    draw.rounded_rectangle((84, 96, 878, 660), radius=10, fill=panel, outline=(*accent, 185), width=2)
    draw.rectangle((84, 96, 878, 158), fill=(5, 8, 12, 224))
    draw.text((118, 117), "ORIGIN DOSSIER", fill=accent, font=LABEL_FONT)
    draw.text((706, 118), f"AGE {scene['age']}", fill=(217, 222, 220), font=SMALL_FONT)
    draw.text((118, 188), str(scene["tag"]), fill=(113, 215, 224), font=SMALL_FONT)
    y = 230
    for line in wrap(draw, str(scene["title"]), TITLE_FONT, 650):
        draw.text((118, y), line, fill=(246, 245, 238), font=TITLE_FONT)
        y += 74
    y += 18
    for line in wrap(draw, str(scene["body"]), BODY_FONT, 610):
        draw.text((121, y), line, fill=(225, 229, 228), font=BODY_FONT)
        y += 44

    draw.line((116, 604, 838, 604), fill=(*accent, 155), width=2)
    draw.text((118, 622), "BUILD THE LIFE BEHIND THE STATS", fill=(238, 238, 232), font=SMALL_FONT)
    path = BUILD_DIR / f"{index + 1:02d}_{str(scene['title']).lower().replace(' ', '_')}.png"
    background.convert("RGB").save(path, quality=95)
    return path


def format_ts(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def write_vtt(path: Path, total_seconds: float) -> None:
    lines = ["WEBVTT", ""]
    scene_seconds = total_seconds / len(SCENES)
    for index, scene in enumerate(SCENES, start=1):
        start = (index - 1) * scene_seconds
        end = index * scene_seconds
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", str(scene["voiceover"]), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def render_voice() -> tuple[Path, str, float]:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    raw_mp3 = BUILD_DIR / "origin-dossier-kestrel-unmixr.mp3"
    voice_wav = BUILD_DIR / "origin-dossier-kestrel-voice.wav"
    profile = load_profile(
        prefixes=("UNMIXR_ORIGIN_DOSSIER_KESTREL", "UNMIXR_ORIGIN_DOSSIER"),
        defaults={"speaking_rate": "medium", "speaking_pitch": "low", "speaking_volume": "medium"},
    )
    render_short_tts(NARRATION, raw_mp3, profile=profile)
    provider = provider_token(profile, style="voice")
    source_audio = raw_mp3
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(source_audio),
        "-af",
        "aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono,highpass=f=160,lowpass=f=9000,"
        "acompressor=threshold=-20dB:ratio=2.2:attack=18:release=220:makeup=1.5,"
        "loudnorm=I=-17:LRA=9:TP=-2.0,aresample=48000",
        "-c:a",
        "pcm_s16le",
        str(voice_wav),
    )
    return voice_wav, provider, duration(voice_wav)


def render_mix(voice_wav: Path, total_seconds: float) -> Path:
    mixed = BUILD_DIR / "origin-dossier-kestrel-mix.wav"
    bed = (
        "anoisesrc=color=pink:sample_rate=48000:"
        f"duration={total_seconds:.3f},highpass=f=360,lowpass=f=4200,volume=0.010,"
        "afade=t=in:st=0:d=1.4,afade=t=out:st="
        f"{max(0.0, total_seconds - 3.0):.3f}:d=3[bed];"
        "sine=frequency=880:sample_rate=48000:duration=0.45,volume=0.030,adelay=500|500[ch1];"
        "sine=frequency=988:sample_rate=48000:duration=0.42,volume=0.024,adelay=920|920[ch2];"
        "sine=frequency=660:sample_rate=48000:duration=0.50,volume=0.022,adelay=1420|1420[ch3]"
    )
    filter_complex = (
        f"[0:a]adelay=650|650,apad,atrim=0:{total_seconds:.3f}[vo];"
        f"{bed};[bed][ch1][ch2][ch3][vo]amix=inputs=5:duration=first:dropout_transition=0,"
        "highpass=f=270,highpass=f=270,"
        "equalizer=f=188:width_type=h:width=90:g=-18,equalizer=f=235:width_type=h:width=105:g=-18,"
        "alimiter=limit=0.92,loudnorm=I=-16:LRA=10:TP=-1.5,aresample=48000[a]"
    )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(voice_wav),
        "-filter_complex",
        filter_complex,
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(mixed),
    )
    return mixed


def build_video(slides: list[Path], audio: Path, total_seconds: float) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    scene_seconds = total_seconds / len(slides)
    for index, slide in enumerate(slides):
        inputs.extend(["-loop", "1", "-t", f"{scene_seconds:.3f}", "-i", str(slide)])
        frames = int(round(scene_seconds * FPS))
        zoom_expr = f"1+0.026*on/{frames}"
        pan_x = f"(iw-iw/zoom)/2+{10 * math.sin(index):.3f}"
        pan_y = f"(ih-ih/zoom)/2+{8 * math.cos(index):.3f}"
        filters.append(
            f"[{index}:v]scale={WIDTH + 180}:{HEIGHT + 76},zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p[v{index}]"
        )
    video_inputs = "".join(f"[v{index}]" for index in range(len(slides)))
    filters.append(f"{video_inputs}concat=n={len(slides)}:v=1:a=0[v]")
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
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
        f"{total_seconds:.3f}",
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
        str(SOURCE_MP4),
    )


def publish_public(total_seconds: float) -> None:
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_MP4, PUBLIC_MP4)
    shutil.copy2(SOURCE_VTT, PUBLIC_VTT)
    shutil.copy2(SOURCE_MP4, LEGACY_PUBLIC_MP4)
    shutil.copy2(SOURCE_VTT, LEGACY_PUBLIC_VTT)
    poster = BUILD_DIR / "01_the_name_she_chose.png"
    if poster.is_file():
        shutil.copy2(poster, PUBLIC_POSTER)
        shutil.copy2(poster, LEGACY_PUBLIC_POSTER)
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(SOURCE_MP4),
        "-c:v",
        "libvpx-vp9",
        "-b:v",
        "0",
        "-crf",
        "33",
        "-c:a",
        "libopus",
        "-b:a",
        "128k",
        "-t",
        f"{total_seconds:.3f}",
        str(PUBLIC_WEBM),
    )
    shutil.copy2(PUBLIC_WEBM, LEGACY_PUBLIC_WEBM)


def update_manifest(metadata: dict[str, Any], audio_stats: dict[str, float]) -> None:
    manifest = {
        "contract_name": "chummer.public_product_video_manifest",
        "generated_at_utc": now_iso(),
        "publication_posture": "first_party_static_media_assets_with_audio; legacy /media/horizons path is retained for URL compatibility; surface_class distinguishes core product areas from expansion bets",
        "audio_required": True,
        "source_root": str(SOURCE_ROOT),
        "assets": [],
    }
    if MANIFEST_PATH.is_file():
        try:
            loaded = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest.update({key: loaded.get(key, value) for key, value in manifest.items()})
        except json.JSONDecodeError:
            pass
    assets = [item for item in list(manifest.get("assets") or []) if isinstance(item, dict)]
    assets = [item for item in assets if item.get("public_mp4") != f"/media/horizons/{PUBLIC_MP4.name}"]
    streams = metadata.get("streams") or []
    assets.append(
        {
            "horizon_id": "origin-dossier",
            "surface_id": "origin-dossier",
            "surface_class": "core_product",
            "title": "Origin Dossier: The Name She Chose",
            "public_mp4": f"/media/horizons/{PUBLIC_MP4.name}",
            "public_webm": f"/media/horizons/{PUBLIC_WEBM.name}",
            "public_poster": f"/media/horizons/{PUBLIC_POSTER.name}",
            "public_captions": f"/media/horizons/{PUBLIC_VTT.name}",
            "legacy_public_mp4": f"/media/horizons/{LEGACY_PUBLIC_MP4.name}",
            "source_completion_file": str(SOURCE_MP4),
            "caption": "A cinematic Origin Dossier story trailer about Mara Vale becoming Kestrel.",
            "duration_seconds": float((metadata.get("format") or {}).get("duration") or 0.0),
            "size_bytes": int((metadata.get("format") or {}).get("size") or PUBLIC_MP4.stat().st_size),
            "has_video": any(stream.get("codec_type") == "video" for stream in streams),
            "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
            "audio_mean_volume_db": audio_stats.get("mean_volume_db"),
            "audio_max_volume_db": audio_stats.get("max_volume_db"),
            "video_codec": next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == "video"), ""),
            "audio_codec": next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == "audio"), ""),
        }
    )
    manifest["assets"] = assets
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def volume_stats(path: Path) -> dict[str, float]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-600:])
    stats: dict[str, float] = {}
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            stats["mean_volume_db"] = float(line.rsplit(" ", 2)[-2])
        if "max_volume:" in line:
            stats["max_volume_db"] = float(line.rsplit(" ", 2)[-2])
    if "mean_volume_db" not in stats or "max_volume_db" not in stats:
        raise RuntimeError("volumedetect_missing_stats")
    return stats


def validate(path: Path) -> tuple[dict[str, Any], dict[str, float]]:
    metadata = probe(path)
    streams = metadata.get("streams") or []
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise RuntimeError("origin_dossier_video_stream_missing")
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise RuntimeError("origin_dossier_audio_stream_missing")
    length = float((metadata.get("format") or {}).get("duration") or 0.0)
    if length < 88.0:
        raise RuntimeError(f"origin_dossier_video_too_short:{length:.3f}")
    stats = volume_stats(path)
    if stats["max_volume_db"] <= -35.0 or stats["mean_volume_db"] <= -45.0:
        raise RuntimeError(f"origin_dossier_audio_too_quiet:{stats}")
    return metadata, stats


def main() -> int:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    plate = load_source_plate()
    slides = [draw_slide(index, scene, plate) for index, scene in enumerate(SCENES)]
    voice_wav, voice_provider, voice_duration = render_voice()
    total_seconds = max(TARGET_SECONDS, min(96.0, voice_duration + 2.0))
    audio = render_mix(voice_wav, total_seconds)
    build_video(slides, audio, total_seconds)
    write_vtt(SOURCE_VTT, total_seconds)
    source_metadata, source_audio_stats = validate(SOURCE_MP4)
    publish_public(total_seconds)
    public_metadata, public_audio_stats = validate(PUBLIC_MP4)
    update_manifest(public_metadata, public_audio_stats)
    magicfit_status = {}
    if MAGICFIT_STATUS.is_file():
        magicfit_status = json.loads(MAGICFIT_STATUS.read_text(encoding="utf-8"))
    receipt = {
        "contract_name": "chummer.origin_dossier_kestrel_trailer.v1",
        "generated_at_utc": now_iso(),
        "status": "published",
        "asset_id": ASSET_ID,
        "title": "Origin Dossier: The Name She Chose",
        "public_url": f"https://chummer.run/media/horizons/{PUBLIC_MP4.name}",
        "legacy_public_url": f"https://chummer.run/media/horizons/{LEGACY_PUBLIC_MP4.name}",
        "public_mp4": str(PUBLIC_MP4),
        "public_webm": str(PUBLIC_WEBM),
        "public_poster": str(PUBLIC_POSTER),
        "public_vtt": str(PUBLIC_VTT),
        "source_mp4": str(SOURCE_MP4),
        "source_vtt": str(SOURCE_VTT),
        "duration_seconds": float((public_metadata.get("format") or {}).get("duration") or total_seconds),
        "voice": {
            "provider": voice_provider,
            "direction": "adult female, restrained, intimate, scarred but not defeated",
            "word_count": len(NARRATION.split()),
        },
        "sound": {
            "has_music_bed": True,
            "low_frequency_rumble_avoidance": "bed high-passed at 360Hz; final mix uses the public-video cleanup chain with 270Hz high-pass and 188/235Hz low-tone notches",
            "mean_volume_db": public_audio_stats.get("mean_volume_db"),
            "max_volume_db": public_audio_stats.get("max_volume_db"),
        },
        "render_mode": "first_party_cinematic_motion_trailer",
        "magicfit_claim": {
            "full_reel_claim_allowed": False,
            "status": magicfit_status.get("status", "unknown"),
            "reason": (magicfit_status.get("full_reel") or {}).get("reason", ""),
            "proof_clip": (magicfit_status.get("proof_clip") or {}).get("file", ""),
        },
        "source_metadata": source_metadata,
        "public_metadata": public_metadata,
        "scenes": list(SCENES),
    }
    TARGET_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "published", "receipt": str(TARGET_RECEIPT), "public_url": receipt["public_url"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
