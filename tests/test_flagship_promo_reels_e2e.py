from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REBUILD_SCRIPT = REPO_ROOT / "scripts" / "rebuild_promo_reels_with_narration.py"
AUDIO_QUALITY_SCRIPT = REPO_ROOT / "scripts" / "public_video_audio_quality.py"
MEDIA_ROOT = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
PROMO_SOURCE = REPO_ROOT / "_completion" / "magicfit_jama6_promo_12_scenes"


def _load_audio_quality_module():
    spec = importlib.util.spec_from_file_location("public_video_audio_quality_for_test", AUDIO_QUALITY_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rebuild_flagship_promo_is_reproducible_and_passes_audio_quality() -> None:
    if not PROMO_SOURCE.exists():
        pytest.skip("magicfit source for chummer6 flagship promo is missing")
    if not os.environ.get("UNMIXR_API_KEY", "").strip() or not os.environ.get("UNMIXR_VOICE_ID", "").strip():
        pytest.skip("unmixr runtime credentials are required for the promo rebuild e2e")

    completed = subprocess.run(
        [sys.executable, str(REBUILD_SCRIPT), "--only", "chummer6-flagship-promo"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    mp4 = MEDIA_ROOT / "chummer6-flagship-promo.mp4"
    receipt = MEDIA_ROOT / "chummer6-flagship-promo.receipt.json"
    assert mp4.is_file()
    assert receipt.is_file()

    audio = _load_audio_quality_module()
    quality = audio.audio_quality(mp4)
    assert quality["status"] == "pass"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload.get("scene_count") == 12
    assert payload.get("visual_scene_count") == 12
    assert payload.get("magicfit_final_visual_render_claim") is True
    assert str(payload.get("narration_provider") or "").startswith("unmixr-short-tts")
    assert mp4.stat().st_size > 1_000_000
