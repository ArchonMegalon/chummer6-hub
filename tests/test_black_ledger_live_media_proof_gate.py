import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_black_ledger_live_media_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_black_ledger_live_media_proof", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlackLedgerLiveMediaProofGateTests(unittest.TestCase):
    def _write_capture_result(self, root: Path) -> dict[str, object]:
        entries = []
        for route, viewport, label in (
            ("/", "desktop", "home-desktop"),
            ("/", "mobile", "home-mobile"),
            ("/ledger/map", "desktop", "map-desktop"),
            ("/ledger/map", "mobile", "map-mobile"),
            ("/ledger/newsroom", "desktop", "newsroom-desktop"),
            ("/ledger/newsroom", "mobile", "newsroom-mobile"),
            ("/ledger/factions/ashline-circle/promo", "desktop", "promo-desktop"),
            ("/ledger/factions/ashline-circle/promo", "mobile", "promo-mobile"),
            ("/ledger/map?replay=turn-1", "desktop", "replay-desktop"),
            ("/ledger/map?replay=turn-1", "mobile", "replay-mobile"),
        ):
            screenshot = root / f"{label}.png"
            screenshot.write_bytes(b"0" * 125_000)
            final_url = {
                "/ledger/newsroom": "https://chummer.run/ledger/newsroom/turn-2-newsreel",
                "/ledger/factions/ashline-circle/promo": "https://chummer.run/ledger/factions/ashline-circle/promo",
                "/ledger/map?replay=turn-1": "https://chummer.run/ledger/map?replay=turn-1",
            }.get(route, f"https://chummer.run{route}")
            visual_signals = {
                "textLength": 1400,
                "blackLedgerMentions": 2,
                "commandMapMentions": 2 if "/ledger/map" in route or route == "/" else 0,
                "globeMentions": 1 if route == "/ledger/map" else 0,
                "factionMentions": 6 if route in {"/ledger/map", "/ledger/factions/ashline-circle/promo"} else 1,
                "pressureMentions": 5 if "/ledger/map" in route else 1,
                "newsreelMentions": 2 if route == "/ledger/newsroom" else 0,
                "videoMentions": 2 if route in {"/ledger/newsroom", "/ledger/factions/ashline-circle/promo"} else 1,
                "mediaElementCount": 4,
                "videoElementCount": 1 if route in {"/ledger/newsroom", "/ledger/factions/ashline-circle/promo"} else 0,
                "imageElementCount": 1,
                "svgElementCount": 1,
                "geoscapePanelCount": 1 if "/ledger/map" in route else 0,
                "geoscapeControlCount": 1 if "/ledger/map" in route else 0,
                "geoscapeSignalRailCount": 1 if "/ledger/map" in route else 0,
                "largestMediaArea": 250000 if "/ledger/map" in route else 120000,
                "viewportArea": 1000000,
            }
            entries.append(
                {
                    "route": route,
                    "viewport": viewport,
                    "finalUrl": final_url,
                    "screenshotPath": str(screenshot),
                    "screenshotBytes": screenshot.stat().st_size,
                    "visualSignals": visual_signals,
                }
            )
        return {"entries": entries}

    def test_gate_fails_closed_on_capture_error(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="ledger-media-fail-") as temp_dir:
            output = Path(temp_dir) / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
            with mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(
                module.subprocess,
                "run",
                return_value=mock.Mock(returncode=1, stdout="", stderr="boom"),
            ):
                with self.assertRaises(SystemExit):
                    with mock.patch("sys.argv", ["verify_black_ledger_live_media_proof.py"]):
                        module.main()
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["attempt_count"], module.CAPTURE_ATTEMPTS)
            self.assertEqual(len(payload["attempts"]), module.CAPTURE_ATTEMPTS)

    def test_gate_records_screenshots_on_success(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="ledger-media-pass-") as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
            result = temp_root / "result.json"
            result.write_text(json.dumps(self._write_capture_result(temp_root)), encoding="utf-8")

            def fake_run(*args, **kwargs):
                result_path = Path(args[0][3])
                result_path.write_text(result.read_text(encoding="utf-8"), encoding="utf-8")
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            with mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "SCREENSHOT_ROOT", temp_root / "screens"), mock.patch.object(module.subprocess, "run", side_effect=fake_run):
                with mock.patch("sys.argv", ["verify_black_ledger_live_media_proof.py"]):
                    self.assertEqual(module.main(), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertTrue(payload["screenshots"])
            self.assertEqual(payload["attempt_count"], 1)

    def test_gate_retries_before_success(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="ledger-media-retry-") as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
            result = temp_root / "result.json"
            result.write_text(json.dumps(self._write_capture_result(temp_root)), encoding="utf-8")

            responses = [
                mock.Mock(returncode=1, stdout="", stderr="page.goto chrome-error://chromewebdata"),
                mock.Mock(returncode=0, stdout="ok", stderr=""),
            ]

            def fake_run(*args, **kwargs):
                current = responses.pop(0)
                result_path = Path(args[0][3])
                if current.returncode == 0:
                    result_path.write_text(result.read_text(encoding="utf-8"), encoding="utf-8")
                return current

            with mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "SCREENSHOT_ROOT", temp_root / "screens"), mock.patch.object(module.subprocess, "run", side_effect=fake_run):
                with mock.patch("sys.argv", ["verify_black_ledger_live_media_proof.py"]):
                    self.assertEqual(module.main(), 0)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["attempt_count"], 2)
            self.assertEqual(payload["attempts"][0]["returncode"], 1)
            self.assertEqual(payload["attempts"][1]["returncode"], 0)
            self.assertTrue(payload["screenshots"])

    def test_source_retries_transient_navigation_errors_inside_capture(self) -> None:
        module = load_module()

        self.assertIn('const navigationAttempts = 4;', module.NODE_SCRIPT)
        self.assertIn('"ERR_NETWORK_CHANGED"', module.NODE_SCRIPT)
        self.assertIn('"net::ERR_"', module.NODE_SCRIPT)
        self.assertIn("function isTransientNavigationError", module.NODE_SCRIPT)
        self.assertIn("await context.close().catch(() => undefined);", module.NODE_SCRIPT)
        self.assertIn("await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));", module.NODE_SCRIPT)


if __name__ == "__main__":
    unittest.main()
