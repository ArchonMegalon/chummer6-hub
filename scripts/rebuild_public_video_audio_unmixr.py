#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[1]
MEDIA_ROOT = REPO / "Chummer.Run.Api" / "wwwroot" / "media"
OUT_ROOT = Path("/docker/chummercomplete/_completion/public_video_audio_unmixr_20260619")
LEGACY_PROMO_AUDIO = REPO / "scripts" / "rebuild_promo_audio_continuous.py"
UNMIXR_PROVIDER = "unmixr-short-tts"
TARGET_SR = 48000
HIGH_TONE_CLEANUP_FILTER = "equalizer=f=11730:width_type=h:width=420:g=-48,lowpass=f=9800"
LOW_RUMBLE_HIGHPASS_HZ = 270
LOW_TONE_CLEANUP_FILTER = "equalizer=f=188:width_type=h:width=90:g=-18,equalizer=f=235:width_type=h:width=105:g=-18"
NARRATION_START_DELAY_MS = 500

DEFAULT_VOICE_ENV_KEYS = (
    "UNMIXR_PREMIUM_NARRATOR_VOICE_ID",
    "UNMIXR_NARRATOR_VOICE_ID",
    "UNMIXR_VOICE_ID",
)

VOICE_ENV_BY_GROUP = {
    "alice-90s-deepdive": (
        "UNMIXR_ALICE_VOICE_ID",
        "UNMIXR_FEMALE_NARRATOR_VOICE_ID",
        *DEFAULT_VOICE_ENV_KEYS,
    ),
}


@dataclass(frozen=True)
class VideoGroup:
    key: str
    files: tuple[Path, ...]
    caption_file: Path | None
    receipt_file: Path | None
    narration: str | None
    mode: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(*command: str, capture: bool = False) -> str:
    if command and command[0] == "ffmpeg" and "-loglevel" not in command:
        command = ("ffmpeg", "-hide_banner", "-loglevel", "warning", *command[1:])
    completed = subprocess.run(command, check=True, text=True, capture_output=capture)
    return completed.stdout if capture else ""


def probe(path: Path) -> dict[str, Any]:
    return json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(path),
            capture=True,
        )
    )


def duration(path: Path) -> float:
    return float((probe(path).get("format") or {}).get("duration") or 0.0)


def load_legacy_audio_module() -> Any:
    spec = importlib.util.spec_from_file_location("legacy_promo_audio", LEGACY_PROMO_AUDIO)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {LEGACY_PROMO_AUDIO}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LEGACY = load_legacy_audio_module()


def resolve_voice_id(group_key: str) -> tuple[str, str]:
    for key in VOICE_ENV_BY_GROUP.get(group_key, DEFAULT_VOICE_ENV_KEYS):
        value = LEGACY.env_or_file(key)
        if value:
            return value, key
    return "", ""


@contextmanager
def unmixr_voice_override(group_key: str):
    voice_id, source_env = resolve_voice_id(group_key)
    old_values = {key: os.environ.get(key) for key in DEFAULT_VOICE_ENV_KEYS}
    try:
        if voice_id:
            os.environ["UNMIXR_PREMIUM_NARRATOR_VOICE_ID"] = voice_id
        yield voice_id, source_env
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


SCRIPT_KEY_BY_GROUP = {
    "nexus-pan-90s-deepdive": "nexus_pan_90s_deepdive",
    "nexus-pan-epic-90s": "nexus-pan_epic_90s",
    "alice-90s-deepdive": "alice_90s_deepdive",
    "karma-forge-90s-deepdive": "karma_forge_90s_deepdive",
    "jackpoint-90s-deepdive": "jackpoint_90s_deepdive",
    "runsite-90s-deepdive": "runsite_90s_deepdive",
    "runbook-press-90s-deepdive": "runbook_press_90s_deepdive",
    "table-pulse-90s-deepdive": "table_pulse_90s_deepdive",
    "black-ledger-90s-deepdive": "black_ledger_90s_deepdive",
    "black-ledger-epic-90s": "black_ledger_epic_90s",
    "community-hub-90s-deepdive": "community_hub_90s_deepdive",
}


