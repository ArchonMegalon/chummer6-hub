import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_public_video_cinematic_audio_lane.py"
TOUR_MANIFEST = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "media" / "ledger" / "tours" / "black-ledger-tour-exports.manifest.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_public_video_cinematic_audio_lane_for_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_canonical_key_strips_mobile_suffix() -> None:
    module = _load_module()

    assert module.canonical_key(Path("glass-tower-compact-promo-mobile.mp4")) == "glass-tower-compact-promo"
    assert module.canonical_key(Path("every-wonder-horizon-promo.webm")) == "every-wonder-horizon-promo"


def test_tour_manifest_declares_ambient_audio_boundary() -> None:
    payload = json.loads(TOUR_MANIFEST.read_text(encoding="utf-8"))
    flythrough = payload["flythrough"]

    assert flythrough["audio"] == "first_party_subtle_ambient_bed_present"
    assert "not Chummer-authored" in flythrough["audioClaimBoundary"]


def test_current_public_media_has_cinematic_audio_lane(tmp_path: Path) -> None:
    output = tmp_path / "PUBLIC_VIDEO_CINEMATIC_NARRATION_LANE.generated.json"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--out", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["video_group_count"] >= 20
    assert not payload["issues"]
    assert all(group["status"] == "pass" for group in payload["video_groups"])
