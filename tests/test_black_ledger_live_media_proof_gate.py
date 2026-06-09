import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_black_ledger_live_media_proof.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_black_ledger_live_media_proof", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlackLedgerLiveMediaProofGateTests(unittest.TestCase):
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

    def test_gate_records_screenshots_on_success(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="ledger-media-pass-") as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
            result = temp_root / "result.json"
            result.write_text(json.dumps({"entries": [{"route": "/", "viewport": "desktop", "screenshotPath": "/tmp/home.png"}]}), encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
