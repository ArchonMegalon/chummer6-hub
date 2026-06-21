#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
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
LOW_RUMBLE_HIGHPASS_HZ = 90
LOW_TONE_CLEANUP_FILTER = "equalizer=f=188:width_type=h:width=90:g=-18,equalizer=f=235:width_type=h:width=105:g=-18"
NARRATION_START_DELAY_MS = 180
MAX_SILENCE_SECONDS = 0.70
MAX_EDGE_SILENCE_SECONDS = 0.30
SILENCE_GATE_DBFS = -42.0
ALICE_CLEAN_AUDIO_GROUP = "alice-90s-deepdive"
AUDIOBOOK_STYLE_NORMALIZATION_FILTER = "dynaudnorm=f=150:g=15,loudnorm=I=-16:TP=-1.5:LRA=11"
ALICE_CLEAN_AUDIO_STYLE = "clean_audiobook_style_no_bed_no_noise_floor"
UNMIXR_VOICE_DISCOVERY_API = "https://unmixr.com/api/v1/voice-list/"
DEFAULT_PREMIUM_VOICE_LABEL = "Blue"
ALICE_PREMIUM_FEMALE_VOICE_LABEL = "Ava"
UNMIXR_VOICE_POLICY = "unmixr_premium_required_no_edge_fallback"
ALICE_VOICE_POLICY = "unmixr_premium_female_required_no_edge_fallback"
VOICE_DISCOVERY_FIELDS = "uuid,character,gender,language,quality,use_cases,is_available"

DEFAULT_VOICE_ENV_KEYS = (
    "UNMIXR_PREMIUM_NARRATOR_VOICE_ID",
    "UNMIXR_NARRATOR_VOICE_ID",
)

VOICE_ENV_BY_GROUP = {
    ALICE_CLEAN_AUDIO_GROUP: (
        "UNMIXR_ALICE_VOICE_ID",
        "UNMIXR_FEMALE_NARRATOR_VOICE_ID",
    ),
}

_UNMIXR_DISCOVERY_CACHE: dict[tuple[str, str], dict[str, Any]] = {}

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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def _voice_id_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _unmixr_voice_policy_for_group(group_key: str) -> str:
    return ALICE_VOICE_POLICY if group_key == ALICE_CLEAN_AUDIO_GROUP else UNMIXR_VOICE_POLICY


def _preferred_unmixr_voice_label(group_key: str) -> str:
    env_key = "UNMIXR_ALICE_PREMIUM_VOICE_LABEL" if group_key == ALICE_CLEAN_AUDIO_GROUP else "UNMIXR_PREMIUM_NARRATOR_VOICE_LABEL"
    default = ALICE_PREMIUM_FEMALE_VOICE_LABEL if group_key == ALICE_CLEAN_AUDIO_GROUP else DEFAULT_PREMIUM_VOICE_LABEL
    return LEGACY.env_or_file(env_key) or default


def _unmixr_voice_discovery_use_cases(group_key: str) -> tuple[str, ...]:
    raw = LEGACY.env_or_file("UNMIXR_PUBLIC_VIDEO_VOICE_DISCOVERY_USE_CASES")
    if raw:
        return tuple(part.strip() for part in re.split(r"[,;]+", raw) if part.strip())
    if group_key == ALICE_CLEAN_AUDIO_GROUP:
        return ("documentary-voices", "narration-voices", "audiobook-voices")
    return ("documentary-voices", "narration-voices", "audiobook-voices")