EXTRA_SCRIPT_BY_GROUP = {
    "origin-dossier-90s-deepdive": (
        "Origin Dossier starts where the character sheet stops. It takes the events that shaped a runner and turns them into things the table can actually use: contacts, enemies, debts, scars, secrets, beliefs, and unfinished consequences. "
        "The player keeps control. The GM keeps the campaign steer. Nothing becomes part of the game until both sides approve it. "
        "A clinic favor can become pressure. A family name can become a lead. A mistake can become a secret. A scar can become a code the runner lives by. "
        "The dossier can also feed portraits, scene packets, narration, video, and audiobook versions later, but the mechanics stay in Chummer. Prose never silently changes ware, money, qualities, magic, legality, or build math. "
        "When ALICE reads approved origin material later, it reads character context, not hidden rules. Weak media can be rejected without damaging the runner. Strong material gives the crew a person to bring into the next job. "
        "Not a backstory pasted on top. A life with consequences."
    ),
    "black-ledger-3dvista-flythrough": (
        "Black Ledger is the city with a memory. District pressure, faction motion, open jobs, and newsreel fallout give the GM a place to start when the table asks what changed after the last run. "
        "The flythrough is not decoration. It is a fast way to feel the board: where heat is rising, where opportunity is gathering, and where the crew may have left trouble behind."
    ),
    "black-ledger-video-globe-idle": (
        "The city is still moving. Black Ledger keeps district pressure, faction heat, and visible fallout close enough for the next decision."
    ),
}


