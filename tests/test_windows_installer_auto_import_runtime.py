import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path("/docker/chummercomplete/chummer.run-services")
AUTO_IMPORT_SCRIPT_PATH = ROOT / "scripts" / "auto_import_windows_installer_gold_proof.py"
WATCHER_SCRIPT_PATH = ROOT / "scripts" / "manage_windows_installer_gold_proof_watcher.py"


def load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_auto_import_module():
    return load_script(AUTO_IMPORT_SCRIPT_PATH, "auto_import_windows_installer_gold_proof_runtime_test")


def load_watcher_module():
    return load_script(WATCHER_SCRIPT_PATH, "manage_windows_installer_gold_proof_watcher_runtime_test")


def absolute_path_strings(value):
    found = []
    if isinstance(value, dict):
        for child in value.values():
            found.extend(absolute_path_strings(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(absolute_path_strings(child))
    elif isinstance(value, Path):
        if value.is_absolute():
            found.append(str(value))
    elif isinstance(value, str):
        try:
            if Path(value).is_absolute():
                found.append(value)
        except (TypeError, ValueError):
            pass
    return found


class WindowsInstallerAutoImportRuntimeTests(unittest.TestCase):
    def test_auto_import_json_write_atomically_replaces_and_fsyncs_file_and_parent(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-runtime-write-") as temp_dir:
            root = Path(temp_dir)
            receipt = root / "receipt.json"
            receipt.write_text('{"old": true}\n', encoding="utf-8")

            with mock.patch.object(module.os, "fsync", wraps=os.fsync) as fsync_mock, mock.patch.object(
                module.os,
                "replace",
                wraps=os.replace,
            ) as replace_mock:
                module.write_json(receipt, {"status": "fresh"})

            payload = json.loads(receipt.read_text(encoding="utf-8"))
            remaining_names = sorted(item.name for item in root.iterdir())

        self.assertEqual({"status": "fresh"}, payload)
        self.assertEqual(["receipt.json"], remaining_names)
        self.assertEqual(2, fsync_mock.call_count)
        self.assertEqual(1, replace_mock.call_count)
        self.assertEqual(receipt, Path(replace_mock.call_args.args[1]))

    def test_watcher_json_and_pid_writes_are_atomic_and_durable(self) -> None:
        module = load_watcher_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-runtime-write-") as temp_dir:
            root = Path(temp_dir)
            receipt = root / "watcher.json"
            pid_file = root / "watcher.pid"

            with mock.patch.object(module.os, "fsync", wraps=os.fsync) as fsync_mock, mock.patch.object(
                module.os,
                "replace",
                wraps=os.replace,
            ) as replace_mock:
                module.write_json(receipt, {"status": "running"})
                module.write_pid(pid_file, 4242)

            payload = json.loads(receipt.read_text(encoding="utf-8"))
            pid_text = pid_file.read_text(encoding="utf-8")
            remaining_names = sorted(item.name for item in root.iterdir())

        self.assertEqual({"status": "running"}, payload)
        self.assertEqual("4242\n", pid_text)
        self.assertEqual(["watcher.json", "watcher.pid"], remaining_names)
        self.assertEqual(4, fsync_mock.call_count)
        self.assertEqual(2, replace_mock.call_count)

    def test_durable_writes_reject_symlinks_preserve_modes_and_clean_failures(self) -> None:
        for module in (load_auto_import_module(), load_watcher_module()):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory(
                prefix="windows-proof-runtime-durable-safety-"
            ) as temp_dir:
                root = Path(temp_dir)
                symlink_source = root / "source.json"
                symlink_source.write_text('{"source": true}\n', encoding="utf-8")
                symlink_target = root / "symlink.json"
                symlink_target.symlink_to(symlink_source)

                with self.assertRaises(ValueError):
                    module.write_json(symlink_target, {"unsafe": True})

                self.assertEqual(
                    '{"source": true}\n',
                    symlink_source.read_text(encoding="utf-8"),
                )

                mode_target = root / "mode.json"
                mode_target.write_text('{"old": true}\n', encoding="utf-8")
                mode_target.chmod(0o640)
                module.write_json(mode_target, {"new": True})
                self.assertEqual(0o640, stat.S_IMODE(mode_target.stat().st_mode))

                failed_target = root / "failed.json"
                with mock.patch.object(
                    module.os,
                    "replace",
                    side_effect=OSError("simulated replace failure"),
                ):
                    with self.assertRaises(OSError):
                        module.write_json(failed_target, {"status": "failed"})
                self.assertFalse(failed_target.exists())
                self.assertEqual(
                    [],
                    [item.name for item in root.iterdir() if item.name.endswith(".tmp")],
                )

    def test_durable_writes_fsync_each_new_ancestor_entry(self) -> None:
        for module in (load_auto_import_module(), load_watcher_module()):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory(
                prefix="windows-proof-runtime-ancestor-fsync-"
            ) as temp_dir:
                receipt = Path(temp_dir) / "one" / "two" / "receipt.json"
                with mock.patch.object(
                    module.os,
                    "fsync",
                    wraps=os.fsync,
                ) as fsync_mock:
                    module.write_json(receipt, {"status": "durable"})

                self.assertEqual({"status": "durable"}, json.loads(receipt.read_text()))
                self.assertEqual(4, fsync_mock.call_count)

    def test_startup_receipt_bundle_requirement_cannot_be_disabled_by_intake(self) -> None:
        module = load_auto_import_module()
        false_declarations = [
            {"startup_receipt_bundle_required": False},
            {"operator_request": {"startup_receipt_bundle_required": False}},
            {"artifact_intake": {"startup_receipt_bundle_required": False}},
        ]

        for intake in false_declarations:
            with self.subTest(intake=intake):
                self.assertTrue(module.startup_receipt_bundle_required(intake))

        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-runtime-contract-") as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(module, "program_bindings_for_receipt", return_value={}):
                payload = module.build_waiting_payload(
                    artifact=None,
                    candidates=[],
                    intake={"startup_receipt_bundle_required": False},
                    intake_request=root / "intake.json",
                    downloads_root=root / "downloads",
                    roots=[root],
                )

        self.assertTrue(payload["startup_receipt_bundle_required"])
        self.assertEqual(module.AUTO_IMPORT_CONTRACT_NAME, payload["contract_name"])
        self.assertEqual(2, payload["contract_version"])
        self.assertEqual(
            module.AUTO_IMPORT_CONTRACT_NAME_V1,
            payload["supersedes_contract_name"],
        )

    def test_auto_import_redaction_uses_only_coarse_allowlisted_metadata(self) -> None:
        module = load_auto_import_module()
        sensitive_value = "/private/runtime/credential-value"
        sensitive_digest = hashlib.sha256(sensitive_value.encode("utf-8")).hexdigest()

        redacted = module.redacted_value_receipt(sensitive_value)
        unexpected = module.import_failure_details(RuntimeError(sensitive_value))
        validation = module.import_failure_details(SystemExit(sensitive_value))
        serialized = json.dumps(
            {"redacted": redacted, "unexpected": unexpected, "validation": validation},
            sort_keys=True,
        )

        self.assertEqual(
            {
                "redacted": True,
                "value_type": "text",
                "value_kind": "text",
                "present": True,
            },
            redacted,
        )
        self.assertNotIn("sha256", redacted)
        self.assertNotIn("byte_count", redacted)
        self.assertNotIn(sensitive_value, serialized)
        self.assertNotIn(sensitive_digest, serialized)
        self.assertEqual("Exception", unexpected["type"])
        self.assertEqual("unexpected_failure", unexpected["error_code"])
        self.assertEqual("SystemExit", validation["type"])
        self.assertEqual("artifact_validation_failed", validation["error_code"])

    def test_auto_import_failure_payload_omits_absolute_paths_and_candidate_details(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-runtime-failure-") as temp_dir:
            root = Path(temp_dir)
            marker = str(root)
            payload = module.build_import_failure_payload(
                artifact=root / "incoming" / "bundle.zip",
                intake_request=root / "published" / "intake.json",
                downloads_root=root / "public" / "downloads",
                roots=[root / "incoming"],
                candidates=[{"path": root / "incoming" / "bundle.zip"}],
                error=RuntimeError(marker),
            )
            serialized = json.dumps(payload, sort_keys=True, default=str)

        self.assertNotIn(marker, serialized)
        self.assertEqual([], absolute_path_strings(payload))
        self.assertIn("sha256", serialized)
        self.assertIn("size_bytes", serialized)
        self.assertEqual("bundle.zip", payload["artifact"])
        self.assertEqual("intake.json", payload["intake_request"])
        self.assertEqual([], payload["candidates"])
        self.assertEqual(1, payload["candidate_count"])
        self.assertEqual(module.AUTO_IMPORT_CONTRACT_NAME, payload["contract_name"])
        self.assertEqual(2, payload["contract_version"])
        self.assertEqual(
            module.AUTO_IMPORT_CONTRACT_NAME_V1,
            payload["supersedes_contract_name"],
        )

    def test_intake_materializer_failure_omits_streams_fingerprints_and_paths(self) -> None:
        module = load_auto_import_module()
        sensitive_stream = "/private/runtime/materializer-output"
        sensitive_digest = hashlib.sha256(sensitive_stream.encode("utf-8")).hexdigest()
        completed = subprocess.CompletedProcess(
            args=["materializer"],
            returncode=9,
            stdout=sensitive_stream,
            stderr=sensitive_stream,
        )
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-runtime-materializer-") as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(
                module.proof_importer,
                "run_bound_python_subprocess",
                return_value=(completed, {}),
            ):
                with self.assertRaises(SystemExit) as raised:
                    module.materialize_intake_request(root / "intake.json", root / "downloads")

        message = str(raised.exception)
        self.assertEqual("intake_materializer_failed:returncode=9", message)
        self.assertNotIn(sensitive_stream, message)
        self.assertNotIn(sensitive_digest, message)
        self.assertNotIn(str(root), message)

    def test_watcher_process_capture_is_bounded_and_marks_scan_incomplete(self) -> None:
        module = load_watcher_module()

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(b"bounded-process-listing" * 8)
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def kill(self) -> None:
                self.returncode = -9

        process = FakeProcess()
        with mock.patch.object(module.subprocess, "Popen", return_value=process):
            capture = module.bounded_subprocess_capture(
                ["process-listing"],
                max_capture_bytes=16,
                timeout_seconds=1.0,
            )

        self.assertEqual(16, len(capture["stdout"]))
        self.assertTrue(capture["output_truncated"])
        self.assertFalse(capture["complete"])
        self.assertEqual("process_scan_output_limit", capture["error_code"])
        self.assertTrue(process.stdout.closed)

    def test_successful_watcher_process_capture_closes_stdout(self) -> None:
        module = load_watcher_module()

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(b"4242 python3 watcher.py\n")
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def kill(self) -> None:
                self.returncode = -9

        process = FakeProcess()
        with mock.patch.object(module.subprocess, "Popen", return_value=process):
            capture = module.bounded_subprocess_capture(
                ["process-listing"],
                max_capture_bytes=1024,
                timeout_seconds=1.0,
            )

        self.assertTrue(capture["complete"])
        self.assertEqual("", capture["error_code"])
        self.assertTrue(process.stdout.closed)

    def test_watcher_capture_unavailable_cleanup_is_deadline_bounded(self) -> None:
        module = load_watcher_module()

        class UnreapableProcess:
            def __init__(self) -> None:
                self.stdout = None
                self.returncode = None
                self.wait_timeouts = []
                self.killed = False

            def wait(self, timeout=None):
                self.wait_timeouts.append(timeout)
                raise subprocess.TimeoutExpired(["process-listing"], timeout)

            def kill(self) -> None:
                self.killed = True

        process = UnreapableProcess()
        with mock.patch.object(module.subprocess, "Popen", return_value=process):
            capture = module.bounded_subprocess_capture(
                ["process-listing"],
                timeout_seconds=0.01,
                cleanup_seconds=0.01,
            )

        self.assertTrue(process.killed)
        self.assertTrue(process.wait_timeouts)
        self.assertTrue(all(timeout is not None for timeout in process.wait_timeouts))
        self.assertFalse(capture["complete"])
        self.assertFalse(capture["cleanup_complete"])
        self.assertFalse(capture["process_reaped"])
        self.assertEqual("process_scan_cleanup_incomplete", capture["error_code"])

    def test_watcher_post_kill_reap_is_deadline_bounded_and_fails_closed(self) -> None:
        module = load_watcher_module()

        class UnreapableProcess:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(b"4242 python3 watcher.py\n")
                self.returncode = None
                self.wait_timeouts = []
                self.killed = False

            def wait(self, timeout=None):
                self.wait_timeouts.append(timeout)
                raise subprocess.TimeoutExpired(["process-listing"], timeout)

            def kill(self) -> None:
                self.killed = True

        process = UnreapableProcess()
        with mock.patch.object(module.subprocess, "Popen", return_value=process):
            capture = module.bounded_subprocess_capture(
                ["process-listing"],
                timeout_seconds=0.01,
                cleanup_seconds=0.01,
            )

        self.assertTrue(process.killed)
        self.assertGreaterEqual(len(process.wait_timeouts), 2)
        self.assertTrue(all(timeout is not None for timeout in process.wait_timeouts))
        self.assertFalse(capture["complete"])
        self.assertFalse(capture["cleanup_complete"])
        self.assertEqual("process_scan_cleanup_incomplete", capture["error_code"])

    def test_incomplete_scan_withholds_start_and_stop_actions(self) -> None:
        module = load_watcher_module()
        incomplete_resolution = {
            "pid": 4242,
            "matching_process_pids": [4242],
            "adopted_existing_process": False,
            "process_scan_complete": False,
            "process_scan_error_code": "process_scan_cleanup_incomplete",
            "process_scan_cleanup_complete": False,
            "recorded_pid_alive": True,
            "watcher_instance_id": "",
            "watcher_process_started_at_utc": "",
        }
        with tempfile.TemporaryDirectory(prefix="windows-proof-runtime-withheld-") as temp_dir:
            root = Path(temp_dir)
            for action in ("start", "stop"):
                with self.subTest(action=action):
                    argv = [
                        action,
                        "--intake-request",
                        str(root / "intake.json"),
                        "--state-path",
                        str(root / f"{action}.json"),
                        "--pid-file",
                        str(root / "watcher.pid"),
                        "--log-file",
                        str(root / "watcher.log"),
                    ]
                    args = module.parse_args(argv)
                    with mock.patch.object(
                        module,
                        "resolve_running_process_state",
                        return_value=dict(incomplete_resolution),
                    ), mock.patch.object(
                        module,
                        "build_payload",
                        return_value={"status": "process_state_unknown"},
                    ), mock.patch.object(module, "write_json"), mock.patch.object(
                        module,
                        "launch_process",
                    ) as launch_mock, mock.patch.object(
                        module,
                        "terminate_process_group",
                    ) as terminate_mock, mock.patch("builtins.print"):
                        result = getattr(module, action)(args)

                    self.assertEqual(1, result)
                    launch_mock.assert_not_called()
                    terminate_mock.assert_not_called()

    def test_start_preflight_rejects_invalid_targets_without_launch(self) -> None:
        module = load_watcher_module()
        for target_argument in ("state-path", "pid-file", "log-file"):
            for invalid_kind in ("symlink", "directory"):
                with self.subTest(
                    target_argument=target_argument,
                    invalid_kind=invalid_kind,
                ), tempfile.TemporaryDirectory(
                    prefix="windows-proof-runtime-invalid-target-"
                ) as temp_dir:
                    root = Path(temp_dir)
                    targets = {
                        "state-path": root / "watcher.json",
                        "pid-file": root / "watcher.pid",
                        "log-file": root / "watcher.log",
                    }
                    invalid_target = targets[target_argument]
                    if invalid_kind == "symlink":
                        source = root / f"{target_argument}.source"
                        source.write_text("source\n", encoding="utf-8")
                        invalid_target.symlink_to(source)
                    else:
                        invalid_target.mkdir()
                    args = module.parse_args(
                        [
                            "start",
                            "--intake-request",
                            str(root / "intake.json"),
                            "--state-path",
                            str(targets["state-path"]),
                            "--pid-file",
                            str(targets["pid-file"]),
                            "--log-file",
                            str(targets["log-file"]),
                        ]
                    )
                    with mock.patch.object(
                        module,
                        "resolve_running_process_state",
                    ) as resolve_mock, mock.patch.object(
                        module,
                        "launch_process",
                    ) as launch_mock:
                        with self.assertRaises(ValueError):
                            module.start(args)

                    resolve_mock.assert_not_called()
                    launch_mock.assert_not_called()

    def test_start_preflight_rejects_unwritable_target_without_launch(self) -> None:
        module = load_watcher_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-runtime-unwritable-") as temp_dir:
            root = Path(temp_dir)
            args = module.parse_args(
                [
                    "start",
                    "--intake-request",
                    str(root / "intake.json"),
                    "--state-path",
                    str(root / "watcher.json"),
                    "--pid-file",
                    str(root / "watcher.pid"),
                    "--log-file",
                    str(root / "watcher.log"),
                ]
            )
            with mock.patch.object(
                module,
                "preflight_write_probe",
                side_effect=PermissionError("simulated unwritable target"),
            ), mock.patch.object(
                module,
                "resolve_running_process_state",
            ) as resolve_mock, mock.patch.object(
                module,
                "launch_process",
            ) as launch_mock:
                with self.assertRaises(PermissionError):
                    module.start(args)

        resolve_mock.assert_not_called()
        launch_mock.assert_not_called()

    def test_post_launch_persistence_failures_trigger_bounded_cleanup(self) -> None:
        module = load_watcher_module()
        resolution = {
            "pid": None,
            "matching_process_pids": [],
            "adopted_existing_process": False,
            "process_scan_complete": True,
            "process_scan_error_code": "",
            "process_scan_cleanup_complete": True,
            "recorded_pid_alive": False,
            "watcher_instance_id": "",
            "watcher_process_started_at_utc": "",
        }

        class FakeProcess:
            pid = 4242

        for failure_stage in ("pid", "state"):
            with self.subTest(failure_stage=failure_stage), tempfile.TemporaryDirectory(
                prefix="windows-proof-runtime-persistence-rollback-"
            ) as temp_dir:
                root = Path(temp_dir)
                args = module.parse_args(
                    [
                        "start",
                        "--intake-request",
                        str(root / "intake.json"),
                        "--state-path",
                        str(root / "watcher.json"),
                        "--pid-file",
                        str(root / "watcher.pid"),
                        "--log-file",
                        str(root / "watcher.log"),
                    ]
                )
                pid_failure = (
                    OSError("simulated pid persistence failure")
                    if failure_stage == "pid"
                    else None
                )
                state_failure = (
                    OSError("simulated state persistence failure")
                    if failure_stage == "state"
                    else None
                )
                with mock.patch.object(
                    module,
                    "resolve_running_process_state",
                    return_value=dict(resolution),
                ), mock.patch.object(
                    module,
                    "launch_process",
                    return_value=FakeProcess(),
                ), mock.patch.object(
                    module,
                    "write_pid",
                    side_effect=pid_failure,
                ), mock.patch.object(
                    module,
                    "is_process_alive",
                    return_value=True,
                ), mock.patch.object(
                    module,
                    "build_payload",
                    return_value={"status": "running"},
                ), mock.patch.object(
                    module,
                    "write_json",
                    side_effect=state_failure,
                ), mock.patch.object(
                    module,
                    "bounded_cleanup_launched_process",
                    return_value=True,
                ) as cleanup_mock:
                    with self.assertRaises(OSError):
                        module.start(args)

                cleanup_mock.assert_called_once()

    def test_post_launch_cleanup_waits_are_deadline_bounded(self) -> None:
        module = load_watcher_module()

        class UnreapableProcess:
            pid = 4242
            returncode = None

            def __init__(self) -> None:
                self.wait_timeouts = []

            def wait(self, timeout=None):
                self.wait_timeouts.append(timeout)
                raise subprocess.TimeoutExpired(["watcher"], timeout)

            def terminate(self) -> None:
                return None

            def kill(self) -> None:
                return None

        process = UnreapableProcess()
        with mock.patch.object(module.os, "killpg") as killpg_mock:
            cleaned = module.bounded_cleanup_launched_process(
                process,
                cleanup_seconds=0.01,
                term_seconds=0.005,
            )

        self.assertFalse(cleaned)
        self.assertEqual(2, len(process.wait_timeouts))
        self.assertTrue(all(timeout is not None for timeout in process.wait_timeouts))
        self.assertEqual(
            [mock.call(4242, module.signal.SIGTERM), mock.call(4242, module.signal.SIGKILL)],
            killpg_mock.call_args_list,
        )

    def test_incomplete_process_scan_preserves_pid_evidence(self) -> None:
        module = load_watcher_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-runtime-incomplete-") as temp_dir:
            pid_file = Path(temp_dir) / "watcher.pid"
            pid_file.write_text("4242\n", encoding="utf-8")
            incomplete_scan = {
                "pids": [],
                "complete": False,
                "error_code": "process_scan_output_limit",
                "timed_out": False,
                "output_truncated": True,
                "cleanup_complete": True,
                "process_reaped": True,
                "returncode": 0,
            }
            with mock.patch.object(module, "scan_matching_watcher_pids", return_value=incomplete_scan), mock.patch.object(
                module,
                "is_process_alive",
                return_value=True,
            ), mock.patch.object(module, "remove_pid_file") as remove_mock, mock.patch.object(
                module,
                "write_pid",
            ) as write_mock:
                resolution = module.resolve_running_process_state(pid_file, ["watcher"])

            retained_pid = pid_file.read_text(encoding="utf-8")

        self.assertEqual("4242\n", retained_pid)
        self.assertFalse(resolution["process_scan_complete"])
        self.assertEqual("process_scan_output_limit", resolution["process_scan_error_code"])
        self.assertEqual(4242, resolution["pid_file_recorded_pid"])
        self.assertTrue(resolution["recorded_pid_alive"])
        self.assertFalse(resolution["stale_pid_detected"])
        remove_mock.assert_not_called()
        write_mock.assert_not_called()

    def test_complete_process_scan_reports_and_removes_stale_pid(self) -> None:
        module = load_watcher_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-runtime-stale-pid-") as temp_dir:
            pid_file = Path(temp_dir) / "watcher.pid"
            pid_file.write_text("4242\n", encoding="utf-8")
            complete_scan = {
                "pids": [],
                "complete": True,
                "error_code": "",
                "timed_out": False,
                "output_truncated": False,
                "cleanup_complete": True,
                "process_reaped": True,
                "returncode": 0,
            }
            with mock.patch.object(module, "scan_matching_watcher_pids", return_value=complete_scan), mock.patch.object(
                module,
                "is_process_alive",
                return_value=False,
            ):
                resolution = module.resolve_running_process_state(pid_file, ["watcher"])
            pid_file_exists = pid_file.exists()

        self.assertFalse(pid_file_exists)
        self.assertTrue(resolution["process_scan_complete"])
        self.assertTrue(resolution["stale_pid_detected"])
        self.assertEqual("recorded_pid_not_alive", resolution["stale_pid_reason"])
        self.assertTrue(resolution["stale_pid_file_removed"])

    def test_watcher_heartbeat_reports_missing_stale_and_fresh_health(self) -> None:
        module = load_watcher_module()
        current_time = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-runtime-heartbeat-") as temp_dir:
            root = Path(temp_dir)
            missing = module.auto_import_receipt_summary(
                root / "missing.json",
                current_time=current_time,
                stale_after_seconds=120,
            )
            stale_path = root / "stale.json"
            stale_path.write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": (current_time - timedelta(minutes=5)).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            stale = module.auto_import_receipt_summary(
                stale_path,
                current_time=current_time,
                stale_after_seconds=120,
            )
            fresh_path = root / "fresh.json"
            fresh_path.write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": (current_time - timedelta(seconds=30)).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            fresh = module.auto_import_receipt_summary(
                fresh_path,
                current_time=current_time,
                stale_after_seconds=120,
            )

        self.assertEqual("missing", missing["auto_import_heartbeat_state"])
        self.assertEqual("stale", stale["auto_import_heartbeat_state"])
        self.assertEqual(300.0, stale["auto_import_heartbeat_age_seconds"])
        self.assertEqual("fresh", fresh["auto_import_heartbeat_state"])
        self.assertEqual(30.0, fresh["auto_import_heartbeat_age_seconds"])
        self.assertEqual(
            "degraded_missing_heartbeat",
            module.watcher_health(
                process_alive=True,
                process_scan_complete=True,
                heartbeat_state="missing",
                launched_now=False,
            ),
        )
        self.assertEqual(
            "degraded_stale_heartbeat",
            module.watcher_health(
                process_alive=True,
                process_scan_complete=True,
                heartbeat_state="stale",
                launched_now=False,
            ),
        )
        self.assertEqual(
            "healthy",
            module.watcher_health(
                process_alive=True,
                process_scan_complete=True,
                heartbeat_state="fresh",
                launched_now=False,
                heartbeat_bound=True,
            ),
        )

    def test_fresh_heartbeat_must_match_pid_intake_instance_and_start_time(self) -> None:
        module = load_watcher_module()
        current_time = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
        watcher_started_at = (current_time - timedelta(seconds=60)).isoformat()
        with tempfile.TemporaryDirectory(prefix="windows-proof-runtime-binding-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "intake.json"
            receipt_path = root / "auto-import.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v2",
                        "contract_version": 2,
                        "supersedes_contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
                        "generated_at_utc": (current_time - timedelta(seconds=10)).isoformat(),
                        "status": "waiting_for_artifact",
                        "runtime_binding": {
                            "pid": 4242,
                            "started_at_utc": (current_time - timedelta(seconds=50)).isoformat(),
                            "watcher_instance_id": "instance-one",
                            "watcher_started_at_utc": watcher_started_at,
                            "intake_request": str(intake_request),
                        },
                    }
                ),
                encoding="utf-8",
            )
            matching = module.auto_import_receipt_summary(
                receipt_path,
                current_time=current_time,
                stale_after_seconds=120,
                expected_pid=4242,
                expected_intake_request=intake_request,
                expected_instance_id="instance-one",
                expected_watcher_started_at_utc=watcher_started_at,
            )
            mismatches = {
                "pid_mismatch": {"expected_pid": 5252},
                "intake_mismatch": {
                    "expected_intake_request": root / "different-intake.json"
                },
                "instance_mismatch": {"expected_instance_id": "instance-two"},
                "start_time_mismatch": {
                    "expected_watcher_started_at_utc": (
                        current_time - timedelta(seconds=59)
                    ).isoformat()
                },
            }
            mismatch_receipts = {}
            for expected_state, overrides in mismatches.items():
                arguments = {
                    "current_time": current_time,
                    "stale_after_seconds": 120,
                    "expected_pid": 4242,
                    "expected_intake_request": intake_request,
                    "expected_instance_id": "instance-one",
                    "expected_watcher_started_at_utc": watcher_started_at,
                    **overrides,
                }
                mismatch_receipts[expected_state] = module.auto_import_receipt_summary(
                    receipt_path,
                    **arguments,
                )

        self.assertEqual("fresh", matching["auto_import_heartbeat_state"])
        self.assertEqual("bound", matching["auto_import_heartbeat_binding_state"])
        self.assertTrue(matching["auto_import_heartbeat_bound"])
        for expected_state, receipt in mismatch_receipts.items():
            with self.subTest(expected_state=expected_state):
                self.assertEqual("fresh", receipt["auto_import_heartbeat_state"])
                self.assertEqual(
                    expected_state,
                    receipt["auto_import_heartbeat_binding_state"],
                )
                self.assertFalse(receipt["auto_import_heartbeat_bound"])
                self.assertEqual(
                    "degraded_unbound_heartbeat",
                    module.watcher_health(
                        process_alive=True,
                        process_scan_complete=True,
                        heartbeat_state="fresh",
                        launched_now=False,
                        heartbeat_bound=False,
                    ),
                )

    def test_legacy_fresh_receipt_and_state_cannot_bind_a_new_watcher(self) -> None:
        module = load_watcher_module()
        current_time = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory(prefix="windows-proof-runtime-v1-transition-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "intake.json"
            legacy_receipt = root / "legacy-auto-import.json"
            legacy_receipt.write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
                        "contract_version": 2,
                        "supersedes_contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
                        "generated_at_utc": current_time.isoformat(),
                        "status": "waiting_for_artifact",
                        "runtime_binding": {
                            "pid": 4242,
                            "started_at_utc": current_time.isoformat(),
                            "watcher_instance_id": "new-instance",
                            "watcher_started_at_utc": current_time.isoformat(),
                            "intake_request": str(intake_request),
                        },
                    }
                ),
                encoding="utf-8",
            )
            summary = module.auto_import_receipt_summary(
                legacy_receipt,
                current_time=current_time,
                expected_pid=4242,
                expected_intake_request=intake_request,
                expected_instance_id="new-instance",
                expected_watcher_started_at_utc=current_time.isoformat(),
            )

            legacy_state = root / "legacy-watcher.json"
            legacy_state.write_text(
                json.dumps(
                    {
                        "contract_name": module.WATCHER_CONTRACT_NAME_V1,
                        "pid": 4242,
                        "intake_request": module.receipt_path_text(intake_request),
                        "watcher_instance_id": "old-instance",
                        "watcher_process_started_at_utc": current_time.isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            resolution = module.restore_watcher_binding(
                {
                    "pid": 4242,
                    "watcher_instance_id": "",
                    "watcher_process_started_at_utc": "",
                },
                legacy_state,
                intake_request,
            )

        self.assertEqual("fresh", summary["auto_import_heartbeat_state"])
        self.assertEqual(
            "receipt_contract_mismatch",
            summary["auto_import_heartbeat_binding_state"],
        )
        self.assertFalse(summary["auto_import_heartbeat_bound"])
        self.assertEqual("", resolution["watcher_instance_id"])
        self.assertEqual("", resolution["watcher_process_started_at_utc"])

    def test_heartbeat_contract_requires_exact_v2_version_transition(self) -> None:
        module = load_watcher_module()
        current_time = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory(prefix="windows-proof-runtime-contract-binding-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "intake.json"
            receipt_path = root / "auto-import.json"
            baseline = {
                "contract_name": module.AUTO_IMPORT_CONTRACT_NAME,
                "contract_version": 2,
                "supersedes_contract_name": module.AUTO_IMPORT_CONTRACT_NAME_V1,
                "generated_at_utc": current_time.isoformat(),
                "status": "waiting_for_artifact",
                "runtime_binding": {
                    "pid": 4242,
                    "started_at_utc": current_time.isoformat(),
                    "watcher_instance_id": "instance-one",
                    "watcher_started_at_utc": current_time.isoformat(),
                    "intake_request": str(intake_request),
                },
            }
            invalid_contracts = {
                "legacy_name": {
                    "contract_name": module.AUTO_IMPORT_CONTRACT_NAME_V1,
                },
                "wrong_version": {"contract_version": 1},
                "wrong_transition": {
                    "supersedes_contract_name": "unexpected-contract"
                },
            }
            summaries = {}
            for case, overrides in invalid_contracts.items():
                receipt_path.write_text(
                    json.dumps({**baseline, **overrides}),
                    encoding="utf-8",
                )
                summaries[case] = module.auto_import_receipt_summary(
                    receipt_path,
                    current_time=current_time,
                    expected_pid=4242,
                    expected_intake_request=intake_request,
                    expected_instance_id="instance-one",
                    expected_watcher_started_at_utc=current_time.isoformat(),
                )

        for case, summary in summaries.items():
            with self.subTest(case=case):
                self.assertEqual(
                    "receipt_contract_mismatch",
                    summary["auto_import_heartbeat_binding_state"],
                )
                self.assertFalse(summary["auto_import_heartbeat_bound"])

    def test_process_scan_carries_observed_watcher_instance_binding(self) -> None:
        module = load_watcher_module()
        intake_request = ROOT / "intake.json"
        started_at = "2026-07-17T12:00:00Z"
        command = module.watcher_command(
            intake_request,
            wait_seconds=900,
            poll_seconds=30,
            refresh_intake_request=True,
            watcher_instance_id="instance-one",
            watcher_started_at_utc=started_at,
        )
        process_listing = f"4242 {' '.join(command)}\n".encode("utf-8")
        with mock.patch.object(
            module,
            "bounded_subprocess_capture",
            return_value={
                "stdout": process_listing,
                "returncode": 0,
                "complete": True,
                "timed_out": False,
                "output_truncated": False,
                "cleanup_complete": True,
                "process_reaped": True,
                "error_code": "",
            },
        ), mock.patch.object(module, "is_process_alive", return_value=True):
            scan = module.scan_matching_watcher_pids(command)

        self.assertEqual([4242], scan["pids"])
        self.assertEqual(
            {
                "watcher_instance_id": "instance-one",
                "watcher_process_started_at_utc": started_at,
            },
            scan["bindings_by_pid"]["4242"],
        )

    def test_watcher_payload_exposes_health_pid_evidence_and_portable_paths(self) -> None:
        module = load_watcher_module()
        heartbeat = {
            "auto_import_receipt_path": "published/auto-import.json",
            "auto_import_receipt_exists": True,
            "auto_import_receipt_status": "waiting_for_artifact",
            "auto_import_receipt_generated_at_utc": "2026-07-17T12:00:00Z",
            "auto_import_heartbeat_state": "stale",
            "auto_import_heartbeat_age_seconds": 300.0,
            "auto_import_heartbeat_stale_after_seconds": 120,
            "auto_import_heartbeat_fresh": False,
            "auto_import_heartbeat_stale": True,
            "auto_import_heartbeat_binding_state": "instance_mismatch",
            "auto_import_heartbeat_bound": False,
        }
        resolution = {
            "process_scan_complete": True,
            "process_scan_error_code": "",
            "pid_file_present_before_resolution": True,
            "pid_file_state_before_resolution": "valid",
            "pid_file_recorded_pid": 4242,
            "stale_pid_detected": True,
            "stale_pid_reason": "recorded_pid_not_alive",
            "stale_pid_file_removed": True,
            "watcher_instance_id": "instance-one",
            "watcher_process_started_at_utc": "2026-07-17T11:55:00Z",
        }
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-runtime-payload-") as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(module, "auto_import_receipt_summary", return_value=heartbeat):
                payload = module.build_payload(
                    status="running",
                    action="status",
                    pid=5252,
                    process_alive=True,
                    matching_process_pids=[5252],
                    command=["python3", str(root / "watcher.py"), "--intake-request", str(root / "intake.json")],
                    state_path=root / "state.json",
                    pid_file=root / "watcher.pid",
                    log_file=root / "watcher.log",
                    intake_request=root / "intake.json",
                    wait_seconds=900,
                    poll_seconds=30,
                    refresh_intake_request=True,
                    resolution=resolution,
                )
            serialized = json.dumps(payload, sort_keys=True)

        self.assertEqual("degraded_stale_heartbeat", payload["watcher_health"])
        self.assertEqual(module.WATCHER_CONTRACT_NAME, payload["contract_name"])
        self.assertEqual(2, payload["contract_version"])
        self.assertEqual(
            module.WATCHER_CONTRACT_NAME_V1,
            payload["supersedes_contract_name"],
        )
        self.assertTrue(payload["stale_pid_detected"])
        self.assertTrue(payload["stale_pid_file_removed"])
        self.assertNotIn(str(root), serialized)


if __name__ == "__main__":
    unittest.main()
