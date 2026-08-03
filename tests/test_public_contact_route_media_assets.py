from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = ROOT / "Chummer.Run.Api" / "wwwroot" / "media"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_contact_portraits_are_premium_square_png_assets() -> None:
    for name in ("contact-portrait-current.png", "contact-portrait-revision.png"):
        path = MEDIA_ROOT / "portraits" / name
        data = path.read_bytes()

        assert data.startswith(PNG_SIGNATURE), f"{name} is not a PNG"
        width, height = struct.unpack(">II", data[16:24])
        assert width == height
        assert width >= 1200
        assert len(data) >= 1_000_000


def test_route_recap_clip_is_web_optimized_h264_mp4() -> None:
    path = MEDIA_ROOT / "routes" / "route-recap-clip.mp4"
    data = path.read_bytes()

    assert data[4:8] == b"ftyp"
    assert b"avc1" in data
    assert data.index(b"moov") < data.index(b"mdat"), "MP4 must use faststart"
    assert 1_000_000 <= len(data) <= 5_000_000
