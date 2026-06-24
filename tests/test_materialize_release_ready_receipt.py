from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_release_ready_receipt.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_release_ready_receipt", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaterializeReleaseReadyReceiptTests(unittest.TestCase):
    def test_main_writes_pass_receipt_from_successful_release_verifier(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-receipt-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            completed = mock.Mock(returncode=0, stdout="RELEASE READY\n", stderr="")

            with mock.patch.object(module, "OUTPUT_PATH", output_path), mock.patch.object(module.subprocess, "run", return_value=completed):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("pass", payload["status"])
            self.assertEqual("RELEASE_READY", payload["verdict"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertEqual(module.TIMEOUT_SECONDS, payload["timeout_seconds"])

    def test_main_writes_fail_receipt_when_release_verifier_times_out(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-timeout-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            timeout = module.subprocess.TimeoutExpired(
                cmd=["bash", str(module.VERIFY_SCRIPT)],
                timeout=module.TIMEOUT_SECONDS,
                output="FAIL verify_live_surface_parity\nstill running\n",
                stderr="",
            )

            with mock.patch.object(module, "OUTPUT_PATH", output_path), mock.patch.object(module.subprocess, "run", side_effect=timeout):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(124, payload["returncode"])
            self.assertTrue(payload["timed_out"])
            self.assertIn(f"verify_release_ready timed out after {module.TIMEOUT_SECONDS}s", payload["failures"])
            self.assertIn("FAIL verify_live_surface_parity", payload["failures"])


if __name__ == "__main__":
    unittest.main()