def _discover_unmixr_voice_by_label(group_key: str, label: str) -> dict[str, Any]:
    normalized_label = label.strip().lower()
    if not normalized_label:
        return {}
    cache_key = (group_key, normalized_label)
    if cache_key in _UNMIXR_DISCOVERY_CACHE:
        return dict(_UNMIXR_DISCOVERY_CACHE[cache_key])
    api_key = LEGACY.env_or_file("UNMIXR_API_KEY")
    if not api_key:
        return {}
    for use_case in _unmixr_voice_discovery_use_cases(group_key):
        query = urllib.parse.urlencode(
            {
                "c": use_case,
                "page_size": 80,
                "fields": VOICE_DISCOVERY_FIELDS,
            }
        )
        request = urllib.request.Request(
            f"{UNMIXR_VOICE_DISCOVERY_API}?{query}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        try:
            payload = json.loads(urllib.request.urlopen(request, timeout=20).read().decode("utf-8"))
        except Exception:
            continue
        rows = payload.get("results") if isinstance(payload, dict) else payload
        if isinstance(rows, dict):
            rows = rows.get("results") or rows.get("voices") or []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            character = str(row.get("character") or row.get("name") or row.get("label") or "").strip()
            if character.lower() != normalized_label:
                continue
            voice_id = str(row.get("uuid") or "").strip()
            if not voice_id:
                continue
            result = {
                "voice_id": voice_id,
                "voice_source_env": f"discovery:unmixr:{use_case}:{character}",
                "voice_label": character,
                "voice_gender": str(row.get("gender") or ""),
                "voice_quality": str(row.get("quality") or ""),
                "voice_language": str(row.get("language") or ""),
                "voice_use_cases": row.get("use_cases") if isinstance(row.get("use_cases"), list) else [],
            }
            _UNMIXR_DISCOVERY_CACHE[cache_key] = dict(result)
            return result
    return {}


def resolve_voice_id(group_key: str) -> tuple[str, str]:
    resolved = resolve_voice(group_key)
    return str(resolved.get("voice_id") or ""), str(resolved.get("voice_source_env") or "")


def resolve_voice(group_key: str) -> dict[str, Any]:
    for key in VOICE_ENV_BY_GROUP.get(group_key, DEFAULT_VOICE_ENV_KEYS):
        value = LEGACY.env_or_file(key)
        if value:
            return {
                "voice_id": value,
                "voice_source_env": key,
                "voice_label": "",
                "voice_gender": "female" if key in {"UNMIXR_ALICE_VOICE_ID", "UNMIXR_FEMALE_NARRATOR_VOICE_ID"} else "",
                "voice_quality": "premium" if "PREMIUM" in key or key in {"UNMIXR_ALICE_VOICE_ID", "UNMIXR_FEMALE_NARRATOR_VOICE_ID"} else "",
                "voice_language": "",
                "voice_use_cases": [],
            }
    discovered = _discover_unmixr_voice_by_label(group_key, _preferred_unmixr_voice_label(group_key))
    if discovered:
        return discovered
    return {}


@contextmanager
def unmixr_voice_override(group_key: str):
    resolved = resolve_voice(group_key)
    voice_id = str(resolved.get("voice_id") or "")
    source_env = str(resolved.get("voice_source_env") or "")
    old_values = {key: os.environ.get(key) for key in DEFAULT_VOICE_ENV_KEYS}
    try:
        if voice_id:
            os.environ["UNMIXR_PREMIUM_NARRATOR_VOICE_ID"] = voice_id
        yield resolved
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


SCRIPT_KEY_BY_GROUP = {
    "nexus-pan-90s-deepdive": "nexus_pan_90s_deepdive",
    "nexus-pan-epic-90s": "nexus-pan_epic_90s",
    ALICE_CLEAN_AUDIO_GROUP: "alice-90s-deepdive",
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
        text = humanize_public_narration(legacy_script)
        if key == ALICE_CLEAN_AUDIO_GROUP:
            return text, "legacy_longform_script_humanized_alice_full_length_clean_audio"
        return text, "legacy_longform_script_humanized"
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
        f"afade=t=in:st=0:d=0.025,highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},"
        "acompressor=threshold=-24dB:ratio=2.0:attack=12:release=180:makeup=2.6,"
        "loudnorm=I=-17:LRA=8:TP=-2.0,alimiter=limit=0.90",
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
    meta_file = work / "unmixr-narration.meta.json"
    resolved = resolve_voice(group_key)
    voice_id = str(resolved.get("voice_id") or "")
    source_env = str(resolved.get("voice_source_env") or "")
    voice_policy = _unmixr_voice_policy_for_group(group_key)
    if not voice_id:
        raise RuntimeError(f"unmixr_premium_voice_required:{group_key}")
    script_sha = _sha256_bytes(text.encode("utf-8"))
    voice_sha = _voice_id_sha256(voice_id)
    cached_meta: dict[str, Any] = {}
    if meta_file.is_file():
        try:
            cached_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached_meta = {}
    cache_matches = (
        stitched.is_file()
        and stitched.stat().st_size > 0
        and str(cached_meta.get("script_sha256") or "") == script_sha
        and str(cached_meta.get("voice_id_sha256") or "") == voice_sha
        and str(cached_meta.get("voice_policy") or "") == voice_policy
    )
    if cache_matches and not force_tts:
        return stitched, {
            "provider": UNMIXR_PROVIDER,
            "voice_id_redacted": redact(voice_id),
            "voice_source_env": source_env,
            "voice_policy": voice_policy,
            "voice_label": str(resolved.get("voice_label") or cached_meta.get("voice_label") or ""),
            "voice_gender": str(resolved.get("voice_gender") or cached_meta.get("voice_gender") or ""),
            "voice_quality": str(resolved.get("voice_quality") or cached_meta.get("voice_quality") or ""),
            "voice_language": str(resolved.get("voice_language") or cached_meta.get("voice_language") or ""),
            "voice_reused_from_cache": True,
            "language": str(cached_meta.get("language") or ""),
            "speaking_rate": str(cached_meta.get("speaking_rate") or ""),
            "speaking_pitch": str(cached_meta.get("speaking_pitch") or ""),
            "speaking_volume": str(cached_meta.get("speaking_volume") or ""),
            "beat_count": len(beats),
            "failures": [],
        }

    parts: list[Path] = []
    failures: list[str] = []
    with unmixr_voice_override(group_key) as resolved:
        voice_id = str(resolved.get("voice_id") or "")
        source_env = str(resolved.get("voice_source_env") or "")
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
    meta = {
        "script_sha256": script_sha,
        "voice_id_sha256": voice_sha,
        "voice_source_env": source_env,
        "voice_policy": voice_policy,
        "voice_label": str(resolved.get("voice_label") or ""),
        "voice_gender": str(resolved.get("voice_gender") or ""),
        "voice_quality": str(resolved.get("voice_quality") or ""),
        "voice_language": str(resolved.get("voice_language") or ""),
        "language": config.get("language", ""),
        "speaking_rate": config.get("speaking_rate", ""),
        "speaking_pitch": config.get("speaking_pitch", ""),
        "speaking_volume": config.get("speaking_volume", ""),
        "beat_count": len(beats),
    }
    meta_file.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return stitched, {
        "provider": UNMIXR_PROVIDER,
        "voice_id_redacted": redact(voice_id or config.get("voice_id", "")),
        "voice_source_env": source_env,
        "voice_policy": voice_policy,
        "voice_label": meta["voice_label"],
        "voice_gender": meta["voice_gender"],
        "voice_quality": meta["voice_quality"],
        "voice_language": meta["voice_language"],
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
        volume = 0.70
        lowpass = 3100
        bass_gain = -7.0
        amplitude = 0.090
    else:
        volume = 0.62
        lowpass = 3000
        bass_gain = -8.0
        amplitude = 0.080
    return (
        f"anoisesrc=color=pink:amplitude={amplitude:.3f}:r={TARGET_SR}:d={total_duration:.3f},"
        f"highpass=f=320,{LOW_TONE_CLEANUP_FILTER},lowpass=f={lowpass},"
        f"bass=g={bass_gain}:f=115:w=0.8,treble=g=-3:f=3200:w=0.8,"
        "acompressor=threshold=-31dB:ratio=1.25:attack=24:release=220:makeup=1.0,"
        f"afade=t=in:st=0:d={min(1.2, max(total_duration / 4.0, 0.2)):.3f},"
        f"volume={volume}[bed]"
    )


def build_clean_audiobook_style_audio(narration: Path, total_duration: float, output: Path) -> str:
    trimmed = output.with_name(f"{output.stem}.alice-clean-source.wav")
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(narration),
        "-af",
        "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-50dB,"
        "areverse,silenceremove=start_periods=1:start_duration=0.08:start_threshold=-50dB,areverse",
        "-ar",
        str(TARGET_SR),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(trimmed),
    )
    source = trimmed if trimmed.is_file() and trimmed.stat().st_size > 0 else narration
    source_duration = duration(source)
    target_voice = max(total_duration, 1.0)
    tempo = min(max(source_duration / target_voice, 0.60), 1.16)
    if abs(tempo - 1.0) > 0.015:
        voice_prep = f"atempo={tempo:.5f},atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = f"alice_clean_audiobook_style_{tempo:.3f}"
    else:
        voice_prep = f"atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = "alice_clean_audiobook_style_natural"
    filter_complex = (
        f"[0:a]{voice_prep},"
        f"highpass=f=145,equalizer=f=94:width_type=h:width=60:g=-24,{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},"
        f"{AUDIOBOOK_STYLE_NORMALIZATION_FILTER},"
        "highpass=f=145,equalizer=f=94:width_type=h:width=60:g=-18,"
        f"volume=0.78,alimiter=limit=0.68:level=false,apad,atrim=0:{total_duration:.3f}[a]"
    )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        filter_complex,
        "-map",
        "[a]",
        "-ar",
        str(TARGET_SR),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output),
    )
    return fit


