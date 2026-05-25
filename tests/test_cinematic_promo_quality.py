import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/audit_cinematic_promo_quality.py")
SPEC = importlib.util.spec_from_file_location("audit_cinematic_promo_quality", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CinematicPromoQualityTests(unittest.TestCase):
    def test_parse_vtt_timestamp(self) -> None:
        self.assertEqual(MODULE.parse_vtt_timestamp("00:00:17.000"), 17.0)
        self.assertEqual(MODULE.parse_vtt_timestamp("00:01:02.500"), 62.5)

    def test_motion_score_fails_when_caption_overruns_and_motion_is_weak(self) -> None:
        asset = MODULE.PromoAsset(
            asset_id="faction-test",
            public_name="Faction Test",
            kind="faction",
            mp4_path="/tmp/test.mp4",
            webm_path="/tmp/test.webm",
            poster_path="/tmp/test.png",
            captions_path="/tmp/test.vtt",
            duration_seconds=12.0,
            video_streams=1,
            audio_streams=0,
            scene_cut_frames_gt_0_18=6,
            avg_frame_diff=0.5,
            peak_frame_diff=12.0,
            poster_face_proxy_hits=0,
            video_face_proxy_hits=0,
            captions_end_seconds=17.0,
            caption_segments=2,
            storyboard_shots=2,
            expected_people=1,
            expected_action="run",
            expected_environment="street",
            expected_conflict="pursuit",
            expected_camera_motion=True,
        )
        score = MODULE.score_motion(asset)
        self.assertEqual(score["verdict"], "fail")
        self.assertIn("Caption timing overruns the rendered file duration.", score["notes"])

    def test_people_score_fails_without_faces_audio_or_review(self) -> None:
        asset = MODULE.PromoAsset(
            asset_id="faction-test",
            public_name="Faction Test",
            kind="faction",
            mp4_path="/tmp/test.mp4",
            webm_path="/tmp/test.webm",
            poster_path="/tmp/test.png",
            captions_path="/tmp/test.vtt",
            duration_seconds=12.0,
            video_streams=1,
            audio_streams=0,
            scene_cut_frames_gt_0_18=8,
            avg_frame_diff=2.2,
            peak_frame_diff=15.0,
            poster_face_proxy_hits=0,
            video_face_proxy_hits=0,
            captions_end_seconds=11.0,
            caption_segments=3,
            storyboard_shots=3,
            expected_people=1,
            expected_action="run",
            expected_environment="street",
            expected_conflict="pursuit",
            expected_camera_motion=True,
        )
        score = MODULE.score_people(asset)
        self.assertEqual(score["verdict"], "fail")
        self.assertIn("Character visibility is asserted by the authored shot plan, not by strong face-detection proof.", score["notes"])
        self.assertIn("No audio stream is present for this promo asset.", score["notes"])
        self.assertIn("No signed human creative review receipt exists.", score["notes"])


if __name__ == "__main__":
    unittest.main()
