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
            SCRIPT_PATH.parents[1] / "scripts" / "verify_chummer6_release_ready.sh",
            module.VERIFY_SCRIPT,
        )
        self.assertEqual(
            SCRIPT_PATH.parents[1] / ".codex-studio" / "published" / "RELEASE_READY.generated.json",
            module.OUTPUT_PATH,
        )

    def test_repo_local_verifier_runs_windows_precheck_before_desktop_gold(self) -> None:
        module = load_module()
        text = module.VERIFY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("CHUMMER_RELEASE_READY_STOP_ON_PRECHECK_FAILURE", text)
        self.assertTrue((module.RUN_SERVICES_ROOT / "scripts" / "verify_flagship_product_readiness_gate.py").is_file())
        self.assertIn("verify_flagship_product_readiness_gate.py", text)
        self.assertLess(
            text.index("verify_windows_installer_visual_audit"),
            text.index("verify_chummer6_desktop_gold"),
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
                mock.patch.object(module, "current_git_head", return_value="abc123"),
                mock.patch.object(module.subprocess, "Popen", return_value=process) as popen,
            ):
                result = module.main()

            self.assertEqual(0, result)
            popen_env = popen.call_args.kwargs["env"]
            self.assertEqual(str(module.RUN_SERVICES_ROOT), popen_env["CHUMMER_RUN_SERVICES_ROOT"])
            self.assertEqual(str(module.ROOT), popen_env["CHUMMER_WORKSPACE_ROOT"])
            self.assertTrue(popen_env["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"])
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("pass", payload["status"])
            self.assertEqual("RELEASE_READY", payload["verdict"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertEqual(module.TIMEOUT_SECONDS, payload["timeout_seconds"])
            self.assertTrue(payload["source_binding"]["pass"])
            self.assertTrue(payload["source_binding"]["verifier_accepts_current_root"])
            self.assertIn("CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD=", payload["command"])

    def test_main_writes_fail_receipt_when_release_verifier_times_out(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-timeout-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            timeout = module.subprocess.TimeoutExpired(
                cmd=["bash", str(module.VERIFY_SCRIPT)],
                timeout=module.TIMEOUT_SECONDS,
                output=b"RUN verify_live_surface_parity\nFAIL verify_live_surface_parity\nstill running\n",
                stderr=b"",
            )

            process = mock.Mock(pid=1234, returncode=None)
            process.communicate.side_effect = [
                timeout,
                (b"RUN verify_live_surface_parity\nFAIL verify_live_surface_parity\nstill running\n", b""),
            ]

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "source_binding_failures", return_value=[]),
                mock.patch.object(module, "current_git_head", return_value="abc123"),
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
            self.assertIn("last release-ready gate before timeout: verify_live_surface_parity", payload["failures"])
            self.assertIn("FAIL verify_live_surface_parity", payload["failures"])
            self.assertEqual(["RUN verify_live_surface_parity"], payload["progress"])

    def test_main_writes_fail_receipt_when_verifier_targets_wrong_repo(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-source-binding-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            failure = "release verifier is bound to a different checkout"

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "source_binding_failures", return_value=[failure]),
                mock.patch.object(module, "current_git_head", return_value="abc123"),
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

    def test_source_binding_allows_override_aware_verifier(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-binding-aware-") as temp_dir:
            verifier = Path(temp_dir) / "verify.sh"
            verifier.write_text(
                'run_services_root="${CHUMMER_RUN_SERVICES_ROOT:-$root/chummer.run-services}"\n',
                encoding="utf-8",
            )

            with mock.patch.object(module, "VERIFY_SCRIPT", verifier):
                self.assertEqual([], module.source_binding_failures())


if __name__ == "__main__":
    unittest.main()
