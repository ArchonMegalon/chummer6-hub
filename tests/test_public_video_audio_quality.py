from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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

