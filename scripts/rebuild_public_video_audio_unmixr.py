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
import urllib.error
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
PUBLISHED_REBUILD_RECEIPT = REPO / ".codex-studio" / "published" / "PUBLIC_VIDEO_AUDIO_REBUILD.generated.json"
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
MIN_CLEAN_TTS_COVERAGE_RATIO = 0.84
MAX_LOW_TONE_RESONANCE_DB = 20.0
MIN_LOW_TONE_RESONANCE_RATIO = 0.001
MAX_VOICE_TO_LOW_FOR_RESONANCE_DB = 32.0
ALICE_CLEAN_AUDIO_GROUP = "alice-90s-deepdive"
RUNSITE_CLEAN_AUDIO_GROUP = "runsite-90s-deepdive"
RUNBOOK_PRESS_CLEAN_AUDIO_GROUP = "runbook-press-90s-deepdive"
CLEAN_SPEECH_AUDIO_GROUPS = {
    ALICE_CLEAN_AUDIO_GROUP,
    RUNSITE_CLEAN_AUDIO_GROUP,
    RUNBOOK_PRESS_CLEAN_AUDIO_GROUP,
}
AUDIOBOOK_STYLE_NORMALIZATION_FILTER = "dynaudnorm=f=150:g=15,loudnorm=I=-16:TP=-1.5:LRA=11"
AUDIO_NORMALIZATION_CONTRACT = "ea.public_video_unmixr_beat_trim.v2"
CLEAN_SPEECH_MIX_CONTRACT = "ea.public_video_clean_speech_no_noise_floor.v2"
ALICE_CLEAN_AUDIO_STYLE = "clean_audiobook_style_no_bed_no_noise_floor"
RUNSITE_CLEAN_AUDIO_STYLE = "clean_premium_narration_no_bed_no_noise_floor"
RUNBOOK_PRESS_CLEAN_AUDIO_STYLE = "clean_premium_narration_no_bed_no_noise_floor"
DEFAULT_CLEAN_AUDIO_STYLE = "clean_premium_narration_no_bed_no_noise_floor"
UNMIXR_VOICE_DISCOVERY_API = "https://unmixr.com/api/v1/voice-list/"
DEFAULT_PREMIUM_VOICE_LABEL = "Blue"
ALICE_PREMIUM_FEMALE_VOICE_LABEL = "Ava"
UNMIXR_VOICE_POLICY = "unmixr_premium_required_no_edge_fallback"
ALICE_VOICE_POLICY = "unmixr_premium_female_required_no_edge_fallback"
VOICE_DISCOVERY_FIELDS = "uuid,character,gender,language,quality,use_cases,is_available"
UNMIXR_API_KEY_ENV_KEYS = (
    "UNMIXR_API_KEY",
    "UNMIXR_API_KEY_FALLBACK_1",
    "UNMIXR_API_KEY_FALLBACK_2",
)
UNMIXR_API_KEYS_BULK_ENV = "UNMIXR_API_KEYS"
UNMIXR_API_KEY_DYNAMIC_PREFIX = "UNMIXR_API_KEY_"

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


def _unquote_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def _is_unmixr_api_key_name(key: str) -> bool:
    if key.endswith("_FILE"):
        return False
    return key == "UNMIXR_API_KEY" or key.startswith(UNMIXR_API_KEY_DYNAMIC_PREFIX)


def _split_bulk_unmixr_api_keys(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\s]+", value) if part.strip()]


