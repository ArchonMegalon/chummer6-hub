from __future__ import annotations

import importlib.util
import json
import sys
import wave
from pathlib import Path

import numpy as np


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "public_video_audio_quality.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("public_video_audio_quality_for_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_video_audio_quality_rejects_missing_file() -> None:
    module = _load_module()

    quality = module.audio_quality(Path("/does/not/exist/asset.mp4"))

    assert quality["status"] == "fail"
    assert quality["reasons"] == ["audio_file_missing:/does/not/exist/asset.mp4"]


def test_public_video_audio_quality_cli_prints_quality_receipt() -> None:
    completed = __import__("subprocess").run(  # avoid importing subprocess at module scope to keep test lightweight
        ["python3", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(completed.stdout.strip())

    assert completed.returncode == 0
    assert payload["pipeline"] == "public_video_audio_quality"
    assert payload["status"] == "published"


def test_public_video_audio_quality_detects_narrowband_beep(tmp_path: Path) -> None:
    module = _load_module()
    sample_rate = 16_000
    duration_seconds = 2.0
    timeline = np.linspace(0.0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    samples = (0.35 * np.sin(2 * np.pi * 6200.0 * timeline)).astype(np.float32)
    pcm = np.clip(samples * 32767, -32768, 32767).astype("<i2")
    media_path = tmp_path / "beep.wav"

    with wave.open(str(media_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())

    metrics = module._audio_tone_metrics(media_path)

    assert metrics["status"] == "fail"
    assert 6190.0 <= metrics["dominant_highband_peak_hz"] <= 6210.0
