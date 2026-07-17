import argparse
import importlib.util
import json
import os
import subprocess
import struct
import tempfile
import threading
import time
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_windows_installer_visual_audit.py")
IMPORT_SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/import_windows_installer_gold_proof_artifact.py")
INTAKE_SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/materialize_windows_installer_visual_audit_intake_request.py")
AUTO_IMPORT_SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/auto_import_windows_installer_gold_proof.py")
VERIFY_INTAKE_SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_windows_installer_visual_audit_intake_request.py")
RELEASE_READY_SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_windows_installer_visual_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_import_module():
    spec = importlib.util.spec_from_file_location("import_windows_installer_gold_proof_artifact", IMPORT_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_intake_module():
    spec = importlib.util.spec_from_file_location("materialize_windows_installer_visual_audit_intake_request", INTAKE_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_auto_import_module():
    spec = importlib.util.spec_from_file_location("auto_import_windows_installer_gold_proof", AUTO_IMPORT_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def release_containment_probe(marker: Path) -> None:
    Path(str(marker) + ".release").write_text("release\n", encoding="utf-8")
    time.sleep(0.5)


def load_verify_intake_module():
    spec = importlib.util.spec_from_file_location(
        "verify_windows_installer_visual_audit_intake_request",
        VERIFY_INTAKE_SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_windows_gold_proof_fixture(
    root: Path,
    screenshot_rows: list[dict[str, object]],
) -> tuple[Path, Path]:
    artifact = root / "artifact"
    visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
    startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
    visual_root.mkdir(parents=True)
    startup_root.mkdir(parents=True)
    artifact_digest = "a" * 64
    (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "platform": "windows",
                "hostClass": "native-windows-11",
                "artifactDigest": f"sha256:{artifact_digest}",
            }
        ),
        encoding="utf-8",
    )
    (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "platform": "windows",
                "hostClass": "native-windows-11",
                "artifactSha256": artifact_digest,
                "screenshots": screenshot_rows,
            }
        ),
        encoding="utf-8",
    )
    return artifact, visual_root


def valid_png_bytes(*, width: int = 320, height: int = 180, token: int = 1) -> bytes:
    color = bytes(((token * 31) % 251, (token * 67) % 251, (token * 97) % 251))
    raw = b"".join(b"\x00" + color * width for _ in range(height))

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def write_valid_png(path: Path, *, token: int = 1) -> None:
    path.write_bytes(valid_png_bytes(token=token))


def valid_jpeg_bytes(*, width: int = 320, height: int = 180, token: int = 1) -> bytes:
    frame = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + bytes([8])
        + struct.pack(">HH", height, width)
        + bytes([3, 1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0])
    )
    scan = (
        b"\xff\xda"
        + struct.pack(">H", 12)
        + bytes([3, 1, 0, 2, 0, 3, 0, 0, 63, 0])
        + bytes([token & 0x7F, (token * 3) & 0x7F, (token * 7) & 0x7F])
    )
    return b"\xff\xd8" + frame + scan + b"\xff\xd9"


def proof_generation_entries(module, downloads_root: Path, *, token: int) -> list[tuple[dict[str, object], Path]]:
    artifact_digest = f"{token:064x}"[-64:]
    startup_data = json.dumps(
        {
            "status": "pass",
            "platform": "windows",
            "hostClass": "native-windows-11",
            "artifactDigest": f"sha256:{artifact_digest}",
            "token": token,
        },
        sort_keys=True,
    ).encode("utf-8")
    visual_data = json.dumps(
        {
            "status": "pass",
            "platform": "windows",
            "hostClass": "native-windows-11",
            "artifactSha256": artifact_digest,
            "token": token,
            "screenshots": [{"path": "capture.png"}],
        },
        sort_keys=True,
    ).encode("utf-8")
    image_data = valid_png_bytes(token=token)

    def snapshot(data: bytes, **extra: object) -> dict[str, object]:
        return {
            "data": data,
            "sha256": module.hashlib.sha256(data).hexdigest(),
            **extra,
        }

    return [
        (
            snapshot(startup_data),
            downloads_root / "startup-smoke" / module.STARTUP_RECEIPT_NAME,
        ),
        (
            snapshot(visual_data),
            downloads_root / "visual-audit" / "windows-installer" / module.VISUAL_SOURCE_NAME,
        ),
        (
            snapshot(
                image_data,
                image_metadata={
                    "format": "png",
                    "width": 320,
                    "height": 180,
                    "size_bytes": len(image_data),
                },
            ),
            downloads_root / "visual-audit" / "windows-installer" / "capture.png",
        ),
    ]


def write_valid_gold_proof_zip(
    path: Path,
    *,
    digest: str = "a" * 64,
    token: int = 1,
) -> None:
    visual_prefix = "Chummer.Portal/downloads/visual-audit/windows-installer"
    startup_name = "Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{visual_prefix}/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            json.dumps(
                {
                    "status": "pass",
                    "platform": "windows",
                    "hostClass": "native-windows-11",
                    "artifactSha256": digest,
                    "screenshots": [{"path": "capture.png", "surface": "install-progress"}],
                }
            ),
        )
        archive.writestr(f"{visual_prefix}/capture.png", valid_png_bytes(token=token))
        archive.writestr(
            startup_name,
            json.dumps(
                {
                    "status": "pass",
                    "platform": "windows",
                    "hostClass": "native-windows-11",
                    "artifactDigest": f"sha256:{digest}",
                }
            ),
        )


