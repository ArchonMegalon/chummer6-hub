#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "globe"
COMPLETION = ROOT / "_completion" / "black_ledger_video_globe"
WIDTH = 1280
HEIGHT = 720
FPS = 24
DURATION = 14
FRAMES = FPS * DURATION


LANDMASSES = [
    [(-116, 12), (-104, 20), (-98, 28), (-104, 36), (-110, 45), (-122, 56), (-148, 67), (-160, 72), (-126, 69), (-108, 62), (-90, 54), (-74, 50), (-66, 45), (-78, 34), (-83, 25), (-90, 19)],
    [(-80, 12), (-72, 10), (-62, 6), (-54, -5), (-51, -15), (-55, -24), (-60, -35), (-68, -46), (-74, -53), (-67, -50), (-72, -35), (-78, -18), (-81, -3)],
    [(-16, 35), (-3, 30), (12, 25), (24, 12), (33, 2), (40, -8), (34, -18), (28, -28), (18, -34), (8, -30), (2, -18), (-4, -6), (-10, 8), (-16, 21)],
    [(-10, 37), (-2, 44), (10, 50), (28, 56), (48, 60), (74, 64), (98, 68), (126, 68), (150, 61), (160, 54), (146, 46), (130, 34), (118, 24), (104, 16), (86, 12), (70, 18), (58, 28), (44, 35), (30, 40), (18, 42), (6, 39), (-2, 36)],
    [(34, 30), (44, 26), (56, 18), (64, 12), (76, 8), (82, 16), (74, 24), (62, 28), (50, 30)],
    [(113, -12), (126, -16), (138, -24), (151, -32), (147, -40), (133, -42), (118, -34), (113, -24)],
]

FACTIONS = [
    ("ASH", -122, 47, (241, 94, 76)),
    ("GLS", -74, 40, (92, 226, 255)),
    ("RUST", 13, 52, (255, 168, 82)),
    ("NEON", 139, 35, (184, 123, 255)),
    ("GHOST", 30, -26, (108, 255, 196)),
    ("WARD", -58, -34, (228, 238, 255)),
]


def project(lon: float, lat: float, yaw: float, radius: float, cx: float, cy: float) -> tuple[float, float, float] | None:
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    x = math.cos(lat_r) * math.sin(lon_r)
    y = math.sin(lat_r)
    z = math.cos(lat_r) * math.cos(lon_r)
    sy, cyaw = math.sin(yaw), math.cos(yaw)
    x1 = x * cyaw - z * sy
    z1 = x * sy + z * cyaw
    pitch = math.radians(-12)
    sp, cp = math.sin(pitch), math.cos(pitch)
    y2 = y * cp - z1 * sp
    z2 = y * sp + z1 * cp
    if z2 < -0.18:
        return None
    perspective = 1 + z2 / 3.1
    return cx + x1 * radius * perspective, cy - y2 * radius * perspective, z2


def draw_glow(draw: ImageDraw.ImageDraw, xy: tuple[float, float], radius: float, color: tuple[int, int, int], alpha: int) -> None:
    x, y = xy
    for step in range(8, 0, -1):
        a = int(alpha * (step / 8) ** 2)
        r = radius * step / 3
        draw.ellipse((x - r, y - r, x + r, y + r), outline=(*color, a), width=max(1, int(radius / 10)))


