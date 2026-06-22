#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _unmixr_tts import UNMIXR_SHORT_TTS_PROVIDER

UNMIXR_PROVIDER = UNMIXR_SHORT_TTS_PROVIDER
CLEAN_SPEECH_AUDIO_GROUPS: set[str] = set()
SILENCE_GATE_DBFS = -42.0
MAX_SILENCE_SECONDS = 0.70
MAX_EDGE_SILENCE_SECONDS = 0.30
MAX_START_SILENCE_SECONDS = MAX_EDGE_SILENCE_SECONDS
NARRATION_END_BEFORE_VIDEO_SECONDS = 0.0
MIN_TAIL_SILENCE_SECONDS = 0.0
MAX_TAIL_SILENCE_SECONDS = MAX_EDGE_SILENCE_SECONDS
VIDEO_FADE_OUT_SECONDS = 0.0
VIDEO_FADE_CONTRACT = "ea.public_video_audio_gate.v1"
ALICE_VOICE_POLICY = "mixed_female_or_male_policy_with_fallback"
ALICE_CLEAN_AUDIO_STYLE = "clean_audiobook_style_no_bed_no_noise_floor"
ALICE_VOICE_GENDER = "female"
ALICE_VOICE_QUALITY = "premium"


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(output[:2000])
    return output


def _safe_float(value: str | None) -> float | None:
    if not value:
        return None
    stripped = value.strip()
    if stripped.lower() in {"-inf", "inf", "nan"}:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _parse_volume(value: str) -> dict[str, float]:
    mean_match = re.search(r"mean_volume:\s*([-+]?\d+(?:\.\d+)?|-.?inf)\s*dB", value, re.IGNORECASE)
    max_match = re.search(r"max_volume:\s*([-+]?\d+(?:\.\d+)?|-.?inf)\s*dB", value, re.IGNORECASE)
    mean = _safe_float(mean_match.group(1) if mean_match else None)
    peak = _safe_float(max_match.group(1) if max_match else None)
    return {"mean_volume_db": mean, "max_volume_db": peak}


def _parse_silence_report(value: str) -> tuple[float, float]:
    max_silence = 0.0
    tail_silence = 0.0
    last_start = None
    last_end = None
    for line in value.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)", line)
        end_match = re.search(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)", line)
        if start_match:
            last_start = float(start_match.group(1))
            continue
        if end_match:
            end_time = float(end_match.group(1))
            duration_match = re.search(r"silence_duration:\s*([0-9]+(?:\.[0-9]+)?)", line)
            duration = float(duration_match.group(1)) if duration_match else None
            if duration is None and last_start is not None:
                duration = end_time - last_start
            if duration is not None and duration > max_silence:
                max_silence = duration
                tail_silence = duration if last_end is None else tail_silence
            last_end = end_time
            last_start = None
    return max_silence, tail_silence


def probe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(payload)


def audio_quality(path: Path, allow_clean_speech_pauses: bool = False) -> dict[str, object]:
    reasons: list[str] = []
    if not path.is_file():
        return {"status": "fail", "reasons": [f"audio_file_missing:{path}"], "max_silence_seconds": 0.0, "tail_silence_seconds": 0.0, "audio_duration_seconds": 0.0, "media_duration_seconds": 0.0}

    try:
        media = probe(path)
    except Exception as exc:
        return {"status": "fail", "reasons": [f"audio_probe_failed:{exc}"], "max_silence_seconds": 0.0, "tail_silence_seconds": 0.0, "audio_duration_seconds": 0.0, "media_duration_seconds": 0.0}

    streams = media.get("streams") or []
    audio_streams = [stream for stream in streams if str(stream.get("codec_type") or "").lower() == "audio"]
    duration = float(dict(media.get("format") or {}).get("duration") or 0.0)

    if not audio_streams:
        reasons.append("audio_stream_missing")
    elif len(audio_streams) > 1:
        reasons.append("audio_stream_count_invalid")

    try:
        volume_output = _run_command([
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ])
        volumes = _parse_volume(volume_output)
        mean_volume = volumes["mean_volume_db"]
        max_volume = volumes["max_volume_db"]
        if mean_volume is None:
            reasons.append("audio_volume_missing")
        elif mean_volume < SILENCE_GATE_DBFS:
            reasons.append("audio_mean_too_quiet")
        if max_volume is None:
            reasons.append("audio_peak_missing")
        elif max_volume > -1.0:
            reasons.append("audio_clipping_detected")
    except Exception as exc:
        reasons.append(f"audio_volume_probe_failed:{exc}")
        mean_volume = None
        max_volume = None

    max_silence_seconds = 0.0
    tail_silence_seconds = 0.0
    if not allow_clean_speech_pauses:
        try:
            silence_output = _run_command([
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-af",
                f"silencedetect=noise={SILENCE_GATE_DBFS}dB:d={MAX_SILENCE_SECONDS}",
                "-f",
                "null",
                "-",
            ])
            max_silence_seconds, tail_silence_seconds = _parse_silence_report(silence_output)
            if max_silence_seconds > MAX_SILENCE_SECONDS:
                reasons.append(f"audio_silence_exceeded_{max_silence_seconds:.2f}s")
        except Exception as exc:
            reasons.append(f"audio_silence_probe_failed:{exc}")

    return {
        "status": "pass" if not reasons else "fail",
        "reasons": reasons,
        "audio_duration_seconds": float(duration),
        "media_duration_seconds": float(duration),
        "max_silence_seconds": float(max_silence_seconds),
        "tail_silence_seconds": float(tail_silence_seconds),
        "mean_volume_db": mean_volume,
        "max_volume_db": max_volume,
    }


def retirement_receipt() -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "published",
        "pipeline": "public_video_audio_quality",
        "provider": UNMIXR_PROVIDER,
    }


def main() -> int:
    print(json.dumps(retirement_receipt(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