def humanize_public_narration(text: str) -> str:
    replacements = [
        ("You build with the truth in view", "You build with the important details in view"),
        ("no scavenger hunt for the truth", "no scavenger hunt for the current version"),
        ("another place for the truth to go missing", "another place for the answer to go missing"),
        ("strange little truths", "strange little campaign details"),
        ("Those truths need different doors", "Those details need different doors"),
        ("provider proof", "working check"),
        ("provider proofs", "working checks"),
        ("release truth", "release status"),
        ("source truth", "source material"),
        ("rules truth", "rules"),
        ("build truth", "build math"),
        ("truth matrix", "status view"),
        ("half-truth", "half-story"),
        ("the truth", "the details"),
        ("truths", "details"),
        ("truth", "details"),
        ("receipts", "clear notes"),
        ("receipt", "clear note"),
        ("proof", "backing"),
        ("governed", "table-approved"),
        ("governance", "agreement"),
        ("rule evolution", "house-rule changes"),
        ("lanes", "areas"),
        ("lane", "area"),
        ("open-run area", "open-run board"),
        ("social area", "social side"),
    ]
    cleaned = text
    for before, after in replacements:
        cleaned = re.sub(rf"\b{re.escape(before)}\b", after, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def canonical_group_key(path: Path) -> str:
    stem = path.stem
    if stem.endswith("-mobile"):
        stem = stem.removesuffix("-mobile")
    return stem


def parse_vtt(path: Path) -> str:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.isdigit() or "-->" in line:
            continue
        lines.append(line)
    return " ".join(lines).strip()


def write_vtt(path: Path, text: str, total_duration: float) -> None:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    if not sentences:
        sentences = [text.strip()]
    chunks: list[str] = []
    pending = ""
    for sentence in sentences:
        candidate = f"{pending} {sentence}".strip()
        if len(candidate.split()) <= 22 or not pending:
            pending = candidate
        else:
            chunks.append(pending)
            pending = sentence
    if pending:
        chunks.append(pending)
    usable_duration = max(total_duration, 1.0)
    step = usable_duration / max(len(chunks), 1)

    def fmt(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"

    output = ["WEBVTT", ""]
    for index, chunk in enumerate(chunks, start=1):
        start = (index - 1) * step
        end = min(index * step, usable_duration)
        output.extend([str(index), f"{fmt(start)} --> {fmt(end)}", chunk, ""])
    path.write_text("\n".join(output), encoding="utf-8")


def narration_from_receipt(receipt: Path) -> str | None:
    data = json.loads(receipt.read_text(encoding="utf-8"))
    captions = data.get("captions")
    if isinstance(captions, list) and captions:
        return " ".join(str(item).strip() for item in captions if str(item).strip())
    scenes = data.get("production_scenes") or data.get("scene_payloads") or data.get("scene_narration")
    if isinstance(scenes, list):
        parts: list[str] = []
        for scene in scenes:
            if isinstance(scene, dict):
                text = str(scene.get("narration") or scene.get("caption") or "").strip()
                if text:
                    parts.append(text)
            elif isinstance(scene, str):
                parts.append(scene.strip())
        if parts:
            return " ".join(parts)
    return None


def narration_for_group(key: str, caption_file: Path | None, receipt_file: Path | None) -> tuple[str | None, str]:
    script_key = SCRIPT_KEY_BY_GROUP.get(key, key)
    legacy_script = getattr(LEGACY, "SCRIPTS", {}).get(script_key)
    if legacy_script:
        return humanize_public_narration(legacy_script), "legacy_longform_script_humanized"
    if key in EXTRA_SCRIPT_BY_GROUP:
        return humanize_public_narration(EXTRA_SCRIPT_BY_GROUP[key]), "authored_repair_script"
    if receipt_file and receipt_file.exists():
        receipt_text = narration_from_receipt(receipt_file)
        if receipt_text:
            return humanize_public_narration(receipt_text), "receipt_captions_humanized"
    if caption_file and caption_file.exists():
        caption_text = parse_vtt(caption_file)
        if caption_text:
            return humanize_public_narration(caption_text), "caption_file_humanized"
    return None, "clean_ambient_bed"


def find_groups(selected: set[str] | None = None) -> list[VideoGroup]:
    buckets: dict[str, list[Path]] = {}
    for path in sorted(MEDIA_ROOT.rglob("*")):
        if path.suffix.lower() not in {".mp4", ".webm"}:
            continue
        key = canonical_group_key(path)
        if selected and key not in selected and path.name not in selected:
            continue
        buckets.setdefault(key, []).append(path)

    groups: list[VideoGroup] = []
    for key, files in sorted(buckets.items()):
        roots = {file.parent for file in files}
        caption_file = next((root / f"{key}.vtt" for root in roots if (root / f"{key}.vtt").exists()), None)
        receipt_file = next((root / f"{key}.receipt.json" for root in roots if (root / f"{key}.receipt.json").exists()), None)
        narration, source = narration_for_group(key, caption_file, receipt_file)
        groups.append(
            VideoGroup(
                key=key,
                files=tuple(sorted(files)),
                caption_file=caption_file,
                receipt_file=receipt_file,
                narration=narration,
                mode=source if narration else "clean_ambient_bed",
            )
        )
    return groups


def render_pause(output: Path, seconds: float) -> None:
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={TARGET_SR}:cl=mono:d={seconds:.3f}",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def normalize_voice(source: Path, output: Path) -> None:
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-af",
        f"afade=t=in:st=0:d=0.025,highpass=f={LOW_RUMBLE_HIGHPASS_HZ},highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},acompressor=threshold=-23dB:ratio=2.2:attack=16:release=240:makeup=1.8,alimiter=limit=0.91",
        "-ar",
        str(TARGET_SR),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def concat_wavs(parts: list[Path], output: Path) -> None:
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text("".join(f"file '{part}'\n" for part in parts), encoding="utf-8")
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "pcm_s16le", str(output))


def render_unmixr_narration(
    group_key: str,
    text: str,
    work: Path,
    *,
    force_tts: bool = False,
) -> tuple[Path, dict[str, Any]]:
    beats = LEGACY.split_script_into_beats(text)
    beat_dir = work / "beats"
    beat_dir.mkdir(parents=True, exist_ok=True)
    stitched = work / "unmixr-narration.wav"
    voice_id, source_env = resolve_voice_id(group_key)
    if stitched.is_file() and stitched.stat().st_size > 0 and not force_tts:
        return stitched, {
            "provider": UNMIXR_PROVIDER,
            "voice_id_redacted": redact(voice_id),
            "voice_source_env": source_env,
            "voice_reused_from_cache": True,
            "language": "",
            "speaking_rate": "",
            "speaking_pitch": "",
            "speaking_volume": "",
            "beat_count": len(beats),
            "failures": [],
        }

    parts: list[Path] = []
    failures: list[str] = []
    with unmixr_voice_override(group_key) as (voice_id, source_env):
        for index, beat in enumerate(beats, start=1):
            raw = beat_dir / f"beat-{index:02d}.mp3"
            ok = LEGACY.render_unmixr_tts(beat, raw)
            if not ok:
                failures.append(f"beat-{index:02d}")
                raise RuntimeError(f"Unmixr TTS failed for {work.name} beat {index}")
            normalized = beat_dir / f"beat-{index:02d}.wav"
            normalize_voice(raw, normalized)
            parts.append(normalized)
            if index < len(beats):
                pause = beat_dir / f"pause-{index:02d}.wav"
                pause_seconds = min(max(0.12 + len(beat.split()) * 0.004, 0.16), 0.34)
                render_pause(pause, pause_seconds)
                parts.append(pause)
    concat_wavs(parts, stitched)
    config = LEGACY.unmixr_config() or {}
    return stitched, {
        "provider": UNMIXR_PROVIDER,
        "voice_id_redacted": redact(voice_id or config.get("voice_id", "")),
        "voice_source_env": source_env,
        "voice_reused_from_cache": False,
        "language": config.get("language", ""),
        "speaking_rate": config.get("speaking_rate", ""),
        "speaking_pitch": config.get("speaking_pitch", ""),
        "speaking_volume": config.get("speaking_volume", ""),
        "beat_count": len(beats),
        "failures": failures,
    }


def redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def bed_filter(total_duration: float, style: str) -> str:
    if style == "ambient":
        volume = 0.060
        lowpass = 3400
        modulation = "aphaser=in_gain=0.18:out_gain=0.42:delay=2.0:decay=0.08:speed=0.10"
    else:
        volume = 0.045
        lowpass = 3200
        modulation = "aphaser=in_gain=0.14:out_gain=0.34:delay=2.0:decay=0.06:speed=0.10"
    fade_out = min(2.4, max(total_duration / 4.0, 0.4))
    return (
        f"anoisesrc=color=pink:amplitude=0.050:r={TARGET_SR}:d={total_duration:.3f},"
        f"highpass=f={LOW_RUMBLE_HIGHPASS_HZ},highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},lowpass=f={lowpass},{modulation},"
        f"afade=t=in:st=0:d={min(1.2, max(total_duration / 4.0, 0.2)):.3f},"
        f"afade=t=out:st={max(total_duration - fade_out, 0):.3f}:d={fade_out:.3f},"
        f"volume={volume}[bed]"
    )


def build_mixed_audio(narration: Path | None, total_duration: float, output: Path) -> str:
    if narration is None:
        filter_complex = f"{bed_filter(total_duration, 'ambient')};[bed]highpass=f={LOW_RUMBLE_HIGHPASS_HZ},highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},alimiter=limit=0.83[a]"
        run(
            "ffmpeg",
            "-y",
            "-filter_complex",
            filter_complex,
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(output),
        )
        return "ambient_bed_only"

    source_duration = duration(narration)
    target_voice = max(total_duration - 2.7, 1.0)
    if source_duration > target_voice:
        tempo = min(max(source_duration / target_voice, 1.0), 1.18)
        voice_prep = f"atempo={tempo:.5f},atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = f"sped_up_{tempo:.3f}"
    elif source_duration < target_voice * 0.90:
        tempo = max(source_duration / target_voice, 0.86)
        voice_prep = f"atempo={tempo:.5f},atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = f"stretched_{tempo:.3f}"
    else:
        voice_prep = f"atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = "natural"

    filter_complex = (
        f"[0:a]{voice_prep},afade=t=in:st=0:d=0.35,afade=t=out:st={max(target_voice - 0.6, 0):.3f}:d=0.6,"
        f"highpass=f={LOW_RUMBLE_HIGHPASS_HZ},highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},acompressor=threshold=-22dB:ratio=2.4:attack=18:release=260:makeup=2.0,"
        f"alimiter=limit=0.88[vo0];"
        f"[vo0]adelay={NARRATION_START_DELAY_MS}|{NARRATION_START_DELAY_MS},apad,atrim=0:{total_duration:.3f},volume=1.10[vo];"
        f"{bed_filter(total_duration, 'narration')};"
        f"[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,highpass=f={LOW_RUMBLE_HIGHPASS_HZ},highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},alimiter=limit=0.90[a]"
    )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(narration),
        "-filter_complex",
        filter_complex,
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(output),
    )
    return fit