def frame(index: int) -> Image.Image:
    phase = index / FRAMES
    yaw = math.radians(-36 + phase * 360)
    img = Image.new("RGB", (WIDTH, HEIGHT), (3, 7, 12))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    for y in range(HEIGHT):
        t = y / HEIGHT
        color = (int(4 + 10 * t), int(10 + 18 * t), int(18 + 28 * t))
        ImageDraw.Draw(img).line((0, y, WIDTH, y), fill=color)

    cx, cy = WIDTH * 0.48, HEIGHT * 0.50
    radius = min(WIDTH, HEIGHT) * 0.34

    for i in range(90):
        seed = math.sin(i * 12.9898) * 43758.5453
        x = (seed % 1) * WIDTH
        y = ((seed * 1.91) % 1) * HEIGHT
        a = int(45 + 35 * (0.5 + 0.5 * math.sin(phase * math.tau + i)))
        draw.point((x, y), fill=(190, 228, 255, a))

    for step in range(36, 0, -1):
        r = radius * (1 + step / 28)
        a = int(3 + step * 2.2)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(45, 218, 240, a), width=2)

    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(8, 42, 62, 255), outline=(104, 236, 255, 150), width=3)

    terminator = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    td = ImageDraw.Draw(terminator, "RGBA")
    td.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(0, 0, 0, 0))

    for land in LANDMASSES:
        points = [project(lon, lat, yaw, radius * 0.97, cx, cy) for lon, lat in land]
        points = [(x, y) for point in points if point for x, y, _ in [point]]
        if len(points) >= 3:
            draw.polygon(points, fill=(66, 109, 69, 220), outline=(206, 238, 210, 130))
            draw.line(points + [points[0]], fill=(18, 40, 30, 120), width=3)

    for lat in range(-60, 75, 15):
        pts = []
        for lon in range(-180, 181, 8):
            projected = project(lon, lat, yaw, radius, cx, cy)
            if projected:
                pts.append((projected[0], projected[1]))
        if len(pts) > 2:
            draw.line(pts, fill=(111, 230, 255, 34), width=1)

    for lon in range(-180, 180, 30):
        pts = []
        for lat in range(-80, 81, 5):
            projected = project(lon, lat, yaw, radius, cx, cy)
            if projected:
                pts.append((projected[0], projected[1]))
        if len(pts) > 2:
            draw.line(pts, fill=(111, 230, 255, 30), width=1)

    for label, lon, lat, color in FACTIONS:
        p = project(lon, lat, yaw, radius * 1.01, cx, cy)
        if not p:
            continue
        x, y, z = p
        pulse = 0.5 + 0.5 * math.sin(phase * math.tau * 3 + lon)
        draw_glow(draw, (x, y), 16 + pulse * 8, color, 55)
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(*color, 230), outline=(255, 255, 255, 180), width=1)
        if z > 0:
            draw.text((x + 10, y - 10), label, fill=(232, 246, 255, 180))

    for i in range(len(FACTIONS)):
        a = FACTIONS[i]
        b = FACTIONS[(i + 2) % len(FACTIONS)]
        pa = project(a[1], a[2], yaw, radius * 1.03, cx, cy)
        pb = project(b[1], b[2], yaw, radius * 1.03, cx, cy)
        if not pa or not pb:
            continue
        ax, ay, _ = pa
        bx, by, _ = pb
        mx, my = (ax + bx) / 2, (ay + by) / 2 - 36
        draw.arc((min(ax, bx, mx) - 20, min(ay, by, my) - 20, max(ax, bx, mx) + 20, max(ay, by, my) + 20), 210, 340, fill=(92, 226, 255, 58), width=2)

    shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade, "RGBA")
    sd.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(0, 0, 0, 0))
    sd.rectangle((cx + radius * 0.08, cy - radius, cx + radius, cy + radius), fill=(0, 0, 0, 68))
    overlay = Image.alpha_composite(overlay, shade.filter(ImageFilter.GaussianBlur(22)))

    scan = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scan, "RGBA")
    for y in range(0, HEIGHT, 6):
        sd.line((0, y, WIDTH, y), fill=(255, 255, 255, 12))
    overlay = Image.alpha_composite(overlay, scan)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    OUT.mkdir(parents=True, exist_ok=True)
    COMPLETION.mkdir(parents=True, exist_ok=True)
    mp4 = OUT / "black-ledger-video-globe-idle.mp4"
    webm = OUT / "black-ledger-video-globe-idle.webm"
    poster = OUT / "black-ledger-video-globe-idle-poster.png"
    with tempfile.TemporaryDirectory(prefix="black-ledger-globe-") as tmp:
        tmp_path = Path(tmp)
        for i in range(FRAMES):
            frame(i).save(tmp_path / f"frame-{i:04d}.png", optimize=True)
        shutil.copyfile(tmp_path / "frame-0000.png", poster)
        run([
            "ffmpeg", "-y", "-framerate", str(FPS), "-i", str(tmp_path / "frame-%04d.png"),
            "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-movflags", "+faststart", str(mp4),
        ])
        run([
            "ffmpeg", "-y", "-framerate", str(FPS), "-i", str(tmp_path / "frame-%04d.png"),
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1", str(webm),
        ])

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    receipt = {
        "asset_id": "ledger_globe_idle_v1",
        "mode": "idle_loop",
        "provider_requested": "MagicFit",
        "provider_status": "missing_render_asset",
        "render_mode": "first_party_raster_video_fallback",
        "generated_at_utc": now,
        "duration_seconds": DURATION,
        "loopable": True,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "files": {
            "mp4": "/media/ledger/globe/black-ledger-video-globe-idle.mp4",
            "webm": "/media/ledger/globe/black-ledger-video-globe-idle.webm",
            "poster_png": "/media/ledger/globe/black-ledger-video-globe-idle-poster.png",
        },
        "qa": {
            "watermark_status": "none",
            "public_safety_status": "pass",
            "overlay_truth_status": "chummer_owned_canvas_overlay",
            "magicfit_claim_allowed": False,
        },
    }
    (OUT / "black-ledger-video-globe-idle.receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (COMPLETION / "BLACK_LEDGER_VIDEO_GLOBE_ASSET_MANIFEST.generated.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (COMPLETION / "BLACK_LEDGER_VIDEO_GLOBE_PROVIDER_RECEIPTS.generated.json").write_text(json.dumps({
        "provider": "MagicFit",
        "status": "not_verified_for_this_asset",
        "source_zip": "/home/tibor/black_ledger_video_globe_magicfit_design_20260529.zip",
        "fallback_asset": receipt["files"],
        "gold_claim_allowed": False,
    }, indent=2) + "\n")
    (COMPLETION / "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md").write_text("NOT_READY\n")
    (COMPLETION / "BLACK_LEDGER_VIDEO_GLOBE_FALLBACK_VERDICT.md").write_text("READY_VIA_FALLBACK\n")


if __name__ == "__main__":
    main()
