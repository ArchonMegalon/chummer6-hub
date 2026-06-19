from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/rebuild_public_video_audio_unmixr.py")
SPEC = importlib.util.spec_from_file_location("rebuild_public_video_audio_unmixr", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PublicVideoAudioUnmixrTests(unittest.TestCase):
    def render_tone(self, frequency: int, output: Path) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:duration=1:sample_rate={MODULE.TARGET_SR}",
                "-af",
                "volume=0.2",
                str(output),
            ],
            check=True,
        )

    def test_low_tone_brum_is_a_hard_audio_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brum.wav"
            self.render_tone(188, path)

            quality = MODULE.audio_quality(path)

        self.assertEqual(quality["status"], "fail")
        self.assertIn("low_frequency_tonal_artifact", quality["reasons"])

    def test_clean_voice_band_tone_is_not_misclassified_as_brum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice-band.wav"
            self.render_tone(1000, path)

            quality = MODULE.audio_quality(path)

        self.assertEqual(quality["status"], "pass")
        self.assertNotIn("low_frequency_tonal_artifact", quality["reasons"])

    def test_alice_prefers_dedicated_female_voice_env_before_default_voice(self) -> None:
        original = MODULE.LEGACY.env_or_file

        def fake_env_or_file(key: str) -> str:
            values = {
                "UNMIXR_ALICE_VOICE_ID": "alice-female",
                "UNMIXR_FEMALE_NARRATOR_VOICE_ID": "generic-female",
                "UNMIXR_PREMIUM_NARRATOR_VOICE_ID": "default-premium",
                "UNMIXR_VOICE_ID": "default",
            }
            return values.get(key, "")

        try:
            MODULE.LEGACY.env_or_file = fake_env_or_file
            voice_id, source_env = MODULE.resolve_voice_id("alice-90s-deepdive")
        finally:
            MODULE.LEGACY.env_or_file = original

        self.assertEqual(voice_id, "alice-female")
        self.assertEqual(source_env, "UNMIXR_ALICE_VOICE_ID")


if __name__ == "__main__":
    unittest.main()
