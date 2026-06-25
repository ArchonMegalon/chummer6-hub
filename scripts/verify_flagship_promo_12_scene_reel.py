#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
MEDIA_ROOT = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
OUT_DIR = WORKSPACE / "_completion" / "chummer6_flagship_promo_12_scene_reel"
MAGICFIT_SOURCE_AUDIT = WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes" / "MAGICFIT_12_SCENE_PROMO_SOURCE_AUDIT.generated.json"

TARGET_SECONDS = 90.0
SCENE_COUNT = 12
SAMPLE_TIMES = (2, 9, 17, 25, 33, 41, 49, 57, 65, 73, 81, 88)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def probe(path: Path) -> dict[str, Any]:
    completed = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
        ]
    )
    if completed.returncode != 0:
        return {"status": "fail", "stderr": completed.stderr}
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    return {
        "status": "pass",
        "duration": float(dict(payload.get("format") or {}).get("duration") or 0.0),
        "has_video": any(stream.get("codec_type") == "video" for stream in streams),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "streams": streams,
    }


def average_hash(path: Path) -> str:
    image = Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(image.get_flattened_data())
    mean = sum(pixels) / len(pixels)
    return "".join("1" if pixel >= mean else "0" for pixel in pixels)


def hamming(left: str, right: str) -> int:
    return sum(1 for a, b in zip(left, right, strict=True) if a != b)


def accent_signature(path: Path) -> tuple[int, int, int]:
    image = Image.open(path).convert("RGB").crop((760, 150, 1180, 610))
    pixels: list[tuple[int, int, int]] = []
    for r, g, b in image.get_flattened_data():
        if r + g + b > 120 and (max(r, g, b) - min(r, g, b) > 35 or r + g + b > 690):
            pixels.append((r, g, b))
    if not pixels:
        return (0, 0, 0)
    average = tuple(sum(pixel[channel] for pixel in pixels) // len(pixels) for channel in range(3))
    return tuple(value // 24 for value in average)


def extract_frames(asset_id: str, mp4: Path) -> list[Path]:
    frame_dir = OUT_DIR / f"{asset_id}_sample_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index, second in enumerate(SAMPLE_TIMES, start=1):
        target = frame_dir / f"{index:02d}_{second:02d}s.jpg"
        completed = run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(second),
                "-i",
                str(mp4),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(target),
            ]
        )
        if completed.returncode != 0:
            raise SystemExit(completed.stderr)
        frames.append(target)
    return frames


def build_contact_sheet(asset_id: str, frames: list[Path]) -> Path:
    thumb_w, thumb_h = 320, 180
    margin = 16
    label_h = 34
    sheet = Image.new("RGB", (4 * thumb_w + 5 * margin, 3 * (thumb_h + label_h) + 4 * margin), (9, 13, 18))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 18)
    for index, frame in enumerate(frames):
        image = Image.open(frame).convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = index % 4
        row = index // 4
        x = margin + col * (thumb_w + margin)
        y = margin + row * (thumb_h + label_h + margin)
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + thumb_h + 7), f"scene {index + 1:02d} @ {SAMPLE_TIMES[index]}s", fill=(231, 238, 244), font=font)
    target = OUT_DIR / f"{asset_id.upper().replace('-', '_')}_12_SCENE_CONTACT_SHEET.jpg"
    sheet.save(target, quality=92)
    return target


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Chummer6 flagship promo is a true 12-scene 90-second reel.")
    parser.add_argument("--asset", default="every-wonder-horizon-promo")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mp4 = MEDIA_ROOT / f"{args.asset}.mp4"
    receipt_path = MEDIA_ROOT / f"{args.asset}.receipt.json"
    vtt = MEDIA_ROOT / f"{args.asset}.vtt"
    frames = extract_frames(args.asset, mp4)
    hashes = [average_hash(frame) for frame in frames]
    accent_signatures = [accent_signature(frame) for frame in frames]
    pair_distances = [hamming(hashes[index], hashes[index + 1]) for index in range(len(hashes) - 1)]
    unique_hashes = len(set(hashes))
    unique_accent_signatures = len(set(accent_signatures))
    contact_sheet = build_contact_sheet(args.asset, frames)

    receipt = load_json(receipt_path)
    probe_result = probe(mp4)
    caption_segment_count = sum(1 for line in vtt.read_text(encoding="utf-8").splitlines() if line.strip().isdigit()) if vtt.is_file() else 0
    failures: list[str] = []
    if probe_result.get("status") != "pass" or not probe_result.get("has_video") or not probe_result.get("has_audio"):
        failures.append("mp4 must contain audio and video")
    if float(probe_result.get("duration") or 0) < TARGET_SECONDS - 0.5:
        failures.append("mp4 must be at least 89.5 seconds")
    if receipt.get("visual_scene_count") != SCENE_COUNT:
        failures.append("receipt must claim exactly 12 visual scenes")
    source_audit = load_json(MAGICFIT_SOURCE_AUDIT)
    if receipt.get("magicfit_claim_allowed") is not True or receipt.get("magicfit_final_visual_render_claim") is not True:
        failures.append("receipt must prove MagicFit final rendering")
    if source_audit.get("status") != "pass":
        failures.append("MagicFit source audit must pass")
    if source_audit.get("unique_magicfit_cdn_url_count") != SCENE_COUNT:
        failures.append("MagicFit source audit must prove 12 unique CDN render URLs")
    if source_audit.get("unique_file_sha256_count") != SCENE_COUNT:
        failures.append("MagicFit source audit must prove 12 unique source files")
    if caption_segment_count != SCENE_COUNT:
        failures.append("caption track must contain 12 segments")
    if unique_hashes < 10:
        failures.append(f"sampled scene frames must prove broad visual variety; unique={unique_hashes}")

    payload = {
        "contract_name": "chummer.flagship_promo.true_12_scene_reel",
        "generated_at_utc": utc_now(),
        "asset_id": args.asset,
        "status": "pass" if not failures else "fail",
        "verdict": "FLAGSHIP_PROMO_12_SCENE_REEL_READY" if not failures else "NOT_READY",
        "sample_times_seconds": SAMPLE_TIMES,
        "unique_sample_count": unique_hashes,
        "unique_accent_signature_count": unique_accent_signatures,
        "accent_signatures": accent_signatures,
        "consecutive_hash_hamming_distances": pair_distances,
        "contact_sheet": str(contact_sheet),
        "mp4_probe": probe_result,
        "caption_segment_count": caption_segment_count,
        "receipt_path": str(receipt_path),
        "magicfit_source_audit": str(MAGICFIT_SOURCE_AUDIT),
        "failures": failures,
    }
    out = OUT_DIR / "FLAGSHIP_PROMO_12_SCENE_REEL_AUDIT.generated.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "unique_sample_count": unique_hashes, "contact_sheet": str(contact_sheet)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