def fake_bound_python_result(
    module,
    bound_argv: list[str],
    *,
    returncode: int = 0,
    stdout: str = "ok\n",
    stderr: str = "",
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    execution_argv = [
        "/proc/self/fd/101",
        "-I",
        "-c",
        module.SEALED_PYTHON_LAUNCHER_SOURCE,
        bound_argv[1],
        "102",
        "103",
        *bound_argv[2:],
    ]
    return (
        subprocess.CompletedProcess(execution_argv, returncode, stdout, stderr),
        {
            "transport": "sealed_memfd",
            "bound_argv": list(bound_argv),
            "execution_argv": execution_argv,
            "logical_script_path": bound_argv[1],
            "launcher_sha256": module.SEALED_PYTHON_LAUNCHER_SHA256,
            "process_group_mode": "linux_child_subreaper_descendant_sweep",
            "timed_out": returncode == 124,
            "containment": {
                "subreaper_enabled": True,
                "remaining_descendant_count": 0,
                "zero_descendants_proven": True,
            },
        },
    )


class WindowsInstallerVisualAuditTests(unittest.TestCase):
    def test_windows_operator_request_artifacts_flags_stale_delivery_for_resend(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-operator-resend-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            delivery_root = root / "telegram"
            delivery_root.mkdir(parents=True, exist_ok=True)
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            (delivery_root / "windows.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": "2026-07-04T20:58:05Z",
                        "text_sha256": module.hashlib.sha256("stale\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(
                json.dumps(
                    {
                        "preferred_drop_path": str(root / "incoming" / "windows.zip"),
                        "promoted_installer_sha256": "a" * 64,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text_path),
                            "current_metadata_path": str(ask_metadata_path),
                            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file current.txt --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                f"bundle.zip --intake-request {intake_request} --verify"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {intake_request} --wait-seconds 900"
                            ),
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request), mock.patch.object(
                module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root
            ):
                payload = module.windows_operator_request_artifacts()

        self.assertTrue(payload["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(payload["operator_ask_delivery_matches_current_text"])
        self.assertTrue(payload["operator_ask_delivery_needs_resend"])
        self.assertFalse(payload["pass"])
        self.assertIn("operator ask delivery no longer matches current text", payload["failures"])
        self.assertEqual(
            "python3 scripts/send_telegram_message_via_ea.py --text-file current.txt --receipt-name windows.receipt.json",
            payload["operator_ask_resend_command"],
        )

    def test_windows_operator_request_artifacts_marks_prepared_recovery_pack_pass(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-operator-pass-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(
                json.dumps(
                    {
                        "preferred_drop_path": str(root / "incoming" / "windows.zip"),
                        "promoted_installer_sha256": "b" * 64,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text_path),
                            "current_metadata_path": str(ask_metadata_path),
                            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file current.txt --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                f"bundle.zip --intake-request {intake_request} --verify"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {intake_request} --wait-seconds 900"
                            ),
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request), mock.patch.object(
                module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", root / "telegram"
            ):
                payload = module.windows_operator_request_artifacts()

        self.assertTrue(payload["pass"])
        self.assertEqual([], payload["failures"])

    def test_windows_operator_request_artifacts_reads_watcher_state(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-state-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            watcher_state_path = root / ".state" / "windows_installer_gold_proof_watcher.generated.json"
            auto_import_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T14:39:02Z",
                        "status": "running",
                        "pid": 1866861,
                        "process_alive": True,
                        "matching_process_pids": [1866861],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "watcher discovered by pid file or process scan",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            auto_import_path.parent.mkdir(parents=True, exist_ok=True)
            auto_import_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T14:39:03Z",
                        "status": "waiting_for_artifact",
                        "actionable_candidate_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(
                json.dumps(
                    {
                        "preferred_drop_path": str(root / "incoming" / "windows.zip"),
                        "promoted_installer_sha256": "b" * 64,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text_path),
                            "current_metadata_path": str(ask_metadata_path),
                            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file current.txt --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                f"bundle.zip --intake-request {intake_request} --verify"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {intake_request} --wait-seconds 900"
                            ),
                            "auto_import_command": "python3 auto-import-status",
                            "watcher_state_path": str(watcher_state_path),
                            "watcher_start_command": "python3 watcher-start",
                            "watcher_status_command": "python3 watcher-status",
                            "watcher_stop_command": "python3 watcher-stop",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request),
                mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT", auto_import_path),
                mock.patch.object(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", root / "telegram"),
                mock.patch.object(
                    module.subprocess,
                    "run",
                    side_effect=AssertionError("default verification must not run operator-state commands"),
                ),
            ):
                payload = module.windows_operator_request_artifacts()

        self.assertEqual(str(watcher_state_path), payload["watcher_state_receipt_path"])
        self.assertTrue(payload["watcher_state_receipt_exists"])
        self.assertEqual("running", payload["watcher_status"])
        self.assertEqual(1866861, payload["watcher_pid"])
        self.assertEqual(1, payload["watcher_matching_process_count"])
        self.assertEqual(0, payload["watcher_duplicate_process_count"])
        self.assertFalse(payload["watcher_attention_required"])
        self.assertFalse(payload["operator_state_refresh_requested"])
        self.assertEqual("2026-07-06T14:39:03Z", payload["auto_import_receipt_generated_at_utc"])
        self.assertEqual("waiting_for_artifact", payload["auto_import_receipt_status"])

    def test_windows_operator_request_artifacts_refreshes_watcher_state_via_status_command(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-watcher-refresh-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            watcher_state_path = root / ".state" / "windows_installer_gold_proof_watcher.generated.json"
            auto_import_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "running",
                        "pid": 1111,
                        "process_alive": True,
                        "matching_process_pids": [1111],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "stale watcher snapshot",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            auto_import_path.parent.mkdir(parents=True, exist_ok=True)
            auto_import_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:23:45Z",
                        "status": "waiting_for_artifact",
                        "actionable_candidate_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(
                json.dumps(
                    {
                        "preferred_drop_path": str(root / "incoming" / "windows.zip"),
                        "promoted_installer_sha256": "b" * 64,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text_path),
                            "current_metadata_path": str(ask_metadata_path),
                            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file current.txt --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                f"bundle.zip --intake-request {intake_request} --verify"
                            ),
                            "auto_import_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {intake_request}"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {intake_request} --wait-seconds 900"
                            ),
                            "watcher_state_path": str(watcher_state_path),
                            "watcher_start_command": "python3 watcher-start",
                            "watcher_status_command": "python3 watcher-status --intake-request /tmp/intake.json",
                            "watcher_stop_command": "python3 watcher-stop",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            run_calls: list[tuple[list[str], dict[str, str] | None]] = []

            def fake_run(args, **_kwargs):
                command = list(args)
                env = _kwargs.get("env")
                run_calls.append((command, env if isinstance(env, dict) else None))
                if command[:2] == ["python3", "scripts/auto_import_windows_installer_gold_proof.py"]:
                    auto_import_path.write_text(
                        json.dumps(
                            {
                                "generated_at_utc": "2026-07-06T15:24:12Z",
                                "status": "candidate_available",
                                "actionable_candidate_count": 1,
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif command[:2] == ["python3", "watcher-status"]:
                    watcher_state_path.write_text(
                        json.dumps(
                            {
                                "generated_at_utc": "2026-07-06T15:24:14Z",
                                "status": "running",
                                "pid": 2086931,
                                "process_alive": True,
                                "matching_process_pids": [2086931],
                                "matching_process_count": 1,
                                "duplicate_process_pids": [],
                                "duplicate_process_count": 0,
                                "note": "watcher discovered by pid file or process scan",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request),
                mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT", auto_import_path),
                mock.patch.object(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", root / "telegram"),
                mock.patch.object(module, "auto_import_side_effects_paused", return_value=False),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            ):
                payload = module.windows_operator_request_artifacts(refresh_operator_state=True)

        self.assertEqual("2026-07-06T15:24:14Z", payload["watcher_state_receipt_generated_at_utc"])
        self.assertEqual(2086931, payload["watcher_pid"])
        self.assertEqual("watcher discovered by pid file or process scan", payload["watcher_note"])
        self.assertEqual("2026-07-06T15:24:12Z", payload["auto_import_receipt_generated_at_utc"])
        self.assertEqual("candidate_available", payload["auto_import_receipt_status"])
        self.assertEqual(1, payload["auto_import_actionable_candidate_count"])
        self.assertTrue(payload["operator_state_refresh_requested"])
        self.assertEqual(
            [["python3", "scripts/auto_import_windows_installer_gold_proof.py"], ["python3", "watcher-status"]],
            [command[:2] for command, _env in run_calls],
        )
        self.assertEqual(2, len(run_calls))
        for _command, env in run_calls:
            self.assertIsInstance(env, dict)
            self.assertTrue(env)
            self.assertTrue(str(env.get("TMPDIR") or "").strip())

    def test_main_threads_explicit_operator_state_refresh_opt_in(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-refresh-opt-in-") as temp_dir:
            root = Path(temp_dir)
            output = root / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            args = argparse.Namespace(
                release_channel=root / "RELEASE_CHANNEL.generated.json",
                portal_release_channel=root / "portal" / "RELEASE_CHANNEL.generated.json",
                downloads_root=root / "downloads",
                startup_receipt=root / "startup-smoke.receipt.json",
                source=root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                output=output,
                refresh_operator_state=True,
                expected_verifier_sha256="a" * 64,
            )
            with (
                mock.patch.object(module, "parse_args", return_value=args),
                mock.patch.object(
                    module,
                    "build_payload",
                    return_value={"status": "pass"},
                ) as build_payload,
            ):
                exit_code = module.main()

            self.assertTrue(output.is_file())

        self.assertEqual(0, exit_code)
        build_payload.assert_called_once_with(
            release_channel_path=args.release_channel,
            portal_release_channel_path=args.portal_release_channel,
            downloads_root=args.downloads_root,
            startup_receipt_path=args.startup_receipt,
            source_path=args.source,
            refresh_operator_state=True,
            expected_verifier_sha256="a" * 64,
        )

    def test_visual_audit_verifier_binding_rejects_stale_expected_bytes(self) -> None:
        module = load_module()
        actual_sha256 = module.sha256_file(SCRIPT_PATH)
        stale_sha256 = "0" * 64 if actual_sha256 != "0" * 64 else "1" * 64

        current_binding, current_failures = module.verifier_binding(actual_sha256)
        stale_binding, stale_failures = module.verifier_binding(stale_sha256)

        self.assertEqual([], current_failures)
        self.assertEqual("pass", current_binding["status"])
        self.assertTrue(current_binding["sha256_matches"])
        self.assertEqual("observational_default", current_binding["execution_mode"])
        self.assertEqual(actual_sha256, current_binding["actual_sha256"])
        self.assertEqual(
            [
                "Windows visual-audit verifier bytes do not match the SHA-256-bound intake request"
            ],
            stale_failures,
        )
        self.assertEqual("fail", stale_binding["status"])
        self.assertFalse(stale_binding["sha256_matches"])

    def test_default_authority_selection_prefers_existing_hub_manifest(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-release-authority-") as temp_dir:
            root = Path(temp_dir)
            hub = root / "hub" / "RELEASE_CHANNEL.generated.json"
            portal = root / "portal" / "RELEASE_CHANNEL.generated.json"
            hub.parent.mkdir(parents=True)
            portal.parent.mkdir(parents=True)
            hub.write_text("{}\n", encoding="utf-8")
            portal.write_text("{}\n", encoding="utf-8")
            os.utime(portal, (hub.stat().st_mtime + 60, hub.stat().st_mtime + 60))

            selected = module.select_authoritative_release_channel_path(hub, portal)

        self.assertEqual(hub, selected)

    def test_promoted_digest_prefers_authoritative_manifest_over_shelf_bytes(self) -> None:
        module = load_module()

        self.assertEqual(
            "a" * 64,
            module.effective_promoted_artifact_sha256(
                {"sha256": "a" * 64},
                "b" * 64,
            ),
        )
        self.assertEqual(
            "b" * 64,
            module.effective_promoted_artifact_sha256({}, "b" * 64),
        )

    def test_visual_audit_keeps_hub_binding_and_fails_portal_disagreement(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-release-projection-") as temp_dir:
            root = Path(temp_dir)
            downloads = root / "downloads"
            files = downloads / "files"
            files.mkdir(parents=True)
            installer_name = "chummer-avalonia-win-x64-installer.exe"
            installer_path = files / installer_name
            installer_path.write_bytes(b"newer portal shelf bytes")
            actual_sha = module.sha256_file(installer_path)
            hub_sha = "a" * 64
            portal_sha = "b" * 64
            hub = root / "hub" / "RELEASE_CHANNEL.generated.json"
            portal = downloads / "RELEASE_CHANNEL.generated.json"
            hub.parent.mkdir(parents=True)
            hub.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-hub-authority",
                        "channelId": "preview",
                        "artifacts": [
                            {
                                "artifactId": "avalonia-win-x64-installer",
                                "platform": "windows",
                                "kind": "installer",
                                "fileName": installer_name,
                                "sha256": hub_sha,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            portal.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-newer-portal",
                        "channelId": "preview",
                        "artifacts": [
                            {
                                "artifactId": "avalonia-win-x64-installer",
                                "platform": "windows",
                                "kind": "installer",
                                "fileName": installer_name,
                                "sha256": portal_sha,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                module,
                "windows_operator_request_artifacts",
                return_value={},
            ):
                payload = module.build_payload(
                    release_channel_path=hub,
                    portal_release_channel_path=portal,
                    downloads_root=downloads,
                    startup_receipt_path=root / "startup.json",
                    source_path=root / "visual.json",
                )

        self.assertEqual(hub_sha, payload["required_promoted_digest"])
        self.assertEqual(hub_sha, payload["artifact"]["effectiveSha256"])
        self.assertEqual(actual_sha, payload["artifact"]["actualSha256"])
        self.assertEqual("run-hub-authority", payload["release"]["version"])
        self.assertEqual("release_channel_manifest", payload["release"]["bindingAuthority"])
        self.assertFalse(payload["releaseProjection"]["matchesAuthority"])
        self.assertEqual("disagrees", payload["releaseProjection"]["status"])
        self.assertEqual(portal_sha, payload["releaseProjection"]["projectionBinding"]["sha256"])
        self.assertIn(
            "Portal release channel Windows installer binding disagrees with authoritative release channel",
            payload["failures"],
        )
        self.assertIn(
            "promoted Windows installer manifest sha256 does not match artifact bytes",
            payload["failures"],
        )

    def test_release_ready_windows_gate_names_hub_authority_and_portal_projection(self) -> None:
        script = RELEASE_READY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn(
            'REGISTRY_RELEASE_CHANNEL = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"',
            script,
        )
        self.assertIn(
            'PORTAL_RELEASE_CHANNEL = LIVE_DOWNLOADS_SHELF_DIR / "RELEASE_CHANNEL.generated.json"',
            script,
        )
        self.assertIn('f"--release-channel {REGISTRY_RELEASE_CHANNEL} "', script)
        self.assertIn('f"--portal-release-channel {PORTAL_RELEASE_CHANNEL} "', script)

    def test_intake_forwards_portal_projection_without_replacing_authority(self) -> None:
        module = load_intake_module()
        promoted_sha = "c" * 64
        projection = {
            "status": "disagrees",
            "matchesAuthority": False,
            "authorityBinding": {"sha256": promoted_sha},
            "projectionBinding": {"sha256": "d" * 64},
        }
        with tempfile.TemporaryDirectory(prefix="windows-intake-authority-") as temp_dir:
            root = Path(temp_dir)
            release_channel = root / "hub" / "RELEASE_CHANNEL.generated.json"
            portal_release_channel = root / "portal" / "RELEASE_CHANNEL.generated.json"
            release_channel.parent.mkdir(parents=True)
            portal_release_channel.parent.mkdir(parents=True)
            release_channel.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-hub",
                        "channelId": "preview",
                    }
                ),
                encoding="utf-8",
            )
            portal_release_channel.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(
                module.visual_audit,
                "build_payload",
                return_value={
                    "status": "fail",
                    "artifact": {
                        "fileName": "chummer-avalonia-win-x64-installer.exe",
                        "sha256": promoted_sha,
                        "effectiveSha256": promoted_sha,
                        "actualSha256": promoted_sha,
                    },
                    "visualAuditSource": {},
                    "startupReceipt": {},
                    "failures": [
                        "Portal release channel Windows installer binding disagrees with authoritative release channel"
                    ],
                    "releaseProjection": projection,
                },
            ) as build_payload:
                payload = module.build_request(
                    release_channel=release_channel,
                    portal_release_channel=portal_release_channel,
                    downloads_root=root / "downloads",
                    startup_receipt=root / "startup.json",
                    source=root / "visual.json",
                    request_output=root / "request.json",
                    discovery_roots=[],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "incoming",
                )

        build_payload.assert_called_once_with(
            release_channel_path=release_channel,
            portal_release_channel_path=portal_release_channel,
            downloads_root=root / "downloads",
            startup_receipt_path=root / "startup.json",
            source_path=root / "visual.json",
        )
        self.assertEqual("release_channel_manifest", payload["release_channel_binding_authority"])
        self.assertIs(payload["portal_release_channel_projection_matches_authority"], False)
        self.assertEqual(projection, payload["portal_release_channel_projection"])
        self.assertEqual(promoted_sha, payload["promoted_installer_sha256"])

    def test_intake_default_discovery_roots_are_portable(self) -> None:
        module = load_intake_module()

        self.assertEqual(
            (
                module.DEFAULT_DEDICATED_DROP_ROOT,
                Path("/tmp"),
            ),
            module.DEFAULT_DISCOVERY_ROOTS,
        )
        self.assertTrue(all("/home/" not in str(path) for path in module.DEFAULT_DISCOVERY_ROOTS))

    def test_intake_artifact_discovery_roots_include_common_operator_sync_locations(self) -> None:
        module = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-roots-") as temp_dir:
            home = Path(temp_dir) / "home"
            dedicated = Path(temp_dir) / "runtime" / "incoming_windows_installer_gold_proof"
            with mock.patch("pathlib.Path.home", return_value=home):
                roots = module.artifact_discovery_roots(dedicated)

        self.assertEqual(
            [
                dedicated,
                Path("/tmp"),
                home / "Downloads",
                home / "pCloud Drive" / "EA",
            ],
            roots,
        )

    def test_intake_gitignored_runtime_root_accepts_run_services_and_workspace_state(self) -> None:
        module = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-gitignored-") as temp_dir:
            runtime_root = Path(temp_dir) / "chummer.run-services"
            workspace_root = runtime_root.parent
            with mock.patch.object(module, "ROOT", runtime_root), mock.patch.object(module, "WORKSPACE_ROOT", workspace_root):
                self.assertTrue(module.is_gitignored_runtime_root(runtime_root / ".state" / "incoming"))
                self.assertTrue(module.is_gitignored_runtime_root(workspace_root / ".state" / "incoming"))
                self.assertFalse(module.is_gitignored_runtime_root(workspace_root / "Downloads"))

    def test_intake_discover_files_uses_bounded_walk_instead_of_path_rglob(self) -> None:
        module = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-discovery-") as temp_dir:
            root = Path(temp_dir)
            shallow = root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"
            shallow.parent.mkdir(parents=True)
            shallow.write_bytes(b"shallow")

            deep = root
            for index in range(module.DISCOVERY_MAX_DEPTH + 2):
                deep = deep / f"deep-{index}"
            deep.mkdir(parents=True)
            too_deep = deep / "windows-installer-gold-proof-too-deep.zip"
            too_deep.write_bytes(b"too-deep")

            with mock.patch("pathlib.Path.rglob", side_effect=AssertionError("discover_files should not use Path.rglob")):
                discovered = module.discover_files("*windows-installer-gold-proof*.zip", [root])

        self.assertIn(shallow, discovered)
        self.assertNotIn(too_deep, discovered)

    def test_intake_discover_files_can_skip_recursive_walk_for_broad_roots(self) -> None:
        module = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-shallow-") as temp_dir:
            root = Path(temp_dir) / "Downloads"
            root.mkdir(parents=True)
            preferred = root / "windows-installer-gold-proof-deadbeef.zip"
            preferred.write_bytes(b"preferred")

            with mock.patch.object(module, "walk_candidate_files", side_effect=AssertionError("broad roots should not recurse")):
                discovered = module.discover_files(
                    "*windows-installer-gold-proof*.zip",
                    [root],
                    recursive_roots=[],
                )

        self.assertEqual([preferred], discovered)

    def _write_release_fixture(self, root: Path) -> tuple[Path, Path, str]:
        downloads_root = root / "downloads"
        files_root = downloads_root / "files"
        files_root.mkdir(parents=True)
        artifact = files_root / "chummer-avalonia-win-x64-installer.exe"
        artifact.write_bytes(b"windows installer bytes")
        sha = load_module().sha256_file(artifact)
        release_channel = downloads_root / "RELEASE_CHANNEL.generated.json"
        release_channel.write_text(
            json.dumps(
                {
                    "version": "run-test",
                    "channelId": "preview",
                    "artifacts": [
                        {
                            "artifactId": "avalonia-win-x64-installer",
                            "fileName": artifact.name,
                            "platform": "windows",
                            "kind": "installer",
                            "sha256": sha,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return downloads_root, release_channel, sha

    def _write_windows_visual_source_fixture(
        self,
        downloads_root: Path,
        *,
        source_artifact_sha: str,
    ) -> Path:
        source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        (source.parent / "old-progress.png").write_bytes(b"old-progress")
        (source.parent / "old-completion.png").write_bytes(b"old-completion")
        source.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "platform": "windows",
                    "hostClass": "native-windows-11",
                    "artifactSha256": source_artifact_sha,
                    "screenshots": [
                        {
                            "path": "old-progress.png",
                            "surface": "install-progress",
                            "dpiScale": 1.0,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                        },
                        {
                            "path": "old-completion.png",
                            "surface": "completion",
                            "dpiScale": 1.5,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return source

    def _write_valid_windows_visual_source_fixture(
        self,
        downloads_root: Path,
        *,
        source_artifact_sha: str,
    ) -> Path:
        source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        for name in [
            "progress-default.png",
            "progress-scaled.png",
            "completion-default.png",
            "completion-scaled.png",
        ]:
            (source.parent / name).write_bytes(name.encode("utf-8"))
        source.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "platform": "windows",
                    "hostClass": "native-windows-11",
                    "artifactSha256": source_artifact_sha,
                    "screenshots": [
                        {
                            "path": "progress-default.png",
                            "surface": "install-progress",
                            "dpiScale": 1.0,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                        {
                            "path": "progress-scaled.png",
                            "surface": "install-progress",
                            "dpiScale": 1.5,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                        {
                            "path": "completion-default.png",
                            "surface": "completion",
                            "dpiScale": 1.0,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                        {
                            "path": "completion-scaled.png",
                            "surface": "completion",
                            "dpiScale": 1.5,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return source

    def _build_windows_visual_intake_request_payload(
        self,
        root: Path,
        *,
        startup_receipt_payload: dict[str, object] | None = None,
        source_artifact_sha: str | None = None,
    ) -> tuple[dict[str, object], Path, str]:
        intake = load_intake_module()
        downloads_root, release_channel, sha = self._write_release_fixture(root)
        startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup_payload = {"status": "pass", "artifactDigest": f"sha256:{sha}"}
        if startup_receipt_payload:
            startup_payload.update(startup_receipt_payload)
        startup.write_text(json.dumps(startup_payload), encoding="utf-8")
        source = self._write_windows_visual_source_fixture(
            downloads_root,
            source_artifact_sha=source_artifact_sha or sha,
        )
        receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
        original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
        intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
        try:
            payload = intake.build_request(
                release_channel=release_channel,
                downloads_root=downloads_root,
                startup_receipt=startup,
                source=source,
                request_output=receipt_path,
                discovery_roots=[root / "drop"],
                nightly_root=root / "nightly",
                dedicated_drop_root=root / "drop",
            )
            payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                payload["operator_telegram_draft"]
            )
        finally:
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root
        return payload, receipt_path, sha

    def _write_current_windows_visual_audit_receipt(
        self,
        path: Path,
        *,
        status: str,
        source_digest_matches_promoted: bool,
        manifest_artifact_sha: str | None = None,
        startup_status: str = "pass",
        startup_digest_matches_promoted: bool = True,
        visual_status: str = "pass",
        visual_digest_matches_promoted: bool = True,
        failures: list[str] | None = None,
        failed_gates: list[str] | None = None,
        explicit_pass: bool | None = True,
        artifact_sha: str = "a" * 64,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "status": status,
            "required_promoted_digest": artifact_sha,
            "manifest_promoted_digest": manifest_artifact_sha or artifact_sha,
            "artifact": {
                "sha256": manifest_artifact_sha or artifact_sha,
                "actualSha256": artifact_sha,
                "effectiveSha256": artifact_sha,
            },
            "source_digest_matches_promoted": source_digest_matches_promoted,
            "startupReceipt": {
                "status": startup_status,
                "verificationDisposition": "pass",
                "skipClass": "",
                "artifactDigest": f"sha256:{artifact_sha}",
                "artifactDigestMatchesPromoted": startup_digest_matches_promoted,
            },
            "visualAuditSource": {
                "exists": True,
                "status": visual_status,
                "platform": "windows",
                "hostClass": "native-windows-11",
                "artifactSha256": artifact_sha,
                "artifactDigestMatchesPromoted": visual_digest_matches_promoted,
                "requiredSurfaces": ["install-progress", "completion"],
                "screenshotCount": 4,
                "defaultDpiScreenshotCount": 2,
                "scaledDpiScreenshotCount": 2,
            },
            "failures": failures or [],
            "failed_gates": failed_gates or [],
        }
        if explicit_pass is not None:
            payload["pass"] = explicit_pass
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_incompatible_host_startup_receipt_blocks_visual_gold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "skipped",
                        "verificationDisposition": "incompatible_host",
                        "skipClass": "incompatible_host",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            )

        self.assertEqual("fail", payload["status"])
        self.assertEqual(
            "Native Windows visual audit still failing: Windows startup receipt is an incompatible-host skip, not native proof",
            payload["summary"],
        )
        self.assertIn("Windows startup receipt is an incompatible-host skip, not native proof", payload["failures"])
        self.assertIn("Windows installer visual audit source is missing", " ".join(payload["failures"]))
        self.assertIn("nextActions", payload)
        self.assertTrue(any("capture_windows_installer_visual_audit.ps1" in item for item in payload["nextActions"]))
        self.assertTrue(any("capture_windows_installer_gold_proof.ps1" in item for item in payload["nextActions"]))
        self.assertTrue(any("-CaptureRequiredSet" in item for item in payload["nextActions"]))
        self.assertTrue(any("import_windows_installer_gold_proof_artifact.py" in item for item in payload["nextActions"]))
        self.assertTrue(any("native Windows proof runner" in item for item in payload["nextActions"]))
        self.assertTrue(any("does not publish downloads" in item for item in payload["nextActions"]))
        self.assertTrue(any("byte-identical" in item for item in payload["nextActions"]))
        self.assertTrue(any("native Windows pass" in item for item in payload["nextActions"]))

    def test_missing_release_channel_receipt_is_reported_structurally(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-missing-release-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir(parents=True)
            startup.write_text(json.dumps({"status": "pass", "artifactDigest": "sha256:" + ("a" * 64)}), encoding="utf-8")
            payload = module.build_payload(
                release_channel_path=downloads_root / "RELEASE_CHANNEL.generated.json",
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            )

        self.assertEqual("fail", payload["status"])
        self.assertEqual("missing", payload["release"]["loadStatus"])
        self.assertEqual(str(downloads_root / "RELEASE_CHANNEL.generated.json"), payload["release"]["path"])
        self.assertIn(
            f"Release channel receipt is missing: {downloads_root / 'RELEASE_CHANNEL.generated.json'}",
            payload["failures"],
        )

    def test_manifest_sha_mismatch_keeps_manifest_as_required_promoted_digest(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-manifest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, actual_sha = self._write_release_fixture(root)
            release_payload = json.loads(release_channel.read_text(encoding="utf-8"))
            manifest_sha = "b" * 64
            release_payload["artifacts"][0]["sha256"] = manifest_sha
            release_channel.write_text(json.dumps(release_payload), encoding="utf-8")
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir(parents=True, exist_ok=True)
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{actual_sha}"}),
                encoding="utf-8",
            )
            source = self._write_valid_windows_visual_source_fixture(
                downloads_root,
                source_artifact_sha=actual_sha,
            )
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            preferred_drop_path = root / "incoming" / f"windows-installer-gold-proof-{actual_sha[:12]}.zip"
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(
                json.dumps(
                    {
                        "status": "external_artifact_required",
                        "promoted_installer_sha256": actual_sha,
                        "preferred_drop_path": str(preferred_drop_path),
                        "preferred_zip_name": preferred_drop_path.name,
                        "required_zip_filename": preferred_drop_path.name,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request):
                payload = module.build_payload(
                    release_channel_path=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt_path=startup,
                    source_path=source,
                )

        self.assertEqual("fail", payload["status"])
        self.assertIn("promoted Windows installer manifest sha256 does not match artifact bytes", payload["failures"])
        self.assertEqual(manifest_sha, payload["required_promoted_digest"])
        self.assertEqual(manifest_sha, payload["manifest_promoted_digest"])
        self.assertEqual(actual_sha, payload["artifact"]["actualSha256"])
        self.assertEqual(manifest_sha, payload["artifact"]["effectiveSha256"])
        self.assertFalse(payload["startupReceipt"]["artifactDigestMatchesPromoted"])
        self.assertFalse(payload["visualAuditSource"]["artifactDigestMatchesPromoted"])
        self.assertIn(
            "Windows startup receipt digest does not match promoted installer",
            payload["failures"],
        )
        self.assertIn(
            "Windows installer visual audit source digest does not match promoted installer",
            payload["failures"],
        )
        self.assertEqual(actual_sha, payload["operator_request_artifacts"]["promoted_installer_sha256"])
        self.assertEqual(preferred_drop_path.name, payload["required_zip_filename"])

    def test_malformed_visual_audit_source_is_not_reported_as_missing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-invalid-source-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            source.write_text("{not json}\n", encoding="utf-8")
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertTrue(payload["visualAuditSource"]["exists"])
        self.assertEqual("invalid", payload["visualAuditSource"]["loadStatus"])
        self.assertIn(f"Windows installer visual audit source is malformed: {source}", payload["failures"])
        self.assertFalse(any(item == f"Windows installer visual audit source is missing: {source}" for item in payload["failures"]))

    def test_native_startup_with_only_completion_screenshots_still_fails(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-pass-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "default.png").write_bytes(b"png")
            (source.parent / "scaled.png").write_bytes(b"png")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("Windows installer visual audit has no install-progress screenshot", payload["failures"])

    def test_matching_startup_with_stale_visual_digest_keeps_startup_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-stale-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for index, name in enumerate(["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"]):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            stale_sha = "0" * 64
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": stale_sha,
                        "sourceUpdatedAtUtc": "2026-06-21T17:44:15Z",
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertEqual(
            "Native Windows visual audit still failing: Windows installer visual audit source digest does not match promoted installer",
            payload["summary"],
        )
        self.assertIn("Windows installer visual audit source digest does not match promoted installer", payload["failures"])
        self.assertTrue(payload["startupReceipt"]["artifactDigestMatchesPromoted"])
        self.assertFalse(payload["startupReceipt"]["requiresNativeRefresh"])
        self.assertFalse(payload["visualAuditSource"]["artifactDigestMatchesPromoted"])
        self.assertTrue(payload["visualAuditSource"]["requiresRecapture"])
        self.assertEqual("2026-06-21T17:44:15Z", payload["visualAuditSource"]["sourceUpdatedAtUtc"])
        self.assertTrue(any("Recapture the Windows installer visual audit" in item for item in payload["nextActions"]))
        self.assertTrue(any("Keep the current Windows startup-smoke receipt" in item for item in payload["nextActions"]))
        self.assertFalse(any("Replace or refresh the Windows startup-smoke receipt" in item for item in payload["nextActions"]))

    def test_native_startup_and_required_surface_dpi_screenshots_pass(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-pass-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for index, name in enumerate(["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"]):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("pass", payload["status"])
        self.assertEqual("Native Windows visual audit matches the promoted installer.", payload["summary"])
        self.assertEqual([], payload["failures"])
        self.assertEqual([], payload["nextActions"])
        self.assertEqual(["install-progress", "completion"], payload["visualAuditSource"]["requiredSurfaces"])
        self.assertTrue(all(row["sha256"] for row in payload["screenshots"]))

    def test_digest_mismatch_surfaces_missing_bundle_and_auto_import_hint_details(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-hints-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for index, name in enumerate(
                [
                    "progress-default.png",
                    "progress-scaled.png",
                    "completion-default.png",
                    "completion-scaled.png",
                ]
            ):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            stale_source_sha = "c" * 64
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": stale_source_sha,
                        "generatedAt": "2026-07-05T13:00:00Z",
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            intake_request = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            delivery_root = root / "telegram"
            ask_text.parent.mkdir(parents=True, exist_ok=True)
            delivery_root.mkdir(parents=True, exist_ok=True)
            ask_text.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata.write_text("{}\n", encoding="utf-8")
            (delivery_root / "windows.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": "2026-07-04T20:58:05Z",
                        "message_ids": ["3555"],
                        "text_sha256": module.hashlib.sha256("windows ask current\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            preferred_drop_path = root / "incoming" / "windows-installer-gold-proof.zip"
            intake_request.write_text(
                json.dumps(
                    {
                        "status": "not_required",
                        "preferred_drop_path": str(preferred_drop_path),
                        "preferred_zip_name": preferred_drop_path.name,
                        "required_zip_filename": preferred_drop_path.name,
                        "promoted_installer_sha256": sha,
                        "startup_receipt_bundle_required": False,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text),
                            "current_metadata_path": str(ask_metadata),
                            "send_command": "python3 send-windows-ask",
                            "receipt_name": "windows.receipt.json",
                        },
                        "artifact_intake": {
                            "discover_command": "python3 discover-windows-proof",
                            "import_command": "python3 import-windows-proof",
                            "auto_import_watch_command": "python3 watch-windows-proof",
                            "post_import_verify_command": "python3 verify-windows-proof",
                            "post_import_verify_note": "verify the imported bundle",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            auto_import = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            auto_import.write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "actionable_candidate_count": 0,
                        "stage_visual_proof_receipt_count": 8,
                        "matching_promoted_stage_visual_proof_receipt_count": 0,
                        "stale_stage_visual_proof_receipt_count": 8,
                        "stage_startup_smoke_receipt_count": 43,
                        "matching_promoted_stage_startup_smoke_receipt_count": 4,
                        "stale_stage_startup_smoke_receipt_count": 39,
                        "stage_visual_proof_receipt_note": "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
                        "stage_startup_smoke_receipt_note": "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest.",
                        "stale_stage_visual_proof_receipts": [
                            {"path": "/tmp/stale-proof-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                            {"path": "/tmp/stale-proof-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request), mock.patch.object(
                module, "DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT", auto_import
            ), mock.patch.object(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root):
                payload = module.build_payload(
                    release_channel_path=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt_path=startup,
                    source_path=source,
                )

        self.assertEqual("fail", payload["status"])
        self.assertIn("Windows installer visual audit source digest does not match promoted installer", payload["failures"])
        self.assertIn(
            f"windows installer visual audit source still targets {stale_source_sha} instead of promoted digest {sha}: {source}",
            payload["failures"],
        )
        self.assertIn(
            f"windows installer gold proof artifact is still missing: {preferred_drop_path}",
            payload["failures"],
        )
        self.assertEqual(sha, payload["required_promoted_digest"])
        self.assertEqual(stale_source_sha, payload["source_digest"])
        self.assertFalse(payload["source_digest_matches_promoted"])
        self.assertEqual(str(preferred_drop_path), payload["expected_bundle_path"])
        self.assertFalse(payload["expected_bundle_path_exists"])
        self.assertEqual(preferred_drop_path.name, payload["required_zip_filename"])
        self.assertEqual(preferred_drop_path.name, payload["preferred_zip_name"])
        self.assertEqual("external_artifact_required", payload["proof_request_status"])
        self.assertEqual("not_required", payload["proof_request_raw_status"])
        self.assertEqual(str(delivery_root / "windows.receipt.json"), payload["operator_ask_delivery_receipt_path"])
        self.assertTrue(payload["operator_ask_delivery_receipt_exists"])
        self.assertEqual("sent", payload["operator_ask_delivery_status"])
        self.assertEqual("2026-07-04T20:58:05Z", payload["operator_ask_delivery_generated_at_utc"])
        self.assertEqual(["3555"], payload["operator_ask_delivery_message_ids"])
        self.assertTrue(payload["operator_ask_delivery_current_text_comparable"])
        self.assertTrue(payload["operator_ask_delivery_matches_current_text"])
        self.assertFalse(payload["operator_ask_delivery_needs_resend"])
        self.assertEqual("", payload["operator_ask_resend_command"])
        self.assertEqual("not_required", payload["operator_request_artifacts"]["request_status"])
        self.assertEqual(
            "external_artifact_required",
            payload["operator_request_artifacts"]["request_effective_status"],
        )
        self.assertTrue(payload["operator_request_artifacts"]["operator_action_still_required"])
        self.assertFalse(payload["operator_request_artifacts"]["preferred_drop_path_exists"])
        self.assertEqual("waiting_for_artifact", payload["operator_request_artifacts"]["auto_import_receipt_status"])
        self.assertEqual(8, payload["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_count"])
        self.assertEqual(43, payload["operator_request_artifacts"]["auto_import_stage_startup_smoke_receipt_count"])
        self.assertEqual(
            [
                "/tmp/stale-proof-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                "/tmp/stale-proof-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            ],
            payload["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_sample_paths"],
        )
        self.assertTrue(
            any("visual-proof receipts=8, startup-smoke receipts=43" in item for item in payload["nextActions"])
        )
        self.assertTrue(
            any(
                "Sample stale Windows proof hint paths: /tmp/stale-proof-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; /tmp/stale-proof-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
                in item
                for item in payload["nextActions"]
            )
        )

    def test_passing_visual_audit_ignores_stale_external_artifact_required_request_status(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-stale-request-pass-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for index, name in enumerate(
                [
                    "progress-default.png",
                    "progress-scaled.png",
                    "completion-default.png",
                    "completion-scaled.png",
                ]
            ):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            intake_request = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            ask_text.parent.mkdir(parents=True, exist_ok=True)
            ask_text.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata.write_text("{}\n", encoding="utf-8")
            preferred_drop_path = root / "incoming" / "windows-installer-gold-proof.zip"
            intake_request.write_text(
                json.dumps(
                    {
                        "status": "external_artifact_required",
                        "preferred_drop_path": str(preferred_drop_path),
                        "preferred_zip_name": preferred_drop_path.name,
                        "required_zip_filename": preferred_drop_path.name,
                        "promoted_installer_sha256": sha,
                        "startup_receipt_bundle_required": False,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text),
                            "current_metadata_path": str(ask_metadata),
                            "send_command": "python3 send-windows-ask",
                            "receipt_name": "windows.receipt.json",
                        },
                        "artifact_intake": {
                            "discover_command": "python3 discover-windows-proof",
                            "import_command": "python3 import-windows-proof",
                            "auto_import_watch_command": "python3 watch-windows-proof",
                            "post_import_verify_command": "python3 verify-windows-proof",
                            "post_import_verify_note": "verify the imported bundle",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request), mock.patch.object(
                module, "DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT", published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ), mock.patch.object(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", root / "telegram"):
                payload = module.build_payload(
                    release_channel_path=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt_path=startup,
                    source_path=source,
                )

        self.assertEqual("pass", payload["status"])
        self.assertEqual([], payload["failures"])
        self.assertEqual([], payload["nextActions"])
        self.assertEqual("not_required", payload["proof_request_status"])
        self.assertEqual("external_artifact_required", payload["proof_request_raw_status"])
        self.assertEqual("external_artifact_required", payload["operator_request_artifacts"]["request_status"])
        self.assertEqual("not_required", payload["operator_request_artifacts"]["request_effective_status"])
        self.assertFalse(payload["operator_request_artifacts"]["operator_action_still_required"])
        self.assertNotIn(
            f"windows installer gold proof artifact is still missing: {preferred_drop_path}",
            payload["failures"],
        )

    def test_distinct_required_surfaces_must_not_be_byte_identical(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-identical-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for name in ["progress-default.png", "completion-default.png"]:
                (source.parent / name).write_bytes(b"same screenshot")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertTrue(
            any("distinct required surfaces are byte-identical" in item for item in payload["failures"])
        )

    def test_automated_full_desktop_capture_bounds_block_visual_gold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-bounds-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for index, name in enumerate(["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"]):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 180, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 180, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 0, "top": 0, "width": 1024, "height": 768},
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "reused-same-surface",
                                "captureBounds": {"left": 0, "top": 0, "width": 1024, "height": 768},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertTrue(
            any("used full-desktop fallback bounds" in item for item in payload["failures"])
        )

    def test_windows_capture_helper_updates_source_receipt_without_manual_json_editing(self) -> None:
        script = Path("/docker/chummercomplete/chummer.run-services/scripts/capture_windows_installer_visual_audit.ps1")
        text = script.read_text(encoding="utf-8")

        self.assertIn("WINDOWS_INSTALLER_VISUAL_AUDIT.source.json", text)
        self.assertIn("CopyFromScreen", text)
        self.assertIn("artifactSha256", text)
        self.assertIn("review_required", text)
        self.assertIn("Get-FileHash", text)
        self.assertIn("$normalized = @{}", text)
        self.assertIn("function Test-MapHasKey", text)
        self.assertIn("Get-MapValue $source \"screenshots\"", text)
        self.assertIn('ValidateSet("install-progress", "completion")', text)
        self.assertIn("function Test-CaptureBoundsLookLikeDesktopFallback", text)
        self.assertIn("function Test-CaptureBoundsMapLookLikeDesktopFallback", text)
        self.assertIn("Test-CaptureBoundsLookLikeDesktopFallback $bounds", text)
        self.assertIn("Test-CaptureBoundsMapLookLikeDesktopFallback $item.captureBounds", text)
        self.assertIn("$surfacesByHash", text)
        self.assertIn("[System.Collections.Generic.HashSet[string]]::new()", text)
        self.assertIn('"install-progress", "completion"', text)
        self.assertIn("[switch]$CaptureRequiredSet", text)
        self.assertIn("$ScaledDpiScale", text)
        self.assertLess(
            text.index('[ordered]@{ Surface = "install-progress"; DpiScale = $ScaledDpiScale }'),
            text.index('[ordered]@{ Surface = "completion"; DpiScale = "1.0" }'),
        )
        self.assertIn("foreach ($request in $captureRequests)", text)
        self.assertIn("function Wait-ForInstallerSurface", text)
        self.assertIn("function New-InstallerSurfaceWindow", text)
        self.assertIn("function Get-VisibleInstallerWindows", text)
        self.assertIn("public static extern bool EnumWindows", text)
        self.assertIn("public static extern bool IsWindowVisible", text)
        self.assertIn("public static extern int GetWindowTextLength", text)
        self.assertIn("public static extern int GetWindowText", text)
        self.assertIn("public static extern uint GetWindowThreadProcessId", text)
        self.assertIn("public static class WindowScanner", text)
        self.assertIn("GetVisibleTopLevelWindows", text)
        self.assertIn("ProcessId = [int]$Window.ProcessId", text)
        self.assertIn("MainWindowHandle = $Window.Handle", text)
        self.assertIn("public static extern bool PostMessage", text)
        self.assertIn("function Close-InstallerSurfaceWindows", text)
        self.assertIn("function Stop-InstallerSurfaceProcesses", text)
        self.assertIn("function Stop-LaunchedInstallerProcess", text)
        self.assertIn("function Write-InstallerCaptureFailure", text)
        self.assertIn("function Get-InstallerTraceCandidates", text)
        self.assertIn("function Get-InstallerProcessSnapshotRows", text)
        self.assertIn("function Invoke-InstallerCaptureCleanup", text)
        self.assertIn("Requested close for installer window", text)
        self.assertIn("WINDOWS_INSTALLER_CAPTURE_FAILURE.txt", text)
        self.assertIn("chummerProcesses:", text)
        self.assertIn("traceCandidates:", text)
        self.assertIn("Get-Content -LiteralPath $candidate -Tail 40", text)
        self.assertIn("Stopped launched installer process", text)
        self.assertIn("Stopped installer window process", text)
        self.assertIn("$script:LaunchedInstallerProcessId = $launchedProcess.Id", text)
        self.assertIn("trap {", text)
        self.assertIn("Invoke-InstallerCaptureCleanup", text)
        self.assertIn("if ($AutoCapture -and $LaunchInstaller)", text)
        self.assertIn("function Find-InstallerSurfaceWindow([string]$SurfaceValue, [bool]$AllowCompletionInstallerFallback = $false)", text)
        self.assertIn("Find-InstallerSurfaceWindow $SurfaceValue $AllowCompletionInstallerFallback", text)
        self.assertIn("$AllowCompletionInstallerFallback -and $title.IndexOf(\"Installer\"", text)
        self.assertIn("handle=$($_.Handle)", text)
        self.assertIn("MainWindowTitle", text)
        self.assertNotIn("Get-Process | Where-Object {\n        -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle)", text)
        self.assertIn('$title.IndexOf("Install Complete"', text)
        self.assertIn('$title.IndexOf("Installer"', text)
        self.assertIn("function Get-CaptureBounds", text)
        self.assertIn("GetWindowRect", text)
        self.assertIn("function Get-AutomationCaptureBounds", text)
        self.assertIn("Add-Type -AssemblyName UIAutomationClient", text)
        self.assertIn("[System.Windows.Automation.AutomationElement]::FromHandle", text)
        self.assertIn("Using UI Automation bounds for installer window after GetWindowRect was unavailable.", text)
        self.assertIn("SetForegroundWindow", text)
        self.assertIn("Automated installer capture refused full-screen fallback", text)
        self.assertIn("expected compact installer window bounds", text)
        self.assertIn("Get-CaptureBounds $window (-not $AutoCapture)", text)
        self.assertIn("window-bounds", text)
        self.assertIn("captureBounds", text)
        self.assertIn("Launching installer for visual capture", text)
        self.assertIn('$isProgressSurface = (Normalize-Surface $captureSurface) -eq "install-progress"', text)
        self.assertIn("Progress surfaces are captured immediately so fast installers cannot close before bounds are read.", text)
        self.assertLess(
            text.index("Progress surfaces are captured immediately"),
            text.index("[void][ChummerInstallerCapture.NativeMethods]::SetForegroundWindow"),
        )
        self.assertLess(text.index('Add-Type @"'), text.index("Launching installer for visual capture"))
        self.assertLess(text.index("Launching installer for visual capture"), text.index("foreach ($request in $captureRequests)"))
        self.assertIn("$previousSameSurfaceRows", text)
        self.assertIn("reused-same-surface", text)
        self.assertIn("reusedFrom", text)
        self.assertIn("Reused previous $captureSurface screenshot after the window closed", text)
        self.assertIn("Reused previous $captureSurface screenshot after the window bounds became unavailable", text)
        self.assertIn("Timed out waiting for Chummer installer surface", text)
        self.assertIn("$AutoCaptureTimeoutSeconds", text)
        self.assertIn("$effectiveAutoCaptureTimeoutSeconds", text)
        self.assertIn("[Math]::Min($AutoCaptureTimeoutSeconds, 90)", text)
        self.assertIn("Auto-capture timeout capped", text)
        self.assertIn("$delaySeconds = 0", text)
        self.assertIn("$delaySeconds = [Math]::Max($delaySeconds, 8)", text)
        self.assertIn('$requiredSurfaces = @("install-progress", "completion")', text)
        self.assertIn("$requiredSurfaces -notcontains (Normalize-Surface $_.surface)", text)
        self.assertIn("surfaceCoverage", text)

    def test_windows_gold_proof_helper_writes_startup_receipt_and_delegates_visual_capture(self) -> None:
        script = Path("/docker/chummercomplete/chummer.run-services/scripts/capture_windows_installer_gold_proof.ps1")
        text = script.read_text(encoding="utf-8")

        self.assertIn("startup-smoke-$HeadId-$Rid.receipt.json", text)
        self.assertIn('status = "pass"', text)
        self.assertIn('readyCheckpoint = "pre_ui_event_loop"', text)
        self.assertIn('hostClass = "native-windows"', text)
        self.assertIn('artifactDigest = "sha256:$artifactHash"', text)
        self.assertIn("if ($LaunchInstaller -and -not $CaptureVisualAudit)", text)
        self.assertIn("elseif ($LaunchInstaller)", text)
        self.assertIn("capture_windows_installer_visual_audit.ps1", text)
        self.assertIn("$normalized = @{}", text)
        self.assertIn("function Test-MapHasKey", text)
        self.assertIn("Get-MapValue $releaseChannel \"version\"", text)
        self.assertIn("$captureArgs = @{", text)
        self.assertIn("CaptureRequiredSet = $true", text)
        self.assertIn('$captureArgs["AutoCapture"] = $true', text)
        self.assertIn("ClippingStatus = $VisualClippingStatus", text)
        self.assertIn("ReadabilityStatus = $VisualReadabilityStatus", text)
        self.assertIn("$AutoCaptureVisualAudit", text)
        self.assertIn('$captureArgs["AutoCaptureDelaySeconds"] = $AutoCaptureDelaySeconds', text)
        self.assertIn('$captureArgs["AutoCaptureTimeoutSeconds"] = $AutoCaptureTimeoutSeconds', text)
        self.assertIn('$captureArgs["LaunchInstaller"] = $true', text)

        self.assertIn("ui_desktop_run_id", text)
        self.assertIn("chummer-avalonia-win-x64-installer.exe", text)
        self.assertIn("RELEASE_CHANNEL.generated.json", text)
        self.assertIn("avalonia-win-x64-installer", text)

    def test_import_windows_installer_gold_proof_artifact_copies_expected_receipts_and_screenshots(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            for token, name in enumerate(
                ["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"],
                start=1,
            ):
                write_valid_png(visual_root / name, token=token)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "a" * 64,
                        "screenshots": [
                            {"path": "progress-default.png"},
                            {"path": "progress-scaled.png"},
                            {"path": "completion-default.png"},
                            {"path": "completion-scaled.png"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            downloads_root.mkdir()
            summary = module.import_artifact(artifact, downloads_root)

            self.assertTrue((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").is_file())
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").is_file())
            self.assertEqual(4, len(summary["screenshots"]))
            self.assertEqual("artifact_bundle", summary["startupReceiptSource"])
            self.assertTrue(summary["startupReceiptBundleRequired"])
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "completion-scaled.png").is_file())
            self.assertEqual("committed", summary["proofSetTransaction"]["status"])
            self.assertEqual(6, summary["proofSetTransaction"]["item_count"])
            self.assertTrue(summary["proofSetTransaction"]["atomic_cutover"])
            self.assertTrue(summary["proofSetTransaction"]["root_dirfd_no_follow"])
            self.assertRegex(
                summary["proofSetTransaction"]["generation_id"],
                r"^generation-[0-9a-f]{32}$",
            )
            self.assertTrue((downloads_root / ".windows-installer-proof" / "current").is_symlink())
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

    def test_windows_gold_proof_generation_update_retains_old_tree_and_switches_current_atomically(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-update-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            downloads_root.mkdir()
            first_entries = proof_generation_entries(module, downloads_root, token=1)
            second_entries = proof_generation_entries(module, downloads_root, token=2)

            first = module.publish_proof_set_transactionally(first_entries, downloads_root)
            old_public_bytes = (
                downloads_root / "visual-audit" / "windows-installer" / "capture.png"
            ).read_bytes()
            second = module.publish_proof_set_transactionally(second_entries, downloads_root)

            self.assertNotEqual(first["generation_id"], second["generation_id"])
            self.assertTrue(second["previous_generation_retained"])
            generations = downloads_root / ".windows-installer-proof" / "generations"
            self.assertTrue((generations / first["generation_id"]).is_dir())
            self.assertTrue((generations / second["generation_id"]).is_dir())
            self.assertEqual(
                old_public_bytes,
                (generations / first["generation_id"] / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )
            self.assertEqual(
                valid_png_bytes(token=2),
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )
            self.assertEqual(
                f"generations/{second['generation_id']}",
                os.readlink(downloads_root / ".windows-installer-proof" / "current"),
            )

    def test_windows_gold_proof_generation_recovers_crash_after_pointer_cutover(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-crash-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=3)
            original_install = module._install_current_pointer

            child_pid = os.fork()
            if child_pid == 0:
                def crash_after_install(control_fd, target):
                    original_install(control_fd, target)
                    os._exit(73)

                module._install_current_pointer = crash_after_install
                module.publish_proof_set_transactionally(entries, downloads_root)
                os._exit(74)
            waited_pid, wait_status = os.waitpid(child_pid, 0)
            self.assertEqual(child_pid, waited_pid)
            self.assertEqual(73, os.waitstatus_to_exitcode(wait_status))

            journal_path = downloads_root / ".windows-installer-proof" / "recovery-journal.json"
            self.assertEqual("cutover_pending", json.loads(journal_path.read_text())["state"])
            recovered = module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual("completed_atomic_cutover", recovered["recovery_disposition"])
            self.assertEqual("committed", json.loads(journal_path.read_text())["state"])
            self.assertEqual(
                valid_png_bytes(token=3),
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )

    def test_windows_gold_proof_generation_public_reads_never_observe_partial_tree_during_cutover(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-reader-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first_entries = proof_generation_entries(module, downloads_root, token=4)
            second_entries = proof_generation_entries(module, downloads_root, token=5)
            module.publish_proof_set_transactionally(first_entries, downloads_root)
            expected_pairs = {
                (4, module.hashlib.sha256(valid_png_bytes(token=4)).hexdigest()),
                (5, module.hashlib.sha256(valid_png_bytes(token=5)).hexdigest()),
            }
            observations: list[tuple[int, str]] = []
            read_failures: list[str] = []
            stop = threading.Event()

            def reader() -> None:
                public_directory = downloads_root / "visual-audit" / "windows-installer"
                while not stop.is_set():
                    try:
                        directory_fd = os.open(public_directory, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            source_fd = os.open(module.VISUAL_SOURCE_NAME, os.O_RDONLY, dir_fd=directory_fd)
                            image_fd = os.open("capture.png", os.O_RDONLY, dir_fd=directory_fd)
                            try:
                                source = json.loads(os.read(source_fd, 65536).decode("utf-8"))
                                image = os.read(image_fd, module.MAX_SCREENSHOT_BYTES)
                            finally:
                                os.close(image_fd)
                                os.close(source_fd)
                        finally:
                            os.close(directory_fd)
                        observations.append((int(source["token"]), module.hashlib.sha256(image).hexdigest()))
                    except BaseException as exc:
                        read_failures.append(type(exc).__name__)
                        stop.set()

            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            time.sleep(0.03)
            module.publish_proof_set_transactionally(second_entries, downloads_root)
            time.sleep(0.03)
            stop.set()
            thread.join(timeout=2.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual([], read_failures)
            self.assertGreater(len(observations), 0)
            self.assertTrue(set(observations).issubset(expected_pairs), observations[:10])

    def test_windows_gold_proof_generation_rejects_symlinked_public_ancestor_without_writing_outside_root(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-symlink-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            outside = root / "outside"
            downloads_root.mkdir()
            outside.mkdir()
            (downloads_root / "visual-audit").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(SystemExit, "ancestor is linked|separately authorized migration"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, downloads_root, token=6),
                    downloads_root,
                )

            self.assertEqual([], list(outside.iterdir()))
            self.assertFalse((downloads_root / ".windows-installer-proof").exists())

    def test_windows_gold_proof_generation_rejects_symlink_in_downloads_root_ancestry(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-root-ancestor-symlink-") as temp_dir:
            root = Path(temp_dir)
            real_parent = root / "real-parent"
            real_downloads = real_parent / "downloads"
            real_downloads.mkdir(parents=True)
            alias = root / "alias"
            alias.symlink_to(real_parent, target_is_directory=True)
            aliased_downloads = alias / "downloads"

            with self.assertRaisesRegex(SystemExit, "missing, linked, or not a directory"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, aliased_downloads, token=7),
                    aliased_downloads,
                )

            self.assertFalse((real_downloads / ".windows-installer-proof").exists())

    def test_windows_gold_proof_generation_interprocess_lock_fails_closed(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-lock-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first = module.publish_proof_set_transactionally(
                proof_generation_entries(module, downloads_root, token=8),
                downloads_root,
            )
            lock_path = downloads_root / ".windows-installer-proof" / "publish.lock"
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                module.fcntl.flock(lock_fd, module.fcntl.LOCK_EX | module.fcntl.LOCK_NB)
                with self.assertRaisesRegex(SystemExit, "currently holds the lock"):
                    module.publish_proof_set_transactionally(
                        proof_generation_entries(module, downloads_root, token=9),
                        downloads_root,
                    )
            finally:
                module.fcntl.flock(lock_fd, module.fcntl.LOCK_UN)
                os.close(lock_fd)

            self.assertEqual(
                f"generations/{first['generation_id']}",
                os.readlink(downloads_root / ".windows-installer-proof" / "current"),
            )
            self.assertEqual(
                valid_png_bytes(token=8),
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )

    def test_windows_gold_proof_generation_recovers_crash_with_pending_new_anchor(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-pending-anchor-crash-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=10)
            original_ensure = module._ensure_public_anchor

            child_pid = os.fork()
            if child_pid == 0:
                def crash_after_anchor(root_fd, anchor_id):
                    created = original_ensure(root_fd, anchor_id)
                    if anchor_id == "visual":
                        os._exit(75)
                    return created

                module._ensure_public_anchor = crash_after_anchor
                module.publish_proof_set_transactionally(entries, downloads_root)
                os._exit(76)
            _waited_pid, wait_status = os.waitpid(child_pid, 0)
            self.assertEqual(75, os.waitstatus_to_exitcode(wait_status))
            journal_path = downloads_root / ".windows-installer-proof" / "recovery-journal.json"
            crashed_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual("generation_ready", crashed_journal["state"])
            self.assertEqual("visual", crashed_journal["pending_anchor"])
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

            recovered = module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual("removed_uncommitted_anchors", recovered["recovery_disposition"])
            self.assertEqual("committed", json.loads(journal_path.read_text())["state"])
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())
            self.assertTrue(
                (downloads_root / "startup-smoke" / module.STARTUP_RECEIPT_NAME).is_symlink()
            )

    def test_windows_gold_proof_generation_rolls_back_anchor_created_before_fsync_error(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-anchor-fsync-error-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=11)
            original_ensure = module._ensure_public_anchor

            def fail_after_visual_anchor(root_fd, anchor_id):
                created = original_ensure(root_fd, anchor_id)
                if anchor_id == "visual":
                    raise OSError("synthetic anchor parent fsync failure")
                return created

            with mock.patch.object(module, "_ensure_public_anchor", side_effect=fail_after_visual_anchor):
                with self.assertRaisesRegex(OSError, "synthetic anchor parent fsync failure"):
                    module.publish_proof_set_transactionally(entries, downloads_root)

            journal = json.loads(
                (downloads_root / ".windows-installer-proof" / "recovery-journal.json").read_text()
            )
            self.assertEqual("rolled_back", journal["state"])
            self.assertEqual([], journal["created_anchors"])
            self.assertIsNone(journal["pending_anchor"])
            self.assertFalse((downloads_root / ".windows-installer-proof" / "current").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer").exists())

    def test_windows_gold_proof_generation_rejects_unknown_journal_before_public_mutation(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-unknown-journal-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first = module.publish_proof_set_transactionally(
                proof_generation_entries(module, downloads_root, token=12),
                downloads_root,
            )
            control = downloads_root / ".windows-installer-proof"
            current_before = os.readlink(control / "current")
            journal_path = control / "recovery-journal.json"
            journal = json.loads(journal_path.read_text())
            journal["state"] = "delete_everything"
            journal_path.write_text(json.dumps(journal), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "journal state is invalid"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, downloads_root, token=13),
                    downloads_root,
                )

            self.assertEqual(current_before, os.readlink(control / "current"))
            self.assertEqual(f"generations/{first['generation_id']}", current_before)
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

    def test_windows_gold_proof_generation_rejects_empty_journal_before_public_mutation(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-empty-journal-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first = module.publish_proof_set_transactionally(
                proof_generation_entries(module, downloads_root, token=121),
                downloads_root,
            )
            control = downloads_root / ".windows-installer-proof"
            current_before = os.readlink(control / "current")
            journal_path = control / "recovery-journal.json"
            journal_path.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "journal field set is invalid"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, downloads_root, token=122),
                    downloads_root,
                )

            self.assertEqual(current_before, os.readlink(control / "current"))
            self.assertEqual(f"generations/{first['generation_id']}", current_before)
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

    def test_windows_gold_proof_generation_rejects_existing_hardlink_without_repair_or_pointer_loss(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-existing-hardlink-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=14)
            first = module.publish_proof_set_transactionally(entries, downloads_root)
            control = downloads_root / ".windows-installer-proof"
            generation_root = control / "generations" / first["generation_id"]
            image = generation_root / "visual-audit" / "windows-installer" / "capture.png"
            outside = root / "outside.png"
            outside.write_bytes(image.read_bytes())
            outside.chmod(0o640)
            image.parent.chmod(0o755)
            image.unlink()
            os.link(outside, image)
            image.parent.chmod(0o555)

            with self.assertRaisesRegex(SystemExit, "not a bounded regular file|not private"):
                module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual(0o640, outside.stat().st_mode & 0o777)
            self.assertEqual(
                f"generations/{first['generation_id']}",
                os.readlink(control / "current"),
            )

    def test_windows_gold_proof_generation_rejects_extra_empty_directory(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-extra-directory-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=15)
            first = module.publish_proof_set_transactionally(entries, downloads_root)
            control = downloads_root / ".windows-installer-proof"
            generation_root = control / "generations" / first["generation_id"]
            generation_root.chmod(0o755)
            (generation_root / "extra-empty").mkdir()
            (generation_root / "extra-empty").chmod(0o555)
            generation_root.chmod(0o555)

            with self.assertRaisesRegex(SystemExit, "extra directories"):
                module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual(
                f"generations/{first['generation_id']}",
                os.readlink(control / "current"),
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_visual_only_bundle_even_when_legacy_intake_marks_startup_optional(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-reuse-startup-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            visual_root.mkdir(parents=True)
            for token, name in enumerate(
                ["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"],
                start=1,
            ):
                write_valid_png(visual_root / name, token=token)
            promoted_digest = "a" * 64
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress-default.png", "surface": "install-progress"},
                            {"path": "progress-scaled.png", "surface": "install-progress"},
                            {"path": "completion-default.png", "surface": "completion"},
                            {"path": "completion-scaled.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            startup_receipt = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup_receipt.parent.mkdir(parents=True)
            startup_receipt.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{promoted_digest}"}),
                encoding="utf-8",
            )
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps(
                    {
                        "promoted_installer_sha256": promoted_digest,
                        "startup_receipt_bundle_required": False,
                        "artifact_intake": {"startup_receipt_bundle_required": False},
                        "operator_request": {"startup_receipt_bundle_required": False},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                SystemExit,
                "complete generation publication requires the native startup receipt",
            ):
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertTrue(startup_receipt.is_file())
            self.assertFalse(
                (downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists()
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_visual_source_digest_mismatch_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-visual-digest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "a" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{promoted_digest}",
                    }
                ),
                encoding="utf-8",
            )
            for token, name in enumerate(["progress.png", "completion.png"], start=1):
                write_valid_png(visual_root / name, token=token)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "b" * 64,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps({"promoted_installer_sha256": promoted_digest}),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertIn("visual audit source digest does not match the promoted installer", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_missing_intake_request_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-missing-intake-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "a" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{promoted_digest}"}),
                encoding="utf-8",
            )
            for name in ["progress.png", "completion.png"]:
                (visual_root / name).write_bytes(name.encode("utf-8"))
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            downloads_root = root / "downloads"
            missing_intake = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=missing_intake)

            self.assertIn("intake request not found", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_intake_request_without_promoted_digest_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-missing-promoted-digest-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "a" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{promoted_digest}"}),
                encoding="utf-8",
            )
            for name in ["progress.png", "completion.png"]:
                (visual_root / name).write_bytes(name.encode("utf-8"))
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(json.dumps({"startup_receipt_bundle_required": True}), encoding="utf-8")

            downloads_root = root / "downloads"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertIn("missing the promoted installer digest", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_bundled_startup_digest_mismatch_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-startup-digest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "c" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": "sha256:" + ("d" * 64),
                    }
                ),
                encoding="utf-8",
            )
            for token, name in enumerate(["progress.png", "completion.png"], start=1):
                write_valid_png(visual_root / name, token=token)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps({"promoted_installer_sha256": promoted_digest}),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertIn("startup receipt whose digest does not match the promoted installer", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_visual_only_bundle_without_valid_published_startup_receipt(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-missing-startup-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            visual_root.mkdir(parents=True)
            for token, name in enumerate(["progress.png", "completion.png"], start=1):
                write_valid_png(visual_root / name, token=token)
            promoted_digest = "b" * 64
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps(
                    {
                        "promoted_installer_sha256": promoted_digest,
                        "startup_receipt_bundle_required": False,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

        self.assertIn("complete generation publication requires the native startup receipt", str(raised.exception))

    def test_import_windows_installer_gold_proof_artifact_rejects_desktop_fallback_bounds_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-fallback-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            write_valid_png(visual_root / "progress.png", token=1)
            write_valid_png(visual_root / "completion.png", token=2)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "a" * 64,
                        "screenshots": [
                            {
                                "path": "progress.png",
                                "surface": "install-progress",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "completion.png",
                                "surface": "completion",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 0, "top": 0, "width": 1024, "height": 768},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root)

            self.assertIn("full-desktop fallback bounds", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_byte_identical_required_surfaces(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-identical-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            for name in ["progress.png", "completion.png"]:
                write_valid_png(visual_root / name, token=1)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "a" * 64,
                        "screenshots": [
                            {
                                "path": "progress.png",
                                "surface": "install-progress",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "completion.png",
                                "surface": "completion",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, root / "downloads")

            self.assertTrue(
                "byte-identical" in str(raised.exception)
                or "distinct image hashes" in str(raised.exception)
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_absolute_and_parent_screenshot_escapes_before_copy(self) -> None:
        module = load_import_module()
        for escape_kind in ("absolute", "parent"):
            with self.subTest(escape_kind=escape_kind), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-import-{escape_kind}-escape-"
            ) as temp_dir:
                root = Path(temp_dir)
                external = root / "operator-secret.txt"
                external.write_bytes(b"watcher-readable-secret")
                artifact, visual_root = write_windows_gold_proof_fixture(root, [])
                if escape_kind == "absolute":
                    screenshot_path = str(external)
                else:
                    escaped = visual_root.parent / "outside.png"
                    escaped.write_bytes(b"outside-bundle-surface")
                    screenshot_path = "../outside.png"
                (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                    json.dumps(
                        {
                            "status": "pass",
                            "platform": "windows",
                            "hostClass": "native-windows-11",
                            "artifactSha256": "a" * 64,
                            "screenshots": [
                                {"path": screenshot_path, "surface": "install-progress"}
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                downloads_root = root / "downloads"

                with self.assertRaises(SystemExit) as raised:
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())
                self.assertTrue(
                    "bundle-relative" in str(raised.exception)
                    or "parent traversal" in str(raised.exception)
                )

    def test_import_windows_installer_gold_proof_artifact_rejects_symlink_hardlink_and_nonregular_screenshots(self) -> None:
        module = load_import_module()
        for member_kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(member_kind=member_kind), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-import-{member_kind}-"
            ) as temp_dir:
                root = Path(temp_dir)
                artifact, visual_root = write_windows_gold_proof_fixture(
                    root,
                    [{"path": "surface.png", "surface": "install-progress"}],
                )
                surface = visual_root / "surface.png"
                external = root / "external.png"
                external.write_bytes(b"external-surface")
                if member_kind == "symlink":
                    surface.symlink_to(external)
                elif member_kind == "hardlink":
                    os.link(external, surface)
                else:
                    os.mkfifo(surface)
                downloads_root = root / "downloads"

                with self.assertRaises(SystemExit) as raised:
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())
                self.assertTrue(
                    any(
                        marker in str(raised.exception)
                        for marker in ("symlink", "hard-linked", "not a regular file")
                    )
                )

    def test_import_windows_installer_gold_proof_artifact_rejects_public_basename_collisions_before_copy(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-basename-collision-") as temp_dir:
            root = Path(temp_dir)
            rows = [
                {"path": "first/surface.png", "surface": "install-progress"},
                {"path": "second/SURFACE.png", "surface": "completion"},
            ]
            artifact, visual_root = write_windows_gold_proof_fixture(root, rows)
            (visual_root / "first").mkdir()
            (visual_root / "second").mkdir()
            write_valid_png(visual_root / "first" / "surface.png", token=1)
            write_valid_png(visual_root / "second" / "SURFACE.png", token=2)
            downloads_root = root / "downloads"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root)

            self.assertIn("basenames collide", str(raised.exception))
            self.assertFalse(downloads_root.exists())

    def test_import_windows_installer_gold_proof_artifact_accepts_only_real_png_and_jpeg_images(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-valid-images-") as temp_dir:
            root = Path(temp_dir)
            artifact, visual_root = write_windows_gold_proof_fixture(
                root,
                [
                    {"path": "capture.png", "surface": "install-progress"},
                    {"path": "capture.jpg", "surface": "completion"},
                ],
            )
            (visual_root / "capture.png").write_bytes(valid_png_bytes(token=21))
            (visual_root / "capture.jpg").write_bytes(valid_jpeg_bytes(token=22))
            downloads_root = root / "downloads"
            downloads_root.mkdir()

            summary = module.import_artifact(artifact, downloads_root)

            self.assertEqual(
                ["png", "jpeg"],
                [row["image"]["format"] for row in summary["screenshotBindings"]],
            )
            self.assertTrue(
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").is_file()
            )
            self.assertTrue(
                (downloads_root / "visual-audit" / "windows-installer" / "capture.jpg").is_file()
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_empty_html_fake_and_undersized_images_before_public_mutation(self) -> None:
        module = load_import_module()
        scenarios = {
            "empty": ("surface.png", b"", "byte size"),
            "html": ("surface.png", b"<html><body>not an image</body></html>", "valid PNG or JPEG"),
            "truncated_png": ("surface.png", b"\x89PNG\r\n\x1a\n", "missing required image chunks"),
            "undersized": ("surface.png", valid_png_bytes(width=319, height=180), "width is outside"),
            "extension_mismatch": ("surface.jpg", valid_png_bytes(token=23), "does not match"),
        }
        for scenario, (name, image_bytes, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-invalid-image-{scenario}-"
            ) as temp_dir:
                root = Path(temp_dir)
                artifact, visual_root = write_windows_gold_proof_fixture(
                    root,
                    [{"path": name, "surface": "install-progress"}],
                )
                (visual_root / name).write_bytes(image_bytes)
                downloads_root = root / "downloads"

                with self.assertRaisesRegex(SystemExit, message):
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())

    def test_import_windows_installer_gold_proof_artifact_requires_native_windows_metadata_and_full_digests(self) -> None:
        module = load_import_module()
        scenarios = {
            "visual_platform": ("visual", "platform", "linux", "platform must be windows"),
            "visual_host": ("visual", "hostClass", "container-linux", "native Windows host"),
            "visual_digest": ("visual", "artifactSha256", "deadbeef", "full SHA-256"),
            "startup_platform": ("startup", "platform", "linux", "not native Windows proof"),
            "startup_host": ("startup", "hostClass", "wine", "not native Windows proof"),
            "startup_digest": ("startup", "artifactDigest", "sha256:deadbeef", "full SHA-256"),
        }
        for scenario, (target, key, value, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-native-metadata-{scenario}-"
            ) as temp_dir:
                root = Path(temp_dir)
                artifact, visual_root = write_windows_gold_proof_fixture(
                    root,
                    [{"path": "surface.png", "surface": "install-progress"}],
                )
                write_valid_png(visual_root / "surface.png", token=24)
                if target == "visual":
                    metadata_path = visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
                else:
                    metadata_path = (
                        artifact
                        / "Chummer.Portal"
                        / "downloads"
                        / "startup-smoke"
                        / "startup-smoke-avalonia-win-x64.receipt.json"
                    )
                metadata = json.loads(metadata_path.read_text())
                metadata[key] = value
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                downloads_root = root / "downloads"

                with self.assertRaisesRegex(SystemExit, message):
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_directory_artifact_without_inspection(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-directory-rejection-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            artifact.mkdir()
            sentinel = artifact / "operator-secret.txt"
            sentinel.write_text("must-not-be-parsed", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "directory proof artifacts are forbidden"):
                module.extracted_or_directory(artifact, root / "extract")

            self.assertEqual("must-not-be-parsed", sentinel.read_text(encoding="utf-8"))
            self.assertFalse((root / "extract").exists())

    def test_stable_bundle_snapshot_rejects_identity_drift_during_read(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-stable-read-drift-") as temp_dir:
            root = Path(temp_dir)
            source = root / "surface.png"
            source.write_bytes(b"stable-before-read")
            real_fstat = module.os.fstat
            fstat_calls = 0

            def drifting_fstat(descriptor):
                nonlocal fstat_calls
                fstat_calls += 1
                file_stat = real_fstat(descriptor)
                if fstat_calls != 2:
                    return file_stat
                drifted = mock.Mock()
                for name in (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_nlink",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                ):
                    setattr(drifted, name, getattr(file_stat, name))
                drifted.st_ctime_ns += 1
                return drifted

            with mock.patch.object(module.os, "fstat", side_effect=drifting_fstat):
                with self.assertRaises(SystemExit) as raised:
                    module.stable_bundle_file_snapshot(source, root, "test screenshot")

        self.assertIn("changed during stable read", str(raised.exception))

    def test_import_windows_installer_gold_proof_artifact_rejects_unsafe_zip_members(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-zip-") as temp_dir:
            root = Path(temp_dir)
            zip_path = root / "artifact.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../escape.txt", "bad")

            with self.assertRaises(SystemExit):
                module.extracted_or_directory(zip_path, root / "extract")

    def test_import_windows_installer_gold_proof_artifact_enforces_zip_resource_and_path_bounds(self) -> None:
        module = load_import_module()
        scenarios = (
            ("archive_size", {"MAX_ZIP_ARCHIVE_BYTES": 1}),
            ("member_count", {"MAX_ZIP_MEMBER_COUNT": 1}),
            ("member_size", {"MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES": 3}),
            ("total_size", {"MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES": 6}),
            ("compression_ratio", {"MAX_ZIP_COMPRESSION_RATIO": 2.0}),
            ("path_depth", {"MAX_ZIP_MEMBER_PATH_DEPTH": 1}),
            ("path_bytes", {"MAX_ZIP_MEMBER_PATH_BYTES": 4}),
            ("casefold_duplicate", {}),
            ("symlink_member", {}),
        )
        for scenario, patched_bounds in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-zip-bound-{scenario}-"
            ) as temp_dir:
                root = Path(temp_dir)
                zip_path = root / "artifact.zip"
                with zipfile.ZipFile(zip_path, "w") as archive:
                    if scenario == "member_count":
                        archive.writestr("one.bin", b"1")
                        archive.writestr("two.bin", b"2")
                    elif scenario == "member_size":
                        archive.writestr("large.bin", b"1234")
                    elif scenario == "total_size":
                        archive.writestr("one.bin", b"1234")
                        archive.writestr("two.bin", b"5678")
                    elif scenario == "compression_ratio":
                        archive.writestr(
                            "compressed.bin",
                            b"A" * 4096,
                            compress_type=zipfile.ZIP_DEFLATED,
                        )
                    elif scenario == "path_depth":
                        archive.writestr("one/two.bin", b"x")
                    elif scenario == "path_bytes":
                        archive.writestr("12345", b"x")
                    elif scenario == "casefold_duplicate":
                        archive.writestr("Surface.png", b"one")
                        archive.writestr("surface.PNG", b"two")
                    elif scenario == "symlink_member":
                        member = zipfile.ZipInfo("surface-link.png")
                        member.create_system = 3
                        member.external_attr = 0o120777 << 16
                        archive.writestr(member, b"outside.png")
                    else:
                        archive.writestr("payload.bin", b"archive-size")

                patches = [mock.patch.object(module, name, value) for name, value in patched_bounds.items()]
                for patcher in patches:
                    patcher.start()
                try:
                    with self.assertRaises(SystemExit):
                        module.extracted_or_directory(zip_path, root / "extract")
                finally:
                    for patcher in reversed(patches):
                        patcher.stop()

                self.assertFalse((root / "outside.png").exists())

    def test_import_windows_installer_gold_proof_artifact_ignores_request_command_injection_and_uses_fixed_argv(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-post-import-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            injection = "python3 -c 'raise SystemExit(99)' ; touch /tmp/request-command-injection"
            intake_request.write_text(
                json.dumps(
                    {
                        "post_import_gates": [injection],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            plan = module.build_code_owned_post_import_plan(
                root / "downloads",
                intake_request,
                handoff_timestamp="2026-07-13T17:31:14Z",
                authorize_external_mutations=True,
            )
            with mock.patch.object(
                module,
                "run_bound_python_subprocess",
                side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(module, bound_argv),
            ) as run_mock:
                returncode, results = module.run_post_import_chain(
                    intake_request,
                    root / "downloads",
                    plan=plan,
                )

            request_metadata = module.request_post_import_gate_metadata(
                module.load_json(intake_request)
            )

        self.assertEqual(0, returncode)
        self.assertEqual(21, len(results))
        self.assertEqual(21, run_mock.call_count)
        self.assertNotIn(injection, json.dumps(plan))
        self.assertNotIn(injection, json.dumps(results))
        self.assertTrue(request_metadata["ignored"])
        self.assertEqual(1, request_metadata["item_count"])
        self.assertNotIn(injection, json.dumps(request_metadata))
        for call, result, step in zip(run_mock.call_args_list, results, plan["steps"]):
            bound_argv = call.args[0]
            execution_argv = result["sealed_execution"]["execution_argv"]
            self.assertEqual(step["argv"], bound_argv)
            self.assertTrue(execution_argv[0].startswith("/proc/self/fd/"))
            self.assertEqual(["-I", "-c"], execution_argv[1:3])
            self.assertEqual(module.SEALED_PYTHON_LAUNCHER_SOURCE, execution_argv[3])
            self.assertEqual(step["argv"][1], execution_argv[4])
            self.assertEqual(step["argv"], result["sealed_execution"]["bound_argv"])
            self.assertNotIn("bash", execution_argv)
            self.assertNotIn("-lc", execution_argv)
            self.assertEqual(module.code_owned_post_import_environment(), call.kwargs["environment"])
            self.assertNotIn("BASH_ENV", call.kwargs["environment"])
            self.assertNotIn("ENV", call.kwargs["environment"])
            self.assertNotIn("PYTHONPATH", call.kwargs["environment"])
            self.assertNotIn("PYTHONHOME", call.kwargs["environment"])
        self.assertTrue(all(row["plan_sha256"] == plan["plan_sha256"] for row in results))
        self.assertTrue(all(row["shell"] is False for row in results))
        self.assertTrue(all(row["program_bindings"] == plan["program_bindings"] for row in results))
        self.assertTrue(
            all(
                {
                    "importer",
                    "auto_importer",
                    "python_dependency_bundle",
                    "sealed_python_launcher",
                }.issubset(set(row["program_bindings"]))
                for row in results
            )
        )

    def test_import_windows_installer_gold_proof_artifact_fixed_plan_binds_downloads_root_and_receipt(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-post-import-fallback-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            intake_request = root / "missing-intake.json"
            plan = module.build_code_owned_post_import_plan(
                downloads_root,
                intake_request,
                handoff_timestamp="2026-07-13T17:31:14Z",
                authorize_external_mutations=True,
            )
            receipt = module.post_import_plan_receipt(plan, [])

        self.assertEqual(module.POST_IMPORT_PLAN_CONTRACT, plan["contract_name"])
        self.assertEqual(module.POST_IMPORT_PLAN_AUTHORITY, plan["authority"])
        self.assertEqual(21, len(plan["steps"]))
        first_argv = plan["steps"][0]["argv"]
        self.assertIn("--downloads-root", first_argv)
        self.assertEqual(str(downloads_root.resolve()), first_argv[first_argv.index("--downloads-root") + 1])
        self.assertEqual(str(intake_request.resolve()), plan["steps"][1]["argv"][-1])
        self.assertEqual(str(intake_request.resolve()), plan["steps"][2]["argv"][-1])
        self.assertEqual(plan["plan_sha256"], receipt["plan_sha256"])
        self.assertEqual(21, receipt["step_count"])
        self.assertFalse(receipt["shell"])
        self.assertEqual(
            "linux_child_subreaper_descendant_sweep",
            plan["process_termination_policy"]["mode"],
        )
        self.assertTrue(plan["process_termination_policy"]["zero_descendants_required"])
        self.assertEqual(
            module.POST_IMPORT_LOCAL_TIMEOUT_SECONDS,
            plan["steps"][0]["timeout_seconds"],
        )
        self.assertEqual(
            module.POST_IMPORT_EXTERNAL_TIMEOUT_SECONDS,
            plan["steps"][-1]["timeout_seconds"],
        )
        self.assertEqual(
            module.POST_IMPORT_TERMINATION_GRACE_SECONDS,
            receipt["steps"][0]["termination_grace_seconds"],
        )
        self.assertEqual(
            "linux_child_subreaper_descendant_sweep",
            receipt["steps"][0]["process_group_mode"],
        )

    def test_post_import_plan_defaults_to_local_staging_and_requires_cli_authority_for_external_mutations(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-local-stage-plan-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "intake.json"
            intake_request.write_text(
                json.dumps(
                    {
                        "authorize_external_mutations": True,
                        "post_import_gates": ["sync and promote from untrusted intake"],
                    }
                ),
                encoding="utf-8",
            )
            plan = module.build_code_owned_post_import_plan(
                root / "downloads",
                intake_request,
                handoff_timestamp="2026-07-13T17:31:14Z",
            )
            with mock.patch.object(
                module,
                "run_bound_python_subprocess",
                side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(module, bound_argv),
            ) as run_mock:
                returncode, results = module.run_post_import_chain(
                    intake_request,
                    root / "downloads",
                    plan=plan,
                )
            receipt = module.post_import_plan_receipt(plan, results)

        self.assertFalse(plan["external_mutation_authorization"]["requested"])
        self.assertFalse(plan["external_mutation_authorization"]["intake_request_can_authorize"])
        self.assertEqual(
            ["sync_important_work_to_teable", "attempt_flagship_public_stable_promotion"],
            [step["step_id"] for step in plan["steps"][-2:]],
        )
        self.assertTrue(
            all(step["execution_phase"] == "validation_staging" for step in plan["steps"][:-2])
        )
        self.assertTrue(
            all(step["execution_phase"] == "external_mutation" for step in plan["steps"][-2:])
        )
        self.assertEqual(4, returncode)
        self.assertEqual(19, len(results))
        self.assertEqual(19, run_mock.call_count)
        self.assertEqual("pending_authorized_external_mutation", receipt["status"])
        self.assertEqual(2, receipt["pending_external_step_count"])
        self.assertEqual(
            ["sync_important_work_to_teable", "attempt_flagship_public_stable_promotion"],
            receipt["pending_external_step_ids"],
        )

    def test_post_import_plan_is_fail_fast_and_never_promotes_after_sync_failure(self) -> None:
        module = load_import_module()
        plan = module.build_code_owned_post_import_plan(
            Path("/tmp/windows-proof-downloads"),
            Path("/tmp/windows-proof-intake.json"),
            handoff_timestamp="2026-07-13T17:31:14Z",
            authorize_external_mutations=True,
        )
        call_count = 0

        def fake_step(bound_argv, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 20:
                return fake_bound_python_result(
                    module,
                    bound_argv,
                    returncode=1,
                    stdout="",
                    stderr="sync failed\n",
                )
            return fake_bound_python_result(module, bound_argv)

        with mock.patch.object(module, "run_bound_python_subprocess", side_effect=fake_step) as run_mock:
            results = module.execute_code_owned_post_import_plan(plan)
        receipt = module.post_import_plan_receipt(plan, results)

        self.assertEqual(20, len(results))
        self.assertEqual(20, run_mock.call_count)
        self.assertEqual("sync_important_work_to_teable", results[-1]["step_id"])
        self.assertNotIn(
            "attempt_flagship_public_stable_promotion",
            [row["step_id"] for row in results],
        )
        self.assertEqual("fail", receipt["status"])

    def test_materialize_windows_installer_visual_audit_intake_request_keeps_external_blocker_honest(self) -> None:
        intake = load_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            drop = root / "drop"
            matching_source = drop / "returned" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            matching_source.parent.mkdir(parents=True)
            matching_source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            nightly_root = root / "staging"
            handoff = nightly_root / "nightly-run-test" / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"
            handoff.parent.mkdir(parents=True)
            handoff.write_text(
                json.dumps(
                    {
                        "status": "ready_for_windows_host",
                        "summary": "Windows installer visual proof is missing.",
                        "release_shelf_root": str(handoff.parent),
                        "only_blocker_is_visual_proof": True,
                    }
                ),
                encoding="utf-8",
            )
            visual_proof_receipt = handoff.parent / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
            visual_proof_receipt.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "contract_name": "chummer6-ui.windows_installer_visual_proof",
                        "platform": "windows",
                        "head": "avalonia",
                        "rid": "win-x64",
                        "artifactDigest": f"sha256:{sha}",
                        "screenshots": [
                            {"role": "progress", "path": "windows-installer-progress.png"},
                            {"role": "completion", "path": "windows-installer-completion.png"},
                        ],
                        "readabilityReview": {"status": "pass", "reviewer": "local_wine_capture"},
                        "contrastReview": {"status": "pass", "reviewer": "local_wine_capture"},
                        "clippingReview": {"status": "pass", "reviewer": "local_wine_capture"},
                        "checks": {"capture_mode": "manual_fallback_for_publish_automation"},
                        "notes": "Temporary proxy proof for publish-latest-nightly automation in Linux lane.",
                    }
                ),
                encoding="utf-8",
            )
            handoff.write_text(
                json.dumps(
                    {
                        "status": "ready_for_windows_host",
                        "summary": "Windows installer visual proof is missing.",
                        "release_shelf_root": str(handoff.parent),
                        "only_blocker_is_visual_proof": True,
                        "visual_proof_receipt_path": str(visual_proof_receipt),
                    }
                ),
                encoding="utf-8",
            )
            payload = intake.build_request(
                release_channel=release_channel,
                downloads_root=downloads_root,
                startup_receipt=startup,
                source=source,
                discovery_roots=[drop],
                nightly_root=nightly_root,
                dedicated_drop_root=drop / "dedicated",
                auto_import_roots=[drop, root / "Downloads"],
            )

        self.assertEqual("external_artifact_required", payload["status"])
        self.assertEqual("run-test", payload["release_version"])
        self.assertEqual("preview", payload["release_channel"])
        self.assertEqual(str(release_channel), payload["release_channel_receipt_path"])
        self.assertEqual(sha, payload["promoted_installer"]["sha256"])
        self.assertEqual(sha, payload["promoted_installer_sha256"])
        self.assertEqual(payload["operator_request"]["summary"], payload["summary"])
        self.assertEqual(payload["promoted_installer"], payload["artifact"])
        self.assertEqual(payload["artifact_intake"], payload["intake"])
        self.assertEqual(payload["preferred_drop_path"], payload["preferredDropPath"])
        self.assertTrue(payload["request_receipt_path"].endswith("WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"))
        self.assertFalse(payload["current_blocker"]["current_visual_source_matches_promoted"])
        self.assertEqual("not_found", payload["last_discovery"]["gold_proof_zip"]["status"])
        self.assertEqual(1, payload["last_discovery"]["visual_sources"]["matching_promoted_count"])
        self.assertTrue(payload["latest_nightly_visual_proof_handoff"]["only_blocker_is_visual_proof"])
        self.assertIn("Provide the native Windows gold proof bundle for the promoted installer.", payload["operator_request"]["summary"])
        self.assertIn(
            "Native Windows startup already matches the promoted digest; the remaining gap is digest-bound visual proof for install-progress and completion.",
            payload["operator_request"]["summary"],
        )
        self.assertIn("does not satisfy the native Windows gold audit", payload["operator_request"]["summary"])
        nightly_visual_proof = payload["latest_nightly_visual_proof_handoff"]["visual_proof_receipt"]
        self.assertFalse(nightly_visual_proof["suffices_for_native_gold_audit"])
        self.assertTrue(any("proxy or fallback" in item for item in nightly_visual_proof["native_gold_audit_gaps"]))
        self.assertTrue(any("default and scaled DPI" in item for item in nightly_visual_proof["native_gold_audit_gaps"]))
        self.assertEqual(str(drop / "dedicated"), payload["preferred_drop_folder"])
        self.assertEqual(str(drop / "dedicated" / f"windows-installer-gold-proof-{sha[:12]}.zip"), payload["preferred_drop_path"])
        self.assertEqual(f"windows-installer-gold-proof-{sha[:12]}.zip", payload["preferred_zip_name"])
        self.assertEqual(payload["preferred_zip_name"], payload["required_zip_filename"])
        self.assertEqual(str(drop / "dedicated" / "windows-installer"), payload["preferred_extracted_visual_dir"])
        self.assertEqual(str(drop / "dedicated"), payload["operator_request"]["preferred_drop_folder"])
        self.assertIn(f"windows-installer-gold-proof-{sha[:12]}.zip", payload["operator_request"]["preferred_zip_name"])
        self.assertEqual(str(drop / "dedicated" / "windows-installer"), payload["operator_request"]["preferred_extracted_visual_dir"])
        self.assertIn(str(drop / "dedicated" / f"windows-installer-gold-proof-{sha[:12]}.zip"), payload["import_command"])
        self.assertIn("--intake-request", payload["import_command"])
        self.assertIn("--verify", payload["import_command"])
        self.assertEqual(str(drop / "dedicated"), payload["artifact_intake"]["dedicated_drop_root"])
        self.assertFalse(payload["artifact_intake"]["dedicated_drop_root_gitignored"])
        self.assertIn("artifact_intake.py discover", payload["artifact_intake"]["discover_command"])
        self.assertIn("WINDOWS_INSTALLER_VISUAL_AUDIT.source.json", payload["artifact_intake"]["discover_visual_source_command"])
        self.assertEqual(str(drop / "dedicated" / "windows-installer"), payload["artifact_intake"]["preferred_extracted_visual_dir"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", payload["artifact_intake"]["auto_import_command"])
        self.assertIn("--intake-request", payload["artifact_intake"]["auto_import_command"])
        self.assertNotIn("--discovery-root", payload["artifact_intake"]["auto_import_command"])
        self.assertEqual(
            [str(drop), str(root / "Downloads")],
            payload["artifact_intake"]["auto_import_roots"],
        )
        self.assertEqual([str(drop)], payload["drop_roots_checked"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", payload["artifact_intake"]["auto_import_watch_command"])
        self.assertIn("--wait-seconds 900", payload["artifact_intake"]["auto_import_watch_command"])
        self.assertIn("--poll-seconds 10", payload["artifact_intake"]["auto_import_watch_command"])
        self.assertIn("--refresh-intake-request", payload["artifact_intake"]["auto_import_watch_command"])
        self.assertEqual("python_subprocess_start_new_session", payload["artifact_intake"]["watcher_launch_mode"])
        self.assertTrue(payload["artifact_intake"]["watcher_state_path"].endswith("windows_installer_gold_proof_watcher.generated.json"))
        self.assertTrue(payload["artifact_intake"]["watcher_pid_file"].endswith("windows_installer_gold_proof_watcher.pid"))
        self.assertTrue(payload["artifact_intake"]["watcher_log_path"].endswith("windows_installer_gold_proof_auto_import_watch.log"))
        self.assertIn("manage_windows_installer_gold_proof_watcher.py start", payload["artifact_intake"]["watcher_start_command"])
        self.assertIn("--intake-request", payload["artifact_intake"]["watcher_start_command"])
        self.assertIn("--refresh-intake-request", payload["artifact_intake"]["watcher_start_command"])
        self.assertIn("manage_windows_installer_gold_proof_watcher.py status", payload["artifact_intake"]["watcher_status_command"])
        self.assertIn("--intake-request", payload["artifact_intake"]["watcher_status_command"])
        self.assertIn("manage_windows_installer_gold_proof_watcher.py stop", payload["artifact_intake"]["watcher_stop_command"])
        self.assertIn("--intake-request", payload["artifact_intake"]["watcher_stop_command"])
        self.assertIn("verify_windows_installer_visual_audit.py", payload["artifact_intake"]["post_import_verify_command"])
        verifier_binding = payload["visual_audit_verifier_binding"]
        expected_verifier_sha256 = intake.sha256_file(SCRIPT_PATH)
        expected_bound_verify_command = intake.build_bound_visual_audit_verify_command(
            verifier_binding
        )
        self.assertEqual(str(SCRIPT_PATH), verifier_binding["path"])
        self.assertEqual(expected_verifier_sha256, verifier_binding["sha256"])
        self.assertEqual("observational_default", verifier_binding["execution_mode"])
        self.assertEqual(
            expected_bound_verify_command,
            payload["artifact_intake"]["post_import_verify_command"],
        )
        self.assertIn(
            f"--expected-verifier-sha256 {expected_verifier_sha256}",
            expected_bound_verify_command,
        )
        self.assertIn(
            "python3 ../scripts/release/_release_gate_common.py",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 scripts/sync_important_work_to_teable.py --sync",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
            payload["post_import_gates"],
        )
        self.assertIn(
            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
            payload["post_import_gates"],
        )
        self.assertTrue(
            all("http://127.0.0.1" not in command and "http://localhost" not in command for command in payload["post_import_gates"])
        )
        self.assertTrue(
            any("scripts/materialize_hub_local_release_proof.py" in command for command in payload["post_import_gates"])
        )
        verify_index = payload["post_import_gates"].index(
            expected_bound_verify_command
        )
        intake_refresh_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
        )
        intake_verify_index = payload["post_import_gates"].index(
            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py"
        )
        google_proof_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run"
        )
        google_request_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run"
        )
        google_verify_index = payload["post_import_gates"].index(
            "python3 scripts/verify_google_oauth_linking_proof.py"
        )
        ea_materialize_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_ea_operator_readiness.py"
        )
        ea_verify_index = payload["post_import_gates"].index(
            "python3 scripts/verify_ea_operator_readiness.py"
        )
        mymedia_materialize_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_mymedia_public_surface.py"
        )
        mymedia_verify_index = payload["post_import_gates"].index(
            "python3 scripts/verify_mymedia_public_surface.py"
        )
        teable_sync_index = payload["post_import_gates"].index(
            "python3 scripts/sync_important_work_to_teable.py --sync"
        )
        release_ready_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier"
        )
        readiness_gate_index = payload["post_import_gates"].index(
            "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
        )
        operator_dashboard_index = payload["post_import_gates"].index(
            "python3 scripts/materialize_operator_release_dashboard.py"
        )
        hub_local_proof_index = next(
            index
            for index, command in enumerate(payload["post_import_gates"])
            if "scripts/materialize_hub_local_release_proof.py" in command
        )
        final_gold_index = payload["post_import_gates"].index(
            "python3 scripts/final_gold_janitor.py --skip-materializers"
        )
        release_blockers_index = payload["post_import_gates"].index(
            "python3 ../scripts/release/_release_gate_common.py"
        )
        promotion_attempt_index = payload["post_import_gates"].index(
            "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json"
        )
        flagship_materialize_index = payload["post_import_gates"].index(
            "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json"
        )
        flagship_verify_index = payload["post_import_gates"].index(
            "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass"
        )
        handoff_refresh_index = payload["post_import_gates"].index(
            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\""
        )
        self.assertLess(verify_index, intake_refresh_index)
        self.assertLess(intake_refresh_index, intake_verify_index)
        self.assertLess(intake_verify_index, readiness_gate_index)
        self.assertLess(intake_refresh_index, readiness_gate_index)
        self.assertLess(readiness_gate_index, google_request_index)
        self.assertLess(google_request_index, google_proof_index)
        self.assertLess(google_proof_index, google_verify_index)
        self.assertLess(google_verify_index, ea_materialize_index)
        self.assertLess(ea_materialize_index, ea_verify_index)
        self.assertLess(ea_verify_index, mymedia_materialize_index)
        self.assertLess(mymedia_materialize_index, mymedia_verify_index)
        self.assertLess(mymedia_verify_index, teable_sync_index)
        self.assertLess(teable_sync_index, release_ready_index)
        self.assertLess(mymedia_verify_index, release_ready_index)
        self.assertLess(ea_verify_index, release_ready_index)
        self.assertLess(readiness_gate_index, release_ready_index)
        self.assertLess(readiness_gate_index, operator_dashboard_index)
        self.assertLess(operator_dashboard_index, hub_local_proof_index)
        self.assertLess(hub_local_proof_index, final_gold_index)
        self.assertLess(final_gold_index, release_blockers_index)
        self.assertLess(release_blockers_index, promotion_attempt_index)
        self.assertLess(promotion_attempt_index, flagship_materialize_index)
        self.assertLess(flagship_materialize_index, flagship_verify_index)
        self.assertLess(flagship_verify_index, handoff_refresh_index)
        self.assertFalse(payload["direct_telegram_sent"])
        self.assertTrue(payload["secrets_redacted"])
        telegram_draft = payload["operator_telegram_draft"]
        self.assertEqual("prepared_not_sent", telegram_draft["status"])
        self.assertIn("Chummer flagship blocker", telegram_draft["message_text"])
        self.assertIn("Current promoted release tuple: run-test | channel=preview", telegram_draft["message_text"])
        self.assertIn(sha, telegram_draft["message_text"])
        self.assertIn(str(drop / "dedicated" / f"windows-installer-gold-proof-{sha[:12]}.zip"), telegram_draft["message_text"])
        self.assertIn("Current startup-smoke receipt already matches the promoted installer digest.", telegram_draft["message_text"])
        self.assertIn(
            "Native Windows startup is already confirmed for the promoted digest; the remaining gap is the matching visual proof bundle.",
            telegram_draft["message_text"],
        )
        self.assertIn(
            "If you already captured the promoted install on Windows, package those screenshots; otherwise rerun the promoted installer and capture visual proof for: install-progress, completion.",
            telegram_draft["message_text"],
        )
        self.assertIn("you only need to include it again if you recapture startup on the Windows host", telegram_draft["message_text"])
        self.assertIn("Current visual source digest:", telegram_draft["message_text"])
        self.assertIn(f"copy that folder extracted to {drop / 'dedicated' / 'windows-installer'}", telegram_draft["message_text"])
        self.assertIn("If you use the extracted-directory route, discover it with:", telegram_draft["message_text"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", telegram_draft["message_text"])
        self.assertIn("full intake-request post-import gate chain", telegram_draft["message_text"])
        self.assertEqual(str(drop / "dedicated" / "windows-installer"), telegram_draft["preferred_extracted_visual_dir"])
        self.assertIn("WINDOWS_INSTALLER_VISUAL_AUDIT.source.json", telegram_draft["discover_visual_source_command"])
        self.assertIn("Provide the native Windows gold proof bundle for the promoted installer.", payload["operator_request"]["summary"])
        self.assertIn(
            "Native Windows startup already matches the promoted digest; the remaining gap is digest-bound visual proof for install-progress and completion.",
            payload["operator_request"]["summary"],
        )
        self.assertIn("send_telegram_message_via_ea.py", telegram_draft["send_command"])
        self.assertIn("--receipt-name", telegram_draft["send_command"])
        self.assertIn(telegram_draft["current_message_path"], telegram_draft["send_command"])
        self.assertNotIn(telegram_draft["message_path"], telegram_draft["send_command"])
        self.assertEqual("run-test", telegram_draft["release_version"])
        self.assertEqual("preview", telegram_draft["release_channel"])
        self.assertEqual(str(release_channel), telegram_draft["release_channel_receipt_path"])
        self.assertTrue(telegram_draft["request_receipt_path"].endswith("WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"))
        self.assertTrue(telegram_draft["message_path"].endswith(".txt"))
        self.assertTrue(telegram_draft["metadata_path"].endswith(".generated.json"))
        self.assertTrue(telegram_draft["current_message_path"].endswith("CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"))
        self.assertTrue(telegram_draft["current_metadata_path"].endswith("CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"))
        self.assertEqual(intake.sha256_text(telegram_draft["message_text"]), telegram_draft["message_sha256"])
        self.assertIn("import_windows_installer_gold_proof_artifact.py", telegram_draft["import_command"])
        self.assertIn("--intake-request", telegram_draft["import_command"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", telegram_draft["auto_import_watch_command"])
        self.assertIn("--intake-request", telegram_draft["auto_import_watch_command"])
        self.assertIn("--refresh-intake-request", telegram_draft["auto_import_watch_command"])
        self.assertTrue(telegram_draft["startup_receipt_matches_promoted"])
        self.assertFalse(payload["startup_receipt_bundle_required"])
        self.assertFalse(payload["operator_request"]["startup_receipt_bundle_required"])
        self.assertFalse(payload["artifact_intake"]["startup_receipt_bundle_required"])
        self.assertFalse(telegram_draft["startup_receipt_bundle_required"])
        self.assertFalse(telegram_draft["direct_send_allowed"])

    def test_materializer_blocks_unbound_installer_without_none_or_placeholder_instructions(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-unbound-installer-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            downloads_root.mkdir(parents=True)
            release_channel = downloads_root / "RELEASE_CHANNEL.generated.json"
            release_channel.write_text(
                json.dumps(
                    {
                        "version": "run-unbound",
                        "channel": "preview",
                        "supportabilityState": "preview_supported",
                        "rolloutState": "promoted_preview",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            try:
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    request_output=receipt_path,
                    discovery_roots=[root / "drop"],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "drop",
                )
                payload["operator_telegram_draft_materialized"] = (
                    intake.materialize_operator_telegram_draft(
                        payload["operator_telegram_draft"]
                    )
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertEqual(
            "blocked_missing_promoted_installer_binding",
            payload["status"],
        )
        self.assertFalse(payload["promoted_installer_binding_ready"])
        self.assertIn(
            "promoted_installer_sha256_missing_or_invalid",
            payload["promoted_installer_binding_failures"],
        )
        self.assertIn(
            "promoted_installer_filename_missing_or_invalid",
            payload["promoted_installer_binding_failures"],
        )
        self.assertEqual("", payload["preferred_zip_name"])
        self.assertEqual("", payload["required_zip_filename"])
        self.assertEqual("", payload["preferred_drop_path"])
        self.assertEqual("", payload["import_command"])
        self.assertFalse(payload["operator_request"]["actionable"])
        self.assertEqual([], payload["operator_request"]["powershell_commands"])
        self.assertEqual([], payload["operator_request"]["copy_to_windows"])
        self.assertEqual("blocked_not_sendable", payload["operator_telegram_draft"]["status"])
        self.assertEqual("", payload["operator_telegram_draft"]["send_command"])
        self.assertNotIn("windows-installer-gold-proof-promoted.zip", json.dumps(payload))
        self.assertNotIn("/None", json.dumps(payload))
        self.assertNotIn("\\\\None", json.dumps(payload))
        self.assertIn(
            "Do not run, capture, package, import, or send",
            payload["operator_telegram_draft"]["message_text"],
        )
        self.assertTrue(ok)
        self.assertEqual("pass", result["status"])
        self.assertEqual(
            "blocked_missing_promoted_installer_binding",
            result["effective_status"],
        )
        self.assertFalse(result["operator_action_still_required"])
        self.assertTrue(result["visual_audit_verifier_sha256_matches_current"])

    def test_intake_verifier_rejects_missing_or_stale_visual_verifier_binding(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-stale-verifier-binding-") as temp_dir:
            root = Path(temp_dir)
            payload, receipt_path, _sha = self._build_windows_visual_intake_request_payload(root)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)

            missing_binding_payload = json.loads(json.dumps(payload))
            missing_binding_payload.pop("visual_audit_verifier_binding")
            receipt_path.write_text(
                json.dumps(missing_binding_payload, indent=2) + "\n",
                encoding="utf-8",
            )
            missing_ok, missing_result = verifier.verify(
                receipt_path,
                require_pass=False,
            )

            stale_binding_payload = json.loads(json.dumps(payload))
            actual_sha256 = stale_binding_payload["visual_audit_verifier_binding"]["sha256"]
            stale_sha256 = "0" * 64 if actual_sha256 != "0" * 64 else "1" * 64
            stale_binding_payload["visual_audit_verifier_binding"]["sha256"] = stale_sha256
            receipt_path.write_text(
                json.dumps(stale_binding_payload, indent=2) + "\n",
                encoding="utf-8",
            )
            stale_ok, stale_result = verifier.verify(
                receipt_path,
                require_pass=False,
            )

        self.assertFalse(missing_ok)
        self.assertIn(
            "visual_audit_verifier_binding_missing",
            missing_result["structural_issues"],
        )
        self.assertIn(
            "artifact_intake_post_import_verify_command_unbound",
            missing_result["structural_issues"],
        )
        self.assertFalse(stale_ok)
        self.assertIn(
            "visual_audit_verifier_sha256_stale",
            stale_result["structural_issues"],
        )
        self.assertIn(
            "artifact_intake_post_import_verify_command_binding_mismatch",
            stale_result["structural_issues"],
        )
        self.assertFalse(
            stale_result["visual_audit_verifier_sha256_matches_current"]
        )

    def test_windows_visual_intake_request_keeps_manifest_digest_when_shelf_bytes_disagree(self) -> None:
        intake = load_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-manifest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, actual_sha = self._write_release_fixture(root)
            release_payload = json.loads(release_channel.read_text(encoding="utf-8"))
            manifest_sha = "c" * 64
            release_payload["artifacts"][0]["sha256"] = manifest_sha
            release_channel.write_text(json.dumps(release_payload), encoding="utf-8")
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir(parents=True, exist_ok=True)
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{actual_sha}"}),
                encoding="utf-8",
            )
            source = self._write_valid_windows_visual_source_fixture(
                downloads_root,
                source_artifact_sha=actual_sha,
            )

            payload = intake.build_request(
                release_channel=release_channel,
                downloads_root=downloads_root,
                startup_receipt=startup,
                source=source,
                request_output=root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                discovery_roots=[root / "drop"],
                nightly_root=root / "nightly",
                dedicated_drop_root=root / "drop",
            )

        self.assertEqual(manifest_sha, payload["promoted_installer_sha256"])
        self.assertEqual(manifest_sha, payload["promoted_installer"]["sha256"])
        self.assertEqual(manifest_sha, payload["promoted_installer"]["manifest_sha256"])
        self.assertEqual(actual_sha, payload["promoted_installer"]["actual_sha256"])
        self.assertEqual(f"windows-installer-gold-proof-{manifest_sha[:12]}.zip", payload["preferred_zip_name"])
        self.assertEqual(payload["preferred_zip_name"], payload["required_zip_filename"])
        self.assertIn(
            "promoted Windows installer manifest sha256 does not match artifact bytes",
            payload["current_blocker"]["failure"],
        )

    def test_materialize_windows_installer_visual_audit_intake_request_rejects_pass_shaped_audit_wrapper(self) -> None:
        intake = load_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-pass-shaped-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir(parents=True, exist_ok=True)
            startup.write_text(json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}) + "\n", encoding="utf-8")
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("{}\n", encoding="utf-8")
            drop = root / "drop"
            drop.mkdir(parents=True, exist_ok=True)

            mocked_audit = {
                "status": "pass",
                "artifact": {
                    "fileName": "chummer-avalonia-win-x64-installer.exe",
                    "sha256": sha,
                    "actualSha256": sha,
                    "path": str(downloads_root / "files" / "chummer-avalonia-win-x64-installer.exe"),
                },
                "source_digest_matches_promoted": False,
                "startupReceipt": {
                    "status": "pass",
                    "artifactDigestMatchesPromoted": True,
                    "requiresNativeRefresh": False,
                },
                "visualAuditSource": {
                    "status": "pass",
                    "path": str(source),
                    "artifactSha256": "0" * 64,
                    "artifactDigestMatchesPromoted": False,
                },
                "failures": [],
                "nextActions": [],
            }

            with mock.patch.object(intake.visual_audit, "build_payload", return_value=mocked_audit):
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    discovery_roots=[drop],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=drop / "dedicated",
                )

        self.assertEqual("external_artifact_required", payload["status"])
        self.assertFalse(payload["current_blocker"]["current_visual_source_matches_promoted"])
        self.assertFalse(payload["startup_receipt_bundle_required"])
        self.assertIn(
            "Native Windows startup already matches the promoted digest; the remaining gap is digest-bound visual proof for install-progress and completion.",
            payload["operator_request"]["summary"],
        )

    def test_materialize_windows_installer_visual_audit_intake_request_resolves_relative_output_path(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-main-relative-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            relative_output = Path(".codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json")
            output_path = root / relative_output
            original_cwd = Path.cwd()
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            original_published_root = intake.PUBLISHED_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            intake.PUBLISHED_ROOT = root / "published"
            try:
                with mock.patch.object(
                    intake,
                    "parse_args",
                    return_value=argparse.Namespace(
                        release_channel=release_channel,
                        portal_release_channel=release_channel,
                        downloads_root=downloads_root,
                        startup_receipt=startup,
                        source=source,
                        output=relative_output,
                        nightly_root=root / "nightly",
                        dedicated_drop_root=root / "drop",
                        discovery_root=None,
                    ),
                ):
                    os.chdir(root)
                    self.assertEqual(0, intake.main())
            finally:
                os.chdir(original_cwd)
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root
                intake.PUBLISHED_ROOT = original_published_root

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(str(output_path.resolve()), payload["request_receipt_path"])
            self.assertEqual(str(output_path.resolve()), payload["operator_telegram_draft"]["request_receipt_path"])
            self.assertEqual(str(output_path.resolve()), payload["operator_telegram_draft_materialized"]["request_receipt_path"])

            ok, result = verifier.verify(output_path, require_pass=False)

        self.assertTrue(ok)
        self.assertEqual("pass", result["status"])
        self.assertTrue(result["recovery_pack_pass"])

    def test_verify_windows_installer_visual_audit_intake_request_reports_missing_receipt_structurally(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-verify-missing-") as temp_dir:
            path = Path(temp_dir) / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"

            ok, result = verifier.verify(path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertEqual("missing", result["structural_status"])
        self.assertEqual("missing", result["effective_status"])
        self.assertEqual("missing", result["request_status"])
        self.assertEqual(
            [f"missing_windows_visual_intake_request:{path}"],
            result["issues"],
        )

    def test_verify_windows_installer_visual_audit_intake_request_reports_malformed_receipt_structurally(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-verify-invalid-") as temp_dir:
            path = Path(temp_dir) / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            path.write_text("{not json}\n", encoding="utf-8")

            ok, result = verifier.verify(path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertEqual("invalid", result["structural_status"])
        self.assertEqual("invalid", result["effective_status"])
        self.assertEqual("invalid", result["request_status"])
        self.assertEqual(
            [f"malformed_windows_visual_intake_request:{path}"],
            result["issues"],
        )

    def test_verify_windows_installer_visual_audit_intake_request_accepts_structural_recovery_pack(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-verify-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            original_published_root = intake.PUBLISHED_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            intake.PUBLISHED_ROOT = root / "published"
            try:
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    discovery_roots=[root / "drop"],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "drop",
                )
                payload["request_receipt_path"] = str(output_path)
                payload["operator_telegram_draft"]["request_receipt_path"] = str(output_path)
                payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                    payload["operator_telegram_draft"]
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root
                intake.PUBLISHED_ROOT = original_published_root

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(output_path, require_pass=False)

        self.assertTrue(ok)
        self.assertEqual("pass", result["status"])
        self.assertEqual("external_artifact_required", result["request_status"])
        self.assertTrue(result["operator_action_still_required"])
        self.assertTrue(result["recovery_pack_pass"])
        self.assertEqual([], result["issues"])
        self.assertEqual(
            payload["operator_telegram_draft_materialized"]["operator_ask_text_path"],
            result["operator_ask_text_path"],
        )
        self.assertEqual(
            payload["operator_telegram_draft_materialized"]["operator_ask_metadata_path"],
            result["operator_ask_metadata_path"],
        )
        self.assertEqual(
            payload["operator_telegram_draft_materialized"]["operator_ask_send_command"],
            result["operator_ask_send_command"],
        )
        self.assertEqual(
            payload["operator_telegram_draft_materialized"]["operator_ask_receipt_name"],
            result["operator_ask_receipt_name"],
        )

    def test_verify_windows_installer_visual_audit_intake_request_only_flags_manifest_mismatch_when_live_startup_and_visual_match_effective_digest(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-live-audit-manifest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            payload, receipt_path, sha = self._build_windows_visual_intake_request_payload(root)
            current_audit_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            self._write_current_windows_visual_audit_receipt(
                current_audit_path,
                status="fail",
                source_digest_matches_promoted=True,
                manifest_artifact_sha="b" * 64,
                startup_status="pass",
                startup_digest_matches_promoted=True,
                visual_status="pass",
                visual_digest_matches_promoted=True,
                failures=["promoted Windows installer manifest sha256 does not match artifact bytes"],
                failed_gates=[],
                explicit_pass=False,
            )
            payload["current_blocker"]["receipt"] = str(current_audit_path)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertTrue(ok)
        self.assertEqual("pass", result["status"])
        self.assertEqual("external_artifact_required", result["effective_status"])
        self.assertIn(
            "current_windows_visual_audit_artifact_digest_mismatch",
            result["current_windows_visual_audit_issues"],
        )
        self.assertNotIn(
            "current_windows_visual_audit_startup_digest_mismatch",
            result["current_windows_visual_audit_issues"],
        )
        self.assertNotIn(
            "current_windows_visual_audit_visual_digest_mismatch",
            result["current_windows_visual_audit_issues"],
        )

    def test_verify_windows_installer_visual_audit_intake_request_rejects_stale_not_required_when_live_audit_fails(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-live-audit-fail-") as temp_dir:
            root = Path(temp_dir)
            payload, receipt_path, sha = self._build_windows_visual_intake_request_payload(
                root,
                source_artifact_sha="0" * 64,
            )
            current_audit_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            self._write_current_windows_visual_audit_receipt(
                current_audit_path,
                status="pass",
                source_digest_matches_promoted=False,
                startup_status="pass",
                startup_digest_matches_promoted=True,
                visual_status="pass",
                visual_digest_matches_promoted=False,
                failures=[],
                failed_gates=[],
                explicit_pass=True,
                artifact_sha=sha,
            )
            payload["status"] = "not_required"
            payload["current_blocker"]["receipt"] = str(current_audit_path)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertEqual("not_required", result["request_status"])
        self.assertEqual("external_artifact_required", result["effective_status"])
        self.assertTrue(result["operator_action_still_required"])
        self.assertFalse(result["current_windows_visual_audit_effective_pass"])
        self.assertEqual("pass", result["current_windows_visual_audit_status"])
        self.assertIn("not_required_without_valid_current_windows_visual_audit", result["issues"])
        self.assertIn(
            "current_windows_visual_audit_source_digest_mismatch",
            result["current_windows_visual_audit_issues"],
        )
        self.assertIn(
            "current_windows_visual_audit_visual_digest_mismatch",
            result["current_windows_visual_audit_issues"],
        )
        self.assertTrue(result["recovery_pack_pass"])

    def test_verify_windows_installer_visual_audit_intake_request_rejects_stale_external_artifact_required_when_live_audit_passes(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-live-audit-pass-") as temp_dir:
            root = Path(temp_dir)
            payload, receipt_path, sha = self._build_windows_visual_intake_request_payload(
                root,
            )
            current_audit_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            self._write_current_windows_visual_audit_receipt(
                current_audit_path,
                status="pass",
                source_digest_matches_promoted=True,
                startup_status="pass",
                startup_digest_matches_promoted=True,
                visual_status="pass",
                visual_digest_matches_promoted=True,
                failures=[],
                failed_gates=[],
                explicit_pass=True,
                artifact_sha=sha,
            )
            payload["status"] = "external_artifact_required"
            payload["current_blocker"]["receipt"] = str(current_audit_path)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertEqual("external_artifact_required", result["request_status"])
        self.assertEqual("not_required", result["effective_status"])
        self.assertFalse(result["operator_action_still_required"])
        self.assertTrue(result["current_windows_visual_audit_effective_pass"])
        self.assertEqual("pass", result["current_windows_visual_audit_status"])
        self.assertIn(
            "external_artifact_required_despite_valid_current_windows_visual_audit",
            result["issues"],
        )
        self.assertEqual([], result["current_windows_visual_audit_issues"])
        self.assertTrue(result["recovery_pack_pass"])

    def test_verify_windows_installer_visual_audit_intake_request_keeps_current_digest_request_active(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-stale-audit-digest-") as temp_dir:
            root = Path(temp_dir)
            payload, receipt_path, sha = self._build_windows_visual_intake_request_payload(root)
            current_audit_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            stale_sha = "a" * 64
            self.assertNotEqual(sha, stale_sha)
            self._write_current_windows_visual_audit_receipt(
                current_audit_path,
                status="pass",
                source_digest_matches_promoted=True,
                startup_status="pass",
                startup_digest_matches_promoted=True,
                visual_status="pass",
                visual_digest_matches_promoted=True,
                failures=[],
                failed_gates=[],
                explicit_pass=True,
                artifact_sha=stale_sha,
            )
            payload["status"] = "external_artifact_required"
            payload["current_blocker"]["receipt"] = str(current_audit_path)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertTrue(ok)
        self.assertEqual("pass", result["status"])
        self.assertEqual("external_artifact_required", result["request_status"])
        self.assertEqual("external_artifact_required", result["effective_status"])
        self.assertTrue(result["operator_action_still_required"])
        self.assertFalse(result["current_windows_visual_audit_effective_pass"])
        self.assertEqual(stale_sha, result["current_windows_visual_audit_promoted_installer_sha256"])
        self.assertEqual(sha, result["promoted_installer_sha256"])
        self.assertIn(
            "current_windows_visual_audit_promoted_digest_mismatch",
            result["current_windows_visual_audit_issues"],
        )
        self.assertNotIn(
            "external_artifact_required_despite_valid_current_windows_visual_audit",
            result["issues"],
        )
        self.assertTrue(result["recovery_pack_pass"])

    def test_verify_windows_installer_visual_audit_intake_request_rejects_mismatched_request_path(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-verify-fail-") as temp_dir:
            root = Path(temp_dir)
            current_message_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            current_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            source_message_path = root / "_completion" / "windows-proof-operator-ask.txt"
            source_metadata_path = root / "_completion" / "windows-proof-operator-ask.generated.json"
            for path, content in [
                (current_message_path, "windows ask\n"),
                (source_message_path, "windows ask\n"),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            message_sha = load_intake_module().sha256_text("windows ask\n")
            metadata_payload = {
                "request_receipt_path": str(root / "wrong.json"),
                "current_message_path": str(current_message_path),
                "message_sha256": message_sha,
                "receipt_name": "windows.receipt.json",
                "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file operator-ask.txt --receipt-name windows.receipt.json",
                "preferred_drop_path": str(root / "drop" / "windows.zip"),
                "promoted_installer_sha256": "a" * 64,
                "secrets_redacted": True,
                "source_message_path": str(source_message_path),
                "source_metadata_path": str(source_metadata_path),
            }
            current_metadata_path.write_text(json.dumps(metadata_payload) + "\n", encoding="utf-8")
            source_metadata_path.write_text(
                json.dumps(
                    {
                        "request_receipt_path": str(root / "wrong.json"),
                        "message_sha256": message_sha,
                        "receipt_name": "windows.receipt.json",
                        "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file operator-ask.txt --receipt-name windows.receipt.json",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.windows_installer_visual_audit_intake_request.v1",
                        "generated_at_utc": "2026-07-04T21:15:00Z",
                        "status": "external_artifact_required",
                        "provider": "native_windows_operator",
                        "release_channel_receipt_path": str(root / "RELEASE_CHANNEL.generated.json"),
                        "release_version": "run-test",
                        "release_channel": "stable",
                        "request_receipt_path": str(root / "wrong.json"),
                        "promoted_installer_sha256": "a" * 64,
                        "preferred_drop_path": str(root / "drop" / "windows.zip"),
                        "preferred_zip_name": "windows.zip",
                        "required_zip_filename": "windows.zip",
                        "current_blocker": {"receipt": str(root / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json")},
                        "operator_request": {
                            "summary": "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
                            "required_surfaces": ["install-progress", "completion"],
                            "required_dpi_scales": ["1.0", "1.5"],
                            "required_host_class_prefix": "native-windows",
                            "powershell_commands": ["one", "two"],
                        },
                        "operator_telegram_draft": {
                            "current_message_path": str(current_message_path),
                            "current_metadata_path": str(current_metadata_path),
                            "message_path": str(source_message_path),
                            "metadata_path": str(source_metadata_path),
                            "message_sha256": message_sha,
                            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file operator-ask.txt --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "discover_command": "discover",
                            "import_command": "import",
                            "auto_import_command": "auto",
                            "auto_import_watch_command": "watch",
                            "auto_import_roots": [str(root / "drop")],
                            "post_import_verify_command": "verify",
                        },
                        "expected_artifact_patterns": [
                            "*windows-installer-gold-proof*.zip",
                            "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                            "windows.zip",
                        ],
                        "post_import_gates": [
                            "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
                            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
                            "python3 scripts/materialize_operator_release_dashboard.py",
                            "python3 scripts/final_gold_janitor.py --skip-materializers",
                            "python3 ../scripts/release/_release_gate_common.py",
                            "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json",
                            "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json",
                            "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass",
                            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
                        ],
                        "secrets_redacted": True,
                        "direct_telegram_sent": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertIn("request_receipt_path_mismatch", result["issues"])

    def test_verify_windows_installer_visual_audit_intake_request_rejects_loopback_url_in_published_commands(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-loopback-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            try:
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    discovery_roots=[root / "drop"],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "drop",
                )
                payload["request_receipt_path"] = str(receipt_path)
                payload["operator_telegram_draft"]["request_receipt_path"] = str(receipt_path)
                payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                    payload["operator_telegram_draft"]
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

            payload["post_import_gates"][0] = "python3 scripts/tool.py --base-url http://127.0.0.1:8091"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertIn("published_commands_contain_loopback_url", result["issues"])

    def test_verify_windows_installer_visual_audit_intake_request_rejects_import_commands_without_intake_request_and_verify_note(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-import-flags-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            try:
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    request_output=receipt_path,
                    discovery_roots=[root / "drop"],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "drop",
                )
                payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                    payload["operator_telegram_draft"]
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

            payload["artifact_intake"]["import_command"] = "python3 scripts/import_windows_installer_gold_proof_artifact.py bundle.zip --verify"
            payload["artifact_intake"]["auto_import_command"] = "python3 scripts/auto_import_windows_installer_gold_proof.py"
            payload["artifact_intake"]["auto_import_watch_command"] = "python3 scripts/auto_import_windows_installer_gold_proof.py --wait-seconds 900 --poll-seconds 10"
            payload["artifact_intake"]["watcher_state_path"] = ""
            payload["artifact_intake"]["watcher_pid_file"] = ""
            payload["artifact_intake"]["watcher_log_path"] = ""
            payload["artifact_intake"]["watcher_start_command"] = "python3 scripts/manage_windows_installer_gold_proof_watcher.py start --wait-seconds 3600"
            payload["artifact_intake"]["watcher_status_command"] = "python3 scripts/manage_windows_installer_gold_proof_watcher.py status"
            payload["artifact_intake"]["watcher_stop_command"] = "python3 scripts/manage_windows_installer_gold_proof_watcher.py stop"
            payload["artifact_intake"]["post_import_verify_note"] = ""
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertIn("artifact_intake_import_command_missing_intake_request", result["issues"])
        self.assertIn("artifact_intake_auto_import_command_missing_intake_request", result["issues"])
        self.assertIn("artifact_intake_auto_import_watch_command_missing_intake_request", result["issues"])
        self.assertIn("artifact_intake_watcher_state_path_missing", result["issues"])
        self.assertIn("artifact_intake_watcher_pid_file_missing", result["issues"])
        self.assertIn("artifact_intake_watcher_log_path_missing", result["issues"])
        self.assertIn("artifact_intake_watcher_start_command_missing_intake_request", result["issues"])
        self.assertIn("artifact_intake_watcher_status_command_missing_intake_request", result["issues"])
        self.assertIn("artifact_intake_watcher_stop_command_missing_intake_request", result["issues"])
        self.assertIn("artifact_intake_post_import_verify_note_mismatch", result["issues"])

    def test_verify_windows_installer_visual_audit_intake_request_rejects_flagship_refresh_order_drift(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-flagship-refresh-order-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            try:
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    request_output=receipt_path,
                    discovery_roots=[root / "drop"],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "drop",
                )
                payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                    payload["operator_telegram_draft"]
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

            final_gold_command = "python3 scripts/final_gold_janitor.py --skip-materializers"
            release_blockers_command = "python3 ../scripts/release/_release_gate_common.py"
            promotion_attempt_command = (
                "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output "
                "../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json"
            )
            flagship_materialize_command = (
                "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output "
                "../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json"
            )
            flagship_verify_command = (
                "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt "
                "../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json "
                "--require-flagship-pass"
            )
            handoff_command = (
                "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "
                "\"$(date --iso-8601=seconds)\""
            )
            final_gold_index = payload["post_import_gates"].index(final_gold_command)
            release_blockers_index = payload["post_import_gates"].index(release_blockers_command)
            promotion_attempt_index = payload["post_import_gates"].index(promotion_attempt_command)
            flagship_materialize_index = payload["post_import_gates"].index(flagship_materialize_command)
            flagship_verify_index = payload["post_import_gates"].index(flagship_verify_command)
            handoff_index = payload["post_import_gates"].index(handoff_command)
            payload["post_import_gates"][promotion_attempt_index] = handoff_command
            payload["post_import_gates"][handoff_index] = promotion_attempt_command
            self.assertLess(release_blockers_index, payload["post_import_gates"].index(promotion_attempt_command))
            self.assertLess(flagship_materialize_index, payload["post_import_gates"].index(promotion_attempt_command))
            self.assertLess(flagship_verify_index, payload["post_import_gates"].index(promotion_attempt_command))

            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(receipt_path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertIn("post_import_gates_flagship_refresh_order_invalid", result["issues"])

    def test_materialize_windows_installer_visual_audit_operator_telegram_draft_writes_files(self) -> None:
        intake = load_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-draft-") as temp_dir:
            root = Path(temp_dir)
            expected_draft_root = root / "_completion" / "windows_installer_visual_audit"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = expected_draft_root
            try:
                draft = intake.build_operator_telegram_draft(
                    promoted_digest="deadbeef" * 8,
                    installer_file_name="chummer-avalonia-win-x64-installer.exe",
                    preferred_drop_path=root / "incoming" / "windows-installer-gold-proof-deadbeefdead.zip",
                    import_command=(
                        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                        f"bundle.zip --intake-request {root / 'published' / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                        "--verify"
                    ),
                    operator_summary="Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
                    current_failure="Windows installer visual audit source digest does not match promoted installer",
                    required_surfaces=["install-progress", "completion"],
                    required_dpi_scales=["1.0", "1.5"],
                )
                metadata = intake.materialize_operator_telegram_draft(draft)
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

            message_path = Path(draft["message_path"])
            metadata_path = Path(draft["metadata_path"])
            current_message_path = Path(draft["current_message_path"])
            current_metadata_path = Path(draft["current_metadata_path"])
            self.assertTrue(message_path.is_file())
            self.assertTrue(metadata_path.is_file())
            self.assertTrue(current_message_path.is_file())
            self.assertTrue(current_metadata_path.is_file())
            self.assertIn("native Windows host", message_path.read_text(encoding="utf-8"))
            self.assertEqual(message_path.read_text(encoding="utf-8"), current_message_path.read_text(encoding="utf-8"))
            stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            current_metadata = json.loads(current_metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["message_sha256"], stored_metadata["message_sha256"])
            self.assertEqual(metadata["message_sha256"], current_metadata["message_sha256"])
            self.assertEqual("deadbeef" * 8, stored_metadata["promoted_installer_sha256"])
            self.assertEqual(str(root / "incoming" / "windows-installer-gold-proof-deadbeefdead.zip"), stored_metadata["preferred_drop_path"])
            self.assertEqual(str(current_message_path), stored_metadata["operator_ask_text_path"])
            self.assertEqual(str(current_metadata_path), stored_metadata["operator_ask_metadata_path"])
            self.assertEqual(draft["send_command"], stored_metadata["operator_ask_send_command"])
            self.assertEqual(draft["receipt_name"], stored_metadata["operator_ask_receipt_name"])
            self.assertNotIn("message_text", stored_metadata)
            self.assertEqual(str(message_path), current_metadata["source_message_path"])
            self.assertEqual(str(metadata_path), current_metadata["source_metadata_path"])
            self.assertEqual(str(current_message_path), current_metadata["operator_ask_text_path"])
            self.assertEqual(str(current_metadata_path), current_metadata["operator_ask_metadata_path"])
            self.assertEqual(draft["send_command"], current_metadata["operator_ask_send_command"])
            self.assertEqual(draft["receipt_name"], current_metadata["operator_ask_receipt_name"])
            self.assertTrue(stored_metadata["secrets_redacted"])
            self.assertTrue(current_metadata["secrets_redacted"])
            self.assertTrue(str(current_message_path).startswith(str(expected_draft_root)))
            self.assertTrue(str(current_metadata_path).startswith(str(expected_draft_root)))

    def test_build_operator_telegram_draft_rebinds_current_paths_to_patched_draft_root(self) -> None:
        intake = load_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-current-paths-") as temp_dir:
            root = Path(temp_dir)
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            try:
                draft = intake.build_operator_telegram_draft(
                    promoted_digest="feedface" * 8,
                    installer_file_name="chummer-avalonia-win-x64-installer.exe",
                    preferred_drop_path=root / "incoming" / "windows-installer-gold-proof-feedfacefeed.zip",
                    import_command=(
                        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                        f"bundle.zip --intake-request {root / 'published' / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                        "--verify"
                    ),
                    operator_summary="Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
                    current_failure="Windows installer visual audit source digest does not match promoted installer",
                    required_surfaces=["install-progress", "completion"],
                    required_dpi_scales=["1.0", "1.5"],
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

        self.assertTrue(
            draft["current_message_path"].startswith(str(root / "_completion" / "windows_installer_visual_audit"))
        )
        self.assertTrue(
            draft["current_metadata_path"].startswith(str(root / "_completion" / "windows_installer_visual_audit"))
        )
        self.assertTrue(draft["current_message_path"].endswith("CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"))
        self.assertTrue(
            draft["current_metadata_path"].endswith("CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json")
        )
        self.assertIn(draft["current_message_path"], draft["send_command"])
        self.assertNotIn(draft["message_path"], draft["send_command"])

    def test_auto_import_windows_installer_gold_proof_prefers_named_drop_bundle(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-discover-") as temp_dir:
            root = Path(temp_dir)
            dedicated = root / "dedicated"
            other = root / "other"
            dedicated.mkdir()
            other.mkdir()
            preferred = dedicated / "windows-installer-gold-proof-deadbeef1234.zip"
            preferred.write_bytes(b"preferred")
            (other / "windows-installer-gold-proof-random.zip").write_bytes(b"other")
            intake = {
                "artifact_intake": {
                    "preferred_drop_path": str(preferred),
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                ],
            }

            candidates = module.discover_candidates(intake, [dedicated, other])

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(str(preferred), candidates[0]["path"])
        self.assertEqual("preferred_drop_path", candidates[0]["discovery_kind"])

    def test_auto_import_windows_installer_gold_proof_accepts_top_level_preferred_drop_path(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-top-level-") as temp_dir:
            root = Path(temp_dir)
            dedicated = root / "dedicated"
            other = root / "other"
            dedicated.mkdir()
            other.mkdir()
            preferred = dedicated / "windows-installer-gold-proof-deadbeef1234.zip"
            preferred.write_bytes(b"preferred")
            (other / "windows-installer-gold-proof-random.zip").write_bytes(b"other")
            intake = {
                "preferred_drop_path": str(preferred),
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                ],
            }

            roots = module.discovery_roots_from_intake(intake)
            candidates = module.discover_candidates(intake, roots + [other])

        self.assertTrue(any(path == dedicated for path in roots))
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(str(preferred), candidates[0]["path"])
        self.assertEqual("preferred_drop_path", candidates[0]["discovery_kind"])

    def test_auto_import_windows_installer_gold_proof_does_not_auto_select_generic_zip_when_required_filename_is_known(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-generic-zip-") as temp_dir:
            root = Path(temp_dir)
            dedicated = root / "dedicated"
            other = root / "other"
            dedicated.mkdir()
            other.mkdir()
            preferred = dedicated / "windows-installer-gold-proof-deadbeef1234.zip"
            generic = other / "windows-installer-gold-proof-random.zip"
            generic.write_bytes(b"generic")
            intake = {
                "artifact_intake": {
                    "preferred_drop_path": str(preferred),
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                ],
            }

            candidates = module.discover_candidates(intake, [dedicated, other])
            selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual(str(generic), candidates[0]["path"])
        self.assertTrue(candidates[0]["is_zip_candidate"])
        self.assertFalse(candidates[0]["required_zip_filename_match"])
        self.assertFalse(candidates[0]["auto_import_ready"])
        self.assertEqual("invalid", candidates[0]["zip_inspection_status"])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_auto_selects_matching_nonpreferred_zip_candidates(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-matching-generic-zip-") as temp_dir:
            root = Path(temp_dir)
            dedicated = root / "dedicated"
            other = root / "other"
            dedicated.mkdir()
            other.mkdir()
            preferred = dedicated / "windows-installer-gold-proof-deadbeef1234.zip"
            generic = other / "windows-installer-gold-proof-random.zip"
            promoted_digest = "d" * 64
            write_valid_gold_proof_zip(generic, digest=promoted_digest)
            intake = {
                "promoted_installer_sha256": promoted_digest,
                "startup_receipt_bundle_required": False,
                "artifact_intake": {
                    "preferred_drop_path": str(preferred),
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [dedicated, other])
            selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual(str(generic), candidates[0]["path"])
        self.assertTrue(candidates[0]["is_zip_candidate"])
        self.assertFalse(candidates[0]["required_zip_filename_match"])
        self.assertTrue(candidates[0]["matches_promoted_installer"])
        self.assertTrue(candidates[0]["auto_import_ready"])
        self.assertEqual("ready", candidates[0]["zip_inspection_status"])
        self.assertEqual(generic.resolve(), selected.resolve())

    def test_auto_import_windows_installer_gold_proof_accepts_artifact_intake_auto_import_roots(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-intake-roots-") as temp_dir:
            root = Path(temp_dir)
            dedicated = root / "dedicated"
            downloads = root / "Downloads"
            dedicated.mkdir()
            downloads.mkdir()
            intake = {
                "artifact_intake": {
                    "auto_import_roots": [
                        str(dedicated),
                        str(downloads),
                    ],
                },
            }

            roots = module.discovery_roots_from_intake(intake)

        self.assertEqual([dedicated, downloads], roots)

    def test_auto_import_windows_installer_gold_proof_expands_home_relative_auto_import_roots(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-home-relative-") as temp_dir:
            home = Path(temp_dir) / "home"
            downloads = home / "Downloads"
            intake = {
                "artifact_intake": {
                    "auto_import_roots": ["~/Downloads"],
                },
            }

            with mock.patch("pathlib.Path.home", return_value=home):
                roots = module.discovery_roots_from_intake(intake)

        self.assertEqual([downloads], roots)

    def test_auto_import_windows_installer_gold_proof_does_not_recurse_broad_auto_import_roots(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-broad-root-") as temp_dir:
            root = Path(temp_dir)
            downloads = root / "Downloads"
            downloads.mkdir()
            preferred = downloads / "windows-installer-gold-proof-deadbeef1234.zip"
            preferred.write_bytes(b"preferred")
            intake = {
                "artifact_intake": {
                    "auto_import_roots": [str(downloads)],
                    "preferred_drop_path": str(preferred),
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                ],
                "drop_roots_checked": [],
            }

            with mock.patch.object(module, "walk_candidate_files", side_effect=AssertionError("broad roots should not recurse")):
                candidates = module.discover_candidates(intake, [downloads])

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(str(preferred), candidates[0]["path"])
        self.assertEqual("preferred_drop_path", candidates[0]["discovery_kind"])

    def test_auto_import_windows_installer_gold_proof_reports_but_rejects_temp_directory_artifact(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-temp-root-") as temp_dir:
            temp_root = Path(temp_dir) / "tmp"
            artifact = temp_root / "nested" / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                encoding="utf-8",
            )
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "deadbeef",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "artifact_intake": {
                    "auto_import_roots": [str(temp_root)],
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
                "drop_roots_checked": [],
            }

            with mock.patch("tempfile.gettempdir", return_value=str(temp_root)):
                candidates = module.discover_candidates(intake, [temp_root])

        self.assertEqual(1, len(candidates))
        self.assertEqual("visual_source_directory", candidates[0]["discovery_kind"])
        self.assertFalse(candidates[0]["matches_promoted_installer"])
        self.assertFalse(candidates[0]["auto_import_ready"])
        self.assertEqual("rejected_directory_artifact", candidates[0]["inspection_status"])
        self.assertEqual("zip_bundle_required", candidates[0]["rejection_code"])

    def test_auto_import_windows_installer_gold_proof_ignores_visual_source_only_candidates(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-ignore-source-") as temp_dir:
            root = Path(temp_dir)
            visual_root = root / "returned" / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            visual_root.mkdir(parents=True)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps({"status": "pass", "screenshots": []}),
                encoding="utf-8",
            )
            intake = {
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [root])

        self.assertEqual([], candidates)

    def test_auto_import_windows_installer_gold_proof_never_inspects_or_selects_matching_directory_candidates(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-dir-candidate-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                encoding="utf-8",
            )
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "deadbeef",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual("visual_source_directory", candidates[0]["discovery_kind"])
        self.assertFalse(candidates[0]["matches_promoted_installer"])
        self.assertFalse(candidates[0]["auto_import_ready"])
        self.assertEqual("rejected_directory_artifact", candidates[0]["inspection_status"])
        self.assertNotIn("artifact_sha256", candidates[0])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_rejects_visual_only_directory_when_startup_bundle_optional(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-visual-only-dir-candidate-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            visual_root.mkdir(parents=True)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "deadbeef",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "startup_receipt_bundle_required": False,
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual("visual_source_directory", candidates[0]["discovery_kind"])
        self.assertFalse(candidates[0]["matches_promoted_installer"])
        self.assertEqual("zip_bundle_required", candidates[0]["rejection_code"])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_rejects_portable_visual_only_directory_when_startup_bundle_optional(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-portable-visual-only-dir-candidate-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "windows-installer"
            artifact.mkdir(parents=True)
            (artifact / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "deadbeef",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "startup_receipt_bundle_required": False,
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual("visual_source_directory", candidates[0]["discovery_kind"])
        self.assertFalse(candidates[0]["matches_promoted_installer"])
        self.assertEqual("zip_bundle_required", candidates[0]["rejection_code"])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_rejects_stale_directory_without_inspecting_digest(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-stale-dir-candidate-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                encoding="utf-8",
            )
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "staledigest",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual("visual_source_directory", candidates[0]["discovery_kind"])
        self.assertNotIn("artifact_sha256", candidates[0])
        self.assertFalse(candidates[0]["matches_promoted_installer"])
        self.assertEqual("zip_bundle_required", candidates[0]["rejection_code"])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_surfaces_stage_visual_proof_receipts_without_auto_selecting_them(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-stage-receipt-") as temp_dir:
            root = Path(temp_dir)
            receipt = root / "matching" / "Chummer.Portal" / "downloads" / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(
                json.dumps(
                    {
                        "contractName": "chummer6-ui.windows_installer_visual_proof",
                        "status": "pass",
                        "releaseVersion": "run-test",
                        "artifactDigest": "sha256:artifactdeadbeef",
                        "installerSha256": "deadbeef",
                        "headId": "avalonia",
                        "rid": "win-x64",
                        "generatedAt": "2026-07-06T03:00:00Z",
                        "screenshots": [
                            {"role": "progress"},
                            {"role": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)
            actionable = module.actionable_waiting_candidates(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual("stage_visual_proof_receipt", candidates[0]["discovery_kind"])
        self.assertTrue(candidates[0]["is_stage_visual_proof_receipt"])
        self.assertEqual("deadbeef", candidates[0]["installer_sha256"])
        self.assertEqual("artifactdeadbeef", candidates[0]["artifact_sha256"])
        self.assertTrue(candidates[0]["matches_promoted_installer"])
        self.assertEqual("avalonia", candidates[0]["head_id"])
        self.assertEqual("win-x64", candidates[0]["rid"])
        self.assertEqual(["progress", "completion"], candidates[0]["screenshot_roles"])
        self.assertTrue(candidates[0]["requires_gold_bundle_recapture"])
        self.assertIsNone(selected)
        self.assertEqual([], actionable)

    def test_auto_import_windows_installer_gold_proof_discovers_candidates_without_path_rglob(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-no-rglob-") as temp_dir:
            root = Path(temp_dir)
            preferred = root / "incoming" / "windows-installer-gold-proof-deadbeef1234.zip"
            preferred.parent.mkdir(parents=True)
            preferred.write_bytes(b"preferred")
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                encoding="utf-8",
            )
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "deadbeef",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "artifact_intake": {
                    "preferred_drop_path": str(preferred),
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
            }

            with mock.patch("pathlib.Path.rglob", side_effect=AssertionError("discover_candidates should not use Path.rglob")):
                candidates = module.discover_candidates(intake, [root])
                selected = module.selected_candidate(candidates)

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(str(preferred), candidates[0]["path"])
        self.assertEqual("preferred_drop_path", candidates[0]["discovery_kind"])
        self.assertTrue(any(row["discovery_kind"] == "visual_source_directory" for row in candidates))
        self.assertFalse(candidates[0]["auto_import_ready"])
        self.assertEqual("invalid", candidates[0]["zip_inspection_status"])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_tolerates_candidate_removed_before_sort(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-disappearing-candidate-") as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            incoming.mkdir()
            bundle = incoming / "windows-installer-gold-proof-deadbeef1234.zip"
            bundle.write_bytes(b"not a zip")
            intake = {
                "artifact_intake": {
                    "preferred_drop_path": str(bundle),
                },
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    bundle.name,
                ],
            }

            original_file_row = module.file_row

            def disappearing_file_row(path: Path, discovery_kind: str, priority: int) -> dict[str, object]:
                row = original_file_row(path, discovery_kind, priority)
                if path == bundle and bundle.exists():
                    bundle.unlink()
                return row

            with mock.patch.object(module, "file_row", side_effect=disappearing_file_row):
                candidates = module.discover_candidates(intake, [incoming])
                selected = module.selected_candidate(candidates)

        self.assertEqual(1, len(candidates))
        self.assertEqual(str(bundle), candidates[0]["path"])
        self.assertEqual("invalid", candidates[0]["zip_inspection_status"])
        self.assertIsNone(selected)

    def test_auto_import_windows_installer_gold_proof_waiting_payload_surfaces_expected_bundle_details(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-waiting-") as temp_dir:
            root = Path(temp_dir)
            promoted_sha = "deadbeef1234" + ("0" * 52)
            preferred_drop_path = root / "incoming" / "windows-installer-gold-proof-deadbeef1234.zip"
            intake = {
                "release_channel_receipt_path": str(root / "published" / "RELEASE_CHANNEL.generated.json"),
                "release_version": "run-test",
                "release_channel": "preview",
                "release_supportability_state": "preview_supported",
                "release_rollout_state": "promoted_preview",
                "promoted_installer_sha256": promoted_sha,
                "preferred_drop_folder": str(preferred_drop_path.parent),
                "preferred_drop_path": str(preferred_drop_path),
                "preferred_zip_name": preferred_drop_path.name,
                "required_zip_filename": preferred_drop_path.name,
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred_drop_path.name,
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
                "drop_roots_checked": [
                    str(preferred_drop_path.parent),
                    "/tmp",
                ],
                "last_discovery": {
                    "visual_sources": {
                        "count": 3,
                        "matching_promoted_count": 1,
                    }
                },
                "artifact_intake": {
                    "dedicated_drop_root": str(preferred_drop_path.parent),
                    "preferred_drop_path": str(preferred_drop_path),
                    "auto_import_roots": [
                        str(preferred_drop_path.parent),
                        "/tmp",
                        "~/Downloads",
                    ],
                    "import_command": (
                        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                        f"{preferred_drop_path} --intake-request {root / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                        "--verify"
                    ),
                    "discover_command": "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover ...",
                    "post_import_verify_command": "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                },
                "operator_request": {
                    "summary": "Provide the native Windows gold-proof bundle.",
                },
                "operator_telegram_draft": {
                    "message_path": str(root / "_completion" / "windows-proof-operator-ask.txt"),
                    "current_message_path": str(root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"),
                    "current_metadata_path": str(root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"),
                    "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file operator-ask.txt",
                    "message_preview": "Native Windows gold proof still missing.",
                },
            }

            payload = module.build_waiting_payload(
                artifact=None,
                candidates=[],
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[preferred_drop_path.parent, Path("/tmp"), Path("~/Downloads")],
            )

        self.assertEqual("waiting_for_artifact", payload["status"])
        self.assertEqual(str(root / "published" / "RELEASE_CHANNEL.generated.json"), payload["release_channel_receipt_path"])
        self.assertEqual("run-test", payload["release_version"])
        self.assertEqual("preview", payload["release_channel"])
        self.assertEqual("preview_supported", payload["release_supportability_state"])
        self.assertEqual("promoted_preview", payload["release_rollout_state"])
        self.assertEqual(promoted_sha, payload["promoted_installer_sha256"])
        self.assertEqual(str(preferred_drop_path.parent), payload["preferred_drop_folder"])
        self.assertEqual(str(preferred_drop_path), payload["preferred_drop_path"])
        self.assertEqual(preferred_drop_path.name, payload["preferred_zip_name"])
        self.assertEqual(preferred_drop_path.name, payload["required_zip_filename"])
        self.assertEqual(
            [
                "*windows-installer-gold-proof*.zip",
                preferred_drop_path.name,
                "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            ],
            payload["expected_artifact_patterns"],
        )
        self.assertEqual([str(preferred_drop_path.parent), "/tmp"], payload["drop_roots_checked"])
        self.assertEqual(
            [str(preferred_drop_path.parent), "/tmp", "~/Downloads"],
            payload["auto_import_roots_checked"],
        )
        self.assertEqual(
            [str(preferred_drop_path.parent), "/tmp", "~/Downloads"],
            payload["all_discovery_roots_checked"],
        )
        self.assertIn("all_discovery_roots_checked", payload["drop_roots_checked_note"])
        self.assertEqual([preferred_drop_path.name], payload["expected_exact_names"])
        self.assertEqual(
            [
                "*windows-installer-gold-proof*.zip",
                preferred_drop_path.name,
                "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            ],
            payload["expected_glob_patterns"],
        )
        for key in (
            "import_command",
            "discover_command",
            "auto_import_command",
            "auto_import_watch_command",
            "post_import_verify_command",
            "operator_summary",
            "operator_telegram_draft",
            "operator_telegram_send_command",
        ):
            self.assertTrue(payload[key]["redacted"], key)
            self.assertRegex(payload[key]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(0, payload["directory_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_directory_candidate_count"])
        self.assertEqual([], payload["matching_promoted_directory_candidates"])
        self.assertEqual(0, payload["stale_directory_candidate_count"])
        self.assertEqual([], payload["stale_directory_candidates"])
        self.assertEqual(0, payload["suppressed_stale_directory_candidate_count"])
        self.assertEqual(0, payload["zip_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_zip_candidate_count"])
        self.assertEqual([], payload["matching_promoted_zip_candidates"])
        self.assertEqual([], payload["candidates"])
        self.assertEqual(0, payload["actionable_candidate_count"])
        self.assertFalse(payload["directory_candidates_require_explicit_artifact"])
        self.assertEqual("", payload["directory_candidate_note"])
        self.assertEqual(3, payload["intake_visual_source_count"])
        self.assertEqual(1, payload["intake_matching_promoted_visual_source_count"])
        serialized_payload = json.dumps(payload, sort_keys=True)
        self.assertNotIn("send_telegram_message_via_ea.py", serialized_payload)
        self.assertNotIn("Native Windows gold proof still missing.", serialized_payload)
        self.assertEqual(0, payload["stage_visual_proof_receipt_count"])
        self.assertEqual(0, payload["matching_promoted_stage_visual_proof_receipt_count"])
        self.assertEqual([], payload["matching_promoted_stage_visual_proof_receipts"])
        self.assertEqual(0, payload["stale_stage_visual_proof_receipt_count"])
        self.assertEqual([], payload["stale_stage_visual_proof_receipts"])
        self.assertEqual(0, payload["suppressed_stale_stage_visual_proof_receipt_count"])
        self.assertEqual("", payload["stage_visual_proof_receipt_note"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_redacts_operator_commands_drafts_and_secrets(self) -> None:
        module = load_auto_import_module()
        command_secret = "COMMAND_SECRET_8f540c"
        draft_secret = "DRAFT_SECRET_3d7e1b"
        token_secret = "TOKEN_SECRET_9b0a6e"
        with tempfile.TemporaryDirectory(prefix="windows-proof-waiting-redaction-") as temp_dir:
            root = Path(temp_dir)
            intake = {
                "promoted_installer_sha256": "a" * 64,
                "promoted_installer_binding_failures": [
                    f"binding failed with {command_secret}"
                ],
                "operator_request": {"summary": draft_secret},
                "operator_telegram_draft": {
                    "message_text": draft_secret,
                    "send_command": f"telegram --token {token_secret}",
                },
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "proof.zip"),
                    "import_command": f"import --credential {command_secret}",
                    "discover_command": f"discover --secret {command_secret}",
                    "auto_import_command": f"auto --token {token_secret}",
                    "auto_import_watch_command": f"watch --token {token_secret}",
                    "post_import_verify_command": f"verify --password {command_secret}",
                },
                "last_discovery": {
                    "api_token": token_secret,
                    "visual_sources": {"count": 0, "matching_promoted_count": 0},
                },
            }

            payload = module.build_waiting_payload(
                artifact=None,
                candidates=[],
                intake=intake,
                intake_request=root / "intake.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        serialized_payload = json.dumps(payload, sort_keys=True)
        for secret in (command_secret, draft_secret, token_secret):
            self.assertNotIn(secret, serialized_payload)
        self.assertTrue(payload["import_command"]["redacted"])
        self.assertTrue(payload["operator_telegram_draft"]["redacted"])
        self.assertTrue(payload["operator_summary"]["redacted"])
        self.assertTrue(payload["intake_last_discovery"]["api_token"]["redacted"])
        self.assertTrue(payload["promoted_installer_binding_failures"]["redacted"])

    def test_auto_import_receipt_redactor_removes_raw_exception_candidate_result_and_nested_secrets(self) -> None:
        module = load_auto_import_module()
        secrets = {
            "exception": "EXCEPTION_SECRET_d9a76c",
            "candidate": "CANDIDATE_SECRET_c48231",
            "result": "RESULT_SECRET_1e970b",
            "token": "TOKEN_SECRET_4120ac",
        }
        payload = module.redact_waiting_receipt_value(
            {
                "raw_exception": {"message": secrets["exception"]},
                "raw_candidate": {"path": secrets["candidate"]},
                "raw_result": {"stdout": secrets["result"]},
                "safe_candidate": {
                    "path": "/portable/proof.zip",
                    "session_token": secrets["token"],
                },
            }
        )

        serialized = json.dumps(payload, sort_keys=True)
        for secret in secrets.values():
            self.assertNotIn(secret, serialized)
        for key in ("raw_exception", "raw_candidate", "raw_result"):
            self.assertTrue(payload[key]["redacted"], key)
            self.assertRegex(payload[key]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("/portable/proof.zip", payload["safe_candidate"]["path"])
        self.assertTrue(payload["safe_candidate"]["session_token"]["redacted"])

    def test_auto_import_failure_details_never_emit_raw_exception_message(self) -> None:
        module = load_auto_import_module()
        secret = "RAW_EXCEPTION_SECRET_25b5d8"

        details = module.import_failure_details(RuntimeError(secret))

        serialized = json.dumps(details, sort_keys=True)
        self.assertNotIn(secret, serialized)
        self.assertEqual("RuntimeError", details["type"])
        self.assertIsNone(details["code"])
        self.assertTrue(details["message_receipt"]["redacted"])
        self.assertRegex(details["message_receipt"]["sha256"], r"^[0-9a-f]{64}$")

    def test_auto_import_failure_details_redacts_string_system_exit_code(self) -> None:
        module = load_auto_import_module()
        secret = "SYSTEM_EXIT_CODE_SECRET_a72fd1"

        details = module.import_failure_details(SystemExit(secret))

        serialized = json.dumps(details, sort_keys=True)
        self.assertNotIn(secret, serialized)
        self.assertEqual("SystemExit", details["type"])
        self.assertIsNone(details["code"])
        self.assertTrue(details["code_receipt"]["redacted"])
        self.assertTrue(details["message_receipt"]["redacted"])
        self.assertRegex(details["code_receipt"]["sha256"], r"^[0-9a-f]{64}$")

    def test_auto_import_windows_installer_gold_proof_waiting_payload_surfaces_rejected_directory_candidates(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-waiting-dir-") as temp_dir:
            root = Path(temp_dir)
            candidate = root / "candidate"
            visual_root = candidate / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = candidate / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                encoding="utf-8",
            )
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "hostClass": "native-windows-test-host",
                        "artifactSha256": "deadbeef",
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "last_discovery": {
                    "visual_sources": {
                        "count": 1,
                        "matching_promoted_count": 1,
                    }
                },
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"),
                },
            }
            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(1, payload["directory_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_directory_candidate_count"])
        self.assertEqual([], payload["matching_promoted_directory_candidates"])
        self.assertEqual(1, payload["stale_directory_candidate_count"])
        self.assertEqual(1, len(payload["stale_directory_candidates"]))
        self.assertEqual(0, payload["suppressed_stale_directory_candidate_count"])
        self.assertEqual(0, payload["zip_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_zip_candidate_count"])
        self.assertEqual([], payload["matching_promoted_zip_candidates"])
        self.assertEqual(0, payload["actionable_candidate_count"])
        self.assertEqual([], payload["candidates"])
        self.assertTrue(payload["directory_candidates_require_explicit_artifact"])
        self.assertIn("rejected without inspection", payload["directory_candidate_note"])
        self.assertEqual("zip_bundle_required", payload["stale_directory_candidates"][0]["rejection_code"])
        self.assertEqual(1, payload["intake_visual_source_count"])
        self.assertEqual(1, payload["intake_matching_promoted_visual_source_count"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_surfaces_matching_zip_candidates(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-waiting-zip-") as temp_dir:
            root = Path(temp_dir)
            preferred = root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"
            generic = root / "other" / "windows-installer-gold-proof-random.zip"
            generic.parent.mkdir(parents=True)
            promoted_digest = "d" * 64
            write_valid_gold_proof_zip(generic, digest=promoted_digest)
            intake = {
                "promoted_installer_sha256": promoted_digest,
                "startup_receipt_bundle_required": False,
                "expected_artifact_patterns": [
                    "*windows-installer-gold-proof*.zip",
                    preferred.name,
                    "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                ],
                "artifact_intake": {
                    "preferred_drop_path": str(preferred),
                },
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(generic.resolve(), selected.resolve())
        self.assertEqual(0, payload["directory_candidate_count"])
        self.assertEqual(1, payload["zip_candidate_count"])
        self.assertEqual(1, payload["matching_promoted_zip_candidate_count"])
        self.assertEqual(1, len(payload["matching_promoted_zip_candidates"]))
        self.assertEqual(str(generic), payload["matching_promoted_zip_candidates"][0]["path"])
        self.assertEqual("ready", payload["matching_promoted_zip_candidates"][0]["zip_inspection_status"])
        self.assertEqual(1, payload["actionable_candidate_count"])
        self.assertEqual(1, len(payload["candidates"]))
        self.assertTrue(payload["candidates"][0]["auto_import_ready"])
        self.assertTrue(payload["candidates"][0]["manual_import_command"]["redacted"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_surfaces_stage_visual_proof_receipt_hints_separately(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-stage-payload-") as temp_dir:
            root = Path(temp_dir)
            matching = root / "matching" / "Chummer.Portal" / "downloads" / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
            stale = root / "stale" / "Chummer.Portal" / "downloads" / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
            matching.parent.mkdir(parents=True)
            stale.parent.mkdir(parents=True)
            matching.write_text(
                json.dumps(
                    {
                        "contractName": "chummer6-ui.windows_installer_visual_proof",
                        "status": "pass",
                        "releaseVersion": "run-test",
                        "installerSha256": "deadbeef",
                        "headId": "avalonia",
                        "rid": "win-x64",
                        "generatedAt": "2026-07-06T03:00:00Z",
                        "screenshots": [{"role": "progress"}, {"role": "completion"}],
                    }
                ),
                encoding="utf-8",
            )
            stale.write_text(
                json.dumps(
                    {
                        "contractName": "chummer6-ui.windows_installer_visual_proof",
                        "status": "pass",
                        "releaseVersion": "run-stale",
                        "installerSha256": "staledigest",
                        "headId": "avalonia",
                        "rid": "win-x64",
                        "generatedAt": "2026-07-06T02:00:00Z",
                        "screenshots": [{"role": "progress"}],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"),
                },
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(0, payload["directory_candidate_count"])
        self.assertEqual(0, payload["actionable_candidate_count"])
        self.assertEqual([], payload["candidates"])
        self.assertEqual(2, payload["stage_visual_proof_receipt_count"])
        self.assertEqual(1, payload["matching_promoted_stage_visual_proof_receipt_count"])
        self.assertEqual(1, len(payload["matching_promoted_stage_visual_proof_receipts"]))
        self.assertEqual(1, payload["stale_stage_visual_proof_receipt_count"])
        self.assertEqual(1, len(payload["stale_stage_visual_proof_receipts"]))
        self.assertEqual(0, payload["suppressed_stale_stage_visual_proof_receipt_count"])
        self.assertTrue(payload["matching_promoted_stage_visual_proof_receipts"][0]["requires_gold_bundle_recapture"])
        self.assertIn("not auto-importable gold-proof bundles", payload["stage_visual_proof_receipt_note"])
        self.assertIn("digest-mismatched", payload["stage_visual_proof_receipt_note"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_surfaces_startup_smoke_receipt_hints_separately(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-startup-payload-") as temp_dir:
            root = Path(temp_dir)
            matching = root / "matching" / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            stale = root / "stale" / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            matching.parent.mkdir(parents=True)
            stale.parent.mkdir(parents=True)
            matching.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "releaseVersion": "run-test",
                        "artifactDigest": "sha256:deadbeef",
                        "headId": "avalonia",
                        "rid": "win-x64",
                        "recordedAtUtc": "2026-07-06T03:05:00Z",
                    }
                ),
                encoding="utf-8",
            )
            stale.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "releaseVersion": "run-stale",
                        "artifactDigest": "sha256:staledigest",
                        "headId": "avalonia",
                        "rid": "win-x64",
                        "recordedAtUtc": "2026-07-06T02:05:00Z",
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"),
                },
            }

            candidates = module.discover_candidates(intake, [root])
            selected = module.selected_candidate(candidates)
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(0, payload["directory_candidate_count"])
        self.assertEqual(0, payload["actionable_candidate_count"])
        self.assertIsNone(selected)
        self.assertEqual(0, payload["stage_visual_proof_receipt_count"])
        self.assertEqual(2, payload["stage_startup_smoke_receipt_count"])
        self.assertEqual(1, payload["matching_promoted_stage_startup_smoke_receipt_count"])
        self.assertEqual(1, len(payload["matching_promoted_stage_startup_smoke_receipts"]))
        self.assertEqual(1, payload["stale_stage_startup_smoke_receipt_count"])
        self.assertEqual(1, len(payload["stale_stage_startup_smoke_receipts"]))
        self.assertEqual(0, payload["suppressed_stale_stage_startup_smoke_receipt_count"])
        self.assertTrue(payload["matching_promoted_stage_startup_smoke_receipts"][0]["startup_already_proven"])
        self.assertIn("Startup is already proven", payload["stage_startup_smoke_receipt_note"])
        self.assertIn("digest-mismatched", payload["stage_startup_smoke_receipt_note"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_rejects_pass_shaped_stage_startup_receipt(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-startup-pass-shaped-") as temp_dir:
            root = Path(temp_dir)
            matching = root / "matching" / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            matching.parent.mkdir(parents=True)
            matching.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "releaseVersion": "run-test",
                        "artifactDigest": "sha256:deadbeef",
                        "headId": "avalonia",
                        "rid": "win-x64",
                        "recordedAtUtc": "2026-07-06T03:05:00Z",
                        "failures": ["startup receipt still has an embedded blocker"],
                    }
                ),
                encoding="utf-8",
            )
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"),
                },
            }

            candidates = module.discover_candidates(intake, [root])
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(1, payload["matching_promoted_stage_startup_smoke_receipt_count"])
        self.assertEqual(0, payload["matching_promoted_stage_startup_smoke_proven_count"])
        self.assertFalse(payload["matching_promoted_stage_startup_smoke_receipts"][0]["startup_already_proven"])
        self.assertIn("not semantically passing", payload["stage_startup_smoke_receipt_note"])
        self.assertNotIn("Startup is already proven", payload["stage_startup_smoke_receipt_note"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_summarizes_stale_directory_noise(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-stale-summary-") as temp_dir:
            root = Path(temp_dir)
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "startup_receipt_bundle_required": False,
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"),
                },
            }

            for index in range(module.STALE_DIRECTORY_SAMPLE_LIMIT + 2):
                candidate = root / f"stale-{index}"
                visual_root = candidate / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
                startup_root = candidate / "Chummer.Portal" / "downloads" / "startup-smoke"
                visual_root.mkdir(parents=True)
                startup_root.mkdir(parents=True)
                (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                    json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                    encoding="utf-8",
                )
                (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                    json.dumps(
                        {
                            "status": "pass",
                            "hostClass": "native-windows-test-host",
                            "artifactSha256": f"stale-{index}",
                            "screenshots": [],
                        }
                    ),
                    encoding="utf-8",
                )

            candidates = module.discover_candidates(intake, [root])
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(module.STALE_DIRECTORY_SAMPLE_LIMIT + 2, payload["directory_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_directory_candidate_count"])
        self.assertEqual([], payload["matching_promoted_directory_candidates"])
        self.assertEqual(module.STALE_DIRECTORY_SAMPLE_LIMIT + 2, payload["stale_directory_candidate_count"])
        self.assertEqual(module.STALE_DIRECTORY_SAMPLE_LIMIT, len(payload["stale_directory_candidates"]))
        self.assertEqual(1, len(payload["stale_directory_digest_summary"]))
        self.assertEqual(
            module.STALE_DIRECTORY_SAMPLE_LIMIT + 2,
            payload["stale_directory_digest_summary"][0]["count"],
        )
        self.assertEqual("missing", payload["stale_directory_digest_summary"][0]["artifact_sha256"])
        self.assertEqual(0, payload["stage_like_stale_directory_candidate_count"])
        self.assertEqual(2, payload["suppressed_stale_directory_candidate_count"])
        self.assertEqual([], payload["candidates"])
        self.assertEqual(0, payload["actionable_candidate_count"])
        self.assertTrue(payload["directory_candidates_require_explicit_artifact"])
        self.assertIn("rejected without inspection", payload["directory_candidate_note"])

    def test_auto_import_windows_installer_gold_proof_groups_stale_directory_digests_and_stage_like_counts(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-stale-digests-") as temp_dir:
            root = Path(temp_dir)
            intake = {
                "promoted_installer_sha256": "deadbeef",
                "startup_receipt_bundle_required": False,
                "artifact_intake": {
                    "preferred_drop_path": str(root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"),
                },
            }

            fixtures = [
                ("stage-a", "old-digest-a", True),
                ("stage-b", "old-digest-a", False),
                ("stage-c", "old-digest-b", True),
            ]
            for name, digest, stage_like in fixtures:
                candidate = root / name
                downloads_root = candidate / "Chummer.Portal" / "downloads"
                visual_root = downloads_root / "visual-audit" / "windows-installer"
                visual_root.mkdir(parents=True)
                (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                    json.dumps(
                        {
                            "status": "pass",
                            "hostClass": "native-windows-test-host",
                            "artifactSha256": digest,
                            "sourceUpdatedAtUtc": "2026-07-06T02:00:00Z",
                            "screenshots": [],
                        }
                    ),
                    encoding="utf-8",
                )
                if stage_like:
                    (downloads_root / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json").write_text(
                        json.dumps({"status": "pass"}),
                        encoding="utf-8",
                    )
                    (downloads_root / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json").write_text(
                        json.dumps({"status": "ready_for_windows_host"}),
                        encoding="utf-8",
                    )

            candidates = module.discover_candidates(intake, [root])
            payload = module.build_waiting_payload(
                artifact=None,
                candidates=candidates,
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[root],
            )

        self.assertEqual(3, payload["stale_directory_candidate_count"])
        self.assertEqual(0, payload["stage_like_stale_directory_candidate_count"])
        self.assertEqual(1, len(payload["stale_directory_digest_summary"]))
        self.assertEqual("missing", payload["stale_directory_digest_summary"][0]["artifact_sha256"])
        self.assertEqual(3, payload["stale_directory_digest_summary"][0]["count"])
        self.assertEqual(0, payload["stale_directory_digest_summary"][0]["stage_like_count"])

    def test_auto_import_windows_installer_gold_proof_imports_and_uses_code_owned_plan(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-import-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "windows-installer-gold-proof.zip"
            write_valid_gold_proof_zip(artifact)
            downloads_root = root / "downloads"
            downloads_root.mkdir()
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            injection = "touch /tmp/auto-import-request-command-injection && false"
            intake = {
                "post_import_gates": [injection],
            }
            intake_request.write_text(json.dumps(intake) + "\n", encoding="utf-8")

            import_summary = module.import_proof_artifact(artifact, downloads_root)
            plan = module.build_code_owned_post_import_plan(
                downloads_root,
                intake_request,
                handoff_timestamp="2026-07-13T17:31:14Z",
                authorize_external_mutations=True,
            )
            fake_results = [
                {
                    "status": "pass",
                    "returncode": 0,
                    "plan_sha256": plan["plan_sha256"],
                    "step_id": step["step_id"],
                    "ordinal": step["ordinal"],
                    "execution_binding_sha256": step["execution_binding_sha256"],
                    "shell": False,
                }
                for step in plan["steps"]
            ]
            with mock.patch.object(
                module.proof_importer,
                "execute_code_owned_post_import_plan",
                return_value=fake_results,
            ) as execute_mock:
                results = module.execute_code_owned_post_import_plan(
                    plan,
                    side_effects_paused=False,
                )
            payload = module.build_result_payload(
                artifact=artifact,
                intake_request=intake_request,
                downloads_root=downloads_root,
                roots=[root],
                candidates=[],
                import_summary=import_summary,
                command_results=results,
                post_import_plan=plan,
                intake_post_import_gate_metadata=(
                    module.proof_importer.request_post_import_gate_metadata(intake)
                ),
                post_import_side_effects_paused=False,
            )

            self.assertTrue((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").is_file())
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").is_file())

        self.assertEqual("pass", payload["status"])
        execute_mock.assert_called_once_with(
            plan,
            external_mutation_pause_check=module.auto_import_side_effects_paused,
        )
        self.assertEqual(module.proof_importer.POST_IMPORT_PLAN_AUTHORITY, payload["post_import_plan"]["authority"])
        self.assertEqual(plan["plan_sha256"], payload["post_import_plan"]["plan_sha256"])
        self.assertTrue(payload["intake_post_import_gates"]["ignored"])
        self.assertEqual(1, payload["intake_post_import_gates"]["item_count"])
        self.assertNotIn(injection, json.dumps(plan))
        self.assertNotIn(injection, json.dumps(payload))

    def test_auto_import_windows_installer_gold_proof_main_writes_fail_receipt_for_invalid_selected_bundle(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-import-invalid-") as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            incoming.mkdir()
            bundle = incoming / "windows-installer-gold-proof-deadbeefdead.zip"
            bundle.write_bytes(b"not a zip")
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            output = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            downloads_root = root / "downloads"

            with (
                mock.patch.object(
                    module,
                    "parse_args",
                    return_value=argparse.Namespace(
                        artifact=bundle,
                        intake_request=intake_request,
                        output=output,
                        downloads_root=downloads_root,
                        discovery_root=[str(incoming)],
                        wait_seconds=0.0,
                        poll_seconds=5.0,
                        refresh_intake_request=False,
                    ),
                ),
                mock.patch.object(
                    module,
                    "auto_import_side_effects_paused",
                    return_value=False,
                ),
            ):
                intake_request.write_text(
                    json.dumps(
                        {
                            "promoted_installer_sha256": "deadbeef" * 8,
                            "preferred_drop_path": str(bundle),
                            "preferred_zip_name": bundle.name,
                            "required_zip_filename": bundle.name,
                            "expected_artifact_patterns": [
                                "*windows-installer-gold-proof*.zip",
                                bundle.name,
                            ],
                            "artifact_intake": {
                                "preferred_drop_path": str(bundle),
                                "auto_import_roots": [str(incoming)],
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                exit_code = module.main()

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertEqual(str(bundle), payload["artifact"])
        self.assertEqual("BadZipFile", payload["import_failure"]["type"])
        self.assertIn("Selected Windows installer gold-proof artifact failed import validation", payload["summary"])
        self.assertEqual([], payload["post_import_commands"])

    def test_auto_import_windows_installer_gold_proof_main_passes_downloads_root_into_ensure_intake_request(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-import-refresh-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            output = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            downloads_root = root / "downloads"
            incoming = root / "incoming"
            incoming.mkdir()
            captured: dict[str, object] = {}

            def fake_ensure(path: Path, refresh: bool, downloads_root: Path) -> dict[str, object]:
                captured["path"] = path
                captured["refresh"] = refresh
                captured["downloads_root"] = downloads_root
                return {
                    "preferred_drop_path": str(incoming / "windows-installer-gold-proof.zip"),
                    "artifact_intake": {
                        "preferred_drop_path": str(incoming / "windows-installer-gold-proof.zip"),
                        "auto_import_roots": [str(incoming)],
                    },
                }

            with (
                mock.patch.object(
                    module,
                    "parse_args",
                    return_value=argparse.Namespace(
                        artifact=None,
                        intake_request=intake_request,
                        output=output,
                        downloads_root=downloads_root,
                        discovery_root=None,
                        wait_seconds=0.0,
                        poll_seconds=5.0,
                        refresh_intake_request=True,
                    ),
                ),
                mock.patch.object(module, "ensure_intake_request", side_effect=fake_ensure),
                mock.patch.object(module, "wait_for_candidate", return_value=(None, [])),
            ):
                exit_code = module.main()

            self.assertEqual(2, exit_code)
            self.assertEqual(
                {
                    "path": intake_request,
                    "refresh": True,
                    "downloads_root": downloads_root,
                },
                captured,
            )

    def test_auto_import_code_owned_plan_pause_prevents_execution(self) -> None:
        module = load_auto_import_module()
        plan = module.build_code_owned_post_import_plan(
            Path("/tmp/windows-proof-downloads"),
            Path("/tmp/windows-proof-intake.json"),
            handoff_timestamp="2026-07-13T17:31:14Z",
        )

        with mock.patch.object(
            module.proof_importer,
            "execute_code_owned_post_import_plan",
            side_effect=AssertionError("paused auto-import must not execute post-import gates"),
        ):
            result = module.execute_code_owned_post_import_plan(
                plan,
                side_effects_paused=True,
            )

        self.assertEqual([], result)

    def test_auto_import_pause_blocks_before_artifact_import_and_returns_nonpass(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-import-paused-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "windows-installer-gold-proof.zip"
            artifact.write_bytes(b"must-not-be-opened")
            intake_request = root / "intake.json"
            output = root / "auto-import.json"
            downloads_root = root / "downloads"
            intake = {
                "promoted_installer_sha256": "a" * 64,
                "post_import_gates": ["touch /tmp/must-not-run"],
            }
            intake_request.write_text(json.dumps(intake), encoding="utf-8")

            with (
                mock.patch.object(
                    module,
                    "parse_args",
                    return_value=argparse.Namespace(
                        artifact=artifact,
                        intake_request=intake_request,
                        output=output,
                        downloads_root=downloads_root,
                        discovery_root=[],
                        wait_seconds=0.0,
                        poll_seconds=5.0,
                        refresh_intake_request=False,
                        authorize_external_mutations=False,
                    ),
                ),
                mock.patch.object(module, "ensure_intake_request", return_value=intake),
                mock.patch.object(module, "discover_candidates", return_value=[]),
                mock.patch.object(module, "auto_import_side_effects_paused", return_value=True),
                mock.patch.object(
                    module,
                    "import_proof_artifact",
                    side_effect=AssertionError("paused auto-import must not read or import the artifact"),
                ) as import_mock,
            ):
                exit_code = module.main()

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(3, exit_code)
        import_mock.assert_not_called()
        self.assertFalse(downloads_root.exists())
        self.assertEqual("blocked_auto_import_paused", payload["status"])
        self.assertFalse(payload["import_performed"])
        self.assertFalse(payload["public_bytes_written"])
        self.assertEqual("blocked_paused", payload["post_import_plan"]["status"])
        self.assertIn("importer", payload["program_bindings"])
        self.assertIn("auto_importer", payload["program_bindings"])

    def test_auto_import_pause_appearing_during_import_blocks_before_post_import_plan(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-import-late-pause-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "windows-installer-gold-proof.zip"
            artifact.write_bytes(b"fixture")
            intake_request = root / "intake.json"
            output = root / "auto-import.json"
            downloads_root = root / "downloads"
            intake = {"promoted_installer_sha256": "a" * 64}
            intake_request.write_text(json.dumps(intake), encoding="utf-8")

            with (
                mock.patch.object(
                    module,
                    "parse_args",
                    return_value=argparse.Namespace(
                        artifact=artifact,
                        intake_request=intake_request,
                        output=output,
                        downloads_root=downloads_root,
                        discovery_root=[],
                        wait_seconds=0.0,
                        poll_seconds=5.0,
                        refresh_intake_request=False,
                        authorize_external_mutations=True,
                    ),
                ),
                mock.patch.object(module, "ensure_intake_request", return_value=intake),
                mock.patch.object(module, "discover_candidates", return_value=[]),
                mock.patch.object(
                    module,
                    "auto_import_side_effects_paused",
                    side_effect=[False, True],
                ),
                mock.patch.object(
                    module,
                    "import_proof_artifact",
                    return_value={"visualAuditSource": "fixture"},
                ) as import_mock,
                mock.patch.object(
                    module,
                    "execute_code_owned_post_import_plan",
                    side_effect=AssertionError("late pause must stop before post-import execution"),
                ),
            ):
                exit_code = module.main()

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(3, exit_code)
        import_mock.assert_called_once()
        self.assertEqual("blocked_auto_import_paused_after_import", payload["status"])
        self.assertTrue(payload["import_performed"])
        self.assertTrue(payload["public_bytes_written"])
        self.assertEqual("blocked_paused", payload["post_import_plan"]["status"])

    def test_auto_import_rechecks_pause_interlock_before_external_mutation(self) -> None:
        module = load_auto_import_module()
        plan = module.build_code_owned_post_import_plan(
            Path("/tmp/windows-proof-downloads"),
            Path("/tmp/windows-proof-intake.json"),
            handoff_timestamp="2026-07-13T17:31:14Z",
            authorize_external_mutations=True,
        )
        with (
            mock.patch.object(
                module.proof_importer,
                "run_bound_python_subprocess",
                side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(
                    module.proof_importer,
                    bound_argv,
                ),
            ) as run_mock,
            mock.patch.object(
                module,
                "auto_import_side_effects_paused",
                return_value=True,
            ),
        ):
            results = module.execute_code_owned_post_import_plan(
                plan,
                side_effects_paused=False,
            )

        self.assertEqual(20, len(results))
        self.assertEqual(19, run_mock.call_count)
        self.assertEqual("sync_important_work_to_teable", results[-1]["step_id"])
        self.assertEqual("blocked_pause_interlock", results[-1]["status"])
        self.assertEqual(125, results[-1]["returncode"])
        self.assertNotIn(
            "attempt_flagship_public_stable_promotion",
            [row["step_id"] for row in results],
        )

    def test_auto_import_intake_refresh_ignores_path_shadow_and_uses_sealed_code_owned_programs(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-refresh-path-shadow-") as temp_dir:
            root = Path(temp_dir)
            shadow = root / "shadow-bin"
            shadow.mkdir()
            shadow_python = shadow / "python3"
            shadow_python.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            shadow_python.chmod(0o755)
            output = root / "intake.json"
            output.write_text(json.dumps({"status": "fixture"}), encoding="utf-8")

            with (
                mock.patch.dict(os.environ, {"PATH": f"{shadow}:{os.environ.get('PATH', '')}"}),
                mock.patch.object(
                    module.proof_importer,
                    "run_bound_python_subprocess",
                    side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(
                        module.proof_importer,
                        bound_argv,
                    ),
                ) as run_mock,
            ):
                payload = module.materialize_intake_request(output, root / "downloads")

        self.assertEqual("fixture", payload["status"])
        bound_argv = run_mock.call_args.args[0]
        self.assertEqual(str(module.proof_importer.PYTHON_EXECUTABLE), bound_argv[0])
        self.assertEqual(str(module.INTAKE_MATERIALIZER), bound_argv[1])
        environment = run_mock.call_args.kwargs["environment"]
        self.assertEqual(module.proof_importer.POST_IMPORT_FIXED_PATH, environment["PATH"])
        self.assertNotIn(str(shadow), environment["PATH"])

    def test_auto_import_intake_refresh_failure_redacts_subprocess_streams(self) -> None:
        module = load_auto_import_module()
        stdout_secret = "INTAKE_STDOUT_SECRET_23499f"
        stderr_secret = "INTAKE_STDERR_SECRET_bc6ff4"
        with tempfile.TemporaryDirectory(prefix="windows-proof-refresh-redaction-") as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(
                module.proof_importer,
                "run_bound_python_subprocess",
                side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(
                    module.proof_importer,
                    bound_argv,
                    returncode=9,
                    stdout=stdout_secret,
                    stderr=stderr_secret,
                ),
            ):
                with self.assertRaises(SystemExit) as raised:
                    module.materialize_intake_request(root / "intake.json", root / "downloads")

        message = str(raised.exception)
        self.assertNotIn(stdout_secret, message)
        self.assertNotIn(stderr_secret, message)
        self.assertIn("returncode=9", message)
        self.assertIn('"redacted": true', message)

    def test_import_code_owned_step_uses_shell_false_and_sanitized_deterministic_env(self) -> None:
        module = load_import_module()
        plan = module.build_code_owned_post_import_plan(
            Path("/tmp/windows-proof-downloads"),
            Path("/tmp/windows-proof-intake.json"),
            handoff_timestamp="2026-07-13T17:31:14Z",
        )

        with mock.patch.object(
            module,
            "run_bound_python_subprocess",
            side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(module, bound_argv),
        ) as run_mock:
            result = module.run_code_owned_post_import_step(
                plan,
                plan["steps"][0],
            )

        self.assertEqual(0, result["returncode"])
        self.assertFalse(result["shell"])
        self.assertEqual(plan["plan_sha256"], result["plan_sha256"])
        self.assertEqual(plan["steps"][0]["execution_binding_sha256"], result["execution_binding_sha256"])
        self.assertEqual(plan["steps"][0]["argv"], result["sealed_execution"]["bound_argv"])
        self.assertEqual(plan["steps"][0]["argv"], run_mock.call_args.args[0])
        execution_argv = result["sealed_execution"]["execution_argv"]
        self.assertTrue(execution_argv[0].startswith("/proc/self/fd/"))
        self.assertEqual(["-I", "-c"], execution_argv[1:3])
        self.assertEqual(module.SEALED_PYTHON_LAUNCHER_SOURCE, execution_argv[3])
        self.assertEqual(plan["steps"][0]["argv"][1], execution_argv[4])
        env = run_mock.call_args.kwargs["environment"]
        self.assertEqual(module.code_owned_post_import_environment(), env)
        self.assertEqual(module.POST_IMPORT_FIXED_PATH, env["PATH"])
        self.assertTrue(str(env["TMPDIR"]).strip())
        self.assertNotIn("BASH_ENV", env)
        self.assertNotIn("ENV", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)

    def test_import_code_owned_step_redacts_subprocess_output_receipts(self) -> None:
        module = load_import_module()
        plan = module.build_code_owned_post_import_plan(
            Path("/tmp/windows-proof-downloads"),
            Path("/tmp/windows-proof-intake.json"),
            handoff_timestamp="2026-07-13T17:31:14Z",
        )
        stdout_secret = "OPERATOR_STDOUT_SECRET_97e164"
        stderr_secret = "OPERATOR_STDERR_SECRET_f8571a"

        with mock.patch.object(
            module,
            "run_bound_python_subprocess",
            side_effect=lambda bound_argv, **_kwargs: fake_bound_python_result(
                module,
                bound_argv,
                returncode=1,
                stdout=stdout_secret + "\n",
                stderr=stderr_secret + "\n",
            ),
        ):
            result = module.run_code_owned_post_import_step(plan, plan["steps"][0])

        serialized_result = json.dumps(result, sort_keys=True)
        self.assertNotIn(stdout_secret, serialized_result)
        self.assertNotIn(stderr_secret, serialized_result)
        self.assertEqual([], result["stdout_tail"])
        self.assertEqual([], result["stderr_tail"])
        self.assertTrue(result["stdout_receipt"]["redacted"])
        self.assertTrue(result["stdout_receipt"]["present"])
        self.assertTrue(result["stderr_receipt"]["redacted"])
        self.assertTrue(result["stderr_receipt"]["present"])
        self.assertRegex(result["stdout_receipt"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["stderr_receipt"]["sha256"], r"^[0-9a-f]{64}$")

    def test_sealed_timeout_terminates_same_group_term_ignoring_and_setsid_descendants(self) -> None:
        module = load_import_module()
        cases = {
            "same_process_group": (
                "subprocess.Popen(['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]])\n"
            ),
            "term_ignoring": (
                "subprocess.Popen(['/bin/sh', '-c', "
                "'trap \"\" TERM; while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]])\n"
            ),
            "setsid": (
                "subprocess.Popen(['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', "
                "'sh', sys.argv[1]], start_new_session=True)\n"
            ),
        }
        for case_name, spawn_source in cases.items():
            with self.subTest(case_name=case_name), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-real-timeout-{case_name}-"
            ) as temp_dir:
                root = Path(temp_dir)
                marker = root / "escaped-child-marker.txt"
                probe = root / "timeout_probe.py"
                probe.write_text(
                    "import subprocess, sys, time\n"
                    + spawn_source
                    + "time.sleep(10)\n",
                    encoding="utf-8",
                )
                bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])

                completed, evidence = module.run_bound_python_subprocess(
                    [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                    interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                    script_sha256=module.sha256_file(probe),
                    cwd=root,
                    environment=module.code_owned_post_import_environment(),
                    dependency_bundle_bytes=bundle_bytes,
                    dependency_bundle_binding=bundle_binding,
                    timeout_seconds=0.15,
                    termination_grace_seconds=0.1,
                )
                release_containment_probe(marker)

                self.assertEqual(124, completed.returncode, completed.stderr)
                self.assertFalse(marker.exists(), evidence)
                self.assertEqual(0.15, evidence["timeout_seconds"])
                self.assertEqual(0.1, evidence["termination_grace_seconds"])
                self.assertEqual(
                    "linux_child_subreaper_descendant_sweep",
                    evidence["process_group_mode"],
                )
                self.assertTrue(evidence["timed_out"])
                self.assertTrue(evidence["containment"]["zero_descendants_proven"])
                self.assertEqual(0, evidence["containment"]["remaining_descendant_count"])

    def test_sealed_environment_marker_contains_setsid_child_when_ancestry_is_unavailable(self) -> None:
        module = load_import_module()
        process_table_baseline = {
            module._process_identity(row)
            for row in module._proc_process_table().values()
        }
        with tempfile.TemporaryDirectory(prefix="windows-proof-marker-containment-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "escaped-marker-contained-child.txt"
            probe = root / "marker_containment_probe.py"
            probe.write_text(
                "import subprocess, sys, time\n"
                "subprocess.Popen(\n"
                "    ['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]],\n"
                "    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
                ")\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])
            containment_secret = "ab" * 32

            with mock.patch.object(
                module,
                "_descendant_identities",
                return_value=set(),
            ), mock.patch.object(
                module.secrets,
                "token_hex",
                return_value=containment_secret,
            ):
                completed, evidence = module.run_bound_python_subprocess(
                    [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                    interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                    script_sha256=module.sha256_file(probe),
                    cwd=root,
                    environment=module.code_owned_post_import_environment(),
                    dependency_bundle_bytes=bundle_bytes,
                    dependency_bundle_binding=bundle_binding,
                    timeout_seconds=0.15,
                    termination_grace_seconds=0.1,
                )
            release_containment_probe(marker)

            self.assertEqual(124, completed.returncode, completed.stderr)
            self.assertFalse(marker.exists(), evidence)
            self.assertRegex(
                evidence["containment"]["environment_marker_sha256"],
                r"^[0-9a-f]{64}$",
            )
            self.assertNotIn(containment_secret, json.dumps(evidence, sort_keys=True))
            self.assertEqual(
                module.POST_IMPORT_CONTAINMENT_ENVIRONMENT_KEY,
                evidence["runtime_environment_extension"]["key"],
            )
            self.assertRegex(
                evidence["runtime_environment_extension"]["value_sha256"],
                r"^[0-9a-f]{64}$",
            )
            self.assertGreaterEqual(evidence["containment"]["kill_signalled_count"], 1)
            self.assertTrue(evidence["containment"]["zero_descendants_proven"])
            self.assertEqual(0, evidence["containment"]["remaining_descendant_count"])
            leaked_direct_children = {
                module._process_identity(row)
                for row in module._proc_process_table().values()
                if int(row["ppid"]) == os.getpid()
                and module._process_identity(row) not in process_table_baseline
            }
            self.assertEqual(set(), leaked_direct_children)

    def test_sealed_success_still_reaps_detached_background_descendant(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-real-success-containment-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "escaped-success-child-marker.txt"
            probe = root / "success_probe.py"
            probe.write_text(
                "import subprocess, sys\n"
                "subprocess.Popen(\n"
                "    ['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]],\n"
                "    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
                ")\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])

            completed, evidence = module.run_bound_python_subprocess(
                [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                script_sha256=module.sha256_file(probe),
                cwd=root,
                environment=module.code_owned_post_import_environment(),
                dependency_bundle_bytes=bundle_bytes,
                dependency_bundle_binding=bundle_binding,
                timeout_seconds=2.0,
                termination_grace_seconds=0.1,
            )
            release_containment_probe(marker)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(marker.exists(), evidence)
            self.assertFalse(evidence["timed_out"])
            self.assertTrue(evidence["containment"]["zero_descendants_proven"])
            self.assertEqual(0, evidence["containment"]["remaining_descendant_count"])

    def test_sealed_binary_capture_tolerates_non_utf8_and_reaps_detached_descendant(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-non-utf8-containment-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "escaped-non-utf8-child-marker.txt"
            probe = root / "non_utf8_probe.py"
            probe.write_text(
                "import os, subprocess, sys\n"
                "os.write(1, b'\\xffnon-utf8\\n')\n"
                "subprocess.Popen(\n"
                "    ['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]],\n"
                "    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
                ")\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])

            completed, evidence = module.run_bound_python_subprocess(
                [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                script_sha256=module.sha256_file(probe),
                cwd=root,
                environment=module.code_owned_post_import_environment(),
                dependency_bundle_bytes=bundle_bytes,
                dependency_bundle_binding=bundle_binding,
                timeout_seconds=2.0,
                termination_grace_seconds=0.1,
            )
            release_containment_probe(marker)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("\ufffdnon-utf8", completed.stdout)
            self.assertFalse(marker.exists(), evidence)
            self.assertTrue(evidence["containment"]["zero_descendants_proven"])
            self.assertEqual(0, evidence["containment"]["remaining_descendant_count"])

    def test_sealed_unexpected_communicate_error_still_reaps_all_descendants(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-communicate-error-containment-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "escaped-communicate-error-child-marker.txt"
            probe = root / "communicate_error_probe.py"
            probe.write_text(
                "import subprocess, sys, time\n"
                "subprocess.Popen(\n"
                "    ['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]],\n"
                "    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
                ")\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])
            original_communicate = module.subprocess.Popen.communicate
            original_terminate = module._terminate_and_reap_contained_step
            injected = False
            containment_receipts = []
            raw_secret = "COMMUNICATE_EXCEPTION_SECRET_a3b72f"

            def communicate_with_one_failure(process, *args, **kwargs):
                nonlocal injected
                if not injected:
                    injected = True
                    raise OSError(raw_secret)
                return original_communicate(process, *args, **kwargs)

            def capture_containment(*args, **kwargs):
                receipt = original_terminate(*args, **kwargs)
                containment_receipts.append(receipt)
                return receipt

            with mock.patch.object(
                module.subprocess.Popen,
                "communicate",
                new=communicate_with_one_failure,
            ), mock.patch.object(
                module,
                "_terminate_and_reap_contained_step",
                side_effect=capture_containment,
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "communication failed after descendant containment",
                ) as raised:
                    module.run_bound_python_subprocess(
                        [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                        interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                        script_sha256=module.sha256_file(probe),
                        cwd=root,
                        environment=module.code_owned_post_import_environment(),
                        dependency_bundle_bytes=bundle_bytes,
                        dependency_bundle_binding=bundle_binding,
                        timeout_seconds=2.0,
                        termination_grace_seconds=0.1,
                    )
            release_containment_probe(marker)

            self.assertNotIn(raw_secret, str(raised.exception))
            self.assertIsNone(raised.exception.__cause__)
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertFalse(marker.exists())
            self.assertEqual(1, len(containment_receipts))
            self.assertTrue(containment_receipts[0]["zero_descendants_proven"])
            self.assertEqual(0, containment_receipts[0]["remaining_descendant_count"])

    def test_sealed_observer_start_failure_still_runs_containment_exactly_once(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-observer-start-failure-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "escaped-observer-start-child-marker.txt"
            probe = root / "observer_start_failure_probe.py"
            probe.write_text(
                "import subprocess, sys, time\n"
                "subprocess.Popen(\n"
                "    ['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]],\n"
                "    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
                ")\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])
            original_terminate = module._terminate_and_reap_contained_step
            containment_receipts = []
            raw_secret = "OBSERVER_START_SECRET_f206b8"

            def capture_containment(*args, **kwargs):
                receipt = original_terminate(*args, **kwargs)
                containment_receipts.append(receipt)
                return receipt

            with mock.patch.object(
                module.threading.Thread,
                "start",
                side_effect=RuntimeError(raw_secret),
            ), mock.patch.object(
                module,
                "_terminate_and_reap_contained_step",
                side_effect=capture_containment,
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "communication failed after descendant containment",
                ) as raised:
                    module.run_bound_python_subprocess(
                        [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                        interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                        script_sha256=module.sha256_file(probe),
                        cwd=root,
                        environment=module.code_owned_post_import_environment(),
                        dependency_bundle_bytes=bundle_bytes,
                        dependency_bundle_binding=bundle_binding,
                        timeout_seconds=2.0,
                        termination_grace_seconds=0.1,
                    )
            release_containment_probe(marker)

            self.assertNotIn(raw_secret, str(raised.exception))
            self.assertIsNone(raised.exception.__cause__)
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertFalse(marker.exists())
            self.assertEqual(1, len(containment_receipts))
            self.assertTrue(containment_receipts[0]["zero_descendants_proven"])
            self.assertEqual(0, containment_receipts[0]["remaining_descendant_count"])

    def test_sealed_persistent_proc_failure_emergency_kills_owned_session_and_fails_closed(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-proc-failure-containment-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "escaped-proc-failure-child-marker.txt"
            probe = root / "proc_failure_probe.py"
            probe.write_text(
                "import subprocess, sys, time\n"
                "subprocess.Popen(\n"
                "    ['/bin/sh', '-c', 'while [ ! -e \"$1.release\" ]; do sleep 0.05; done; printf escaped > \"$1\"', 'sh', sys.argv[1]],\n"
                "    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
                ")\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])
            original_process_table = module._proc_process_table
            original_emergency = module._emergency_kill_and_reap_primary_session
            process_table_call_count = 0
            emergency_call_count = 0
            raw_secret = "PROC_INSPECTION_SECRET_b371d0"

            def fail_process_table_after_baseline():
                nonlocal process_table_call_count
                process_table_call_count += 1
                if process_table_call_count == 1:
                    return original_process_table()
                raise SystemExit(raw_secret)

            def capture_emergency(*args, **kwargs):
                nonlocal emergency_call_count
                emergency_call_count += 1
                return original_emergency(*args, **kwargs)

            with mock.patch.object(
                module,
                "_proc_process_table",
                side_effect=fail_process_table_after_baseline,
            ), mock.patch.object(
                module,
                "_emergency_kill_and_reap_primary_session",
                side_effect=capture_emergency,
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "emergency session cleanup; zero descendants could not be proven",
                ) as raised:
                    module.run_bound_python_subprocess(
                        [str(module.PYTHON_EXECUTABLE), str(probe), str(marker)],
                        interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                        script_sha256=module.sha256_file(probe),
                        cwd=root,
                        environment=module.code_owned_post_import_environment(),
                        dependency_bundle_bytes=bundle_bytes,
                        dependency_bundle_binding=bundle_binding,
                        timeout_seconds=2.0,
                        termination_grace_seconds=0.1,
                    )
            release_containment_probe(marker)

            self.assertNotIn(raw_secret, str(raised.exception))
            self.assertIsNone(raised.exception.__cause__)
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertEqual(1, emergency_call_count)
            self.assertGreaterEqual(process_table_call_count, 3)
            self.assertFalse(marker.exists())

    def test_sealed_python_launcher_preserves_logical_file_sys_path_and_sibling_import_in_real_process(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-real-sealed-launcher-") as temp_dir:
            root = Path(temp_dir)
            sibling = root / "sibling.py"
            sibling.write_text("VALUE = 'sealed-sibling-ok'\n", encoding="utf-8")
            probe = root / "probe.py"
            probe.write_text(
                "import json, sys\n"
                "from pathlib import Path\n"
                "from sibling import VALUE\n"
                "print(json.dumps({'file': __file__, 'resolve': str(Path(__file__).resolve()), "
                "'sys0': sys.path[0], 'value': VALUE, 'argv': sys.argv}))\n",
                encoding="utf-8",
            )
            bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])

            completed, evidence = module.run_bound_python_subprocess(
                [str(module.PYTHON_EXECUTABLE), str(probe), "argument-one"],
                interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                script_sha256=module.sha256_file(probe),
                cwd=root,
                environment=module.code_owned_post_import_environment(),
                dependency_bundle_bytes=bundle_bytes,
                dependency_bundle_binding=bundle_binding,
            )
            payload = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(str(probe), payload["file"])
        self.assertEqual(str(probe.resolve()), payload["resolve"])
        self.assertEqual(str(probe.parent), payload["sys0"])
        self.assertEqual("sealed-sibling-ok", payload["value"])
        self.assertEqual([str(probe), "argument-one"], payload["argv"])
        self.assertEqual("sealed_memfd", evidence["transport"])
        self.assertEqual(module.SEALED_PYTHON_LAUNCHER_SHA256, evidence["launcher_sha256"])
        self.assertEqual(bundle_binding["bundle_sha256"], evidence["dependency_bundle_sha256"])

    def test_sealed_python_launcher_rejects_late_created_module_and_namespace_package(self) -> None:
        module = load_import_module()
        for import_kind in ("module", "namespace_package"):
            with self.subTest(import_kind=import_kind), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-late-{import_kind}-"
            ) as temp_dir:
                root = Path(temp_dir)
                probe = root / "probe.py"
                import_statement = (
                    "from late_dependency import VALUE"
                    if import_kind == "module"
                    else "from late_namespace.member import VALUE"
                )
                probe.write_text(
                    f"{import_statement}\nprint(VALUE)\n",
                    encoding="utf-8",
                )
                bundle_bytes, bundle_binding = module.build_code_owned_python_dependency_bundle([root])
                if import_kind == "module":
                    (root / "late_dependency.py").write_text(
                        "VALUE = 'UNBOUND_LATE_CODE_EXECUTED'\n",
                        encoding="utf-8",
                    )
                else:
                    namespace = root / "late_namespace"
                    namespace.mkdir()
                    (namespace / "member.py").write_text(
                        "VALUE = 'UNBOUND_NAMESPACE_CODE_EXECUTED'\n",
                        encoding="utf-8",
                    )

                completed, _evidence = module.run_bound_python_subprocess(
                    [str(module.PYTHON_EXECUTABLE), str(probe)],
                    interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
                    script_sha256=module.sha256_file(probe),
                    cwd=root,
                    environment=module.code_owned_post_import_environment(),
                    dependency_bundle_bytes=bundle_bytes,
                    dependency_bundle_binding=bundle_binding,
                )

                self.assertNotEqual(0, completed.returncode)
                self.assertNotIn("UNBOUND_", completed.stdout)
                self.assertIn("unsealed Python import under governed root is forbidden", completed.stderr)

    def test_sealed_python_launcher_runs_representative_verifier_help_in_real_process(self) -> None:
        module = load_import_module()
        dependency_bytes, dependency_binding = (
            module.production_code_owned_python_dependency_bundle()
        )
        verifier = module.VERIFY_SCRIPT.resolve()

        completed, evidence = module.run_bound_python_subprocess(
            [str(module.PYTHON_EXECUTABLE), str(verifier), "--help"],
            interpreter_sha256=module.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"],
            script_sha256=module.sha256_file(verifier),
            cwd=module.ROOT,
            environment=module.code_owned_post_import_environment(),
            dependency_bundle_bytes=dependency_bytes,
            dependency_bundle_binding=dependency_binding,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage: verify_windows_installer_visual_audit.py", completed.stdout)
        self.assertEqual(str(verifier), evidence["logical_script_path"])
        self.assertGreater(int(dependency_binding["file_count"]), 0)

    def test_auto_import_windows_installer_gold_proof_wait_for_candidate_reports_waiting_progress_each_poll(self) -> None:
        module = load_auto_import_module()
        progress: list[list[dict[str, object]]] = []

        with (
            mock.patch.object(module, "discover_candidates", side_effect=[[], [], []]),
            mock.patch.object(module, "selected_candidate", return_value=None),
            mock.patch.object(module.time, "monotonic", side_effect=[0.0, 0.0, 0.02, 0.06]),
            mock.patch.object(module.time, "sleep") as sleep_mock,
        ):
            artifact, candidates = module.wait_for_candidate(
                {},
                [],
                0.05,
                0.01,
                on_waiting=lambda rows: progress.append(list(rows)),
            )

        self.assertIsNone(artifact)
        self.assertEqual([], candidates)
        self.assertEqual([[], [], []], progress)
        self.assertEqual(2, sleep_mock.call_count)

    def test_auto_import_windows_installer_gold_proof_main_refreshes_waiting_receipt_during_watch_mode(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-watch-refresh-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            output = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            downloads_root = root / "downloads"
            incoming = root / "incoming"
            incoming.mkdir()
            writes: list[tuple[Path, dict[str, object]]] = []

            def fake_wait_for_candidate(
                intake: dict[str, object],
                roots: list[Path],
                wait_seconds: float,
                poll_seconds: float,
                on_waiting=None,
                refresh_binding=None,
            ) -> tuple[None, list[dict[str, object]]]:
                self.assertIsNotNone(on_waiting)
                self.assertIsNotNone(refresh_binding)
                assert on_waiting is not None
                on_waiting([{"path": "first"}])
                on_waiting([{"path": "second"}])
                return None, []

            def fake_build_waiting_payload(**kwargs) -> dict[str, object]:
                candidates = kwargs["candidates"]
                return {
                    "status": "waiting_for_artifact",
                    "candidate_count": len(candidates),
                }

            with (
                mock.patch.object(
                    module,
                    "parse_args",
                    return_value=argparse.Namespace(
                        artifact=None,
                        intake_request=intake_request,
                        output=output,
                        downloads_root=downloads_root,
                        discovery_root=None,
                        wait_seconds=900.0,
                        poll_seconds=30.0,
                        refresh_intake_request=True,
                    ),
                ),
                mock.patch.object(
                    module,
                    "ensure_intake_request",
                    return_value={
                        "preferred_drop_path": str(incoming / "windows-installer-gold-proof.zip"),
                        "artifact_intake": {
                            "preferred_drop_path": str(incoming / "windows-installer-gold-proof.zip"),
                            "auto_import_roots": [str(incoming)],
                        },
                    },
                ),
                mock.patch.object(module, "wait_for_candidate", side_effect=fake_wait_for_candidate),
                mock.patch.object(module, "build_waiting_payload", side_effect=fake_build_waiting_payload),
                mock.patch.object(module, "write_json", side_effect=lambda path, payload: writes.append((path, dict(payload)))),
            ):
                exit_code = module.main()

        self.assertEqual(2, exit_code)
        self.assertEqual(3, len(writes))
        self.assertEqual(output, writes[0][0])
        self.assertEqual(output, writes[1][0])
        self.assertEqual(output, writes[2][0])
        self.assertEqual(1, writes[0][1]["candidate_count"])
        self.assertEqual(1, writes[1][1]["candidate_count"])
        self.assertEqual(0, writes[2][1]["candidate_count"])

    def test_auto_import_windows_installer_gold_proof_wait_refreshes_intake_binding_between_polls(self) -> None:
        module = load_auto_import_module()
        intake: dict[str, object] = {"promoted_installer_sha256": "old-digest"}
        roots = [Path("/old-drop")]
        observed_bindings: list[tuple[str, list[Path]]] = []
        selected = Path("/new-drop/windows-installer-gold-proof-new.zip")

        def discover(current_intake, current_roots):
            observed_bindings.append(
                (str(current_intake.get("promoted_installer_sha256") or ""), list(current_roots))
            )
            return []

        def refresh_binding() -> None:
            intake.clear()
            intake.update({"promoted_installer_sha256": "new-digest"})
            roots[:] = [Path("/new-drop")]

        with (
            mock.patch.object(module, "discover_candidates", side_effect=discover),
            mock.patch.object(module, "selected_candidate", side_effect=[None, selected]),
            mock.patch.object(module.time, "monotonic", side_effect=[0.0, 0.0]),
            mock.patch.object(module.time, "sleep") as sleep_mock,
        ):
            artifact, candidates = module.wait_for_candidate(
                intake,
                roots,
                60.0,
                1.0,
                refresh_binding=refresh_binding,
            )

        self.assertEqual(selected, artifact)
        self.assertEqual([], candidates)
        self.assertEqual(
            [
                ("old-digest", [Path("/old-drop")]),
                ("new-digest", [Path("/new-drop")]),
            ],
            observed_bindings,
        )
        sleep_mock.assert_called_once_with(1.0)

    def test_downloads_runbook_documents_windows_gold_proof_loop(self) -> None:
        runbook = Path("/docker/chummercomplete/chummer.run-services/docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md")
        text = runbook.read_text(encoding="utf-8")

        self.assertIn("Windows installer gold proof", text)
        self.assertIn("native Windows proof runner", text)
        self.assertIn("must not publish downloads", text)
        self.assertIn(
            "windows-installer-gold-proof.zip --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify",
            text,
        )
        self.assertIn("reruns the full intake-request post-import gate chain", text)
        self.assertIn(".state/incoming_windows_installer_gold_proof", text)
        self.assertIn("Extracted-directory artifacts are rejected without inspection", text)
        self.assertIn("review_required", text)
        self.assertIn("Every bundle must contain both the native-Windows startup receipt", text)
        self.assertIn("Delivery must be a bounded zip", text)
        self.assertIn("WINDOWS_INSTALLER_VISUAL_AUDIT.source.json", text)
        self.assertIn("capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit", text)
        self.assertIn("verify_windows_installer_visual_audit.py", text)

    def test_downloads_runbook_documents_google_oauth_operator_proof_loop(self) -> None:
        runbook = Path("/docker/chummercomplete/chummer.run-services/docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md")
        text = runbook.read_text(encoding="utf-8")

        self.assertIn("/docker/chummercomplete", text)
        self.assertIn("Google OAuth linking operator proof", text)
        self.assertIn("must not publish downloads or promote a release", text)
        self.assertIn("materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run", text)
        self.assertIn("verify_google_oauth_linking_operator_evidence_request.py", text)
        self.assertIn("CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt", text)
        self.assertIn("GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json", text)
        self.assertIn(".state/incoming_google_oauth_linking_operator_evidence", text)
        self.assertIn("auto_import_google_oauth_linking_operator_evidence.py", text)
        self.assertIn("verify_google_oauth_linking_proof.py --require-pass", text)
