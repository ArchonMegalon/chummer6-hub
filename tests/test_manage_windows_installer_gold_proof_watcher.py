from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manage_windows_installer_gold_proof_watcher.py"


def load_module():
    spec = importlib.util.spec_from_file_location("manage_windows_installer_gold_proof_watcher", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManageWindowsInstallerGoldProofWatcherTests(unittest.TestCase):
    def test_list_matching_watcher_pids_uses_wide_ps_and_extracts_all_matches(self) -> None:
        module = load_module()
        intake_request = Path("/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json")
        command = module.watcher_command(
            intake_request,
            wait_seconds=43200,
            poll_seconds=30,
            refresh_intake_request=True,
        )
        ps_stdout = "\n".join(
            [
                "111 /usr/bin/python3 /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --wait-seconds 43200 --poll-seconds 30 --refresh-intake-request",
                "222 /usr/bin/python3 /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --wait-seconds 43200 --poll-seconds 30 --refresh-intake-request",
                "333 /usr/bin/python3 /docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/other.json --wait-seconds 43200 --poll-seconds 30 --refresh-intake-request",
            ]
        )

        with (
            mock.patch.object(module.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=ps_stdout)) as run_mock,
            mock.patch.object(module, "is_process_alive", side_effect=lambda pid: pid in (111, 222)),
        ):
            pids = module.list_matching_watcher_pids(command)

        self.assertEqual([111, 222], pids)
        run_mock.assert_called_once()
        self.assertEqual(["ps", "-ww", "-eo", "pid=,args="], run_mock.call_args.args[0])
        env = run_mock.call_args.kwargs.get("env")
        self.assertIsInstance(env, dict)
        self.assertTrue(str(env.get("TMPDIR") or "").strip())

    def test_start_launches_process_with_start_new_session_and_writes_state(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-watcher-start-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text("{}\n", encoding="utf-8")
            state_path = root / "watcher.generated.json"
            pid_file = root / "watcher.pid"
            log_file = root / "watcher.log"
            process = mock.Mock(pid=4242)

            with (
                mock.patch.object(module.subprocess, "Popen", return_value=process) as popen,
                mock.patch.object(module, "list_matching_watcher_pids", return_value=[]),
                mock.patch.object(module, "is_process_alive", side_effect=lambda pid: pid not in (None, 0)),
                redirect_stdout(io.StringIO()),
            ):
                result = module.main(
                    [
                        "start",
                        "--intake-request",
                        str(intake_request),
                        "--state-path",
                        str(state_path),
                        "--pid-file",
                        str(pid_file),
                        "--log-file",
                        str(log_file),
                        "--wait-seconds",
                        "60",
                        "--poll-seconds",
                        "5",
                    ]
                )

            self.assertEqual(0, result)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("running", payload["status"])
            self.assertEqual(4242, payload["pid"])
            self.assertEqual("python_subprocess_start_new_session", payload["watcher_launch_mode"])
            self.assertIn("auto_import_windows_installer_gold_proof.py", payload["command_text"])
            self.assertEqual("4242", pid_file.read_text(encoding="utf-8").strip())
            self.assertIn("START ", log_file.read_text(encoding="utf-8"))
            self.assertTrue(payload["process_alive"])
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            env = popen.call_args.kwargs.get("env")
            self.assertIsInstance(env, dict)
            self.assertTrue(str(env.get("TMPDIR") or "").strip())

    def test_start_adopts_existing_process_without_launching_duplicate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-watcher-adopt-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text("{}\n", encoding="utf-8")
            state_path = root / "watcher.generated.json"
            pid_file = root / "watcher.pid"
            log_file = root / "watcher.log"

            with (
                mock.patch.object(module, "list_matching_watcher_pids", return_value=[5150]),
                mock.patch.object(module, "is_process_alive", side_effect=lambda pid: pid not in (None, 0)),
                mock.patch.object(module.subprocess, "Popen") as popen,
                redirect_stdout(io.StringIO()),
            ):
                result = module.main(
                    [
                        "start",
                        "--intake-request",
                        str(intake_request),
                        "--state-path",
                        str(state_path),
                        "--pid-file",
                        str(pid_file),
                        "--log-file",
                        str(log_file),
                    ]
                )

            self.assertEqual(0, result)
            popen.assert_not_called()
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("already_running", payload["status"])
            self.assertTrue(payload["adopted_existing_process"])
            self.assertEqual(5150, payload["pid"])
            self.assertEqual([5150], payload["matching_process_pids"])
            self.assertEqual(1, payload["matching_process_count"])
            self.assertEqual("5150", pid_file.read_text(encoding="utf-8").strip())

    def test_status_surfaces_duplicate_matching_watcher_pids(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-watcher-duplicates-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text("{}\n", encoding="utf-8")
            state_path = root / "watcher.generated.json"
            pid_file = root / "watcher.pid"
            log_file = root / "watcher.log"

            with (
                mock.patch.object(module, "list_matching_watcher_pids", return_value=[5150, 6161]),
                mock.patch.object(module, "is_process_alive", side_effect=lambda pid: pid not in (None, 0)),
                redirect_stdout(io.StringIO()),
            ):
                result = module.main(
                    [
                        "status",
                        "--intake-request",
                        str(intake_request),
                        "--state-path",
                        str(state_path),
                        "--pid-file",
                        str(pid_file),
                        "--log-file",
                        str(log_file),
                    ]
                )

            self.assertEqual(0, result)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("running", payload["status"])
            self.assertEqual(5150, payload["pid"])
            self.assertEqual([5150, 6161], payload["matching_process_pids"])
            self.assertEqual([6161], payload["duplicate_process_pids"])
            self.assertEqual(1, payload["duplicate_process_count"])
            self.assertIn("duplicate watchers detected", payload["note"])
            self.assertEqual("5150", pid_file.read_text(encoding="utf-8").strip())

    def test_stop_terminates_all_matching_process_groups_and_clears_pid_file(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-watcher-stop-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text("{}\n", encoding="utf-8")
            state_path = root / "watcher.generated.json"
            pid_file = root / "watcher.pid"
            pid_file.write_text("6363\n", encoding="utf-8")
            log_file = root / "watcher.log"

            with (
                mock.patch.object(module, "list_matching_watcher_pids", return_value=[6363, 7474]),
                mock.patch.object(module, "is_process_alive", side_effect=lambda pid: pid in (6363, 7474)),
                mock.patch.object(module, "terminate_process_group", side_effect=[(True, False), (True, False)]) as terminate,
                mock.patch.object(module.os, "killpg") as killpg,
                redirect_stdout(io.StringIO()),
            ):
                result = module.main(
                    [
                        "stop",
                        "--intake-request",
                        str(intake_request),
                        "--state-path",
                        str(state_path),
                        "--pid-file",
                        str(pid_file),
                        "--log-file",
                        str(log_file),
                        "--stop-grace-seconds",
                        "0",
                    ]
                )

            self.assertEqual(0, result)
            killpg.assert_not_called()
            self.assertEqual([mock.call(6363, 0.0), mock.call(7474, 0.0)], terminate.call_args_list)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("stopped", payload["status"])
            self.assertEqual([6363, 7474], payload["stopped_pids"])
            self.assertEqual([], payload["failed_stop_pids"])
            self.assertFalse(pid_file.exists())


if __name__ == "__main__":
    unittest.main()
