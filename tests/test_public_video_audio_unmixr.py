from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rebuild_public_video_audio_unmixr.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rebuild_public_video_audio_unmixr", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_video_audio_rebuild_pipeline_is_retired_fail_closed() -> None:
    module = _load_module()

    assert module.PIPELINE_RETIRED is True
    assert module.UNMIXR_PROVIDER == "retired"
    assert module.audio_quality(Path("missing.mp4"))["status"] == "fail"


def test_public_video_audio_rebuild_cli_exits_nonzero_with_retirement_receipt() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT_PATH)], check=False, capture_output=True, text=True)

    assert result.returncode == 2
    assert '"status": "retired"' in result.stdout
    assert "retired_faulty_public_video_audio_pipeline" in result.stdout
