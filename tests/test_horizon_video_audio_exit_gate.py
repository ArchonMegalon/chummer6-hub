import importlib.util
import json
import math
import struct
import sys
import wave
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIO_SCRIPT = REPO_ROOT / "scripts" / "rebuild_public_video_audio_unmixr.py"
GATE_SCRIPT = REPO_ROOT / "scripts" / "verify_horizon_video_audio_exit_gate.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_wav(path: Path, seconds: float, *, silent_tail_seconds: float = 0.0) -> None:
    sample_rate = 48000
    frames = int(seconds * sample_rate)
    silent_tail_frames = int(silent_tail_seconds * sample_rate)
    audible_frames = max(frames - silent_tail_frames, 0)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        payload = bytearray()
        for index in range(audible_frames):
            seconds = index / sample_rate
            sample = 0.12 * math.sin(2 * math.pi * 1000 * seconds)
            envelope = 0.80 + 0.20 * math.sin(2 * math.pi * 3.0 * seconds) ** 2
            value = int(sample * envelope * 32767)
            payload.extend(struct.pack("<h", value))
        payload.extend(b"\x00\x00" * silent_tail_frames)
        wav.writeframes(bytes(payload))


def test_audio_quality_accepts_planned_silent_tail_for_video_fade(tmp_path: Path) -> None:
    audio = _load(AUDIO_SCRIPT, "rebuild_public_video_audio_unmixr_for_test")
    path = tmp_path / "tail.wav"
    _write_wav(path, 3.0, silent_tail_seconds=audio.NARRATION_END_BEFORE_VIDEO_SECONDS)

    quality = audio.audio_quality(path)

    assert quality["status"] == "pass"
    assert audio.MIN_TAIL_SILENCE_SECONDS <= quality["tail_silence_seconds"] <= audio.MAX_TAIL_SILENCE_SECONDS


def test_audio_quality_fails_excessive_silent_tail(tmp_path: Path) -> None:
    audio = _load(AUDIO_SCRIPT, "rebuild_public_video_audio_unmixr_long_tail_for_test")
    path = tmp_path / "tail.wav"
    _write_wav(path, 4.0, silent_tail_seconds=audio.MAX_TAIL_SILENCE_SECONDS + 0.6)

    quality = audio.audio_quality(path)

    assert quality["status"] == "fail"
    assert "audio_ends_too_early" in quality["reasons"]


def test_first_party_bed_covers_full_duration(tmp_path: Path) -> None:
    audio = _load(AUDIO_SCRIPT, "rebuild_public_video_audio_unmixr_bed_for_test")
    path = tmp_path / "bed.wav"

    mode = audio.build_mixed_audio(None, 3.0, path)
    quality = audio.audio_quality(path)

    assert mode == "ambient_bed_only"
    assert quality["status"] == "pass"
    assert audio.MIN_TAIL_SILENCE_SECONDS <= quality["tail_silence_seconds"] <= audio.MAX_TAIL_SILENCE_SECONDS


def test_narration_mix_covers_internal_pauses(tmp_path: Path) -> None:
    audio = _load(AUDIO_SCRIPT, "rebuild_public_video_audio_unmixr_narration_for_test")
    narration = tmp_path / "narration.wav"
    output = tmp_path / "mixed.wav"
    _write_wav(narration, audio.active_audio_duration(3.0))

    audio.build_mixed_audio(narration, 3.0, output)
    quality = audio.audio_quality(output)

    assert quality["status"] == "pass"
    assert quality["max_internal_silence_seconds"] <= audio.MAX_SILENCE_SECONDS
    assert audio.MIN_TAIL_SILENCE_SECONDS <= quality["tail_silence_seconds"] <= audio.MAX_TAIL_SILENCE_SECONDS


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


def test_clean_speech_style_accepts_explicit_no_bed_no_noise_policy() -> None:
    gate = _load(GATE_SCRIPT, "verify_horizon_video_audio_exit_gate_style_for_test")

    assert gate.clean_speech_style_is_current("clean_premium_narration_no_bed_no_noise_floor")
    assert gate.clean_speech_style_is_current("clean_audiobook_style_no_bed_no_noise_floor")
    assert gate.clean_speech_style_is_current("clean_premium_table_pulse_narration_no_bed_no_noise_floor")
    assert not gate.clean_speech_style_is_current("premium_news_anchor_continuous_bed")
