#!/usr/bin/env python3
from __future__ import annotations

import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/ledger/factions")
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FPS = 30
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 900
FACTION_DURATION_SECONDS = 18
SCENE_SECONDS = 6
TOTAL_FRAMES = FPS * FACTION_DURATION_SECONDS
SCENE_FRAMES = FPS * SCENE_SECONDS


@dataclass(frozen=True)
class CameraPath:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    start_zoom: float
    end_zoom: float


@dataclass(frozen=True)
class Scene:
    label: str
    action: str
    environment: str
    conflict: str
    camera: CameraPath


@dataclass(frozen=True)
class FactionSpec:
    slug: str
    title: str
    primary: tuple[int, int, int]
    secondary: tuple[int, int, int]
    sky: tuple[int, int, int]
    ground: tuple[int, int, int]
    lead_role: str
    audio_frequencies: tuple[int, int, int]
    captions: tuple[str, str, str]
    scenes: tuple[Scene, Scene, Scene]


FACTIONS: tuple[FactionSpec, ...] = (
    FactionSpec(
        slug="glass-tower-compact",
        title="Glass Tower Compact",
        primary=(124, 214, 255),
        secondary=(33, 52, 112),
        sky=(8, 18, 40),
        ground=(20, 28, 46),
        lead_role="Executive security captain",
        audio_frequencies=(108, 216, 432),
        captions=(
            "Tonight on the Black Ledger: the Compact swears the skyline still answers to executive command.",
            "An orkish correspondent watches security teams lock the skybridge while residents surge below.",
            "The captain leads the closeout and sells control as a visible public performance, not a whispered claim.",
        ),
        scenes=(
            Scene("Night bulletin", "anchor", "newsroom", "prestige_under_siege", CameraPath(50, 70, 120, 40, 1.0, 1.06)),
            Scene("Live skybridge report", "report", "atrium", "authority_vs_panic", CameraPath(220, 80, 120, 120, 1.04, 1.12)),
            Scene("Compact closeout", "advance", "rooftop", "proof_of_control", CameraPath(120, 60, 220, 110, 1.08, 1.18)),
        ),
    ),
    FactionSpec(
        slug="rust-market-syndicate",
        title="Rust Market Syndicate",
        primary=(255, 170, 78),
        secondary=(94, 38, 20),
        sky=(28, 14, 12),
        ground=(52, 32, 18),
        lead_role="Market loader-boss",
        audio_frequencies=(96, 148, 296),
        captions=(
            "The lead bulletin says the Rust Market books are being settled in public tonight.",
            "An orkish correspondent reports from the freight lane as loaders swing crates through a panicked crowd.",
            "The loader-boss forces a brutal recovery spectacle and challenges the district to call it bluff instead of order.",
        ),
        scenes=(
            Scene("Night bulletin", "anchor", "newsroom", "public_debt_pressure", CameraPath(50, 70, 120, 40, 1.0, 1.06)),
            Scene("Freight lane report", "report", "market", "profit_vs_panic", CameraPath(220, 120, 100, 160, 1.04, 1.12)),
            Scene("Recovery claim", "carry", "checkpoint", "proof_of_closeout", CameraPath(120, 50, 240, 110, 1.08, 1.16)),
        ),
    ),
    FactionSpec(
        slug="ashline-circle",
        title="Ashline Circle",
        primary=(240, 155, 76),
        secondary=(101, 24, 39),
        sky=(20, 10, 18),
        ground=(44, 22, 18),
        lead_role="Awakened enforcer",
        audio_frequencies=(118, 236, 472),
        captions=(
            "The nightly anchor warns that Ashline ritual authority is moving from rumor into visible force.",
            "An orkish correspondent stands at the edge of the ward ring as heat lifts and the crowd recoils.",
            "The enforcer walks into the firelight and turns mystical intimidation into a televised claim of dominion.",
        ),
        scenes=(
            Scene("Night bulletin", "anchor", "newsroom", "ritual_control_vs_fear", CameraPath(50, 70, 120, 40, 1.0, 1.06)),
            Scene("Ward ring report", "report", "ritual", "public_order_vs_chaos", CameraPath(200, 80, 120, 150, 1.04, 1.12)),
            Scene("Witnessed oath", "cast", "ritual", "proof_of_supremacy", CameraPath(120, 60, 250, 110, 1.08, 1.2)),
        ),
    ),
    FactionSpec(
        slug="neon-docks-union",
        title="Neon Docks Union",
        primary=(112, 240, 255),
        secondary=(20, 82, 92),
        sky=(10, 20, 28),
        ground=(18, 44, 52),
        lead_role="Dock rigger",
        audio_frequencies=(92, 184, 368),
        captions=(
            "The bulletin opens with a claim that the docks will keep moving no matter who cut the alarms.",
            "An orkish correspondent reports from the catwalk while containers swing and the harbor fog flashes electric blue.",
            "The dock rigger seizes the gantry line and turns logistics into a hard-edged display of union control.",
        ),
        scenes=(
            Scene("Night bulletin", "anchor", "newsroom", "throughput_vs_sabotage", CameraPath(50, 70, 120, 40, 1.0, 1.06)),
            Scene("Catwalk report", "report", "docks", "route_control_vs_delay", CameraPath(240, 90, 120, 150, 1.04, 1.12)),
            Scene("Harbor proof", "run", "harbor", "proof_of_delivery", CameraPath(120, 70, 240, 90, 1.1, 1.18)),
        ),
    ),
    FactionSpec(
        slug="ghostline-network",
        title="Ghostline Network",
        primary=(145, 255, 242),
        secondary=(14, 34, 52),
        sky=(8, 14, 22),
        ground=(14, 24, 34),
        lead_role="Signal operator",
        audio_frequencies=(128, 192, 384),
        captions=(
            "The opener says Ghostline is fighting for the signal itself, not just the street beneath it.",
            "An orkish correspondent breaks through a glitching wall of screens while false feeds die behind him.",
            "The operator kills the rumor stream and reasserts verified narrative control in full public view.",
        ),
        scenes=(
            Scene("Night bulletin", "anchor", "newsroom", "truth_vs_rumor", CameraPath(50, 70, 120, 40, 1.0, 1.06)),
            Scene("Signal room report", "report", "signal_room", "verification_vs_static", CameraPath(220, 110, 120, 170, 1.04, 1.12)),
            Scene("Broadcast close", "hack", "broadcast_wall", "proof_of_control", CameraPath(100, 70, 230, 110, 1.08, 1.18)),
        ),
    ),
    FactionSpec(
        slug="barrens-free-wardens",
        title="Barrens Free Wardens",
        primary=(194, 210, 124),
        secondary=(40, 64, 51),
        sky=(10, 14, 18),
        ground=(28, 32, 24),
        lead_role="Convoy marshal",
        audio_frequencies=(84, 168, 336),
        captions=(
            "The bulletin says the Wardens are broadcasting survival as a promise, not a slogan.",
            "An orkish correspondent crouches at the barricade while floodlights catch steel and frightened civilians.",
            "The convoy marshal drives the line forward and sells protection as something the whole district can witness.",
        ),
        scenes=(
            Scene("Night bulletin", "anchor", "newsroom", "defense_vs_collapse", CameraPath(50, 70, 120, 40, 1.0, 1.06)),
            Scene("Barricade report", "report", "barricade", "survival_vs_attrition", CameraPath(220, 100, 120, 160, 1.04, 1.12)),
            Scene("Witness close", "advance", "barricade", "proof_of_stand", CameraPath(120, 70, 240, 110, 1.08, 1.18)),
        ),
    ),
)


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = FONT_DIR / name
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


