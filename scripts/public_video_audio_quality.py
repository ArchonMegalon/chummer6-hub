#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import wave
import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _unmixr_tts import UNMIXR_SHORT_TTS_PROVIDER

UNMIXR_PROVIDER = UNMIXR_SHORT_TTS_PROVIDER
CLEAN_SPEECH_AUDIO_GROUPS: set[str] = {
    "alice-90s-deepdive",
    "runsite-90s-deepdive",
    "runbook-press-90s-deepdive",
    "table-pulse-90s-deepdive",
}
SILENCE_GATE_DBFS = -42.0
MAX_SILENCE_SECONDS = 0.70
MAX_EDGE_SILENCE_SECONDS = 0.30
MAX_START_SILENCE_SECONDS = MAX_EDGE_SILENCE_SECONDS
NARRATION_END_BEFORE_VIDEO_SECONDS = 1.25
MIN_TAIL_SILENCE_SECONDS = 0.0
MAX_TAIL_SILENCE_SECONDS = 1.50
VIDEO_FADE_OUT_SECONDS = 0.0
VIDEO_FADE_CONTRACT = "ea.public_video_audio_gate.v1"
MAX_HIGHBAND_P95_RATIO = 0.18
MAX_HIGHBAND_P99_RATIO = 0.28
HIGHBAND_START_HZ = 5500.0
HIGHBAND_END_HZ = 7600.0
ALICE_VOICE_POLICY = "unmixr_premium_female_required_no_edge_fallback"
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


def _parse_silence_intervals(value: str, media_duration_seconds: float) -> list[tuple[float, float, float]]:
    intervals: list[tuple[float, float, float]] = []
    last_start = None
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
            if duration is not None and duration > 0:
                start_time = end_time - duration if last_start is None else last_start
                intervals.append((start_time, end_time, duration))
            last_start = None
    if last_start is not None and media_duration_seconds > last_start:
        intervals.append((last_start, media_duration_seconds, media_duration_seconds - last_start))
    return intervals


def _parse_silence_report(value: str, media_duration_seconds: float = 0.0) -> tuple[float, float]:
    intervals = _parse_silence_intervals(value, media_duration_seconds)
    if not intervals:
        return 0.0, 0.0
    max_silence = 0.0
    tail_silence = 0.0
    for start_time, end_time, duration in intervals:
        max_silence = max(max_silence, duration)
        if media_duration_seconds and end_time >= media_duration_seconds - 0.05:
            tail_silence = max(tail_silence, duration)
    return max_silence, tail_silence


def _audio_tone_metrics(path: Path) -> dict[str, object]:
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - dependency failure is still reported by the gate.
        return {"status": "unknown", "reason": f"numpy_unavailable:{exc}"}

    with tempfile.TemporaryDirectory(prefix="chummer-audio-gate-") as temp_dir:
        wav_path = Path(temp_dir) / "audio.wav"
        _run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-y",
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(wav_path),
            ]
        )
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            samples = np.frombuffer(wav.readframes(frames), dtype=np.int16).astype(np.float32) / 32768.0

    if samples.size < 4096:
        return {"status": "unknown", "reason": "audio_too_short_for_tone_probe"}

    window_size = 4096
    hop = 2048
    frequencies = np.fft.rfftfreq(window_size, 1.0 / sample_rate)
    full_band = (frequencies >= 80.0) & (frequencies <= HIGHBAND_END_HZ)
    high_band = (frequencies >= HIGHBAND_START_HZ) & (frequencies <= HIGHBAND_END_HZ)
    high_ratios: list[float] = []
    peak_frequencies: list[float] = []
    for offset in range(0, samples.size - window_size, hop):
        frame = samples[offset : offset + window_size]
        rms = float(np.sqrt(np.mean(frame * frame)))
        if rms < 0.003:
            continue
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(window_size))) ** 2
        total_energy = float(spectrum[full_band].sum() + 1e-12)
        high_energy = float(spectrum[high_band].sum())
        high_ratios.append(high_energy / total_energy)
        if high_energy > 0:
            high_values = spectrum[high_band]
            high_freqs = frequencies[high_band]
            peak_frequencies.append(float(high_freqs[int(np.argmax(high_values))]))

    if not high_ratios:
        return {"status": "unknown", "reason": "no_voiced_frames_for_tone_probe"}

    p95 = float(np.percentile(high_ratios, 95))
    p99 = float(np.percentile(high_ratios, 99))
    return {
        "status": "pass" if p95 <= MAX_HIGHBAND_P95_RATIO and p99 <= MAX_HIGHBAND_P99_RATIO else "fail",
        "highband_p95_ratio": round(p95, 6),
        "highband_p99_ratio": round(p99, 6),
        "highband_hz": [HIGHBAND_START_HZ, HIGHBAND_END_HZ],
        "dominant_highband_peak_hz": round(float(np.median(peak_frequencies)), 1) if peak_frequencies else None,
        "voiced_frame_count": len(high_ratios),
    }


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
            intervals = _parse_silence_intervals(silence_output, duration)
            if intervals:
                max_silence_seconds = max(duration_seconds for _, _, duration_seconds in intervals)
                tail_silence_seconds = max(
                    (
                        duration_seconds
                        for _, end_time, duration_seconds in intervals
                        if duration and end_time >= duration - 0.05
                    ),
                    default=0.0,
                )
            for _, end_time, silence_seconds in intervals:
                is_tail_silence = bool(duration and end_time >= duration - 0.05)
                if is_tail_silence:
                    if not MIN_TAIL_SILENCE_SECONDS <= silence_seconds <= MAX_TAIL_SILENCE_SECONDS:
                        reasons.append(f"audio_tail_silence_out_of_range_{silence_seconds:.2f}s")
                elif silence_seconds > MAX_SILENCE_SECONDS:
                    reasons.append(f"audio_silence_exceeded_{silence_seconds:.2f}s")
        except Exception as exc:
            reasons.append(f"audio_silence_probe_failed:{exc}")

    try:
        tone_metrics = _audio_tone_metrics(path)
        if tone_metrics.get("status") == "fail":
            reasons.append(
                "narrowband_beep_suspected:"
                f"highband_p95={tone_metrics.get('highband_p95_ratio')}:"
                f"highband_p99={tone_metrics.get('highband_p99_ratio')}"
            )
    except Exception as exc:
        tone_metrics = {"status": "fail", "reason": f"audio_tone_probe_failed:{exc}"}
        reasons.append(str(tone_metrics["reason"]))

    return {
        "status": "pass" if not reasons else "fail",
        "reasons": reasons,
        "audio_duration_seconds": float(duration),
        "media_duration_seconds": float(duration),
        "max_silence_seconds": float(max_silence_seconds),
        "tail_silence_seconds": float(tail_silence_seconds),
        "mean_volume_db": mean_volume,
        "max_volume_db": max_volume,
        "tone_metrics": tone_metrics,
    }


def retirement_receipt() -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "published",
        "pipeline": "public_video_audio_quality",
        "provider": UNMIXR_PROVIDER,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate public video audio for volume, silence, and narrowband beep artifacts.")
    parser.add_argument("media", nargs="*", type=Path)
    parser.add_argument("--allow-clean-speech-pauses", action="store_true")
    args = parser.parse_args()
    if not args.media:
        print(json.dumps(retirement_receipt(), sort_keys=True))
        return 0
    results = [
        {
            "path": str(path),
            "quality": audio_quality(path, allow_clean_speech_pauses=args.allow_clean_speech_pauses),
        }
        for path in args.media
    ]
    payload = {
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "pass" if all(item["quality"]["status"] == "pass" for item in results) else "fail",
        "media": results,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
