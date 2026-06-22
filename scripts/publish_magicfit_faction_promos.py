#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _unmixr_tts import (
    UNMIXR_SHORT_TTS_PROVIDER,
    UnmixrTtsError,
    load_profile,
    render_short_tts,
    slug_prefix,
)


ROOT = Path("/docker/chummercomplete")
SERIES_ROOT = ROOT / "_completion" / "faction_video_series" / "generated"
PUBLIC_ROOT = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "factions"
PROVIDER_PROOF = ROOT / "_completion" / "magicfit_provider" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json"
OUT_RECEIPT = ROOT / "_completion" / "faction_video_series" / "FACTION_VIDEO_PUBLICATION.generated.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish MagicFit-rendered faction promos to the public Black Ledger media lane.")
    parser.add_argument("--only", action="append", default=[], help="Specific faction slug to publish; may be repeated.")
    return parser.parse_args()


def run(*args: str) -> None:
    subprocess.run(list(args), check=True)


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


def render_music(output: Path, duration: float) -> None:
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=84:sample_rate=48000:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=168:sample_rate=48000:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=336:sample_rate=48000:duration={duration}",
        "-filter_complex",
        "[0:a]volume=0.06,lowpass=f=240[a0];"
        "[1:a]volume=0.035,lowpass=f=520[a1];"
        "[2:a]volume=0.018,highpass=f=140[a2];"
        "[a0][a1][a2]amix=inputs=3:normalize=0,"
        "aecho=0.8:0.82:50:0.16,alimiter=limit=0.82[out]",
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def narration_for(payload: dict) -> str:
    title = str(payload.get("title") or "").strip()
    captions = [str(item).strip() for item in payload.get("captions") or [] if str(item).strip()]
    scene_titles = [str(item.get("scene_title") or "").strip() for item in payload.get("scene_payloads") or [] if str(item.get("scene_title") or "").strip()]
    opener = captions[0] if captions else f"{title} moves first, and it wants the district to know why."
    closer = captions[-1] if len(captions) > 1 else f"{title} does not ask for permission. It asks whether the city can keep up."
    middle = ", ".join(scene_titles[:3]).replace("-", " ")
    return " ".join(
        part
        for part in [
            opener,
            f"Watch the reel move through {middle}." if middle else "",
            closer,
        ]
        if part
    )


def make_audio_track(video: Path, narration_text: str, faction_slug: str, output: Path) -> tuple[float, str, dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="faction-promo-audio-") as temp_dir:
        temp_root = Path(temp_dir)
        narration = temp_root / "narration.mp3"
        profile = load_profile(
            prefixes=(slug_prefix("UNMIXR_FACTION", faction_slug), "UNMIXR_FACTION"),
            defaults={"speaking_rate": "medium", "speaking_pitch": "low", "speaking_volume": "medium"},
        )
        render_short_tts(narration_text, narration, profile=profile)
        narration_duration = ffprobe_duration(narration)
        target_duration = ffprobe_duration(video)
        music = temp_root / "music.wav"
        render_music(music, target_duration)
        speed_filter = "anull"
        if narration_duration > target_duration * 0.94:
            ratio = min(max(narration_duration / max(target_duration * 0.92, 0.1), 1.0), 1.45)
            speed_filter = f"atempo={ratio:.5f}"
        elif narration_duration < target_duration * 0.74:
            ratio = max(narration_duration / max(target_duration * 0.82, 0.1), 0.82)
            speed_filter = f"atempo={ratio:.5f}"
        run(
            "ffmpeg",
            "-y",
            "-i",
            str(narration),
            "-i",
            str(music),
            "-filter_complex",
            f"[0:a]{speed_filter},apad=pad_dur={target_duration + 1.0},atrim=duration={target_duration}[voice];"
            f"[1:a]volume=0.12,atrim=duration={target_duration}[bed];"
            "[voice][bed]amix=inputs=2:weights='1 0.65':normalize=0[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(output),
        )
    return narration_duration, UNMIXR_SHORT_TTS_PROVIDER, profile


def mux_video(video: Path, audio: Path, output: Path, *, scale: str | None = None, codec: str = "libx264") -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
    ]
    if scale:
        cmd.extend(["-vf", scale])
    if codec == "libvpx-vp9":
        cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "31", "-row-mt", "1", "-tile-columns", "1", "-c:a", "libopus", "-b:a", "128k"])
    else:
        cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"])
    cmd.append(str(output))
    run(*cmd)


def publish_faction(slug: str) -> dict:
    manifest_path = SERIES_ROOT / slug / "video_manifest.generated.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    exports = payload["exports"]
    source_mp4 = Path(exports["mp4"])
    source_webm = Path(exports["webm"])
    source_poster = Path(exports["poster"])
    narration_text = narration_for(payload)
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    public_audio = PUBLIC_ROOT / f"{slug}-promo-audio.m4a"
    public_mp4 = PUBLIC_ROOT / f"{slug}-promo.mp4"
    public_mobile = PUBLIC_ROOT / f"{slug}-promo-mobile.mp4"
    public_webm = PUBLIC_ROOT / f"{slug}-promo.webm"
    public_poster = PUBLIC_ROOT / f"{slug}-promo-poster.png"
    public_receipt = PUBLIC_ROOT / f"{slug}-promo.receipt.json"

    narration_duration, narration_provider, narration_profile = make_audio_track(source_mp4, narration_text, slug, public_audio)
    mux_video(source_mp4, public_audio, public_mp4)
    mux_video(source_mp4, public_audio, public_mobile, scale="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1")
    mux_video(source_webm if source_webm.is_file() else source_mp4, public_audio, public_webm, codec="libvpx-vp9")
    shutil.copy2(source_poster, public_poster)

    receipt_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass",
        "provider": "MagicFit",
        "provider_status": "VERIFIED_PROVIDER",
        "render_mode": "magicfit_cinematic_faction_promo_with_narration",
        "narration_provider": narration_provider,
        "voice": narration_profile["voice_id"],
        "slug": slug,
        "title": payload.get("title"),
        "captions": payload.get("captions") or [],
        "scene_payloads": payload.get("scene_payloads") or [],
        "exports": {
            "mp4": str(public_mp4),
            "mobile_mp4": str(public_mobile),
            "webm": str(public_webm),
            "poster": str(public_poster),
            "audio": str(public_audio),
        },
        "source_manifest": str(manifest_path),
    }
    public_receipt.write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")

    return {
        "slug": slug,
        "status": "pass",
        "voice": narration_profile["voice_id"],
        "narration_provider": narration_provider,
        "narration_duration_seconds": round(narration_duration, 3),
        "public_mp4": str(public_mp4),
        "public_mobile_mp4": str(public_mobile),
        "public_webm": str(public_webm),
        "public_poster": str(public_poster),
        "public_receipt": str(public_receipt),
        "source_manifest": str(manifest_path),
    }


def main() -> int:
    args = parse_args()
    if not PROVIDER_PROOF.is_file():
        raise SystemExit("missing MagicFit provider verification proof")
    proof = json.loads(PROVIDER_PROOF.read_text(encoding="utf-8"))
    if str(proof.get("status") or "").lower() != "verified":
        raise SystemExit("MagicFit provider is not verified")

    all_slugs = sorted(path.name for path in SERIES_ROOT.iterdir() if path.is_dir())
    selected = sorted(set(args.only or all_slugs))
    receipts = [publish_faction(slug) for slug in selected]
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass",
        "provider": "MagicFit",
        "published_count": len(receipts),
        "receipts": receipts,
    }
    OUT_RECEIPT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
