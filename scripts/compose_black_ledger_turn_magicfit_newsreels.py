#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/docker/chummercomplete")
MANIFEST = ROOT / "_completion" / "black_ledger_magicfit_newsreels" / "BLACK_LEDGER_TURN_MAGICFIT_RENDER_MANIFEST.generated.json"
CLIPS = ROOT / "_completion" / "black_ledger_magicfit_newsreels" / "magicfit_clips"
NEWSREELS_ROOT = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "newsreels"
VOICE = "en-US-AvaNeural"
UNMIXR_API_URL = "https://unmixr.com/api/v1/short-tts/"
UNMIXR_ENV_FILES = [
    Path("/docker/EA/.env.local"),
    Path("/docker/EA/.env"),
    Path("/docker/chummercomplete/chummer.run-services/.env"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose Black Ledger turn newsreels from rendered MagicFit clips.")
    parser.add_argument("--asset", action="append", default=[], help="Specific asset id to compose; may be repeated.")
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


def duration(path: Path) -> float:
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
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


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


def scene_voice_profile(scene: dict) -> dict[str, str]:
    config = unmixr_config() or {}
    role = str(scene.get("voice_role") or "narrator").strip().lower()
    if role == "ork_reporter":
        return {
            "voice_id": env_or_file("UNMIXR_ORK_REPORTER_VOICE_ID") or config.get("voice_id", ""),
            "language": env_or_file("UNMIXR_ORK_REPORTER_LANGUAGE") or config.get("language", "en-US"),
            "speaking_rate": env_or_file("UNMIXR_ORK_REPORTER_RATE") or "slow",
            "speaking_pitch": env_or_file("UNMIXR_ORK_REPORTER_PITCH") or "low",
            "speaking_volume": env_or_file("UNMIXR_ORK_REPORTER_VOLUME") or "medium",
        }
    if role == "anchor":
        return {
            "voice_id": env_or_file("UNMIXR_ANCHOR_VOICE_ID") or config.get("voice_id", ""),
            "language": env_or_file("UNMIXR_ANCHOR_LANGUAGE") or config.get("language", "en-US"),
            "speaking_rate": env_or_file("UNMIXR_ANCHOR_RATE") or "medium",
            "speaking_pitch": env_or_file("UNMIXR_ANCHOR_PITCH") or "low",
            "speaking_volume": env_or_file("UNMIXR_ANCHOR_VOLUME") or "medium",
        }
    return {
        "voice_id": env_or_file("UNMIXR_NARRATOR_VOICE_ID") or config.get("voice_id", ""),
        "language": env_or_file("UNMIXR_NARRATOR_LANGUAGE") or config.get("language", "en-US"),
        "speaking_rate": env_or_file("UNMIXR_NARRATOR_RATE") or "slow",
        "speaking_pitch": env_or_file("UNMIXR_NARRATOR_PITCH") or "low",
        "speaking_volume": env_or_file("UNMIXR_NARRATOR_VOLUME") or "medium",
    }


def render_unmixr_tts(text: str, output: Path, scene: dict | None = None) -> bool:
    config = unmixr_config()
    if config is None:
        return False
    profile = scene_voice_profile(scene or {})
    payload = json.dumps(
        {
            "text": text,
            "voice_id": profile["voice_id"],
            "language": profile["language"],
            "speaking_rate": profile["speaking_rate"],
            "speaking_pitch": profile["speaking_pitch"],
            "speaking_volume": profile["speaking_volume"],
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


async def render_tts(text: str, output: Path) -> None:
    helper = output.with_suffix(".edge_tts.py")
    helper.write_text(
        "import asyncio, edge_tts, pathlib, sys\n"
        "voice = sys.argv[1]\n"
        "text = pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')\n"
        "output = pathlib.Path(sys.argv[3])\n"
        "async def main():\n"
        "    await edge_tts.Communicate(text=text, voice=voice, rate='-9%', pitch='-7Hz').save(str(output))\n"
        "asyncio.run(main())\n",
        encoding="utf-8",
    )
    text_path = output.with_suffix(".txt")
    text_path.write_text(text, encoding="utf-8")
    edge_python = next((candidate for candidate in [
        "/tmp/black-ledger-newsreel-venv/bin/python",
        "/tmp/black-ledger-newsreel-venv/bin/python3",
        "/docker/chummercomplete/_completion/promo_video_rework_20260602/tts_venv/bin/python",
    ] if Path(candidate).is_file()), None)
    if edge_python is None:
        raise RuntimeError("edge_tts interpreter unavailable")
    try:
        run(edge_python, str(helper), VOICE, str(text_path), str(output))
    finally:
        helper.unlink(missing_ok=True)
        text_path.unlink(missing_ok=True)


def render_flite_tts(text: str, output: Path) -> None:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    run("ffmpeg", "-y", "-f", "lavfi", "-i", f"flite=text='{escaped}':voice=slt", "-c:a", "pcm_s16le", str(output))


def render_music(output: Path, seconds: float) -> None:
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=92:sample_rate=48000:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=184:sample_rate=48000:duration={seconds}",
        "-filter_complex",
        "[0:a]volume=0.05,lowpass=f=240[a0];[1:a]volume=0.03,lowpass=f=480[a1];[a0][a1]amix=inputs=2:normalize=0,alimiter=limit=0.8[out]",
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def make_vtt(scenes: list[dict], output: Path) -> None:
    def fmt(seconds: float) -> str:
        millis = round(seconds * 1000)
        hours, rem = divmod(millis, 3_600_000)
        minutes, rem = divmod(rem, 60_000)
        secs, ms = divmod(rem, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"

    cursor = 0.0
    lines = ["WEBVTT", ""]
    for idx, scene in enumerate(scenes, start=1):
        dur = float(scene["duration_seconds"])
        lines.extend([str(idx), f"{fmt(cursor)} --> {fmt(cursor + dur)}", str(scene["narration"]), ""])
        cursor += dur
    output.write_text("\n".join(lines), encoding="utf-8")


def clip_path(asset_id: str, scene_id: str) -> Path:
    return CLIPS / asset_id / f"{scene_id}.mp4"


def compose_asset(asset: dict) -> dict:
    asset_id = asset["asset_id"]
    slug = f"turn-{asset['turn']}-newsreel"
    mp4_out = NEWSREELS_ROOT / f"{slug}.mp4"
    webm_out = NEWSREELS_ROOT / f"{slug}.webm"
    poster_out = NEWSREELS_ROOT / f"{slug}-poster.png"
    vtt_out = NEWSREELS_ROOT / f"{slug}.vtt"
    NEWSREELS_ROOT.mkdir(parents=True, exist_ok=True)
    make_vtt(asset["scenes"], vtt_out)

    with tempfile.TemporaryDirectory(prefix=f"{asset_id}_") as temp_dir:
        temp = Path(temp_dir)
        concat = temp / "concat.txt"
        concat_lines: list[str] = []
        speech_provider = "unmixr-scene-tts"
        audio_segments: list[Path] = []
        for scene in asset["scenes"]:
            src = clip_path(asset_id, scene["id"])
            seg = temp / f"{scene['id']}.mp4"
            dur = float(scene["duration_seconds"])
            concat_lines.append(f"file '{seg}'\n")
            run(
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-an",
                "-vf",
                f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,trim=duration={dur},setpts=PTS-STARTPTS",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                str(seg),
            )
            speech = temp / f"{scene['id']}.mp3"
            if not render_unmixr_tts(str(scene["narration"]), speech, scene):
                speech_provider = "edge-tts"
                try:
                    asyncio.run(render_tts(str(scene["narration"]), speech))
                except Exception:
                    speech_provider = "ffmpeg-flite"
                    speech = temp / f"{scene['id']}.wav"
                    render_flite_tts(str(scene["narration"]), speech)
            if not speech.exists():
                speech_provider = "ffmpeg-flite"
                speech = temp / f"{scene['id']}.wav"
                render_flite_tts(str(scene["narration"]), speech)
            aligned = temp / f"{scene['id']}.m4a"
            run(
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(speech),
                "-af",
                f"apad=pad_dur={dur + 0.3},atrim=duration={dur},afade=t=out:st={max(dur - 0.35, 0)}:d=0.35",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                str(aligned),
            )
            audio_segments.append(aligned)
        concat.write_text("".join(concat_lines), encoding="utf-8")
        video_only = temp / "video_only.mp4"
        run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video_only))
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(video_only), "-vf", "select=eq(n\\,45)", "-vframes", "1", str(poster_out))
        speech_concat = temp / "speech_concat.txt"
        speech_concat.write_text("".join([f"file '{segment}'\n" for segment in audio_segments]), encoding="utf-8")
        speech = temp / "speech.m4a"
        run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(speech_concat), "-c", "copy", str(speech))
        music = temp / "music.wav"
        total_duration = duration(video_only)
        render_music(music, total_duration)
        audio = temp / "audio.m4a"
        run(
            "ffmpeg",
            "-y",
            "-i",
            str(speech),
            "-i",
            str(music),
            "-filter_complex",
            f"[0:a]apad=pad_dur={total_duration + 1.0},atrim=duration={total_duration},asplit=2[speechduck][speechmix];"
            "[1:a]volume=0.17[bed];"
            "[bed][speechduck]sidechaincompress=threshold=0.017:ratio=7:attack=4:release=220[ducked];"
            "[speechmix][ducked]amix=inputs=2:weights='1 1':normalize=0[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(audio),
        )
        run("ffmpeg", "-y", "-i", str(video_only), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-shortest", str(mp4_out))
        run("ffmpeg", "-y", "-i", str(video_only), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-tile-columns", "1", "-c:a", "libopus", "-b:a", "128k", "-shortest", str(webm_out))

    return {
        "asset_id": asset_id,
        "turn": asset["turn"],
        "status": "pass",
        "mp4": str(mp4_out),
        "webm": str(webm_out),
        "poster": str(poster_out),
        "vtt": str(vtt_out),
        "narration_provider": speech_provider,
    }


def main() -> int:
    args = parse_args()
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    selected_ids = set(args.asset or [])
    assets = payload["assets"]
    if selected_ids:
        assets = [asset for asset in assets if asset["asset_id"] in selected_ids]
    receipts = [compose_asset(asset) for asset in assets]
    out = ROOT / "_completion" / "black_ledger_magicfit_newsreels" / "BLACK_LEDGER_TURN_MAGICFIT_PUBLICATION.generated.json"
    out.write_text(json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "status": "pass", "receipts": receipts}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "count": len(receipts)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
