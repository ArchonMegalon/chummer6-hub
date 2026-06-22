from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "rebuild_public_video_audio_unmixr.py"
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

    def test_video_with_short_audio_stream_fails_coverage_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "undercovered.mp4"
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
                    "color=black:size=320x180:duration=3:rate=24",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency=1000:duration=1:sample_rate={MODULE.TARGET_SR}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(path),
                ],
                check=True,
            )

            quality = MODULE.audio_quality(path)

        self.assertEqual(quality["status"], "fail")
        self.assertIn("audio_undercovered", quality["reasons"])
        self.assertLess(quality["audio_duration_seconds"], quality["media_duration_seconds"])

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

    def test_default_output_root_is_generic_not_date_stamped(self) -> None:
        self.assertEqual(MODULE.OUT_ROOT, MODULE.REPO.parent / "_completion" / "public_video_audio_unmixr")
        self.assertNotIn("20260619", str(MODULE.OUT_ROOT))
        self.assertEqual(MODULE.LEGACY_OUT_ROOTS, ())

    def test_unmixr_api_key_discovery_supports_more_than_three_accounts(self) -> None:
        original_env_or_file = MODULE.LEGACY.env_or_file
        original_secret_env_files = MODULE._unmixr_secret_env_files

        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.local"
            env_file.write_text(
                "\n".join(
                    [
                        "UNMIXR_API_KEY=main-key",
                        "UNMIXR_API_KEY_FALLBACK_1=backup-one",
                        "UNMIXR_API_KEY_FALLBACK_2=",
                        "UNMIXR_API_KEY_TIER4=backup-three",
                        "UNMIXR_API_KEY_PERSONAL=personal-key",
                        "UNMIXR_API_KEYS=bulk-one,bulk-two",
                    ]
                ),
                encoding="utf-8",
            )

            def fake_env_or_file(key: str) -> str:
                values = {
                    "UNMIXR_API_KEY": "main-key",
                    "UNMIXR_API_KEY_FALLBACK_1": "backup-one",
                    "UNMIXR_API_KEY_FALLBACK_2": "",
                    "UNMIXR_API_KEYS": "bulk-one,bulk-two",
                }
                return values.get(key, "")

            try:
                MODULE.LEGACY.env_or_file = fake_env_or_file
                MODULE._unmixr_secret_env_files = lambda: (env_file,)
                with patch.dict(os.environ, {}, clear=True):
                    keys = MODULE._unmixr_api_keys()
                    preferred = MODULE._unmixr_api_keys("UNMIXR_API_KEY_PERSONAL")
            finally:
                MODULE.LEGACY.env_or_file = original_env_or_file
                MODULE._unmixr_secret_env_files = original_secret_env_files

        self.assertEqual(
            [label for label, _ in keys],
            [
                "UNMIXR_API_KEY",
                "UNMIXR_API_KEY_FALLBACK_1",
                "UNMIXR_API_KEYS[1]",
                "UNMIXR_API_KEYS[2]",
                "UNMIXR_API_KEY_TIER4",
                "UNMIXR_API_KEY_PERSONAL",
            ],
        )
        self.assertEqual([value for _, value in keys], ["main-key", "backup-one", "bulk-one", "bulk-two", "backup-three", "personal-key"])
        self.assertEqual(preferred[0], ("UNMIXR_API_KEY_PERSONAL", "personal-key"))

    def test_public_video_uses_operator_configured_unmixr_account_preference(self) -> None:
        original_env_or_file = MODULE.LEGACY.env_or_file
        original_secret_env_files = MODULE._unmixr_secret_env_files

        def fake_env_or_file(key: str) -> str:
            values = {
                "UNMIXR_API_KEY": "main-key",
                "UNMIXR_API_KEY_TIER4": "tier-four-key",
                "UNMIXR_PUBLIC_VIDEO_PREFERRED_API_KEY_ENV": "UNMIXR_API_KEY_TIER4",
            }
            return values.get(key, "")

        try:
            MODULE.LEGACY.env_or_file = fake_env_or_file
            MODULE._unmixr_secret_env_files = lambda: ()
            with patch.dict(os.environ, {}, clear=True):
                keys = MODULE._unmixr_api_keys(MODULE._preferred_public_video_unmixr_api_key_env())
        finally:
            MODULE.LEGACY.env_or_file = original_env_or_file
            MODULE._unmixr_secret_env_files = original_secret_env_files

        self.assertEqual(keys[0], ("UNMIXR_API_KEY_TIER4", "tier-four-key"))

    def test_public_video_does_not_hardcode_a_specific_unmixr_fallback_slot(self) -> None:
        original_env_or_file = MODULE.LEGACY.env_or_file
        original_secret_env_files = MODULE._unmixr_secret_env_files

        def fake_env_or_file(key: str) -> str:
            values = {
                "UNMIXR_API_KEY": "main-key",
                "UNMIXR_API_KEY_FALLBACK_3": "tier-four-key",
            }
            return values.get(key, "")

        try:
            MODULE.LEGACY.env_or_file = fake_env_or_file
            MODULE._unmixr_secret_env_files = lambda: ()
            with patch.dict(os.environ, {}, clear=True):
                preferred = MODULE._preferred_public_video_unmixr_api_key_env()
                keys = MODULE._unmixr_api_keys(preferred)
        finally:
            MODULE.LEGACY.env_or_file = original_env_or_file
            MODULE._unmixr_secret_env_files = original_secret_env_files

        self.assertEqual(preferred, "")
        self.assertEqual(keys[0], ("UNMIXR_API_KEY", "main-key"))


if __name__ == "__main__":
    unittest.main()