def _unmixr_secret_env_files() -> tuple[Path, ...]:
    files = [
        *(Path(path) for path in getattr(LEGACY, "ENV_FILES", ())),
        REPO / ".env.local",
        Path("/docker/EA/.env.local"),
        Path("/docker/EA/ea/.env.local"),
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for file in files:
        key = str(file)
        if key in seen:
            continue
        seen.add(key)
        unique.append(file)
    return tuple(unique)


def _env_file_unmixr_api_key_assignments() -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []
    for env_file in _unmixr_secret_env_files():
        if not env_file.is_file():
            continue
        for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            value = _unquote_env_value(raw_value)
            if key == UNMIXR_API_KEYS_BULK_ENV:
                for index, api_key in enumerate(_split_bulk_unmixr_api_keys(value), start=1):
                    assignments.append((f"{UNMIXR_API_KEYS_BULK_ENV}[{index}]", api_key))
                continue
            if _is_unmixr_api_key_name(key):
                assignments.append((key, value))
    return assignments


def _unmixr_api_keys(preferred_env: str = "") -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    seen_values: set[str] = set()
    seen_labels: dict[str, int] = {}

    def add_candidate(label: str, value: str) -> None:
        value = _unquote_env_value(value)
        if not value or value in seen_values:
            return
        seen_values.add(value)
        seen_labels[label] = seen_labels.get(label, 0) + 1
        display_label = label if seen_labels[label] == 1 else f"{label}#{seen_labels[label]}"
        keys.append((display_label, value))

    for env_key in UNMIXR_API_KEY_ENV_KEYS:
        add_candidate(env_key, LEGACY.env_or_file(env_key))

    for index, api_key in enumerate(_split_bulk_unmixr_api_keys(LEGACY.env_or_file(UNMIXR_API_KEYS_BULK_ENV)), start=1):
        add_candidate(f"{UNMIXR_API_KEYS_BULK_ENV}[{index}]", api_key)

    for env_key in sorted(os.environ):
        if env_key == UNMIXR_API_KEYS_BULK_ENV:
            for index, api_key in enumerate(_split_bulk_unmixr_api_keys(os.environ.get(env_key, "")), start=1):
                add_candidate(f"{UNMIXR_API_KEYS_BULK_ENV}[{index}]", api_key)
            continue
        if _is_unmixr_api_key_name(env_key):
            add_candidate(env_key, os.environ.get(env_key, ""))

    for label, value in _env_file_unmixr_api_key_assignments():
        add_candidate(label, value)

    if preferred_env:
        keys.sort(key=lambda item: 0 if item[0] == preferred_env else 1)
    return keys


def _unmixr_tts_config(voice_id: str, api_key_env: str = "") -> dict[str, str]:
    return {
        "api_key_env": api_key_env,
        "voice_id": voice_id,
        "language": LEGACY.env_or_file("UNMIXR_LANGUAGE") or "en-US",
        "speaking_rate": LEGACY.env_or_file("UNMIXR_PROMO_SPEAKING_RATE") or LEGACY.env_or_file("UNMIXR_SPEAKING_RATE") or "medium",
        "speaking_pitch": LEGACY.env_or_file("UNMIXR_SPEAKING_PITCH") or "medium",
        "speaking_volume": LEGACY.env_or_file("UNMIXR_SPEAKING_VOLUME") or "medium",
    }


def _unmixr_failure_summary(status: int | None, body: bytes | str) -> str:
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body or "")
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        code = str(payload.get("code") or status or "").strip()
        message = str(payload.get("message") or payload.get("detail") or payload.get("error") or "").strip()
        if "balance" in message.lower():
            return f"provider_{code or 'error'}_insufficient_api_balance"
        if code or message:
            reason = re.sub(r"[^A-Za-z0-9_.:-]+", "_", message).strip("_").lower()[:80] or "request_failed"
            return f"provider_{code or 'error'}_{reason}"
    if status is not None:
        return f"http_{status}"
    return "request_failed"


def render_unmixr_tts_with_fallback_keys(
    text: str,
    voice_id: str,
    output: Path,
    *,
    preferred_key_env: str = "",
) -> tuple[bool, dict[str, str], list[str]]:
    errors: list[str] = []
    output.unlink(missing_ok=True)
    api_keys = _unmixr_api_keys(preferred_key_env)
    if not api_keys:
        return False, _unmixr_tts_config(voice_id), ["unmixr_api_key_missing"]
    for api_key_env, api_key in api_keys:
        config = _unmixr_tts_config(voice_id, api_key_env)
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
            LEGACY.UNMIXR_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response_body = response.read()
            body = json.loads(response_body.decode("utf-8"))
            if isinstance(body, dict) and body.get("success") is False:
                errors.append(f"{api_key_env}:{_unmixr_failure_summary(None, response_body)}")
                continue
            audio_url = str(body.get("audio_url") or "").strip() if isinstance(body, dict) else ""
            if not audio_url:
                errors.append(f"{api_key_env}:audio_url_missing")
                continue
            with urllib.request.urlopen(audio_url, timeout=120) as audio_response:
                output.write_bytes(audio_response.read())
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read()
            except OSError:
                error_body = b""
            errors.append(f"{api_key_env}:{_unmixr_failure_summary(exc.code, error_body)}")
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            errors.append(f"{api_key_env}:{type(exc).__name__}")
            continue
        if output.exists() and output.stat().st_size > 0:
            return True, config, errors
        errors.append(f"{api_key_env}:empty_audio")
    return False, _unmixr_tts_config(voice_id), errors


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
    api_keys = _unmixr_api_keys()
    if not api_keys:
        return {}
    for use_case in _unmixr_voice_discovery_use_cases(group_key):
        query = urllib.parse.urlencode(
            {
                "c": use_case,
                "page_size": 80,
                "fields": VOICE_DISCOVERY_FIELDS,
            }
        )
        for _, api_key in api_keys:
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
    "nexus-pan-90s-deepdive": "nexus-pan-90s-deepdive",
    "nexus-pan-epic-90s": "nexus-pan-epic-90s",
    ALICE_CLEAN_AUDIO_GROUP: "alice-90s-deepdive",
    "karma-forge-90s-deepdive": "karma-forge-90s-deepdive",
    "jackpoint-90s-deepdive": "jackpoint-90s-deepdive",
    "runsite-90s-deepdive": "runsite-90s-deepdive",
    "runbook-press-90s-deepdive": "runbook-press-90s-deepdive",
    "table-pulse-90s-deepdive": "table-pulse-90s-deepdive",
    "black-ledger-90s-deepdive": "black-ledger-90s-deepdive",
    "black-ledger-epic-90s": "black-ledger-epic-90s",
    "community-hub-90s-deepdive": "community-hub-90s-deepdive",
}