def build_mixed_audio_for_group(group_key: str, narration: Path | None, total_duration: float, output: Path) -> str:
    if narration is None:
        filter_complex = f"{bed_filter(total_duration, 'ambient')};[bed]highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},loudnorm=I=-22:LRA=8:TP=-2.5,alimiter=limit=0.83,apad,atrim=0:{total_duration:.3f}[a]"
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

    if group_key == ALICE_CLEAN_AUDIO_GROUP:
        return build_clean_audiobook_style_audio(narration, total_duration, output)

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
        f"highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},acompressor=threshold=-23dB:ratio=2.1:attack=12:release=190:makeup=2.7,"
        f"loudnorm=I=-17:LRA=8:TP=-2.0,alimiter=limit=0.88[vo0];"
        f"[vo0]adelay={NARRATION_START_DELAY_MS}|{NARRATION_START_DELAY_MS},apad,atrim=0:{total_duration:.3f},volume=1.10[vo];"
        f"{bed_filter(total_duration, 'narration')};"
        f"[bed][vo]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,highpass=f={LOW_RUMBLE_HIGHPASS_HZ},{LOW_TONE_CLEANUP_FILTER},{HIGH_TONE_CLEANUP_FILTER},"
        "acompressor=threshold=-21dB:ratio=1.7:attack=12:release=180:makeup=1.1,loudnorm=I=-16:LRA=7:TP=-3.0,alimiter=limit=0.78[main];"
        f"anoisesrc=color=white:amplitude=0.180:r={TARGET_SR}:d={total_duration:.3f},"
        "highpass=f=620,lowpass=f=2400,volume=0.65[floor];"
        f"[main][floor]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,volume=0.72,alimiter=limit=0.76,apad,atrim=0:{total_duration:.3f}[a]"
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


