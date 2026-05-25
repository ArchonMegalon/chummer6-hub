#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


FACTION_SCRIPT = Path("/docker/chummercomplete/chummer.run-services/scripts/build_black_ledger_faction_motion_videos.py")
SPEC = importlib.util.spec_from_file_location("build_black_ledger_faction_motion_videos", FACTION_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
FACTION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = FACTION
SPEC.loader.exec_module(FACTION)


ROOT = Path("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/promo")
FPS = 30
SECONDS_PER_SCENE = 45 / 7
TOTAL_SECONDS = 45
TOTAL_FRAMES = FPS * TOTAL_SECONDS
SCENE_FRAMES = TOTAL_FRAMES // 7
CANVAS_WIDTH = FACTION.CANVAS_WIDTH
CANVAS_HEIGHT = FACTION.CANVAS_HEIGHT
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080


@dataclass(frozen=True)
class TrailerScene:
    label: str
    caption: str
    command: str
    environment: str
    camera: FACTION.CameraPath
    accent: tuple[int, int, int]


SCENES: tuple[TrailerScene, ...] = (
    TrailerScene(
        "Opening bulletin",
        "Tonight on Chummer6: a glam-news anchor opens the Black Ledger war bulletin before the city breaks into motion.",
        "anchor",
        "newsroom",
        FACTION.CameraPath(50, 70, 120, 40, 1.0, 1.08),
        (255, 110, 80),
    ),
    TrailerScene(
        "Street signal",
        "An orkish field correspondent catches the live signal drop while runners break into the street below.",
        "report",
        "street_signal",
        FACTION.CameraPath(100, 90, 190, 70, 1.0, 1.12),
        (112, 220, 255),
    ),
    TrailerScene(
        "Desktop build",
        "A builder tunes the desktop sheet under studio lights before the next crisis packet lands.",
        "point",
        "desktop_build",
        FACTION.CameraPath(180, 80, 110, 70, 1.0, 1.14),
        (255, 190, 86),
    ),
    TrailerScene(
        "GM cockpit",
        "The GM cockpit turns pressure, fallout, and rulings into one visible command rail.",
        "signal",
        "gm_cockpit",
        FACTION.CameraPath(120, 80, 210, 90, 1.02, 1.16),
        (132, 255, 232),
    ),
    TrailerScene(
        "Black Ledger geoscape",
        "District pressure swings across the geoscape while operators pivot the next move live on air.",
        "hack",
        "geoscape",
        FACTION.CameraPath(80, 60, 220, 90, 1.0, 1.1),
        (186, 152, 255),
    ),
    TrailerScene(
        "Remote reaction",
        "A remote packet turns into a response and comes back to the GM as a visible decision receipt.",
        "signal",
        "remote_reaction",
        FACTION.CameraPath(100, 90, 190, 60, 1.03, 1.16),
        (154, 236, 110),
    ),
    TrailerScene(
        "Karma Forge and CTA",
        "Creators push fixes forward, the community sees the follow-through, and the anchor closes with the call to join the next turn.",
        "anchor",
        "newsroom",
        FACTION.CameraPath(70, 80, 150, 40, 1.02, 1.18),
        (255, 226, 132),
    ),
)


def draw_gradient(draw: ImageDraw.ImageDraw, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    FACTION.draw_gradient(draw, top, bottom)


def draw_stage(draw: ImageDraw.ImageDraw, scene: TrailerScene, phase: float) -> None:
    if scene.environment == "newsroom":
        FACTION.draw_newsroom(draw, scene.accent)
        draw.text((210, 182), "CHUMMER6 NIGHT BULLETIN", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((210, 242), scene.label.upper(), fill=scene.accent, font=FACTION.LABEL_FONT)
        draw.text((980, 186), "LIVE", fill=(255, 226, 180), font=FACTION.LABEL_FONT)
        draw.text((980, 228), "COMMUNITY // DESKTOP // BLACK LEDGER", fill=(190, 210, 236), font=FACTION.BODY_FONT)
        draw.rectangle((0, 856, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(12, 10, 16))
        ticker = "CHUMMER6 // BUILD THE RUNNER // RUN THE TABLE // MOVE THE CITY"
        draw.text((80 - (phase * 160), 874), ticker, fill=scene.accent, font=FACTION.LABEL_FONT)
    elif scene.environment == "street_signal":
        FACTION.draw_gradient(draw, (10, 12, 24), (28, 18, 20))
        FACTION.draw_grid(draw, (34, 28, 38))
        FACTION.draw_skyline(draw, scene.accent)
        draw.rectangle((0, 620, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(18, 18, 24))
        for x in range(80, CANVAS_WIDTH, 180):
            draw.line((x, 625, x + 70, CANVAS_HEIGHT), fill=(80, 82, 92), width=4)
        draw.rounded_rectangle((1020, 210, 1450, 360), radius=18, fill=(10, 18, 28), outline=scene.accent, width=4)
        draw.text((1055, 245), "STREET SIGNAL", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((1055, 302), "DROP CONFIRMED // 02:14", fill=scene.accent, font=FACTION.LABEL_FONT)
    elif scene.environment == "desktop_build":
        draw_gradient(draw, (18, 20, 28), (10, 14, 18))
        draw.rounded_rectangle((120, 120, 1520, 770), radius=28, fill=(14, 22, 30), outline=scene.accent, width=4)
        draw.rounded_rectangle((180, 190, 760, 710), radius=20, fill=(24, 32, 42), outline=(90, 120, 138), width=3)
        draw.rounded_rectangle((820, 190, 1460, 710), radius=20, fill=(18, 26, 38), outline=(90, 120, 138), width=3)
        for idx, y in enumerate(range(240, 660, 68)):
            draw.line((860, y, 1390, y), fill=scene.accent if idx % 2 == 0 else (88, 116, 142), width=6)
        draw.text((220, 218), "BUILD", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((220, 274), "Essence 5.8 // Gear tuned // Spell list ready", fill=scene.accent, font=FACTION.LABEL_FONT)
    elif scene.environment == "gm_cockpit":
        draw_gradient(draw, (26, 18, 12), (10, 10, 14))
        for x in range(150, 1450, 260):
            draw.rounded_rectangle((x, 180, x + 210, 330), radius=18, fill=(34, 24, 20), outline=scene.accent, width=3)
        draw.rounded_rectangle((160, 410, 1440, 790), radius=24, fill=(18, 16, 20), outline=scene.accent, width=4)
        for x in range(220, 1380, 190):
            top = 720 - int(120 * abs(math.sin(phase * math.pi + (x / 200))))
            draw.rectangle((x, top, x + 80, 748), fill=scene.accent)
        draw.text((210, 450), "GM COCKPIT", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((210, 510), "Threat clocks, packet pressure, and aftermath stay on one rail.", fill=scene.accent, font=FACTION.LABEL_FONT)
    elif scene.environment == "geoscape":
        draw_gradient(draw, (6, 10, 20), (4, 6, 10))
        center = (790, 470)
        draw.ellipse((300, 80, 1280, 860), outline=(80, 138, 170), width=4)
        for radius in (180, 260, 340):
            draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=(18, 58, 78), width=2)
        points = [(500, 360), (690, 260), (880, 300), (1030, 430), (920, 610), (660, 620), (470, 500)]
        for px, py in points:
            pulse = 28 + int(14 * math.sin((phase * math.pi * 2) + (px / 120)))
            draw.ellipse((px - pulse, py - pulse, px + pulse, py + pulse), outline=scene.accent, width=4)
        for start, end in zip(points, points[1:] + [points[0]]):
            draw.line((*start, *end), fill=(142, 220, 238), width=3)
        draw.text((150, 128), "BLACK LEDGER GEOSCAPE", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((150, 188), "Conflict, logistics, and rumor pressure move together.", fill=scene.accent, font=FACTION.LABEL_FONT)
    elif scene.environment == "remote_reaction":
        draw_gradient(draw, (14, 12, 24), (20, 18, 32))
        draw.rounded_rectangle((180, 150, 620, 760), radius=34, fill=(10, 14, 26), outline=scene.accent, width=4)
        draw.rounded_rectangle((970, 160, 1410, 740), radius=26, fill=(12, 18, 30), outline=(132, 166, 220), width=4)
        draw.text((235, 205), "REMOTE REACTION", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((235, 272), "Packet intercepted // Reply armed", fill=scene.accent, font=FACTION.LABEL_FONT)
        draw.text((1030, 220), "GM RECEIPT", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((1030, 286), "Accept // Delay // Modify // Reject", fill=(180, 200, 255), font=FACTION.LABEL_FONT)
        draw.line((660, 300, 930, 300), fill=scene.accent, width=6)
        draw.line((660, 420, 930, 420), fill=(255, 255, 255), width=3)
        draw.line((660, 540, 930, 540), fill=scene.accent, width=6)
    elif scene.environment == "karma_forge":
        draw_gradient(draw, (20, 22, 16), (12, 18, 12))
        draw.rounded_rectangle((160, 160, 1440, 760), radius=24, fill=(16, 20, 18), outline=scene.accent, width=4)
        for idx, x in enumerate((230, 500, 770, 1040, 1310)):
            height = 120 + int(140 * abs(math.sin((phase * math.pi) + idx)))
            draw.rounded_rectangle((x - 80, 680 - height, x + 80, 680), radius=18, fill=(42, 52, 38), outline=scene.accent, width=3)
        draw.text((210, 214), "KARMA FORGE", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((210, 278), "Candidate rules, public-safe proof, community follow-through.", fill=scene.accent, font=FACTION.LABEL_FONT)
    else:
        draw_gradient(draw, (10, 14, 20), (20, 10, 12))
        FACTION.draw_skyline(draw, scene.accent)
        draw.rounded_rectangle((120, 128, 1480, 790), radius=32, fill=(6, 10, 14, 180), outline=scene.accent, width=4)
        draw.text((210, 248), "CHUMMER6", fill=(255, 255, 255), font=FACTION.TITLE_FONT)
        draw.text((210, 322), "Build the runner. Run the table. Move the city.", fill=scene.accent, font=FACTION.TITLE_FONT)
        draw.text((210, 404), "chummer.run", fill=(255, 240, 190), font=FACTION.TITLE_FONT)


def draw_people(draw: ImageDraw.ImageDraw, scene: TrailerScene, phase: float) -> None:
    if scene.environment == "newsroom":
        FACTION.draw_person(draw, 790, 760, 1.66, scene.accent, (70, 40, 32), "anchor", phase)
        if scene.label.startswith("Karma Forge"):
            FACTION.draw_person(draw, 1140, 724, 0.9, (154, 236, 110), (56, 82, 46), "signal", phase)
    elif scene.environment == "street_signal":
        FACTION.draw_person(draw, 430, 700, 1.3, scene.accent, (58, 42, 34), "report", phase, bulk=1.16)
        FACTION.draw_person(draw, 820, 700, 0.82, (188, 190, 204), (72, 74, 82), "run", phase, bulk=0.95)
        FACTION.draw_person(draw, 980, 708, 0.78, (160, 150, 134), (68, 64, 58), "run", phase, bulk=0.9)
    elif scene.environment == "desktop_build":
        FACTION.draw_person(draw, 540, 720, 1.22, scene.accent, (52, 76, 96), "point", phase)
        FACTION.draw_person(draw, 1130, 716, 0.94, (208, 170, 124), (86, 70, 54), "signal", phase)
    elif scene.environment == "gm_cockpit":
        FACTION.draw_person(draw, 540, 708, 1.18, scene.accent, (86, 52, 28), "signal", phase)
        FACTION.draw_person(draw, 1080, 720, 1.04, (190, 180, 170), (74, 66, 58), "point", phase)
    elif scene.environment == "geoscape":
        FACTION.draw_person(draw, 420, 690, 1.02, scene.accent, (38, 64, 82), "hack", phase)
        FACTION.draw_person(draw, 1180, 700, 1.0, (212, 180, 124), (80, 60, 46), "point", phase)
    elif scene.environment == "remote_reaction":
        FACTION.draw_person(draw, 420, 700, 1.16, scene.accent, (58, 54, 110), "signal", phase)
        FACTION.draw_person(draw, 1170, 700, 1.1, (190, 174, 144), (70, 62, 54), "point", phase)
    elif scene.environment == "karma_forge":
        FACTION.draw_person(draw, 460, 700, 1.1, scene.accent, (54, 72, 40), "advance", phase)
        FACTION.draw_person(draw, 790, 704, 0.98, (180, 190, 144), (62, 72, 52), "point", phase)
        FACTION.draw_person(draw, 1100, 708, 0.96, (164, 144, 202), (68, 56, 84), "signal", phase)
    else:
        FACTION.draw_person(draw, 520, 710, 1.12, scene.accent, (72, 84, 94), "advance", phase)
        FACTION.draw_person(draw, 760, 706, 1.06, (200, 170, 132), (82, 62, 44), "signal", phase)
        FACTION.draw_person(draw, 1010, 712, 1.0, (180, 132, 120), (74, 54, 44), "point", phase)


def render_scene(scene: TrailerScene, scene_progress: float, absolute_progress: float) -> Image.Image:
    image = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    draw_stage(draw, scene, scene_progress)
    image = FACTION.add_glow(image, (-120, -60, 520, 420), scene.accent, 74, 42)
    image = FACTION.add_glow(image, (CANVAS_WIDTH - 520, 40, CANVAS_WIDTH + 120, 700), tuple(min(255, c + 30) for c in scene.accent), 92, 58)
    draw = ImageDraw.Draw(image)
    draw_people(draw, scene, scene_progress)
    draw.rounded_rectangle((72, 60, 860, 188), radius=24, fill=(6, 10, 18, 192), outline=(*scene.accent, 210), width=3)
    draw.text((104, 84), scene.label.upper(), fill=(255, 255, 255), font=FACTION.TITLE_FONT)
    draw.text((106, 136), scene.command.upper(), fill=scene.accent, font=FACTION.LABEL_FONT)
    draw.rounded_rectangle((66, 712, 1534, 844), radius=18, fill=(6, 10, 16, 208), outline=(*scene.accent, 210), width=3)
    wrapped = FACTION.wrap_text(draw, scene.caption, FACTION.BODY_FONT, 1360)
    y = 740
    for line in wrapped[:3]:
        draw.text((96, y), line, fill=(255, 255, 255), font=FACTION.BODY_FONT)
        y += 34
    draw.text((96, 804), "FIRST-PARTY BUILDS // TABLE PRESSURE // COMMUNITY FOLLOW-THROUGH", fill=scene.accent, font=FACTION.LABEL_FONT)
    return image


def write_vtt(path: Path) -> None:
    lines = ["WEBVTT", ""]
    for index, scene in enumerate(SCENES):
        start = index * SECONDS_PER_SCENE
        end = (index + 1) * SECONDS_PER_SCENE
        lines.append(str(index + 1))
        lines.append(f"{format_ts(start)} --> {format_ts(end)}")
        lines.append(scene.caption)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def format_ts(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def render() -> None:
    mp4_path = ROOT / "chummer6-flagship-promo.mp4"
    webm_path = ROOT / "chummer6-flagship-promo.webm"
    poster_path = ROOT / "chummer6-flagship-promo-poster.png"
    captions_path = ROOT / "chummer6-flagship-promo.vtt"
    with tempfile.TemporaryDirectory(prefix="chummer6-flagship-promo-") as temp_dir:
        frames_root = Path(temp_dir)
        for frame_index in range(TOTAL_FRAMES):
            scene_index = min(len(SCENES) - 1, frame_index // SCENE_FRAMES)
            scene = SCENES[scene_index]
            scene_frame = frame_index - (scene_index * SCENE_FRAMES)
            scene_progress = scene_frame / max(1, SCENE_FRAMES - 1)
            absolute_progress = frame_index / max(1, TOTAL_FRAMES - 1)
            image = render_scene(scene, scene_progress, absolute_progress)
            final_frame = FACTION.apply_camera(image, scene.camera, scene_progress)
            final_frame.save(frames_root / f"frame_{frame_index:04d}.png")

        audio_path = frames_root / "score.wav"
        FACTION.render_soundtrack(audio_path, TOTAL_SECONDS, (94, 188, 376))
        FACTION.encode_video(frames_root, audio_path, mp4_path, codec="libx264", crf="18", audio_codec="aac", bitrate="160k", size=(VIDEO_WIDTH, VIDEO_HEIGHT))
        FACTION.encode_video(frames_root, audio_path, webm_path, codec="libvpx-vp9", crf="34", audio_codec="libopus", bitrate="112k", size=(1280, 720))
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4_path),
                "-vf",
                "select=eq(n\\,675)",
                "-frames:v",
                "1",
                str(poster_path),
            ],
            check=True,
        )
    write_vtt(captions_path)


def main() -> int:
    render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
