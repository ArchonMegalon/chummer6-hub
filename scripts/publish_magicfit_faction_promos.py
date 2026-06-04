#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/docker/chummercomplete")
SERIES_ROOT = ROOT / "_completion" / "faction_video_series" / "generated"
PUBLIC_ROOT = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "factions"
PROVIDER_PROOF = ROOT / "_completion" / "magicfit_provider" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json"
OUT_RECEIPT = ROOT / "_completion" / "faction_video_series" / "FACTION_VIDEO_PUBLICATION.generated.json"
UNMIXR_API_URL = "https://unmixr.com/api/v1/short-tts/"
UNMIXR_ENV_FILES = [
    Path("/docker/EA/.env.local"),
    Path("/docker/EA/.env"),
    Path("/docker/chummercomplete/chummer.run-services/.env"),
]
VOICE_FALLBACK = "en-US-GuyNeural"
VOICE_BY_FACTION = {
    "glass-tower-compact": "en-US-GuyNeural",
    "rust-market-syndicate": "en-US-AndrewNeural",
    "ashline-circle": "en-US-AvaNeural",
    "neon-docks-union": "en-US-BrianNeural",
    "ghostline-network": "en-US-DavisNeural",
    "barrens-free-wardens": "en-US-ChristopherNeural",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish MagicFit-rendered faction promos to the public Black Ledger media lane.")
    parser.add_argument("--only", action="append", default=[], help="Specific faction slug to publish; may be repeated.")
    return parser.parse_args()


def run(*args: str) -> None:
    subprocess.run(list(args), check=True)


def env_or_file(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    for env_file in UNMIXR_ENV_FILES:
        if not env_file.is_file():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            left, right = line.split("=", 1)
            if left.strip() != key:
                continue
            parsed = right.strip().strip("'").strip('"')
            if parsed:
                return parsed
    return ""


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


def find_edge_python() -> str | None:
    candidates = [
        "/tmp/black-ledger-newsreel-venv/bin/python",
        "/tmp/black-ledger-newsreel-venv/bin/python3",
        "/docker/chummercomplete/_completion/promo_video_rework_20260602/tts_venv/bin/python",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return None


def unmixr_config() -> dict[str, str] | None:
    api_key = env_or_file("UNMIXR_API_KEY")
    voice_id = env_or_file("UNMIXR_VOICE_ID")
    if not api_key or not voice_id:
        return None
    return {
        "api_key": api_key,
        "voice_id": voice_id,
        "language": env_or_file("UNMIXR_LANGUAGE") or "en-US",
        "speaking_rate": env_or_file("UNMIXR_SPEAKING_RATE") or "medium",
        "speaking_pitch": env_or_file("UNMIXR_SPEAKING_PITCH") or "low",
        "speaking_volume": env_or_file("UNMIXR_SPEAKING_VOLUME") or "medium",
    }


def render_unmixr_tts(text: str, output: Path) -> bool:
    config = unmixr_config()
    if config is None:
        return False
    payload = json.dumps(
        {
            "text": text,
            "voice_id": config["voice_id"],
            "language": config["language"],
            "speaking_rate": config["speaking_rate"],
            "speaking_pitch": config["speaking_pitch"],
            "speaking_volume": config["speaking_volume"],
            "output_type": output.suffix.lstrip(".") or "mp3",
            "response_type": "url",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        UNMIXR_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        audio_url = str(body.get("audio_url") or "").strip()
        if not audio_url:
            return False
        with urllib.request.urlopen(audio_url, timeout=120) as audio_response:
            output.write_bytes(audio_response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False
    return output.is_file() and output.stat().st_size > 0


async def render_edge_tts(text: str, voice: str, output: Path) -> None:
    helper = output.with_suffix(".edge_tts.py")
    helper.write_text(
        "import asyncio, edge_tts, pathlib, sys\n"
        "voice = sys.argv[1]\n"
        "text = pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')\n"
        "output = pathlib.Path(sys.argv[3])\n"
        "async def main():\n"
        "    await edge_tts.Communicate(text=text, voice=voice, rate='-8%', pitch='-6Hz').save(str(output))\n"
        "asyncio.run(main())\n",
        encoding="utf-8",
    )
    text_path = output.with_suffix(".txt")
    text_path.write_text(text, encoding="utf-8")
    edge_python = find_edge_python()
    if edge_python is None:
        raise RuntimeError("edge_tts interpreter unavailable")
    try:
        run(edge_python, str(helper), voice, str(text_path), str(output))
    finally:
        helper.unlink(missing_ok=True)
        text_path.unlink(missing_ok=True)


def render_flite_tts(text: str, output: Path) -> None:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"flite=text='{escaped}':voice=slt",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


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


def make_audio_track(video: Path, narration_text: str, voice: str, output: Path) -> tuple[float, str]:
    with tempfile.TemporaryDirectory(prefix="faction-promo-audio-") as temp_dir:
        temp_root = Path(temp_dir)
        narration = temp_root / "narration.mp3"
        provider = "unmixr-short-tts"
        if not render_unmixr_tts(narration_text, narration):
            provider = "edge-tts"
            try:
                asyncio.run(render_edge_tts(narration_text, voice, narration))
            except Exception:
                provider = "ffmpeg-flite"
                narration = temp_root / "narration.wav"
                render_flite_tts(narration_text, narration)
        if not narration.exists():
            provider = "ffmpeg-flite"
            narration = temp_root / "narration.wav"
            render_flite_tts(narration_text, narration)
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
    return narration_duration, provider


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
    voice = VOICE_BY_FACTION.get(slug, VOICE_FALLBACK)

    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    public_audio = PUBLIC_ROOT / f"{slug}-promo-audio.m4a"
    public_mp4 = PUBLIC_ROOT / f"{slug}-promo.mp4"
    public_mobile = PUBLIC_ROOT / f"{slug}-promo-mobile.mp4"
    public_webm = PUBLIC_ROOT / f"{slug}-promo.webm"
    public_poster = PUBLIC_ROOT / f"{slug}-promo-poster.png"
    public_receipt = PUBLIC_ROOT / f"{slug}-promo.receipt.json"

    narration_duration, narration_provider = make_audio_track(source_mp4, narration_text, voice, public_audio)
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
        "voice": voice,
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
        "voice": voice,
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
