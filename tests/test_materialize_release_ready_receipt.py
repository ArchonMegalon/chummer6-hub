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
    def test_release_ready_receipt_materializes_into_current_repo(self) -> None:
        module = load_module()

        self.assertEqual(SCRIPT_PATH.parents[1], module.RUN_SERVICES_ROOT)
        self.assertEqual(
            SCRIPT_PATH.parents[1] / ".codex-studio" / "published" / "RELEASE_READY.generated.json",
            module.OUTPUT_PATH,
        )

    def test_main_writes_pass_receipt_from_successful_release_verifier(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-receipt-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            process = mock.Mock(pid=1234, returncode=0)
            process.communicate.return_value = ("RELEASE READY\n", "")

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "source_binding_failures", return_value=[]),
                mock.patch.object(module.subprocess, "Popen", return_value=process),
            ):
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
                output=b"FAIL verify_live_surface_parity\nstill running\n",
                stderr=b"",
            )

            process = mock.Mock(pid=1234, returncode=None)
            process.communicate.side_effect = [
                timeout,
                (b"FAIL verify_live_surface_parity\nstill running\n", b""),
            ]

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "source_binding_failures", return_value=[]),
                mock.patch.object(module.subprocess, "Popen", return_value=process),
                mock.patch.object(module.os, "killpg") as killpg,
            ):
                result = module.main()

            self.assertEqual(0, result)
            killpg.assert_called_once_with(1234, module.signal.SIGTERM)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(124, payload["returncode"])
            self.assertTrue(payload["timed_out"])
            self.assertIn(f"verify_release_ready timed out after {module.TIMEOUT_SECONDS}s", payload["failures"])
            self.assertIn("FAIL verify_live_surface_parity", payload["failures"])

    def test_main_writes_fail_receipt_when_verifier_targets_wrong_repo(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-source-binding-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            failure = "release verifier is bound to a different checkout"

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "source_binding_failures", return_value=[failure]),
                mock.patch.object(module.subprocess, "Popen") as popen,
            ):
                result = module.main()

            self.assertEqual(0, result)
            popen.assert_not_called()
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(78, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertIn(failure, payload["failures"])
            self.assertFalse(payload["source_binding"]["pass"])


if __name__ == "__main__":
    unittest.main()