def remux(video: Path, audio: Path, output: Path, total_duration: float) -> None:
    temp = output.with_name(f"{output.stem}.audio-rebuild.tmp{output.suffix}")
    codec_args = ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    if output.suffix.lower() == ".webm":
        codec_args = ["-c:a", "libopus", "-b:a", "128k"]
    run(
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
        "-t",
        f"{total_duration:.3f}",
        "-c:v",
        "copy",
        *codec_args,
        str(temp),
    )
    shutil.move(str(temp), str(output))


def pcm_samples(path: Path) -> np.ndarray:
    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(TARGET_SR),
            "-",
        ]
    )
    if not raw:
        return np.array([], dtype=np.float32)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def dbfs(value: float) -> float:
    if value <= 1e-12:
        return -120.0
    return 20.0 * math.log10(value)


def audio_quality(path: Path) -> dict[str, Any]:
    samples = pcm_samples(path)
    if samples.size == 0:
        return {"status": "fail", "reason": "no_audio_samples"}
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))
    frame = 4096
    hop = 2048
    if samples.size < frame:
        padded = np.pad(samples, (0, frame - samples.size))
        windows = padded.reshape(1, frame)
    else:
        count = 1 + (samples.size - frame) // hop
        windows = np.lib.stride_tricks.as_strided(
            samples,
            shape=(count, frame),
            strides=(samples.strides[0] * hop, samples.strides[0]),
        ).copy()
    windows *= np.hanning(frame)
    spectrum = np.abs(np.fft.rfft(windows, axis=1)) ** 2
    mean_spec = np.mean(spectrum, axis=0)
    freqs = np.fft.rfftfreq(frame, 1.0 / TARGET_SR)
    high_mask = (freqs >= 10000) & (freqs <= 16000)
    tone_mask = (freqs >= 10500) & (freqs <= 13000)
    sub_bass_mask = (freqs >= 20) & (freqs <= 90)
    low_bass_mask = (freqs >= 20) & (freqs <= 280)
    low_tone_mask = (freqs >= 35) & (freqs <= 280)
    voice_mask = (freqs >= 320) & (freqs <= 4200)
    high_power = float(np.sum(mean_spec[high_mask])) if np.any(high_mask) else 0.0
    all_power = float(np.sum(mean_spec)) or 1e-12
    high_ratio = high_power / all_power
    sub_bass_power = float(np.sum(mean_spec[sub_bass_mask])) if np.any(sub_bass_mask) else 0.0
    low_bass_power = float(np.sum(mean_spec[low_bass_mask])) if np.any(low_bass_mask) else 0.0
    voice_power = float(np.sum(mean_spec[voice_mask])) if np.any(voice_mask) else 0.0
    sub_bass_ratio = sub_bass_power / all_power
    low_bass_ratio = low_bass_power / all_power
    voice_to_low_db = 10.0 * math.log10(max(voice_power / max(low_bass_power, 1e-18), 1e-18))
    if np.any(tone_mask):
        tone_values = mean_spec[tone_mask]
        tone_freqs = freqs[tone_mask]
        max_index = int(np.argmax(tone_values))
        tone_peak_hz = float(tone_freqs[max_index])
        tone_peak = float(tone_values[max_index])
        tone_median = float(np.median(tone_values)) or 1e-18
        tone_prominence_db = 10.0 * math.log10(max(tone_peak / tone_median, 1e-18))
    else:
        tone_peak_hz = 0.0
        tone_prominence_db = 0.0
    if np.any(low_tone_mask):
        low_tone_values = mean_spec[low_tone_mask]
        low_tone_freqs = freqs[low_tone_mask]
        low_max_index = int(np.argmax(low_tone_values))
        low_tone_peak_hz = float(low_tone_freqs[low_max_index])
        low_tone_peak = float(low_tone_values[low_max_index])
        low_tone_median = float(np.median(low_tone_values)) or 1e-18
        low_tone_prominence_db = 10.0 * math.log10(max(low_tone_peak / low_tone_median, 1e-18))
    else:
        low_tone_peak_hz = 0.0
        low_tone_prominence_db = 0.0
    status = "pass"
    reasons: list[str] = []
    if peak > 0.98:
        status = "fail"
        reasons.append("peak_too_hot")
    if dbfs(rms) < -38:
        status = "fail"
        reasons.append("too_quiet")
    if high_ratio > 0.018 and tone_prominence_db > 20:
        status = "fail"
        reasons.append("high_frequency_tonal_artifact")
    if sub_bass_ratio > 0.010:
        status = "fail"
        reasons.append("sub_bass_rumble")
    if low_bass_ratio > 0.045 and voice_to_low_db < 16.0:
        status = "fail"
        reasons.append("low_frequency_rumble")
    if low_tone_peak_hz <= 280 and low_tone_prominence_db > 9.0 and low_bass_ratio > 0.020:
        status = "fail"
        reasons.append("low_frequency_tonal_artifact")
    return {
        "status": status,
        "reasons": reasons,
        "rms_dbfs": round(dbfs(rms), 2),
        "peak_dbfs": round(dbfs(peak), 2),
        "high_band_power_ratio": round(high_ratio, 6),
        "tone_peak_hz": round(tone_peak_hz, 1),
        "tone_peak_prominence_db": round(tone_prominence_db, 2),
        "sub_bass_power_ratio": round(sub_bass_ratio, 6),
        "low_bass_power_ratio": round(low_bass_ratio, 6),
        "voice_to_low_db": round(voice_to_low_db, 2),
        "low_tone_peak_hz": round(low_tone_peak_hz, 1),
        "low_tone_peak_prominence_db": round(low_tone_prominence_db, 2),
    }