TITLE_FONT = font(46, bold=True)
LABEL_FONT = font(24, bold=True)
BODY_FONT = font(22)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ease(progress: float) -> float:
    progress = clamp(progress, 0.0, 1.0)
    return progress * progress * (3 - (2 * progress))


def lerp(a: float, b: float, progress: float) -> float:
    return a + ((b - a) * progress)


def blend(a: tuple[int, int, int], b: tuple[int, int, int], progress: float) -> tuple[int, int, int]:
    return tuple(int(lerp(x, y, progress)) for x, y in zip(a, b))


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word]).strip()
        if candidate and draw.textlength(candidate, font=font_obj) <= width:
            current.append(word)
            continue
        if current:
            lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def add_glow(base: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int], alpha: int, blur: int) -> Image.Image:
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse(box, fill=(*color, alpha))
    return Image.alpha_composite(base.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(radius=blur)))


def draw_gradient(draw: ImageDraw.ImageDraw, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    for y in range(CANVAS_HEIGHT):
        mix = y / max(1, CANVAS_HEIGHT - 1)
        color = blend(top, bottom, mix)
        draw.line((0, y, CANVAS_WIDTH, y), fill=color)


def draw_grid(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    for x in range(0, CANVAS_WIDTH, 96):
        draw.line((x, 0, x, CANVAS_HEIGHT), fill=color, width=1)
    for y in range(0, CANVAS_HEIGHT, 72):
        draw.line((0, y, CANVAS_WIDTH, y), fill=color, width=1)


def draw_skyline(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    blocks = [
        (0, 360, 180, 900),
        (120, 250, 340, 900),
        (300, 140, 520, 900),
        (500, 280, 660, 900),
        (620, 180, 860, 900),
        (840, 320, 1040, 900),
        (1010, 120, 1240, 900),
        (1200, 230, 1410, 900),
        (1380, 180, 1600, 900),
    ]
    for index, (x0, y0, x1, y1) in enumerate(blocks):
        shade = 26 + (index * 5)
        draw.rectangle((x0, y0, x1, y1), fill=(shade, shade + 8, shade + 18))
        for wx in range(x0 + 18, x1 - 10, 28):
            for wy in range(y0 + 20, y1 - 20, 38):
                if (wx + wy) % 3 == 0:
                    draw.rectangle((wx, wy, wx + 10, wy + 18), fill=(*accent, 180))


def draw_newsroom(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 0, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(8, 10, 18))
    for y in range(0, CANVAS_HEIGHT, 4):
        glow = 18 + int((y / CANVAS_HEIGHT) * 30)
        draw.line((0, y, CANVAS_WIDTH, y), fill=(glow, glow + 4, glow + 10))
    draw.rounded_rectangle((120, 110, 1480, 430), radius=28, fill=(14, 18, 30), outline=accent, width=4)
    draw.rounded_rectangle((160, 150, 860, 388), radius=20, fill=(18, 26, 38), outline=(84, 120, 160), width=3)
    draw.rounded_rectangle((910, 150, 1440, 388), radius=20, fill=(16, 18, 26), outline=(84, 120, 160), width=3)
    for index in range(9):
        x = 965 + (index * 48)
        top = 338 - (index % 3) * 26
        draw.rectangle((x, top, x + 28, 360), fill=accent)
    draw.rounded_rectangle((240, 470, 1360, 800), radius=40, fill=(10, 14, 22), outline=(36, 46, 68), width=4)
    draw.polygon([(260, 760), (1340, 760), (1260, 820), (340, 820)], fill=(20, 28, 42))
    draw.ellipse((1240, 170, 1540, 470), fill=(*accent, 30), outline=(*accent, 80), width=3)
    draw.ellipse((-80, 100, 240, 420), fill=(*accent, 25), outline=(*accent, 70), width=3)


def draw_warehouse(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 520, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(42, 28, 22))
    for index in range(5):
        x = 90 + (index * 280)
        draw.rectangle((x, 340, x + 220, 760), fill=(74, 52, 36), outline=(130, 92, 64), width=3)
        for level in range(4):
            y = 380 + (level * 86)
            draw.line((x + 18, y, x + 202, y), fill=(156, 110, 72), width=4)
    for index in range(8):
        cx = 80 + (index * 190)
        draw.rectangle((cx, 480, cx + 70, 540), fill=accent, outline=(255, 240, 210), width=2)


def draw_docks(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 560, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(18, 42, 52))
    for y in range(565, CANVAS_HEIGHT, 28):
        draw.line((0, y, CANVAS_WIDTH, y), fill=(24, 66, 78), width=2)
    for x in (220, 480, 820, 1160, 1420):
        draw.rectangle((x, 180, x + 22, 760), fill=(54, 76, 82))
        draw.line((x + 11, 180, x + 150, 120), fill=accent, width=6)
        draw.line((x + 11, 260, x + 180, 260), fill=(110, 156, 166), width=5)
    for index in range(4):
        base_x = 180 + (index * 320)
        draw.rectangle((base_x, 450, base_x + 180, 540), fill=(52, 92, 104), outline=accent, width=3)


def draw_signal_room(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 0, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(8, 16, 28))
    for row in range(3):
        for col in range(5):
            x = 110 + (col * 280)
            y = 110 + (row * 170)
            draw.rounded_rectangle((x, y, x + 220, y + 120), radius=14, fill=(20, 32, 48), outline=accent, width=3)
            draw.line((x + 16, y + 28, x + 200, y + 28), fill=(140, 200, 220), width=3)
            draw.line((x + 16, y + 54, x + 180, y + 54), fill=(90, 160, 190), width=3)
            draw.line((x + 16, y + 82, x + 150, y + 82), fill=(60, 120, 150), width=3)


def draw_barricade(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 560, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(32, 32, 26))
    for x in range(0, CANVAS_WIDTH, 120):
        draw.rectangle((x, 520, x + 46, 900), fill=(58, 60, 50))
    for index in range(7):
        x = 120 + (index * 190)
        draw.rectangle((x, 500, x + 100, 560), fill=(76, 80, 66), outline=accent, width=2)
    for lx in (180, 530, 900, 1260):
        draw.rectangle((lx, 180, lx + 18, 560), fill=(180, 190, 150))
        draw.ellipse((lx - 90, 120, lx + 110, 320), fill=(*accent, 120))


def draw_atrium(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 510, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(28, 34, 42))
    for index in range(6):
        x = 140 + (index * 220)
        draw.line((x, 160, x - 90, 720), fill=(96, 132, 160), width=10)
        draw.line((x + 60, 160, x + 150, 720), fill=(96, 132, 160), width=10)
        draw.line((x - 90, 720, x + 150, 720), fill=accent, width=4)


def draw_rooftop(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 560, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(18, 20, 28))
    for x in range(60, CANVAS_WIDTH, 120):
        draw.rectangle((x, 480, x + 22, 760), fill=(76, 86, 108))
        draw.line((x + 11, 480, x + 70, 420), fill=accent, width=4)
    for index in range(12):
        x = 50 + (index * 130)
        draw.line((x, 620, x + 80, 620), fill=(120, 140, 172), width=3)


def draw_ritual(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int], phase: float) -> None:
    center = (800, 560)
    radius = 200 + int(18 * math.sin(phase * math.pi * 4))
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=accent, width=6)
    draw.ellipse((center[0] - radius + 44, center[1] - radius + 44, center[0] + radius - 44, center[1] + radius - 44), outline=(255, 222, 180), width=3)
    for angle in range(0, 360, 45):
        rad = math.radians(angle + (phase * 16))
        x = center[0] + int(math.cos(rad) * radius)
        y = center[1] + int(math.sin(rad) * radius)
        draw.line((center[0], center[1], x, y), fill=accent, width=2)


def draw_harbor(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 540, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(12, 36, 44))
    for y in range(550, CANVAS_HEIGHT, 26):
        draw.line((0, y, CANVAS_WIDTH, y), fill=(22, 58, 70), width=2)
    for idx in range(5):
        x = 160 + (idx * 260)
        draw.rectangle((x, 410, x + 140, 500), fill=(44, 88, 100), outline=accent, width=3)
    for idx in range(4):
        x = 240 + (idx * 320)
        draw.rectangle((x, 260, x + 10, 540), fill=(190, 210, 214))
        draw.ellipse((x - 80, 170, x + 90, 330), fill=(*accent, 90))


def draw_broadcast_wall(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw_signal_room(draw, accent)
    draw.rectangle((1020, 120, 1530, 690), outline=(220, 240, 250), width=4)
    for row in range(5):
        y = 150 + (row * 100)
        draw.line((1045, y, 1490, y + 30), fill=accent, width=3)


def draw_checkpoint(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    draw.rectangle((0, 560, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(34, 24, 18))
    for index in range(6):
        x = 90 + (index * 240)
        draw.rectangle((x, 420, x + 150, 560), fill=(60, 42, 24), outline=accent, width=3)
    draw.line((0, 610, CANVAS_WIDTH, 610), fill=(180, 150, 82), width=8)
    draw.line((0, 650, CANVAS_WIDTH, 650), fill=(180, 150, 82), width=8)


def environment_renderer(environment: str):
    return {
        "newsroom": draw_newsroom,
        "skybridge": draw_skyline,
        "atrium": draw_atrium,
        "rooftop": draw_rooftop,
        "market": draw_warehouse,
        "checkpoint": draw_checkpoint,
        "ritual": lambda draw, accent, phase=0.0: draw_ritual(draw, accent, phase),
        "docks": draw_docks,
        "harbor": draw_harbor,
        "signal_room": draw_signal_room,
        "broadcast_wall": draw_broadcast_wall,
        "barricade": draw_barricade,
    }[environment]


def draw_face_features(
    draw: ImageDraw.ImageDraw,
    x: float,
    head_top: float,
    head_r: float,
    *,
    eye_color: tuple[int, int, int],
    hair_color: tuple[int, int, int],
    tusks: bool = False,
    pompadour: bool = False,
) -> None:
    eye_y = head_top + (head_r * 1.1)
    eye_w = max(2, int(head_r * 0.26))
    draw.ellipse((x - head_r * 0.55, eye_y, x - head_r * 0.15, eye_y + eye_w), fill=eye_color)
    draw.ellipse((x + head_r * 0.15, eye_y, x + head_r * 0.55, eye_y + eye_w), fill=eye_color)
    brow_y = eye_y - (head_r * 0.18)
    draw.line((x - head_r * 0.65, brow_y, x - head_r * 0.12, brow_y - head_r * 0.12), fill=hair_color, width=max(1, int(head_r * 0.12)))
    draw.line((x + head_r * 0.12, brow_y - head_r * 0.12, x + head_r * 0.65, brow_y), fill=hair_color, width=max(1, int(head_r * 0.12)))
    draw.line((x, eye_y + head_r * 0.15, x - head_r * 0.06, eye_y + head_r * 0.52), fill=(120, 92, 80), width=max(1, int(head_r * 0.08)))
    mouth_y = eye_y + (head_r * 0.84)
    draw.arc((x - head_r * 0.4, mouth_y - head_r * 0.18, x + head_r * 0.4, mouth_y + head_r * 0.24), start=5, end=175, fill=(120, 40, 40), width=max(1, int(head_r * 0.1)))
    if pompadour:
        draw.pieslice((x - head_r * 1.15, head_top - head_r * 0.55, x + head_r * 1.25, head_top + head_r * 1.0), start=180, end=355, fill=hair_color)
        draw.polygon(
            [
                (x - head_r * 0.45, head_top - head_r * 0.2),
                (x + head_r * 0.9, head_top - head_r * 0.9),
                (x + head_r * 0.5, head_top + head_r * 0.55),
            ],
            fill=hair_color,
        )
    else:
        draw.pieslice((x - head_r * 1.05, head_top - head_r * 0.25, x + head_r * 1.05, head_top + head_r * 1.0), start=180, end=360, fill=hair_color)
    if tusks:
        draw.polygon(
            [
                (x - head_r * 0.35, mouth_y + head_r * 0.1),
                (x - head_r * 0.16, mouth_y + head_r * 0.72),
                (x - head_r * 0.02, mouth_y + head_r * 0.08),
            ],
            fill=(246, 234, 214),
        )
        draw.polygon(
            [
                (x + head_r * 0.02, mouth_y + head_r * 0.08),
                (x + head_r * 0.16, mouth_y + head_r * 0.72),
                (x + head_r * 0.35, mouth_y + head_r * 0.1),
            ],
            fill=(246, 234, 214),
        )


def draw_person(draw: ImageDraw.ImageDraw, x: float, y: float, scale: float, primary: tuple[int, int, int], secondary: tuple[int, int, int], action: str, phase: float, *, bulk: float = 1.0) -> None:
    torso_h = 88 * scale * bulk
    torso_w = 34 * scale * bulk
    leg = 68 * scale * bulk
    arm = 58 * scale * bulk
    head_r = 18 * scale * bulk
    shoulder_y = y - torso_h
    hip_y = y - 10 * scale
    body = (20, 22, 28)
    skin = tuple(min(255, c + 50) for c in primary)
    outline = tuple(min(255, c + 40) for c in secondary)

    left_arm_angle = -0.9
    right_arm_angle = 0.9
    left_leg_angle = -0.2
    right_leg_angle = 0.2
    torso_tilt = 0.0
    jacket_color = body
    hair_color = tuple(max(0, c - 20) for c in secondary)
    eye_color = (245, 245, 250)
    face_tusks = False
    pompadour = False

    if action == "run":
        left_arm_angle = -1.0 + (0.4 * math.sin(phase * math.pi * 4))
        right_arm_angle = 1.0 - (0.4 * math.sin(phase * math.pi * 4))
        left_leg_angle = 0.6 * math.sin(phase * math.pi * 4)
        right_leg_angle = -0.6 * math.sin(phase * math.pi * 4)
        torso_tilt = 0.08
    elif action == "carry":
        left_arm_angle = -0.25
        right_arm_angle = 0.2
        left_leg_angle = -0.15 + (0.18 * math.sin(phase * math.pi * 2))
        right_leg_angle = 0.15 - (0.18 * math.sin(phase * math.pi * 2))
    elif action == "cast":
        left_arm_angle = -1.5 + (0.1 * math.sin(phase * math.pi * 2))
        right_arm_angle = 1.45 - (0.1 * math.sin(phase * math.pi * 2))
        left_leg_angle = -0.1
        right_leg_angle = 0.1
    elif action == "hack":
        left_arm_angle = -0.8
        right_arm_angle = 0.2
        left_leg_angle = -0.05
        right_leg_angle = 0.05
        torso_tilt = -0.06
    elif action == "signal":
        left_arm_angle = -0.3
        right_arm_angle = -1.35 + (0.05 * math.sin(phase * math.pi * 2))
        left_leg_angle = -0.1
        right_leg_angle = 0.1
    elif action == "point":
        left_arm_angle = -0.35
        right_arm_angle = -0.95
        left_leg_angle = -0.05
        right_leg_angle = 0.05
    elif action == "advance":
        left_arm_angle = -0.55 + (0.18 * math.sin(phase * math.pi * 2))
        right_arm_angle = 0.55 - (0.18 * math.sin(phase * math.pi * 2))
        left_leg_angle = 0.15 * math.sin(phase * math.pi * 2)
        right_leg_angle = -0.15 * math.sin(phase * math.pi * 2)
    elif action == "anchor":
        left_arm_angle = -0.55
        right_arm_angle = 0.35 - (0.05 * math.sin(phase * math.pi * 2))
        left_leg_angle = -0.02
        right_leg_angle = 0.02
        jacket_color = (18, 18, 24)
        hair_color = (24, 18, 14)
        pompadour = True
        body = jacket_color
    elif action == "report":
        left_arm_angle = -0.25
        right_arm_angle = 0.45
        left_leg_angle = -0.08
        right_leg_angle = 0.08
        jacket_color = (40, 48, 34)
        hair_color = (22, 18, 18)
        face_tusks = True
        skin = (112, 170, 102)
        outline = (66, 92, 58)
        body = jacket_color

    torso_x = x + (torso_tilt * torso_w)
    draw.rounded_rectangle(
        (torso_x - torso_w, shoulder_y, torso_x + torso_w, hip_y),
        radius=int(14 * scale),
        fill=body,
        outline=outline,
        width=max(1, int(2 * scale)),
    )
    head_box = (x - head_r, shoulder_y - (head_r * 2.2), x + head_r, shoulder_y - 4)
    draw.ellipse(head_box, fill=skin, outline=outline, width=max(1, int(scale)))
    head_top = shoulder_y - (head_r * 2.2)
    draw_face_features(draw, x, head_top, head_r, eye_color=eye_color, hair_color=hair_color, tusks=face_tusks, pompadour=pompadour)
    if action == "anchor":
        draw.rectangle((x - torso_w * 0.58, shoulder_y - 2, x + torso_w * 0.58, hip_y + 12), fill=(22, 24, 30))
        draw.polygon([(x, shoulder_y + 12 * scale), (x - 10 * scale, shoulder_y + 48 * scale), (x + 10 * scale, shoulder_y + 48 * scale)], fill=(190, 24, 36))
        draw.rectangle((x - 4 * scale, shoulder_y + 48 * scale, x + 4 * scale, hip_y + 10), fill=(190, 24, 36))
        draw.rectangle((x - torso_w * 0.8, shoulder_y + 6 * scale, x + torso_w * 0.8, shoulder_y + 18 * scale), fill=(236, 236, 238))
        draw.rectangle((x + torso_w * 0.22, shoulder_y + 38 * scale, x + torso_w * 0.58, shoulder_y + 52 * scale), fill=(224, 196, 112))
    elif action == "report":
        draw.rectangle((x - torso_w * 0.55, shoulder_y - 2, x + torso_w * 0.55, hip_y + 8), fill=(58, 68, 46))
        draw.rectangle((x - torso_w * 0.46, shoulder_y + 18 * scale, x + torso_w * 0.46, hip_y - 8 * scale), fill=(40, 48, 34))
        draw.rectangle((x - torso_w * 0.65, shoulder_y + 22 * scale, x + torso_w * 0.65, shoulder_y + 34 * scale), fill=primary)
    elif bulk > 1.1:
        draw.rectangle((x - torso_w * 0.5, shoulder_y - 2, x + torso_w * 0.5, hip_y + 8), fill=primary)
    else:
        draw.polygon([(x - 12 * scale, shoulder_y + 10 * scale), (x, shoulder_y + 42 * scale), (x + 12 * scale, shoulder_y + 10 * scale)], fill=primary)

    def limb(origin_x: float, origin_y: float, length: float, angle: float, color: tuple[int, int, int], width: int) -> tuple[float, float]:
        end_x = origin_x + (math.cos(angle) * length)
        end_y = origin_y + (math.sin(angle) * length)
        draw.line((origin_x, origin_y, end_x, end_y), fill=color, width=width)
        return end_x, end_y

    arm_width = max(2, int(7 * scale))
    leg_width = max(2, int(8 * scale))
    left_hand = limb(torso_x - torso_w * 0.8, shoulder_y + 18 * scale, arm, left_arm_angle, skin, arm_width)
    right_hand = limb(torso_x + torso_w * 0.8, shoulder_y + 18 * scale, arm, right_arm_angle, skin, arm_width)
    left_foot = limb(torso_x - torso_w * 0.45, hip_y, leg, math.pi / 2 + left_leg_angle, body, leg_width)
    right_foot = limb(torso_x + torso_w * 0.45, hip_y, leg, math.pi / 2 + right_leg_angle, body, leg_width)

    if action == "carry":
        draw.rounded_rectangle((left_hand[0] - 28 * scale, left_hand[1] - 18 * scale, right_hand[0] + 28 * scale, right_hand[1] + 18 * scale), radius=int(10 * scale), fill=secondary, outline=primary, width=max(1, int(scale * 2)))
    elif action == "hack":
        draw.rounded_rectangle((right_hand[0] - 40 * scale, right_hand[1] - 26 * scale, right_hand[0] + 40 * scale, right_hand[1] + 26 * scale), radius=int(8 * scale), fill=(18, 36, 52), outline=primary, width=max(1, int(scale * 2)))
    elif action == "cast":
        draw.ellipse((right_hand[0] - 32 * scale, right_hand[1] - 32 * scale, right_hand[0] + 32 * scale, right_hand[1] + 32 * scale), outline=primary, width=max(2, int(scale * 3)))
        draw.ellipse((left_hand[0] - 22 * scale, left_hand[1] - 22 * scale, left_hand[0] + 22 * scale, left_hand[1] + 22 * scale), outline=(255, 222, 180), width=max(2, int(scale * 2)))
    elif action == "signal":
        draw.polygon([(right_hand[0], right_hand[1]), (right_hand[0] + 26 * scale, right_hand[1] - 18 * scale), (right_hand[0] + 38 * scale, right_hand[1] + 8 * scale)], fill=primary)
    elif action == "point":
        draw.line((right_hand[0], right_hand[1], right_hand[0] + 60 * scale, right_hand[1] - 8 * scale), fill=(255, 244, 220), width=max(2, int(scale * 3)))
    elif action == "anchor":
        draw.rectangle((right_hand[0] - 16 * scale, right_hand[1] - 12 * scale, right_hand[0] + 28 * scale, right_hand[1] + 12 * scale), fill=(40, 42, 52), outline=(220, 210, 180), width=max(1, int(scale * 2)))
    elif action == "report":
        draw.rounded_rectangle((right_hand[0] - 10 * scale, right_hand[1] - 34 * scale, right_hand[0] + 12 * scale, right_hand[1] + 12 * scale), radius=int(6 * scale), fill=(34, 34, 40), outline=(220, 220, 220), width=max(1, int(scale * 2)))
        draw.rectangle((right_hand[0] - 22 * scale, right_hand[1] - 42 * scale, right_hand[0] + 24 * scale, right_hand[1] - 18 * scale), fill=primary, outline=(255, 255, 255), width=max(1, int(scale * 2)))
    elif action in {"advance", "run"}:
        for fx, fy in (left_foot, right_foot):
            draw.line((fx, fy, fx - 14 * scale, fy + 10 * scale), fill=primary, width=max(1, int(scale * 2)))


def draw_vehicle(draw: ImageDraw.ImageDraw, x: float, y: float, color: tuple[int, int, int], accent: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((x, y, x + 180, y + 70), radius=14, fill=color, outline=accent, width=3)
    draw.rectangle((x + 20, y + 18, x + 72, y + 48), fill=(220, 240, 255))
    draw.rectangle((x + 82, y + 18, x + 134, y + 48), fill=(220, 240, 255))
    for wx in (x + 28, x + 132):
        draw.ellipse((wx, y + 56, wx + 24, y + 80), fill=(20, 20, 24))


def draw_scene(spec: FactionSpec, scene: Scene, scene_progress: float, absolute_progress: float) -> Image.Image:
    image = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    draw_gradient(draw, spec.sky, spec.ground)
    draw_grid(draw, blend(spec.secondary, (40, 44, 56), 0.4))
    image = add_glow(image, (-140, -80, 640, 520), spec.primary, 74, 40)
    image = add_glow(image, (CANVAS_WIDTH - 580, 80, CANVAS_WIDTH + 140, 700), spec.secondary, 96, 54)
    draw = ImageDraw.Draw(image)

    renderer = environment_renderer(scene.environment)
    if scene.environment == "ritual":
        renderer(draw, spec.primary, scene_progress)
    else:
        renderer(draw, spec.primary)
    if scene.environment in {"skybridge", "atrium", "rooftop"}:
        draw_skyline(draw, spec.primary)

    if scene.environment == "newsroom":
        draw.text((210, 178), "BLACK LEDGER NIGHT BULLETIN", fill=(255, 255, 255), font=TITLE_FONT)
        draw.text((210, 238), spec.title.upper(), fill=spec.primary, font=LABEL_FONT)
        draw.text((950, 190), "LIVE", fill=(255, 226, 180), font=LABEL_FONT)
        draw.text((950, 232), "TURN PRESSURE  //  VERIFIED CLIP", fill=(190, 210, 236), font=BODY_FONT)
        draw.rectangle((0, 856, CANVAS_WIDTH, CANVAS_HEIGHT), fill=(14, 10, 16))
        ticker = f"{spec.title.upper()} // {scene.conflict.replace('_', ' ').upper()} // DISTRICT PRESSURE RISING"
        draw.text((76 - (scene_progress * 180), 872), ticker, fill=spec.primary, font=LABEL_FONT)
        draw_person(draw, 790, 760, 1.68, spec.primary, spec.secondary, "anchor", scene_progress)
        draw.rounded_rectangle((420, 610, 1160, 840), radius=24, outline=(255, 255, 255), width=2)
        draw.rounded_rectangle((1190, 522, 1450, 702), radius=18, fill=(14, 18, 30), outline=spec.primary, width=3)
        for idx in range(4):
            y = 566 + (idx * 30)
            draw.line((1224, y, 1408, y), fill=spec.primary if idx % 2 == 0 else (120, 150, 176), width=4)
    elif scene.environment == "barricade":
        convoy_x = 220 + (scene_progress * 180)
        draw_vehicle(draw, convoy_x, 520, (68, 76, 62), spec.primary)
    elif scene.environment in {"docks", "harbor"}:
        crate_x = 220 + (scene_progress * 380)
        draw.rectangle((crate_x, 460, crate_x + 140, 540), fill=spec.secondary, outline=spec.primary, width=3)
        draw.line((crate_x + 70, 300, crate_x + 70, 460), fill=spec.primary, width=5)
    elif scene.environment in {"market", "checkpoint"}:
        crowd_x = 980 - (scene_progress * 240)
        for offset in (0, 55, 110):
            draw_person(draw, crowd_x + offset, 650, 0.55, (160, 150, 130), (90, 70, 50), "run", scene_progress, bulk=1.0)
    elif scene.environment in {"signal_room", "broadcast_wall"}:
        pulse_x = 1060 + (scene_progress * 320)
        draw.line((1040, 190, pulse_x, 240), fill=spec.primary, width=4)
        draw.line((1040, 250, pulse_x - 120, 300), fill=(255, 255, 255), width=2)

    if scene.action != "anchor":
        lead_x = 620 + (90 * math.sin(scene_progress * math.pi * 2))
        lead_y = 670
        if scene.environment in {"skybridge", "atrium", "rooftop"}:
            lead_x = 960 + (40 * math.sin(scene_progress * math.pi * 2))
            lead_y = 640
        elif scene.environment in {"docks", "harbor"}:
            lead_x = 860 + (scene_progress * 120)
            lead_y = 640
        elif scene.environment in {"signal_room", "broadcast_wall"}:
            lead_x = 700
            lead_y = 660
        elif scene.environment == "ritual":
            lead_x = 800
            lead_y = 650
        if scene.action == "report":
            draw_person(draw, 370, 698, 1.34, spec.primary, spec.secondary, "report", scene_progress, bulk=1.18)
            draw.rounded_rectangle((180, 138, 620, 252), radius=18, fill=(10, 12, 20, 188), outline=(*spec.primary, 220), width=3)
            draw.text((214, 164), "LIVE ORK CORRESPONDENT", fill=(255, 255, 255), font=LABEL_FONT)
            draw.text((214, 206), scene.label.upper(), fill=spec.primary, font=LABEL_FONT)
            for offset in (0, 80, 160):
                draw_person(draw, 900 + offset, 692, 0.78, (176, 170, 156), (96, 88, 78), "run", scene_progress, bulk=1.0)
        else:
            draw_person(draw, lead_x, lead_y, 1.2, spec.primary, spec.secondary, scene.action, scene_progress, bulk=1.18 if spec.slug == "barrens-free-wardens" else 1.0)

    draw.rounded_rectangle((58, 52, 620, 182), radius=26, fill=(4, 10, 18, 178), outline=(*spec.primary, 210), width=3)
    draw.text((86, 78), spec.title, fill=(255, 255, 255), font=TITLE_FONT)
    role_label = "Night anchor bulletin" if scene.action == "anchor" else "Orkish field correspondent" if scene.action == "report" else spec.lead_role
    draw.text((88, 130), f"{scene.label.upper()}  //  {role_label.upper()}", fill=spec.primary, font=LABEL_FONT)

    draw.rounded_rectangle((60, 706, 1220, 850), radius=20, fill=(8, 12, 18, 204), outline=(*spec.secondary, 220), width=3)
    caption_index = min(2, spec.scenes.index(scene))
    wrapped = wrap_text(draw, spec.captions[caption_index], BODY_FONT, 1080)
    y = 732
    for line in wrapped[:3]:
        draw.text((92, y), line, fill=(255, 255, 255), font=BODY_FONT)
        y += 34
    footer = "BROADCAST // VERIFIED BULLETIN" if scene.action == "anchor" else "LIVE FEED // FIELD PRESSURE" if scene.action == "report" else f"CONFLICT // {scene.conflict.replace('_', ' ').upper()}"
    draw.text((92, 814), footer, fill=spec.primary, font=LABEL_FONT)
    return image


def apply_camera(scene_image: Image.Image, camera: CameraPath, progress: float) -> Image.Image:
    eased = ease(progress)
    zoom = lerp(camera.start_zoom, camera.end_zoom, eased)
    crop_w = int(VIDEO_WIDTH / zoom)
    crop_h = int(VIDEO_HEIGHT / zoom)
    x = int(lerp(camera.start_x, camera.end_x, eased))
    y = int(lerp(camera.start_y, camera.end_y, eased))
    x = max(0, min(CANVAS_WIDTH - crop_w, x))
    y = max(0, min(CANVAS_HEIGHT - crop_h, y))
    cropped = scene_image.crop((x, y, x + crop_w, y + crop_h))
    return cropped.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.LANCZOS)


def render_soundtrack(output_path: Path, duration: float, frequencies: tuple[int, int, int]) -> None:
    low, mid, high = frequencies
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={low}:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={mid}:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={high}:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:sample_rate=48000:duration={duration}",
            "-filter_complex",
            "[0:a]volume=0.10,lowpass=f=240[a0];"
            "[1:a]volume=0.05,lowpass=f=520[a1];"
            "[2:a]volume=0.03,highpass=f=180[a2];"
            "[3:a]volume=0.018,highpass=f=800[a3];"
            "[a0][a1][a2][a3]amix=inputs=4:normalize=0,"
            "aecho=0.7:0.85:35:0.18,"
            "afade=t=in:st=0:d=1.2,"
            f"afade=t=out:st={max(0.0, duration - 1.4)}:d=1.4,"
            "alimiter=limit=0.85[out]",
            "-map",
            "[out]",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
    )


def encode_video(frames_root: Path, audio_path: Path, output_path: Path, *, codec: str, crf: str, audio_codec: str, bitrate: str | None = None, size: tuple[int, int] | None = None) -> None:
    width, height = size or (VIDEO_WIDTH, VIDEO_HEIGHT)
    vf = f"scale={width}:{height}:flags=lanczos"
    command = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(frames_root / "frame_%04d.png"),
        "-i",
        str(audio_path),
        "-vf",
        vf,
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        codec,
    ]
    if codec == "libx264":
        command.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                crf,
                "-movflags",
                "+faststart",
            ]
        )
    else:
        command.extend(
            [
                "-b:v",
                "0",
                "-crf",
                crf,
                "-row-mt",
                "1",
                "-tile-columns",
                "1",
            ]
        )
    command.extend(["-c:a", audio_codec])
    if bitrate:
        command.extend(["-b:a", bitrate])
    command.extend(["-shortest", str(output_path)])
    subprocess.run(command, check=True)