def build_mixed_audio(narration: Path | None, total_duration: float, output: Path) -> str:
    return build_mixed_audio_for_group("", narration, total_duration, output)


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


def audio_quality(path: Path, *, allow_clean_speech_pauses: bool = False) -> dict[str, Any]:
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
    mid_tone_mask = (freqs >= 300) & (freqs <= 1200)
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
    if np.any(mid_tone_mask):
        mid_tone_values = mean_spec[mid_tone_mask]
        mid_tone_freqs = freqs[mid_tone_mask]
        mid_max_index = int(np.argmax(mid_tone_values))
        mid_tone_peak_hz = float(mid_tone_freqs[mid_max_index])
        mid_tone_peak = float(mid_tone_values[mid_max_index])
        mid_tone_median = float(np.median(mid_tone_values)) or 1e-18
        mid_tone_prominence_db = 10.0 * math.log10(max(mid_tone_peak / mid_tone_median, 1e-18))
        mid_tone_ratio = float(np.sum(mid_tone_values)) / all_power
    else:
        mid_tone_peak_hz = 0.0
        mid_tone_prominence_db = 0.0
        mid_tone_ratio = 0.0
    frame_samples = max(int(TARGET_SR * 0.25), 1)
    frame_count = max(math.ceil(samples.size / frame_samples), 1)
    padded = np.pad(samples, (0, frame_count * frame_samples - samples.size))
    rms_frames = np.sqrt(np.mean(padded.reshape(frame_count, frame_samples) ** 2, axis=1))
    silent = rms_frames < (10 ** (SILENCE_GATE_DBFS / 20.0))
    max_silent_frames = 0
    current_silent_frames = 0
    for value in silent:
        if bool(value):
            current_silent_frames += 1
            max_silent_frames = max(max_silent_frames, current_silent_frames)
        else:
            current_silent_frames = 0
    non_silent_indexes = np.where(~silent)[0]
    if non_silent_indexes.size:
        first_audible_seconds = float(non_silent_indexes[0] * frame_samples / TARGET_SR)
        last_audible_end_seconds = float(min((non_silent_indexes[-1] + 1) * frame_samples / TARGET_SR, samples.size / TARGET_SR))
    else:
        first_audible_seconds = samples.size / TARGET_SR
        last_audible_end_seconds = 0.0
    total_seconds = samples.size / TARGET_SR
    max_silence_seconds = max_silent_frames * frame_samples / TARGET_SR
    tail_silence_seconds = max(0.0, total_seconds - last_audible_end_seconds)
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
    if 390 <= mid_tone_peak_hz <= 720 and mid_tone_prominence_db > 18.0 and mid_tone_ratio > 0.030:
        status = "fail"
        reasons.append("mid_frequency_beep_artifact")
    if max_silence_seconds > MAX_SILENCE_SECONDS and not allow_clean_speech_pauses:
        status = "fail"
        reasons.append("audio_coverage_gap")
    if first_audible_seconds > MAX_EDGE_SILENCE_SECONDS:
        status = "fail"
        reasons.append("audio_starts_late")
    if tail_silence_seconds > MAX_EDGE_SILENCE_SECONDS:
        status = "fail"
        reasons.append("audio_ends_early")
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
        "mid_tone_peak_hz": round(mid_tone_peak_hz, 1),
        "mid_tone_peak_prominence_db": round(mid_tone_prominence_db, 2),
        "mid_tone_power_ratio": round(mid_tone_ratio, 6),
        "silence_gate_dbfs": SILENCE_GATE_DBFS,
        "max_silence_seconds": round(max_silence_seconds, 3),
        "first_audible_seconds": round(first_audible_seconds, 3),
        "tail_silence_seconds": round(tail_silence_seconds, 3),
    }


