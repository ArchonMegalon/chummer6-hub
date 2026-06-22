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
UNMIXR_PROVIDER = "unmixr"
UNMIXR_SHORT_TTS_PROVIDER = f"{UNMIXR_PROVIDER}-short-tts"
PROFILE_FIELDS = (
    ("VOICE_ID", "voice_id"),
    ("LANGUAGE", "language"),
    ("RATE", "speaking_rate"),
    ("PITCH", "speaking_pitch"),
    ("VOLUME", "speaking_volume"),
    ("ACCOUNT", "account"),
)
_ACCOUNT_PREFIX = "UNMIXR_ACCOUNT"
_ACCOUNT_API_KEY_SUFFIX = "API_KEY"
_ACCOUNT_VOICE_ID_SUFFIX = "VOICE_ID"
_ACCOUNT_CREDITS_SUFFIXES = ("CREDITS", "CREDITS_REMAINING", "CREDITS_LEFT")


_ACCOUNT_API_KEY_RE = re.compile(rf"^{re.escape(_ACCOUNT_PREFIX)}_([A-Za-z0-9_]+)_{re.escape(_ACCOUNT_API_KEY_SUFFIX)}$")


class UnmixrTtsError(RuntimeError):
    pass


def env_or_file(key: str, *, env_files: Iterable[Path] = DEFAULT_ENV_FILES) -> str:
    return _load_env_snapshot(env_files).get(key, "")


def _load_env_snapshot(env_files: Iterable[Path]) -> dict[str, str]:
    values: dict[str, str] = {}
    for env_file in env_files:
        if not env_file.is_file():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            left, right = line.split("=", 1)
            value = right.strip().strip("'").strip('"')
            left_key = left.strip()
            if value and left_key not in values:
                values[left_key] = value
    for key, value in os.environ.items():
        parsed = value.strip()
        if parsed:
            values[key] = parsed
    return values


def _select_account(
    accounts: list[dict[str, str]],
    env: Mapping[str, str],
    preferred_account: str | None = None,
) -> dict[str, str]:
    if preferred_account:
        normalized = preferred_account.strip().lower()
        for account in accounts:
            if account["name"].lower() == normalized:
                return account
    def credits_for(account: dict[str, str]) -> float:
        for suffix in _ACCOUNT_CREDITS_SUFFIXES:
            value = env.get(f"{_ACCOUNT_PREFIX}_{account['name'].upper()}_{suffix}", "").strip()
            if value:
                try:
                    return float(value)
                except ValueError:
                    pass
        for suffix in _ACCOUNT_CREDITS_SUFFIXES:
            value = env.get(f"{_ACCOUNT_PREFIX}_{account['name']}_{suffix}", "").strip()
            if value:
                try:
                    return float(value)
                except ValueError:
                    pass
        return -1.0
    scored = [(account, credits_for(account)) for account in accounts]
    with_credits = sorted(scored, key=lambda item: item[1], reverse=True)
    return with_credits[0][0]


def _discover_accounts(env: Mapping[str, str]) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    legacy_api_key = env.get("UNMIXR_API_KEY", "").strip()
    legacy_voice_id = env.get("UNMIXR_VOICE_ID", "").strip()
    if legacy_api_key and legacy_voice_id:
        accounts.append(
            {
                "name": "legacy",
                "api_key": legacy_api_key,
                "voice_id": legacy_voice_id,
            }
        )
    for key in env:
        match = _ACCOUNT_API_KEY_RE.match(key)
        if not match:
            continue
        account_name = match.group(1)
        api_key = env.get(key, "").strip()
        voice_id = env.get(f"{_ACCOUNT_PREFIX}_{account_name}_{_ACCOUNT_VOICE_ID_SUFFIX}", "").strip()
        if api_key and voice_id:
            accounts.append(
                {
                    "name": account_name.lower(),
                    "api_key": api_key,
                    "voice_id": voice_id,
                }
            )
    # Deduplicate repeated account keys and prefer the most recently declared name mapping.
    deduped: dict[str, dict[str, str]] = {}
    for account in accounts:
        deduped[account["name"]] = account
    # Deterministic ordering for account rotation and reproducible tests.
    return [deduped[name] for name in sorted(deduped.keys())]


def _profile_value(prefixes: Iterable[str], field: str, *, env: Mapping[str, str]) -> str:
    for prefix in prefixes:
        value = env.get(f"{prefix}_{field}", "")
        if value:
            return value
    return ""


def _resolve_account(profile_overrides: Mapping[str, str], *, env_files: Iterable[Path] = DEFAULT_ENV_FILES) -> dict[str, str]:
    env = _load_env_snapshot(env_files)
    preferred = (
        profile_overrides.get("account")
        or os.environ.get("UNMIXR_PREFERRED_ACCOUNT", "").strip()
        or env.get("UNMIXR_PREFERRED_ACCOUNT", "").strip()
        or env.get("UNMIXR_ACCOUNT", "").strip()
    )
    accounts = _discover_accounts(env)
    if not accounts:
        raise UnmixrTtsError("unmixr_tts_not_configured")
    selected = _select_account(accounts, env=env, preferred_account=preferred or None)
    return {
        "account": selected["name"],
        "api_key": selected["api_key"],
        "voice_id": selected["voice_id"],
        "language": env.get("UNMIXR_LANGUAGE", "en-US"),
        "speaking_rate": env.get("UNMIXR_SPEAKING_RATE", "medium"),
        "speaking_pitch": env.get("UNMIXR_SPEAKING_PITCH", "low"),
        "speaking_volume": env.get("UNMIXR_SPEAKING_VOLUME", "medium"),
    }


def load_config(
    *,
    env_files: Iterable[Path] = DEFAULT_ENV_FILES,
    profile_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    return _resolve_account(profile_overrides or {}, env_files=env_files)


def load_profile(
    *,
    prefixes: Iterable[str] = (),
    env_files: Iterable[Path] = DEFAULT_ENV_FILES,
    defaults: Mapping[str, str] | None = None,
) -> dict[str, str]:
    profile = {}
    env = _load_env_snapshot(env_files)
    normalized_prefixes = [prefix.strip().upper() for prefix in prefixes if prefix.strip()]
    profile_overrides: dict[str, str] = {}
    for env_field, profile_field in PROFILE_FIELDS:
        override = _profile_value(normalized_prefixes, env_field, env=env)
        if override:
            profile_overrides[profile_field] = override
    profile = dict(_resolve_account(profile_overrides, env_files=env_files))
    default_values = dict(defaults or {})
    for env_field, profile_field in PROFILE_FIELDS:
        if profile_field in profile_overrides:
            profile[profile_field] = profile_overrides[profile_field]
        elif profile_field in default_values and default_values[profile_field]:
            profile[profile_field] = str(default_values[profile_field])
    return profile


def slug_prefix(*parts: str) -> str:
    joined = "_".join(part.strip() for part in parts if part and part.strip())
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", joined).strip("_").upper()
    return normalized


def provider_token(profile: Mapping[str, str], *, style: str = "standard", tempo: float | None = None) -> str:
    base = UNMIXR_SHORT_TTS_PROVIDER
    style_name = style.lower().strip()
    if style_name == "standard":
        return base
    if style_name == "continuous":
        return f"{base}-continuous"
    if style_name == "scene":
        return base
    if style_name == "voice":
        return f"{base}/{profile['voice_id']}"
    if style_name == "atempo":
        if tempo is None:
            raise ValueError("tempo is required when style='atempo'")
        return f"{base}-{profile['voice_id']}-atempo-{tempo:.3f}"
    raise ValueError(f"unknown unmixr tts provider style: {style}")


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
