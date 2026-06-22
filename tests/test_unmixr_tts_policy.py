from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "_unmixr_tts.py"
PROMO_SCRIPT = REPO_ROOT / "scripts" / "rebuild_promo_reels_with_narration.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unmixr_helper_load_profile_reads_prefixed_voice_from_env_file(tmp_path: Path) -> None:
    helper = _load(HELPER_PATH, "unmixr_tts_helper_for_profile_test")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "UNMIXR_API_KEY=key-123",
                "UNMIXR_VOICE_ID=voice-default",
                "UNMIXR_PROMO_REEL_CHUMMER6_FLAGSHIP_PROMO_VOICE_ID=voice-special",
                "UNMIXR_PROMO_REEL_CHUMMER6_FLAGSHIP_PROMO_RATE=slow",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = helper.load_profile(
        prefixes=("UNMIXR_PROMO_REEL_CHUMMER6_FLAGSHIP_PROMO",),
        env_files=(env_file,),
        defaults={"speaking_rate": "medium", "speaking_pitch": "low", "speaking_volume": "medium"},
    )

    assert profile["api_key"] == "key-123"
    assert profile["voice_id"] == "voice-special"
    assert profile["speaking_rate"] == "slow"
    assert profile["speaking_pitch"] == "low"


def test_unmixr_helper_raises_when_not_configured(tmp_path: Path) -> None:
    helper = _load(HELPER_PATH, "unmixr_tts_helper_for_error_test")

    with pytest.raises(helper.UnmixrTtsError, match="unmixr_tts_not_configured"):
        helper.load_config(env_files=(tmp_path / "missing.env",))


def test_unmixr_helper_selects_account_by_credit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    helper = _load(HELPER_PATH, "unmixr_tts_helper_for_account_selection_test")
    monkeypatch.setenv("UNMIXR_PREFERRED_ACCOUNT", "")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "UNMIXR_ACCOUNT_A_API_KEY=a-key",
                "UNMIXR_ACCOUNT_A_VOICE_ID=a-voice",
                "UNMIXR_ACCOUNT_A_CREDITS=12",
                "UNMIXR_ACCOUNT_B_API_KEY=b-key",
                "UNMIXR_ACCOUNT_B_VOICE_ID=b-voice",
                "UNMIXR_ACCOUNT_B_CREDITS=37",
                "UNMIXR_SPEAKING_RATE=medium",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = helper.load_profile(
        env_files=(env_file,),
        prefixes=("UNMIXR_TEST",),
    )

    assert profile["account"] == "b"
    assert profile["voice_id"] == "b-voice"
    assert profile["api_key"] == "b-key"


def test_unmixr_helper_prefers_prefix_account(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    helper = _load(HELPER_PATH, "unmixr_tts_helper_for_profile_account_override_test")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "UNMIXR_ACCOUNT_A_API_KEY=a-key",
                "UNMIXR_ACCOUNT_A_VOICE_ID=a-voice",
                "UNMIXR_ACCOUNT_B_API_KEY=b-key",
                "UNMIXR_ACCOUNT_B_VOICE_ID=b-voice",
                "UNMIXR_TEST_ACCOUNT= a",
                "UNMIXR_TEST_VOICE_ID=forced-voice",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = helper.load_profile(
        prefixes=("UNMIXR_TEST",),
        env_files=(env_file,),
        defaults={"speaking_rate": "medium", "speaking_pitch": "low", "speaking_volume": "medium"},
    )

    assert profile["account"] == "a"
    assert profile["voice_id"] == "forced-voice"


def test_unmixr_provider_token_styles() -> None:
    helper = _load(HELPER_PATH, "unmixr_tts_helper_for_provider_token_test")
    profile = {"voice_id": "v-voice-42"}

    assert helper.provider_token(profile) == "unmixr-short-tts"
    assert helper.provider_token(profile, style="continuous") == "unmixr-short-tts-continuous"
    assert helper.provider_token(profile, style="voice") == "unmixr-short-tts/v-voice-42"
    assert helper.provider_token(profile, style="atempo", tempo=1.234) == "unmixr-short-tts-v-voice-42-atempo-1.234"


def test_flagship_promo_script_has_no_edge_or_flite_tts_fallback() -> None:
    source = PROMO_SCRIPT.read_text(encoding="utf-8")

    assert "edge_tts" not in source
    assert "ffmpeg-flite" not in source
    assert "render_flite_tts" not in source
