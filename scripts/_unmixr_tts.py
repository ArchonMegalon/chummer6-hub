from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Mapping


UNMIXR_API_URL = "https://unmixr.com/api/v1/short-tts/"
DEFAULT_ENV_FILES = (
    Path("/docker/EA/.env.local"),
    Path("/docker/EA/.env"),
    Path("/docker/chummercomplete/chummer.run-services/.env"),
)
PROFILE_FIELDS = (
    ("VOICE_ID", "voice_id"),
    ("LANGUAGE", "language"),
    ("RATE", "speaking_rate"),
    ("PITCH", "speaking_pitch"),
    ("VOLUME", "speaking_volume"),
)


class UnmixrTtsError(RuntimeError):
    pass


def env_or_file(key: str, *, env_files: Iterable[Path] = DEFAULT_ENV_FILES) -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    for env_file in env_files:
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


def _profile_value(prefixes: Iterable[str], field: str, *, env_files: Iterable[Path] = DEFAULT_ENV_FILES) -> str:
    for prefix in prefixes:
        value = env_or_file(f"{prefix}_{field}", env_files=env_files)
        if value:
            return value
    return ""


def load_config(*, env_files: Iterable[Path] = DEFAULT_ENV_FILES) -> dict[str, str]:
    api_key = env_or_file("UNMIXR_API_KEY", env_files=env_files)
    voice_id = env_or_file("UNMIXR_VOICE_ID", env_files=env_files)
    if not api_key or not voice_id:
        raise UnmixrTtsError("unmixr_tts_not_configured")
    return {
        "api_key": api_key,
        "voice_id": voice_id,
        "language": env_or_file("UNMIXR_LANGUAGE", env_files=env_files) or "en-US",
        "speaking_rate": env_or_file("UNMIXR_SPEAKING_RATE", env_files=env_files) or "medium",
        "speaking_pitch": env_or_file("UNMIXR_SPEAKING_PITCH", env_files=env_files) or "low",
        "speaking_volume": env_or_file("UNMIXR_SPEAKING_VOLUME", env_files=env_files) or "medium",
    }


def load_profile(
    *,
    prefixes: Iterable[str] = (),
    env_files: Iterable[Path] = DEFAULT_ENV_FILES,
    defaults: Mapping[str, str] | None = None,
) -> dict[str, str]:
    profile = dict(load_config(env_files=env_files))
    default_values = dict(defaults or {})
    normalized_prefixes = [prefix.strip().upper() for prefix in prefixes if prefix.strip()]
    for env_field, profile_field in PROFILE_FIELDS:
        override = _profile_value(normalized_prefixes, env_field, env_files=env_files)
        if override:
            profile[profile_field] = override
        elif profile_field in default_values and default_values[profile_field]:
            profile[profile_field] = str(default_values[profile_field])
    return profile


def slug_prefix(*parts: str) -> str:
    joined = "_".join(part.strip() for part in parts if part and part.strip())
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", joined).strip("_").upper()
    return normalized


def render_short_tts(
    text: str,
    output: Path,
    *,
    env_files: Iterable[Path] = DEFAULT_ENV_FILES,
    profile: Mapping[str, str] | None = None,
) -> dict[str, str]:
    resolved_profile = dict(profile or load_config(env_files=env_files))
    payload = json.dumps(
        {
            "text": text,
            "voice_id": resolved_profile["voice_id"],
            "language": resolved_profile["language"],
            "speaking_rate": resolved_profile["speaking_rate"],
            "speaking_pitch": resolved_profile["speaking_pitch"],
            "speaking_volume": resolved_profile["speaking_volume"],
            "output_type": output.suffix.lstrip(".") or "mp3",
            "response_type": "url",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        UNMIXR_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {resolved_profile['api_key']}",
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
            raise UnmixrTtsError("unmixr_tts_missing_audio_url")
        with urllib.request.urlopen(audio_url, timeout=120) as audio_response:
            output.write_bytes(audio_response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise UnmixrTtsError(f"unmixr_tts_render_failed:{exc}") from exc
    if not output.is_file() or output.stat().st_size <= 0:
        raise UnmixrTtsError("unmixr_tts_empty_output")
    return resolved_profile