def rebuild_group(group: VideoGroup, *, force_tts: bool = False) -> dict[str, Any]:
    work = OUT_ROOT / group.key
    work.mkdir(parents=True, exist_ok=True)
    provider_meta: dict[str, Any] = {"provider": "first_party_audio_bed", "voice_id_redacted": ""}
    narration_path: Path | None = None
    if group.narration:
        if not LEGACY.unmixr_config():
            raise RuntimeError("unmixr_tts_required_for_public_video_audio")
        narration_path, provider_meta = render_unmixr_narration(group.key, group.narration, work, force_tts=force_tts)
    file_receipts: list[dict[str, Any]] = []
    for video in group.files:
        total_duration = duration(video)
        mixed = work / f"{video.stem}.mixed.wav"
        fit_mode = build_mixed_audio_for_group(group.key, narration_path, total_duration, mixed)
        backup = work / f"{video.name}.before-unmixr-audio"
        shutil.copy2(video, backup)
        remux(video, mixed, video, total_duration)
        alice_clean_audio = group.key == ALICE_CLEAN_AUDIO_GROUP
        quality = audio_quality(video, allow_clean_speech_pauses=alice_clean_audio)
        info = probe(video)
        streams = info.get("streams") or []
        file_receipts.append(
            {
                "file": str(video.relative_to(REPO)),
                "duration_seconds": round(total_duration, 3),
                "backup": str(backup),
                "fit_mode": fit_mode,
                "audio_style": ALICE_CLEAN_AUDIO_STYLE if alice_clean_audio else "premium_news_anchor_continuous_bed",
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
    if group.key == ALICE_CLEAN_AUDIO_GROUP and str(provider_meta.get("provider") or "") != UNMIXR_PROVIDER:
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
    parser = argparse.ArgumentParser(description="Regenerate public Chummer video audio with premium narration and hard audio QA.")
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
                        "quality": audio_quality(
                            video,
                            allow_clean_speech_pauses=group.key == ALICE_CLEAN_AUDIO_GROUP,
                        ),
                    }
                )
            receipts.append({"group_key": group.key, "mode": group.mode, "files": files})
    else:
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
        "hard_exit_gate": {
            "applies_to": "all public video files selected by this script; horizon manifest MP4s are the publication-critical subset",
            "duration_seconds_min": 89.5,
            "duration_seconds_max": 90.5,
            "audio_streams_required": 1,
            "video_streams_required": 1,
            "max_silence_seconds_at_gate_dbfs": MAX_SILENCE_SECONDS,
            "max_start_silence_seconds": MAX_EDGE_SILENCE_SECONDS,
            "max_tail_silence_seconds": MAX_EDGE_SILENCE_SECONDS,
            "silence_gate_dbfs": SILENCE_GATE_DBFS,
            "alice_voice_policy": ALICE_VOICE_POLICY,
            "premium_mix_required": "news-anchor narration with continuous harmonic broadcast bed except Alice, which uses clean audiobook-style speech-only narration; noise-bed-only output is rejected by review policy",
        },
        "provider_posture": {
            "narration_provider": "unmixr-short-tts",
            "unmixr_required": True,
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
                "alice_voice_env_order": list(VOICE_ENV_BY_GROUP[ALICE_CLEAN_AUDIO_GROUP]),
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
