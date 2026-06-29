import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIO_SCRIPT = REPO_ROOT / "scripts" / "public_video_audio_quality.py"
GATE_SCRIPT = REPO_ROOT / "scripts" / "verify_horizon_video_audio_exit_gate.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_video_audio_quality_module_is_active() -> None:
    audio = _load(AUDIO_SCRIPT, "public_video_audio_quality_for_test")

    quality = audio.audio_quality(Path("/does/not/exist/asset.mp4"))

    assert audio.UNMIXR_PROVIDER == "unmixr-short-tts"
    assert "table-pulse-90s-deepdive" in audio.CLEAN_SPEECH_AUDIO_GROUPS
    assert quality["status"] == "fail"
    assert quality["reasons"] == ["audio_file_missing:/does/not/exist/asset.mp4"]
    assert audio.retirement_receipt().get("pipeline") == "public_video_audio_quality"


def test_gate_requires_alice_unmixr_voice_receipt(monkeypatch, tmp_path: Path) -> None:
    gate = _load(GATE_SCRIPT, "verify_horizon_video_audio_exit_gate_for_test")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "public_mp4": "/media/horizons/alice-90s-deepdive.mp4",
                        "title": "ALICE 90-second deep dive",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fake_file = tmp_path / "alice-90s-deepdive.mp4"
    fake_file.write_bytes(b"not-a-real-video")

    class FakeAudio:
        SILENCE_GATE_DBFS = -42.0
        MAX_SILENCE_SECONDS = 0.70
        MAX_EDGE_SILENCE_SECONDS = 0.30
        ALICE_VOICE_POLICY = "unmixr_premium_female_required_no_edge_fallback"
        ALICE_VOICE_GENDER = "female"
        ALICE_VOICE_QUALITY = "premium"
        ALICE_CLEAN_AUDIO_STYLE = "clean_audiobook_style_no_bed_no_noise_floor"

        @staticmethod
        def probe(path):
            return {"format": {"duration": "90.0"}, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}

        @staticmethod
        def audio_quality(path):
            return {"status": "pass", "reasons": [], "max_silence_seconds": 0.0, "tail_silence_seconds": 0.0}

    monkeypatch.setattr(gate, "load_audio_module", lambda: FakeAudio)
    monkeypatch.setattr(gate, "public_path_to_file", lambda public_path: fake_file)
    monkeypatch.setattr(gate, "rebuild_group_receipts", lambda: {})

    result = gate.verify_manifest(manifest)

    assert result["status"] == "fail"
    assert "/media/horizons/alice-90s-deepdive.mp4:alice_voice_policy_requires_unmixr_receipt" in result["issues"]
    assert "/media/horizons/alice-90s-deepdive.mp4:alice_voice_policy_requires_premium_female_no_edge_receipt" in result["issues"]
    assert "/media/horizons/alice-90s-deepdive.mp4:alice_voice_policy_requires_female_receipt" in result["issues"]
    assert "/media/horizons/alice-90s-deepdive.mp4:alice_voice_policy_requires_premium_receipt" in result["issues"]


def test_gate_requires_table_pulse_clean_speech_unmixr_receipt(monkeypatch, tmp_path: Path) -> None:
    gate = _load(GATE_SCRIPT, "verify_horizon_video_audio_exit_gate_table_pulse_for_test")
    clean_speech_pause_calls: list[bool] = []
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "public_mp4": "/media/horizons/table-pulse-90s-deepdive.mp4",
                        "title": "TABLE PULSE 90-second deep dive",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fake_file = tmp_path / "table-pulse-90s-deepdive.mp4"
    fake_file.write_bytes(b"not-a-real-video")

    class FakeAudio:
        SILENCE_GATE_DBFS = -42.0
        MAX_SILENCE_SECONDS = 1.0
        MAX_EDGE_SILENCE_SECONDS = 0.30
        UNMIXR_PROVIDER = "unmixr-short-tts"
        CLEAN_SPEECH_AUDIO_GROUPS = {"table-pulse-90s-deepdive"}

        @staticmethod
        def probe(path):
            return {"format": {"duration": "90.0"}, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}

        @staticmethod
        def audio_quality(path, allow_clean_speech_pauses=False):
            clean_speech_pause_calls.append(bool(allow_clean_speech_pauses))
            return {"status": "pass", "reasons": [], "max_silence_seconds": 0.0, "tail_silence_seconds": 0.0}

    monkeypatch.setattr(gate, "load_audio_module", lambda: FakeAudio)
    monkeypatch.setattr(gate, "public_path_to_file", lambda public_path: fake_file)
    monkeypatch.setattr(gate, "rebuild_group_receipts", lambda: {})

    result = gate.verify_manifest(manifest)

    assert result["status"] == "fail"
    assert (
        "/media/horizons/table-pulse-90s-deepdive.mp4:clean_speech_unmixr_rebuild_receipt_missing"
        in result["issues"]
    )
    assert clean_speech_pause_calls == [True]


def test_clean_speech_style_accepts_explicit_no_bed_no_noise_policy() -> None:
    gate = _load(GATE_SCRIPT, "verify_horizon_video_audio_exit_gate_style_for_test")

    assert gate.clean_speech_style_is_current("clean_premium_narration_no_bed_no_noise_floor")
    assert gate.clean_speech_style_is_current("clean_audiobook_style_no_bed_no_noise_floor")
    assert gate.clean_speech_style_is_current("clean_premium_table_pulse_narration_no_bed_no_noise_floor")
    assert not gate.clean_speech_style_is_current("premium_news_anchor_continuous_bed")