def rebuild_group(group: VideoGroup, *, force_tts: bool = False) -> dict[str, Any]:
    work = OUT_ROOT / group.key
    work.mkdir(parents=True, exist_ok=True)
    provider_meta: dict[str, Any] = {"provider": "first_party_audio_bed", "voice_id_redacted": ""}
    narration_path: Path | None = None
    if group.narration:
        narration_path, provider_meta = render_unmixr_narration(group.key, group.narration, work, force_tts=force_tts)
    file_receipts: list[dict[str, Any]] = []
    for video in group.files:
        total_duration = duration(video)
        mixed = work / f"{video.stem}.mixed.wav"
        fit_mode = build_mixed_audio(narration_path, total_duration, mixed)
        backup = work / f"{video.name}.before-unmixr-audio"
        shutil.copy2(video, backup)
        remux(video, mixed, video, total_duration)
        quality = audio_quality(video)
        info = probe(video)
        streams = info.get("streams") or []
        file_receipts.append(
            {
                "file": str(video.relative_to(REPO)),
                "duration_seconds": round(total_duration, 3),
                "backup": str(backup),
                "fit_mode": fit_mode,
                "probe": info,
                "audio_streams": sum(1 for stream in streams if stream.get("codec_type") == "audio"),
                "video_streams": sum(1 for stream in streams if stream.get("codec_type") == "video"),
                "quality": quality,
            }
        )
    if group.caption_file and group.narration:
        longest_duration = max(duration(file) for file in group.files)
        write_vtt(group.caption_file, group.narration, longest_duration)
    status = "pass"
    for receipt in file_receipts:
        if receipt["audio_streams"] != 1 or receipt["video_streams"] != 1 or receipt["quality"].get("status") != "pass":
            status = "fail"
    return {
        "group_key": group.key,
        "status": status,
        "mode": group.mode,
        "narration_word_count": len(group.narration.split()) if group.narration else 0,
        "caption_file": str(group.caption_file.relative_to(REPO)) if group.caption_file else "",
        "receipt_file": str(group.receipt_file.relative_to(REPO)) if group.receipt_file else "",
        "provider": provider_meta,
        "files": file_receipts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate public Chummer video audio with Unmixr narration and hard audio QA.")
    parser.add_argument("--only", default="", help="Comma-separated group keys or file names.")
    parser.add_argument("--audit-only", action="store_true", help="Only audit current audio quality.")
    parser.add_argument("--force-tts", action="store_true", help="Regenerate Unmixr narration even when a cached narration WAV exists.")
    args = parser.parse_args()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    selected = {part.strip() for part in args.only.split(",") if part.strip()} or None
    groups = find_groups(selected)
    if args.audit_only:
        receipts = []
        for group in groups:
            files = []
            for video in group.files:
                info = probe(video)
                streams = info.get("streams") or []
                files.append(
                    {
                        "file": str(video.relative_to(REPO)),
                        "audio_streams": sum(1 for stream in streams if stream.get("codec_type") == "audio"),
                        "video_streams": sum(1 for stream in streams if stream.get("codec_type") == "video"),
                        "quality": audio_quality(video),
                    }
                )
            receipts.append({"group_key": group.key, "mode": group.mode, "files": files})
    else:
        if not LEGACY.unmixr_config():
            raise SystemExit("UNMIXR_API_KEY and UNMIXR_VOICE_ID are required for this rebuild.")
        receipts = [rebuild_group(group, force_tts=args.force_tts) for group in groups]

    status = "pass"
    for group in receipts:
        for file_receipt in group.get("files", []):
            if file_receipt.get("audio_streams") != 1 or file_receipt.get("video_streams") != 1:
                status = "fail"
            if (file_receipt.get("quality") or {}).get("status") != "pass":
                status = "fail"
        if group.get("status") == "fail":
            status = "fail"

    manifest = {
        "contract_name": "chummer.public_video_audio_rebuild.v1",
        "generated_at_utc": utc_now(),
        "status": status,
        "scope": {
            "definition": "all public MP4/WebM files under Chummer.Run.Api/wwwroot/media, grouped by canonical asset stem; desktop, mobile and WebM variants included",
            "media_root": str(MEDIA_ROOT),
            "group_count": len(receipts),
            "file_count": sum(len(group.get("files", [])) for group in receipts),
        },
        "provider_posture": {
            "narration_provider": UNMIXR_PROVIDER,
            "unmixr_required": not args.audit_only,
            "non_narrated_mode": "clean first-party cinematic ambient bed only when no narration source exists",
            "artifact_filters": {
                "notch_hz": 11730,
                "low_tone_notches_hz": [188, 235],
                "lowpass_hz": 9800,
                "low_rumble_highpass_hz": LOW_RUMBLE_HIGHPASS_HZ,
                "tone_gate": "fails on narrow high-frequency tonal artifact, sub-bass rumble, and 35-190 Hz low-tone brumming, not only missing audio",
            },
            "voice_selection": {
                "default_voice_env_order": list(DEFAULT_VOICE_ENV_KEYS),
                "alice_voice_env_order": list(VOICE_ENV_BY_GROUP["alice-90s-deepdive"]),
            },
        },
        "groups": receipts,
    }
    output = OUT_ROOT / ("PUBLIC_VIDEO_AUDIO_AUDIT.generated.json" if args.audit_only else "PUBLIC_VIDEO_AUDIO_REBUILD.generated.json")
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(output)
    print("PUBLIC_VIDEO_AUDIO_PASS" if status == "pass" else "PUBLIC_VIDEO_AUDIO_FAIL")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