def generate_for_faction(spec: FactionSpec) -> None:
    mp4_path = ROOT / f"{spec.slug}-promo.mp4"
    mobile_mp4_path = ROOT / f"{spec.slug}-promo-mobile.mp4"
    webm_path = ROOT / f"{spec.slug}-promo.webm"
    poster_path = ROOT / f"{spec.slug}-promo-poster.png"

    with tempfile.TemporaryDirectory(prefix=f"{spec.slug}-promo-frames-") as temp_dir:
        frames_root = Path(temp_dir)
        for frame_index in range(TOTAL_FRAMES):
            scene_index = min(len(spec.scenes) - 1, frame_index // SCENE_FRAMES)
            scene = spec.scenes[scene_index]
            scene_frame = frame_index - (scene_index * SCENE_FRAMES)
            scene_progress = scene_frame / max(1, SCENE_FRAMES - 1)
            absolute_progress = frame_index / max(1, TOTAL_FRAMES - 1)
            image = draw_scene(spec, scene, scene_progress, absolute_progress)
            final_frame = apply_camera(image, scene.camera, scene_progress)
            final_frame.save(frames_root / f"frame_{frame_index:04d}.png")

        audio_path = frames_root / "score.wav"
        render_soundtrack(audio_path, FACTION_DURATION_SECONDS, spec.audio_frequencies)

        encode_video(frames_root, audio_path, mp4_path, codec="libx264", crf="18", audio_codec="aac", bitrate="160k", size=(1920, 1080))
        encode_video(frames_root, audio_path, mobile_mp4_path, codec="libx264", crf="20", audio_codec="aac", bitrate="144k", size=(1280, 720))
        encode_video(frames_root, audio_path, webm_path, codec="libvpx-vp9", crf="34", audio_codec="libopus", bitrate="112k", size=(1280, 720))

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mobile_mp4_path),
                "-vf",
                "select=eq(n\\,180)",
                "-frames:v",
                "1",
                str(poster_path),
            ],
            check=True,
        )


def main() -> int:
    for spec in FACTIONS:
        generate_for_faction(spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