EXTRA_SCRIPT_BY_GROUP = {
    "chummer6-flagship-promo": (
        "The old way always sounds the same: tabs open, notes scattered, a runner sheet half remembered, and a GM buying time while the table waits for the moment to come back alive. "
        "Chummer6 is built for the instant when preparation has to become play. It gathers the runner, the crew, the scene, the consequence, and the next decision into one surface that can survive pressure. "
        "You build with the important details in view: gear, chrome, magic, tradeoffs, and every number explained clearly enough that the table can trust it. "
        "You run with momentum: scenes, handouts, opposition, downtime, hooks, fallout, and the next hard choice ready when the room needs them. "
        "When the city answers, it does not answer as decoration. It answers with heat, factions, jobs, rumors, and consequences the GM can turn into tomorrow night's trouble. "
        "House rules stop living as arguments in old chat logs. Recaps stop dissolving into rumor. The aftermath becomes signal, and that signal becomes the next run. "
        "From desktop to tablet to phone, from home table to remote night, Chummer6 is for crews who want the world to remember what they did and still be ready when the next door opens. "
        "The promise is practical: less ceremony, fewer missing details, more time spent in the scene, and a campaign that can keep moving after the dice stop."
    ),
    "all-horizons-90s-magicfit-promo": (
        "Chummer6 should not feel like a shelf of future brands. It should feel like one product spine. Start with the workbench: build the runner, inspect the numbers, understand the sources, and keep the dense rhythm veteran users expect. "
        "ALICE is part of that base product: build help, rules explanation, tradeoff warnings, and a clearer path from a cool idea to a runner who can survive the table. "
        "Origin Dossier belongs beside it, turning the life behind the stats into contacts, debts, enemies, scars, secrets, and approved campaign memory the GM can actually use. "
        "Ready for Tonight, Runner Passport, Knowledge Fabric, Table Pulse, and GM Cockpit are product areas, not a pile of disconnected Horizons. They help the table return, explain, run, and remember. "
        "The future shelf should be saved for bigger bets: Karma Forge, Black Ledger, publishing, community, and specialized play modes. NEXUS-PAN is continuity and recovery, so it belongs in the product story. "
        "Runsite makes mission spaces readable. Runbook Press turns approved campaign material into books people can keep. Jackpoint gives aftermath and handoffs a dramatic home. "
        "That is the cleaner promise: build clearly, run reliably, remember consequences, publish only what the table approves, and keep the whole product legible enough that a new user knows where to start."
    ),
    "every-wonder-horizon-promo": (
        "Chummer6 should not ask players to memorize a shelf of labels before they know why the product matters. It starts with one table: runners, rules, scenes, people, and consequences in reach. "
        "Some areas are base product workbenches. ALICE helps with builds and tradeoffs. Origin Dossier turns the life behind the stats into contacts, enemies, debts, scars, and secrets. Table Pulse keeps campaign pressure bounded and playable. "
        "Runsite makes a location feel like a problem, not just a map. Runbook Press turns approved campaign material into primers, packets, and season books. Jackpoint makes aftermath easier to return to when the next session begins. "
        "Some ideas are expansion bets, and they should be named honestly. NEXUS-PAN is device continuity. KARMA FORGE is table-approved house-rule change. BLACK LEDGER is the living city: heat, factions, jobs, news, and fallout that remembers the crew. "
        "Other areas are clearer when they are called what they are: campaign memory, mission-space prep, publishing, community, and specialized play modes. "
        "The cleaner promise is simple: build clearly, run reliably, remember consequences, and publish only what the table approves. The product gets easier to understand because the names serve the work instead of competing with it."
    ),
    "nexus-pan-90s-deepdive": (
        "A session rarely breaks because the story failed. It breaks because reality intruded first. A tablet sleeps, a laptop wakes crooked, a player reconnects into a scene already moving, and suddenly the table is arguing about which version is current. "
        "NEXUS-PAN exists for that dangerous little gap between what the campaign knows and what the people at the table can trust. Presence has to be clear. Change has to be visible. Recovery has to feel calm enough that nobody mistakes panic for drama. "
        "A reconnect should not become a rules argument. A conflict should surface before it hardens into table folklore. Desktop, tablet, phone, remote night, train ride, home table, same campaign, same moment, no scavenger hunt for the current version. "
        "For the GM, the promise is practical: can I trust what I am seeing right now, and can I recover the room without stopping the fiction. For the player, it is even simpler: rejoin, catch up, answer the scene, and stay in the run. "
        "The system should make repair feel ordinary. Show what arrived, what changed, what is waiting for approval, and what can be ignored until after the scene. "
        "NEXUS-PAN is continuity with a pulse, built for crews who refuse to lose the night because one device blinked first."
    ),
    "nexus-pan-epic-90s": (
        "Every long campaign eventually becomes a split screen. One player is half a city away. One sheet is stale. The GM has too many windows open and no patience left for false confidence. "
        "The epic version of NEXUS-PAN begins there, with trust as the first dramatic question. Who is connected. What changed. Which state is current enough to act on without breaking the scene. "
        "Packets move. Devices disagree. The table does not need more drama from the software. It needs signal, context, and a clear next step before momentum dies. "
        "When conflict appears, the system should expose it cleanly and let the GM make the call before the fiction tears. The campaign should travel with the crew from desk to tablet to train to home table without export rituals, copied files, or wishful thinking. "
        "A returning player should receive the humane version of continuity: where you were, what changed, what danger is live, and what move is waiting. That is the fantasy here. Less ceremony, less panic, more run, and a campaign state that still feels trustworthy when the network does not."
        "The larger promise is not synchronization for its own sake. It is confidence under interruption, so the people can return to the scene instead of negotiating with their tools."
    ),
    "karma-forge-90s-deepdive": (
        "Every table invents house rules. Very few tables remember exactly when they did it, who agreed, what broke, or why everyone still argues about it three sessions later. "
        "Karma Forge treats a rule change as something powerful enough to deserve ceremony. Name it. Scope it. Preview it. Show the blast radius before anyone mistakes enthusiasm for safety. "
        "A good change should arrive with clear notes: who it touches, what it shifts, where it could bend the campaign, and how to reverse it if the table hates what it becomes. Players should react in context, not excavate old chat logs looking for permission. "
        "Campaigns evolve. Their rule environment can evolve with them. But that evolution should feel table-approved, legible, reversible, and connected to the campaign that asked for it. "
        "The GM remains the final authority. The software can show risk, collect reaction, preserve history, and make the next version easier to understand. It should not smuggle private preference into public rules. "
        "A proposed change should carry context: the problem it solves, the characters it touches, the sessions it may affect, and the fallback if the table changes its mind. "
        "Karma Forge is for tables that want custom play without surrendering coherence: a place where house rules can become understandable, testable, and safe enough to try."
    ),
    "jackpoint-90s-deepdive": (
        "The run is over, but the story is not. The table is laughing, exhausted, and already telling three different versions of what happened. That is where campaigns start losing themselves. "
        "Jackpoint gives the aftermath a place with shape: recaps, briefings, dossiers, loose ends, NPC promises, what the players may know, and what the GM must keep behind the curtain. "
        "Those details need different doors. A player-facing briefing should feel like the world speaking back, not like a database export with the serial numbers still attached. A missed player should return to a clean handoff, not a twenty-minute oral history full of contradictions and fading excitement. "
        "As the season grows longer, memory needs structure. Who owes the crew. Which rumor became dangerous. Which contact changed sides. Which choice is still waiting to collect interest. "
        "The best briefing is short enough to read, rich enough to act on, and careful enough not to leak what should stay behind the screen. It gives a returning player confidence without forcing the table to replay the whole night. "
        "The table still owns the story. Jackpoint simply gives that story a sharper, more dramatic way to return when next session begins. It turns aftermath into usable memory without stealing the voice of the campaign."
    ),
    "table-pulse-90s-deepdive": (
        "Pressure is part of the drama, but pressure without boundaries becomes noise. Table Pulse exists to keep the room tense, alive, and readable without turning the session into a dashboard performance. "
        "The GM sees the signal first. The system offers pressure, reaction, and aftermath as packets, not commandments. The table can be nudged when a scene needs oxygen and left alone when silence is the better choice. "
        "Players who are not physically in the room can still matter when they join an opposing faction. If they opt in, they can receive a bounded notification, send a reaction, and push back from outside the table without hijacking the moment inside it. "
        "After the run, they can receive a focused summary of what happened, who won, and what fallout now belongs to their side. Consent, quiet hours, opt-outs, and table policy are not decoration around the system. They are the system. "
        "The point is restraint. A pulse should help the GM notice pressure, help remote participants matter in bounded ways, and then get out of the way before the room starts serving the meter instead of the scene. "
        "A good pulse is felt in the scene, in the aftermath, and in the rising tension of the campaign, while the software itself almost disappears."
    ),
    "black-ledger-90s-deepdive": (
        "Too many campaign cities forget everything by morning. Black Ledger is for the kind of city that keeps score, not on a spreadsheet, but in bruised districts, nervous factions, shifting jobs, and people who suddenly have reason to care what the crew just broke. "
        "After the run, the world should move. Not as homework. As consequence. Heat changes hands. Favors sour. Rumors harden into opportunity. A quiet neighborhood becomes dangerous because the crew made noise there yesterday. "
        "Faction pressure works best when it creates decisions, not encyclopedia weight. The newsroom gives the city a voice: dramatic, biased, occasionally cruel, and just useful enough to become tomorrow night's hook. "
        "The GM should see what changed and why. Players should feel the city react without receiving private notes they were never meant to know. Public projection stays careful, approval-gated, and useful. "
        "A good city surface does not ask the table to study lore before play. It shows pressure, opportunity, rumor, and consequence in a form the GM can turn into a decision. "
        "By the time the next session begins, the world should already have opinions. Black Ledger is for campaigns where the map remembers, the city pushes back, and the fallout is always looking for a new owner."
    ),
    "black-ledger-epic-90s": (
        "Black Ledger begins with a dead-map problem. The crew leaves a crater in the world, and somehow the city wakes up unchanged. That is not consequence. That is amnesia. "
        "In the epic version, the city comes alive like another character at the table. World ticks turn fallout into motion. A quiet district gets hot. A trusted route turns risky. A favor becomes leverage. A mistake becomes the seed of the next mission. "
        "The mission market starts to feel earned because opportunity no longer drops from the sky. It grows from what the crew actually did. Faction pressure becomes playable tension instead of lore the players are expected to memorize. "
        "The newsroom gives the whole machine a voice: rumor, spin, fear, mockery, propaganda, and the kind of half-story runners know how to weaponize. "
        "The GM keeps authority. Public surfaces stay bounded. The city moves because the table approved what happened, and because consequences should have a memory. "
        "The epic promise is a campaign city that grows pressure between sessions without turning the GM into a clerk. The surface should show what is rising, what is cooling, what is now dangerous, and what might become tomorrow night's job. "
        "It should feel like the city took notes while the crew was busy surviving. "
        "Black Ledger is for campaigns where the map remembers the damage and develops an attitude about it."
    ),
    "community-hub-90s-deepdive": (
        "Finding the right table should not feel harder than surviving the run. Community Hub begins with the lonely player, the overworked GM, and the gap between wanting a game and actually getting one to happen without chaos. "
        "Open runs need more than a signup button. They need tone, schedule, safety, expectations, and a reason this particular runner belongs in this particular trouble. Runner preflight should catch problems before anyone is trapped in voice chat waiting for a decision that could have been made yesterday. "
        "A roster is not a list of names. It is chemistry, role fit, availability, consent, and the stubborn practical question of whether this crew can actually meet and play. Scheduling should remove friction, not create another place for the answer to go missing. "
        "For a GM, the hub should reduce coordination drag. For a player, it should make the next honest step obvious. For the table, it should protect expectations before the first scene begins. "
        "The system should respect attention: fewer status pings, clearer commitments, and a clean handoff from interest to attendance to aftermath. "
        "It should also make absence visible early, so the table can adapt before the night is already slipping away. "
        "The best outcome remains beautifully simple: the right people find the right run, the night actually happens, and the campaign remembers what came out the other side."
    ),
    "origin-dossier-the-name-she-chose": (
        "Some stories begin with a handle because the old name no longer fits the person walking into the shadows. The Name She Chose is an Origin Dossier proof of tone: a character history shaped into playable memory, not a generic biography pasted behind the sheet. "
        "The past arrives as pressure. A contact with a reason to call. A debt that was never fully paid. A boundary the runner refuses to cross again. A name that sounds simple until the table learns what it cost. "
        "This is what campaign memory should feel like when it is handled carefully: approved by the player, useful to the GM, dramatic without stealing authorship. "
        "The dossier can turn biography into hooks, images, scene packets, and narration, but it does not silently change the build. Ware, money, qualities, magic, legality, and rules remain in the sheet where the table can inspect them. "
        "When the GM needs a thread, the origin can answer with emotional weight. When the player needs a reason, the past can speak without becoming a lecture. "
        "A strong dossier gives the table handles without turning the runner into a fixed script. It invites play, complication, and choice. "
        "It also gives media a standard: evocative enough to matter, bounded enough to reject, and clear enough that the player remains the author of the person at the center. "
        "The sheet says what she can do. The dossier helps the table understand why she chose to become this person now."
    ),
    "origin-dossier-the-name-she-chose-20260619": (
        "Some stories begin with a handle because the old name no longer fits the person walking into the shadows. The Name She Chose is an Origin Dossier proof of tone: a character history shaped into playable memory, not a generic biography pasted behind the sheet. "
        "The past arrives as pressure. A contact with a reason to call. A debt that was never fully paid. A boundary the runner refuses to cross again. A name that sounds simple until the table learns what it cost. "
        "This is what campaign memory should feel like when it is handled carefully: approved by the player, useful to the GM, dramatic without stealing authorship. "
        "The dossier can turn biography into hooks, images, scene packets, and narration, but it does not silently change the build. Ware, money, qualities, magic, legality, and rules remain in the sheet where the table can inspect them. "
        "When the GM needs a thread, the origin can answer with emotional weight. When the player needs a reason, the past can speak without becoming a lecture. "
        "A strong dossier gives the table handles without turning the runner into a fixed script. It invites play, complication, and choice. "
        "It also gives media a standard: evocative enough to matter, bounded enough to reject, and clear enough that the player remains the author of the person at the center. "
        "The sheet says what she can do. The dossier helps the table understand why she chose to become this person now."
    ),
    RUNBOOK_PRESS_CLEAN_AUDIO_GROUP: (
        "Runbook Press begins with a familiar mess: maps in one folder, session notes in another, "
        "NPC motives in chat, rulings in memory, and a campaign that deserves more than another scattered handoff. "
        "The point is not to make a generic book. The point is to turn approved source material into a useful artifact. "
        "A player primer that welcomes someone new. A district guide that makes a place easy to run. "
        "A mission packet that carries the right details without exposing the wrong ones. A season book that lets the table keep what it built. "
        "Runbook Press keeps the split clear. Player-safe pages stay readable. GM-only material stays behind the curtain. "
        "Credits, changes, source notes, and approval state remain attached, so a polished page does not become a loose claim. "
        "The workflow should feel like a small editorial room inside Chummer: draft, arrange, review, format, export, and revise without losing provenance. "
        "Layout matters because people use books under pressure. They need the map, the faction note, the timeline, or the handout fast enough that the table keeps moving. "
        "A good runbook also knows when to stay quiet. It does not expose spoilers just because the source exists. It does not flatten a living campaign into a brochure. "
        "It turns approved material into pages with hierarchy, context, and enough editorial judgment that a reader can find the next useful thing without digging through the whole archive. "
        "Runbook Press is campaign publishing with memory, structure, and restraint."
    ),
    RUNSITE_CLEAN_AUDIO_GROUP: (
        "Runsite begins with a simple truth: a location is not ready just because a map exists. "
        "A flat floor plan can tell the table where the walls are, but it cannot tell the crew where the pressure lives. "
        "Runsite turns a mission space into something the players can read before the first door opens: approach routes, exposure, exits, camera lines, chokepoints, and the places where a quiet plan starts becoming loud. "
        "The player view stays clean enough to act on. The GM view keeps the teeth behind the curtain. "
        "A warehouse stops being a rectangle and becomes a layered problem: outside light, security habits, blind corners, maintenance paths, alarms that matter, and consequences waiting just off-screen. "
        "The point is not to script the route. The point is to make the site strong enough for improvisation. "
        "If the crew scouts, the space rewards attention. If they rush, the space pushes back. If they split up, the table still understands what each choice costs. "
        "Runsite gives the GM a place that can breathe under pressure and gives the players a location worth planning around. "
        "Before the breach, during the run, and after the fallout, the site remains legible, dangerous, and memorable."
    ),
    "origin-dossier-90s-deepdive": (
        "Origin Dossier starts where the character sheet stops. It takes the events that shaped a runner and turns them into things the table can actually use: contacts, enemies, debts, scars, secrets, beliefs, and unfinished consequences. "
        "The player keeps control. The GM keeps the campaign steer. Nothing becomes part of the game until both sides approve it. "
        "A clinic favor can become pressure. A family name can become a lead. A mistake can become a secret. A scar can become a code the runner lives by. "
        "The dossier can also feed portraits, scene packets, narration, video, and audiobook versions later, but the mechanics stay in Chummer. Prose never silently changes ware, money, qualities, magic, legality, or build math. "
        "When ALICE reads approved origin material later, it reads character context, not hidden rules. Weak media can be rejected without damaging the runner. Strong material gives the crew a person to bring into the next job. "
        "The best version feels intimate without becoming invasive. It gives the GM handles, gives the player choices, and keeps approval visible so nobody confuses generated drama with accepted canon. "
        "The result should feel like a campaign artifact, not a profile card: concise, dramatic, useful, and still open enough for the player to surprise everyone at the table. "
        "Not a backstory pasted on top. A life with consequences, ready for the next scene."
    ),
    "black-ledger-3dvista-flythrough": (
        "Black Ledger is the city with a memory. District pressure, faction motion, open jobs, and newsreel fallout give the GM a place to start when the table asks what changed after the last run. "
        "The flythrough is not decoration. It is a fast way to feel the board: where heat is rising, where opportunity is gathering, and where the crew may have left trouble behind."
    ),
    "black-ledger-video-globe-idle": (
        "The city is still moving. Black Ledger keeps district pressure, faction heat, and visible fallout close enough for the next decision."
    ),
    "ashline-circle-promo": (
        "Ashline Circle sells calm power with dangerous consequences. The public face is wellness, source clarity, and controlled magic heat. "
        "Behind the polish, the table still needs proof: who changed the risk, where the pressure rose, and why the next ritual matters."
    ),
    "barrens-free-wardens-promo": (
        "Barrens Free Wardens begin where polished systems usually stop. They care about closeout witnesses, recovery saves, and safehouse routes that still work in the rain. "
        "Less nuyen, more backbone: when the street breaks, they make sure someone gets home."
    ),
    "ghostline-network-promo": (
        "Ghostline Network is for crews that survive by checking the signal before trusting the rumor. Intel confidence, redaction, and dispatch discipline matter here. "
        "The promise is simple: verify what can be verified, hide what must stay dark, and move before noise becomes a trap."
    ),
    "glass-tower-compact-promo": (
        "Glass Tower Compact turns public trust into a weapon with clean edges. License polish, compliance pressure, and calm paperwork all carry consequences. "
        "The surface is corporate order; the useful part is knowing exactly when that order becomes leverage against someone else."
    ),
    "neon-docks-union-promo": (
        "Neon Docks Union keeps the city moving when cargo, drones, and escape windows all collide. Route control is not decoration here. "
        "It is the difference between a clean handoff, a blocked exit, and a crew learning too late that the dock had already changed sides."
    ),
    "rust-market-syndicate-promo": (
        "Rust Market Syndicate makes every favor visible enough to become dangerous. Debt heat, favor load, and black-market opportunity all share the same table. "
        "Everything is available. Nothing is free. The trick is seeing the cost before the deal starts collecting interest."
    ),
    "turn-1-newsreel": (
        "Emerald Sprawl opens with pressure in Rust Bazaar. Debt heat is visible, Ashline crews are already watching, and the board is no longer abstract. "
        "The city remembers who moved first, which district failed to recover, and where tomorrow's trouble is likely to start."
    ),
    "turn-2-newsreel": (
        "Emerald Sprawl is answering back. Recovery crews pushed Rust Bazaar into the public frame, Ghostline is sorting rumor from dispatch, and faction confidence is moving. "
        "The board closes with one warning: hesitation is now visible, and the next turn will not wait politely."
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
    if key in EXTRA_SCRIPT_BY_GROUP:
        return humanize_public_narration(EXTRA_SCRIPT_BY_GROUP[key]), "authored_repair_script"
    script_key = SCRIPT_KEY_BY_GROUP.get(key, key)
    legacy_script = getattr(LEGACY, "SCRIPTS", {}).get(script_key)
    if legacy_script:
        text = humanize_public_narration(legacy_script)
        if key == ALICE_CLEAN_AUDIO_GROUP:
            return text, "legacy_longform_script_humanized_alice_full_length_clean_audio"
        return text, "legacy_longform_script_humanized"
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
        "silenceremove=start_periods=1:start_duration=0.025:start_threshold=-50dB,"
        "areverse,silenceremove=start_periods=1:start_duration=0.055:start_threshold=-50dB,areverse,"
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
        and str(cached_meta.get("audio_normalization_contract") or "") == AUDIO_NORMALIZATION_CONTRACT
    )
    cached_unmixr_exists = stitched.is_file() and stitched.stat().st_size > 0

    def cached_unmixr_provider_meta(reason: str) -> dict[str, Any]:
        return {
            "provider": UNMIXR_PROVIDER,
            "voice_id_redacted": redact(voice_id),
            "voice_source_env": source_env or str(cached_meta.get("voice_source_env") or ""),
            "voice_policy": voice_policy,
            "voice_label": str(resolved.get("voice_label") or cached_meta.get("voice_label") or ""),
            "voice_gender": str(resolved.get("voice_gender") or cached_meta.get("voice_gender") or ""),
            "voice_quality": str(resolved.get("voice_quality") or cached_meta.get("voice_quality") or ""),
            "voice_language": str(resolved.get("voice_language") or cached_meta.get("voice_language") or ""),
            "voice_reused_from_cache": True,
            "cache_reuse_reason": reason,
            "api_key_env": str(cached_meta.get("api_key_env") or ""),
            "language": str(cached_meta.get("language") or ""),
            "speaking_rate": str(cached_meta.get("speaking_rate") or ""),
            "speaking_pitch": str(cached_meta.get("speaking_pitch") or ""),
            "speaking_volume": str(cached_meta.get("speaking_volume") or ""),
            "beat_count": len(beats),
            "failures": [],
        }

    if cache_matches and not force_tts:
        return stitched, cached_unmixr_provider_meta("current_contract_cache_match")

    if cached_unmixr_exists and not cached_meta:
        stitched.unlink(missing_ok=True)

    parts: list[Path] = []
    failures: list[str] = []
    tts_config: dict[str, str] = {}
    preferred_key_env = ""
    with unmixr_voice_override(group_key) as resolved:
        voice_id = str(resolved.get("voice_id") or "")
        source_env = str(resolved.get("voice_source_env") or "")
        for index, beat in enumerate(beats, start=1):
            raw = beat_dir / f"beat-{index:02d}.mp3"
            ok, beat_config, beat_errors = render_unmixr_tts_with_fallback_keys(
                beat,
                voice_id,
                raw,
                preferred_key_env=preferred_key_env,
            )
            if not ok:
                failure = f"beat-{index:02d}:{';'.join(beat_errors)}"
                failures.append(failure)
                raise RuntimeError(f"Unmixr TTS failed for {work.name} beat {index}: {failure}")
            tts_config = beat_config
            preferred_key_env = beat_config.get("api_key_env", preferred_key_env)
            normalized = beat_dir / f"beat-{index:02d}.wav"
            normalize_voice(raw, normalized)
            parts.append(normalized)
            if index < len(beats):
                pause = beat_dir / f"pause-{index:02d}.wav"
                pause_seconds = min(max(0.12 + len(beat.split()) * 0.004, 0.16), 0.34)
                render_pause(pause, pause_seconds)
                parts.append(pause)
    concat_wavs(parts, stitched)
    meta = {
        "script_sha256": script_sha,
        "voice_id_sha256": voice_sha,
        "voice_source_env": source_env,
        "voice_policy": voice_policy,
        "voice_label": str(resolved.get("voice_label") or ""),
        "voice_gender": str(resolved.get("voice_gender") or ""),
        "voice_quality": str(resolved.get("voice_quality") or ""),
        "voice_language": str(resolved.get("voice_language") or ""),
        "api_key_env": tts_config.get("api_key_env", ""),
        "language": tts_config.get("language", ""),
        "speaking_rate": tts_config.get("speaking_rate", ""),
        "speaking_pitch": tts_config.get("speaking_pitch", ""),
        "speaking_volume": tts_config.get("speaking_volume", ""),
        "beat_count": len(beats),
        "audio_normalization_contract": AUDIO_NORMALIZATION_CONTRACT,
    }
    meta_file.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return stitched, {
        "provider": UNMIXR_PROVIDER,
        "voice_id_redacted": redact(voice_id or tts_config.get("voice_id", "")),
        "voice_source_env": source_env,
        "voice_policy": voice_policy,
        "voice_label": meta["voice_label"],
        "voice_gender": meta["voice_gender"],
        "voice_quality": meta["voice_quality"],
        "voice_language": meta["voice_language"],
        "voice_reused_from_cache": False,
        "api_key_env": tts_config.get("api_key_env", ""),
        "language": tts_config.get("language", ""),
        "speaking_rate": tts_config.get("speaking_rate", ""),
        "speaking_pitch": tts_config.get("speaking_pitch", ""),
        "speaking_volume": tts_config.get("speaking_volume", ""),
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


def build_clean_audiobook_style_audio(narration: Path, total_duration: float, output: Path, group_key: str = ALICE_CLEAN_AUDIO_GROUP) -> str:
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
    compacted = output.with_name(f"{output.stem}.clean-compact-source.wav")
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-af",
        "silenceremove=stop_periods=-1:stop_duration=0.42:stop_threshold=-48dB",
        "-ar",
        str(TARGET_SR),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(compacted),
    )
    if compacted.is_file() and compacted.stat().st_size > 0:
        source = compacted
    source_duration = duration(source)
    target_voice = max(total_duration, 1.0)
    if source_duration < target_voice * MIN_CLEAN_TTS_COVERAGE_RATIO:
        raise RuntimeError(
            f"{group_key}_unmixr_narration_too_short_for_natural_pacing:"
            f"{source_duration:.3f}s_for_{target_voice:.3f}s"
        )
    tempo = min(max(source_duration / target_voice, 0.90), 1.16)
    if tempo > 1.005 or tempo < 0.995:
        voice_prep = f"atempo={tempo:.5f},atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = f"clean_speech_style_{tempo:.3f}"
    else:
        voice_prep = f"atrim=0:{target_voice:.3f},asetpts=PTS-STARTPTS"
        fit = "clean_speech_style_natural"
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

    return build_clean_audiobook_style_audio(narration, total_duration, output, group_key)


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
    if (
        70 <= low_tone_peak_hz <= 180
        and low_tone_prominence_db > MAX_LOW_TONE_RESONANCE_DB
        and low_bass_ratio > MIN_LOW_TONE_RESONANCE_RATIO
        and voice_to_low_db < MAX_VOICE_TO_LOW_FOR_RESONANCE_DB
    ):
        status = "fail"
        reasons.append("low_frequency_resonance_artifact")
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
        if not _unmixr_api_keys():
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
        quality = audio_quality(video, allow_clean_speech_pauses=False)
        info = probe(video)
        streams = info.get("streams") or []
        audio_style = DEFAULT_CLEAN_AUDIO_STYLE if group.narration else "clean_first_party_ambient_bed_no_tonal_noise"
        if group.key == ALICE_CLEAN_AUDIO_GROUP:
            audio_style = ALICE_CLEAN_AUDIO_STYLE
        elif group.key == RUNSITE_CLEAN_AUDIO_GROUP:
            audio_style = RUNSITE_CLEAN_AUDIO_STYLE
        elif group.key == RUNBOOK_PRESS_CLEAN_AUDIO_GROUP:
            audio_style = RUNBOOK_PRESS_CLEAN_AUDIO_STYLE
        file_receipts.append(
            {
                "file": str(video.relative_to(REPO)),
                "duration_seconds": round(total_duration, 3),
                "backup": str(backup),
                "fit_mode": fit_mode,
                "audio_style": audio_style,
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
    if group.key in CLEAN_SPEECH_AUDIO_GROUPS and str(provider_meta.get("provider") or "") != UNMIXR_PROVIDER:
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
                        "quality": audio_quality(video, allow_clean_speech_pauses=False),
                    }
                )
            receipts.append({"group_key": group.key, "mode": group.mode, "files": files})
    else:
        receipts = [rebuild_group(group, force_tts=args.force_tts) for group in groups]
        if selected:
            previous_outputs = (
                PUBLISHED_REBUILD_RECEIPT,
                OUT_ROOT / "PUBLIC_VIDEO_AUDIO_REBUILD.generated.json",
            )
            merged: dict[str, dict[str, Any]] = {}
            for previous_output in previous_outputs:
                if not previous_output.is_file():
                    continue
                try:
                    previous = json.loads(previous_output.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    previous = {}
                merged.update(
                    {
                        str(group.get("group_key") or ""): group
                        for group in previous.get("groups", [])
                        if isinstance(group, dict) and str(group.get("group_key") or "")
                    }
                )
            for group in receipts:
                merged[str(group.get("group_key") or "")] = group
            receipts = [merged[key] for key in sorted(merged)]

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
            "max_low_tone_resonance_db": MAX_LOW_TONE_RESONANCE_DB,
            "min_low_tone_resonance_ratio": MIN_LOW_TONE_RESONANCE_RATIO,
            "alice_voice_policy": ALICE_VOICE_POLICY,
            "premium_mix_required": "clean Unmixr narration with no synthetic noise floor; legacy bed/noise mixes are rejected. Every narrated public promo/video group must carry a passing rebuild receipt before release.",
            "clean_speech_mix_contract": CLEAN_SPEECH_MIX_CONTRACT,
            "audio_normalization_contract": AUDIO_NORMALIZATION_CONTRACT,
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
