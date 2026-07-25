#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from writable_temp_root import configure_process_tmpdir, subprocess_env


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
STATE_ROOT = ROOT / ".state"
AUTO_IMPORT_SCRIPT = ROOT / "scripts" / "auto_import_windows_installer_gold_proof.py"
DEFAULT_INTAKE_REQUEST = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
DEFAULT_STATE_PATH = STATE_ROOT / "windows_installer_gold_proof_watcher.generated.json"
DEFAULT_PID_FILE = STATE_ROOT / "windows_installer_gold_proof_watcher.pid"
DEFAULT_LOG_FILE = STATE_ROOT / "windows_installer_gold_proof_auto_import_watch.log"
DEFAULT_AUTO_IMPORT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
DEFAULT_WAIT_SECONDS = 43200.0
DEFAULT_POLL_SECONDS = 30.0
DEFAULT_STOP_GRACE_SECONDS = 10.0
PROCESS_SCAN_MAX_CAPTURE_BYTES = 256 * 1024
PROCESS_SCAN_TIMEOUT_SECONDS = 5.0
PROCESS_SCAN_CLEANUP_SECONDS = 1.0
POST_LAUNCH_CLEANUP_SECONDS = 3.0
POST_LAUNCH_TERM_SECONDS = 1.0
AUTO_IMPORT_HEARTBEAT_MIN_STALE_SECONDS = 120
AUTO_IMPORT_HEARTBEAT_POLL_MULTIPLIER = 3
AUTO_IMPORT_CONTRACT_NAME_V1 = "chummer.windows_installer_visual_audit_auto_import.v1"
AUTO_IMPORT_CONTRACT_NAME = "chummer.windows_installer_visual_audit_auto_import.v2"
WATCHER_CONTRACT_NAME_V1 = "chummer.windows_installer_gold_proof_watcher.v1"
WATCHER_CONTRACT_NAME = "chummer.windows_installer_gold_proof_watcher.v2"
LAUNCH_MODE = "python_subprocess_start_new_session"

configure_process_tmpdir(workspace_root=ROOT.parent)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def fsync_directory(path: Path) -> None:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_descriptor = os.open(path, directory_flags)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def ensure_durable_parent(path: Path) -> None:
    missing: list[Path] = []
    cursor = path.parent
    while True:
        try:
            cursor_mode = cursor.lstat().st_mode
        except FileNotFoundError:
            missing.append(cursor)
            parent = cursor.parent
            if parent == cursor:
                raise OSError("durable receipt parent has no existing ancestor")
            cursor = parent
            continue
        if stat.S_ISLNK(cursor_mode) or not stat.S_ISDIR(cursor_mode):
            raise ValueError("durable receipt parent must be a real directory")
        break

    for directory in reversed(missing):
        os.mkdir(directory, mode=0o755)
        created_mode = directory.lstat().st_mode
        if stat.S_ISLNK(created_mode) or not stat.S_ISDIR(created_mode):
            raise ValueError("durable receipt parent must be a real directory")
        fsync_directory(directory.parent)


def validate_regular_target(path: Path, *, target_name: str) -> bool:
    try:
        target_stat = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(target_stat.st_mode) or not stat.S_ISREG(target_stat.st_mode):
        raise ValueError(f"{target_name} target must be a regular file")
    return True


def preflight_write_probe(path: Path) -> None:
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.preflight.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        os.fsync(file_descriptor)
        os.close(file_descriptor)
        file_descriptor = -1
        fsync_directory(path.parent)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        fsync_directory(path.parent)


def preflight_replacement_target(path: Path, *, target_name: str) -> None:
    ensure_durable_parent(path)
    validate_regular_target(path, target_name=target_name)
    preflight_write_probe(path)


def preflight_log_target(path: Path) -> None:
    ensure_durable_parent(path)
    exists = validate_regular_target(path, target_name="watcher log")
    if exists:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_APPEND
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("watcher log target must be a regular file")
        finally:
            os.close(descriptor)
    preflight_write_probe(path)


def preflight_watcher_targets(
    *,
    state_path: Path,
    pid_file: Path,
    log_file: Path,
) -> None:
    preflight_replacement_target(state_path, target_name="watcher state")
    preflight_replacement_target(pid_file, target_name="watcher pid")
    preflight_log_target(log_file)


def durable_replace_text(path: Path, text: str) -> None:
    ensure_durable_parent(path)
    try:
        target_stat = path.lstat()
    except FileNotFoundError:
        target_mode = 0o644
    else:
        validate_regular_target(path, target_name="durable write")
        target_mode = stat.S_IMODE(target_stat.st_mode)

    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        os.fchmod(file_descriptor, target_mode)
        handle = os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n")
        file_descriptor = -1
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        fsync_directory(path.parent)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def write_json(path: Path, payload: dict[str, Any]) -> None:
    durable_replace_text(path, json.dumps(payload, indent=2) + "\n")


def read_pid_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "state": "missing", "pid": None}
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return {"present": True, "state": "unreadable", "pid": None}
    if not value:
        return {"present": True, "state": "invalid", "pid": None}
    try:
        pid = int(value)
    except ValueError:
        return {"present": True, "state": "invalid", "pid": None}
    if pid <= 0:
        return {"present": True, "state": "invalid", "pid": None}
    return {"present": True, "state": "valid", "pid": pid}


def read_pid(path: Path) -> int | None:
    return read_pid_state(path)["pid"]


def write_pid(path: Path, pid: int) -> None:
    durable_replace_text(path, f"{pid}\n")


def is_process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def watcher_command(
    intake_request: Path,
    *,
    wait_seconds: float,
    poll_seconds: float,
    refresh_intake_request: bool,
    watcher_instance_id: str = "",
    watcher_started_at_utc: str = "",
) -> list[str]:
    command = [
        "python3",
        str(AUTO_IMPORT_SCRIPT),
        "--intake-request",
        str(intake_request.resolve()),
        "--wait-seconds",
        str(int(wait_seconds)),
        "--poll-seconds",
        str(int(poll_seconds)),
    ]
    if refresh_intake_request:
        command.append("--refresh-intake-request")
    if watcher_instance_id:
        command.extend(["--watcher-instance-id", watcher_instance_id])
    if watcher_started_at_utc:
        command.extend(["--watcher-started-at-utc", watcher_started_at_utc])
    return command


def command_signature(command: list[str]) -> tuple[str, str]:
    script_path = str(AUTO_IMPORT_SCRIPT.resolve())
    intake_request = ""
    for index, token in enumerate(command):
        if token == "--intake-request" and index + 1 < len(command):
            intake_request = command[index + 1]
            break
    return script_path, intake_request


def command_option_value(arguments_text: str, option: str) -> str:
    try:
        arguments = shlex.split(arguments_text)
    except ValueError:
        return ""
    for index, token in enumerate(arguments):
        if token == option and index + 1 < len(arguments):
            return arguments[index + 1]
    return ""


def kill_and_reap_process(
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
) -> tuple[int | None, bool]:
    try:
        process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        return getattr(process, "returncode", None), False
    remaining = max(deadline - time.monotonic(), 0.0)
    try:
        return process.wait(timeout=max(remaining, 0.001)), True
    except subprocess.TimeoutExpired:
        return getattr(process, "returncode", None), False
    except (ChildProcessError, OSError):
        returncode = getattr(process, "returncode", None)
        return returncode, returncode is not None


def bounded_subprocess_capture(
    command: list[str],
    *,
    max_capture_bytes: int = PROCESS_SCAN_MAX_CAPTURE_BYTES,
    timeout_seconds: float = PROCESS_SCAN_TIMEOUT_SECONDS,
    cleanup_seconds: float = PROCESS_SCAN_CLEANUP_SECONDS,
) -> dict[str, Any]:
    capture_limit = max(int(max_capture_bytes), 0)
    captured_chunks: list[bytes] = []
    capture_size = 0
    output_truncated = False
    reader_failed = False

    try:
        process = subprocess.Popen(
            command,
            env=subprocess_env(workspace_root=ROOT.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=False,
            bufsize=0,
        )
    except FileNotFoundError:
        return {
            "stdout": b"",
            "returncode": None,
            "complete": False,
            "timed_out": False,
            "output_truncated": False,
            "cleanup_complete": True,
            "process_reaped": False,
            "error_code": "process_scan_program_missing",
        }
    except PermissionError:
        return {
            "stdout": b"",
            "returncode": None,
            "complete": False,
            "timed_out": False,
            "output_truncated": False,
            "cleanup_complete": True,
            "process_reaped": False,
            "error_code": "process_scan_program_denied",
        }
    except OSError:
        return {
            "stdout": b"",
            "returncode": None,
            "complete": False,
            "timed_out": False,
            "output_truncated": False,
            "cleanup_complete": True,
            "process_reaped": False,
            "error_code": "process_scan_launch_failed",
        }

    stdout_pipe = process.stdout
    if stdout_pipe is None:
        cleanup_deadline = time.monotonic() + max(float(cleanup_seconds), 0.001)
        returncode, process_reaped = kill_and_reap_process(
            process,
            deadline=cleanup_deadline,
        )
        return {
            "stdout": b"",
            "returncode": returncode,
            "complete": False,
            "timed_out": False,
            "output_truncated": False,
            "cleanup_complete": process_reaped,
            "process_reaped": process_reaped,
            "error_code": (
                "process_scan_capture_unavailable"
                if process_reaped
                else "process_scan_cleanup_incomplete"
            ),
        }

    def drain_stdout() -> None:
        nonlocal capture_size, output_truncated, reader_failed
        try:
            while True:
                chunk = stdout_pipe.read(64 * 1024)
                if not chunk:
                    return
                remaining = max(capture_limit - capture_size, 0)
                if remaining:
                    retained = chunk[:remaining]
                    captured_chunks.append(retained)
                    capture_size += len(retained)
                if len(chunk) > remaining:
                    output_truncated = True
        except (OSError, ValueError):
            reader_failed = True

    reader = threading.Thread(
        target=drain_stdout,
        name="windows-proof-watcher-process-scan-reader",
        daemon=True,
    )
    reader.start()
    timed_out = False
    wait_failed = False
    process_reaped = False
    cleanup_deadline: float | None = None
    try:
        returncode = process.wait(timeout=max(float(timeout_seconds), 0.1))
        process_reaped = True
    except subprocess.TimeoutExpired:
        timed_out = True
        cleanup_deadline = time.monotonic() + max(float(cleanup_seconds), 0.001)
        returncode, process_reaped = kill_and_reap_process(
            process,
            deadline=cleanup_deadline,
        )
    except (ChildProcessError, OSError):
        wait_failed = True
        cleanup_deadline = time.monotonic() + max(float(cleanup_seconds), 0.001)
        returncode, process_reaped = kill_and_reap_process(
            process,
            deadline=cleanup_deadline,
        )

    if cleanup_deadline is None:
        cleanup_deadline = time.monotonic() + max(float(cleanup_seconds), 0.001)
    reader.join(timeout=max(cleanup_deadline - time.monotonic(), 0.0))
    if reader.is_alive():
        try:
            stdout_pipe.close()
        except (OSError, ValueError):
            pass
        reader.join(timeout=max(cleanup_deadline - time.monotonic(), 0.0))
        reader_failed = reader.is_alive() or reader_failed
    try:
        stdout_pipe.close()
    except (OSError, ValueError):
        pass

    cleanup_complete = process_reaped and not reader.is_alive()
    if not cleanup_complete:
        error_code = "process_scan_cleanup_incomplete"
    elif timed_out:
        error_code = "process_scan_timeout"
    elif wait_failed or reader_failed:
        error_code = "process_scan_capture_failed"
    elif output_truncated:
        error_code = "process_scan_output_limit"
    elif returncode != 0:
        error_code = "process_scan_nonzero_exit"
    else:
        error_code = ""
    return {
        "stdout": b"".join(captured_chunks),
        "returncode": returncode,
        "complete": not error_code,
        "timed_out": timed_out,
        "output_truncated": output_truncated,
        "cleanup_complete": cleanup_complete,
        "process_reaped": process_reaped,
        "error_code": error_code,
    }


def scan_matching_watcher_pids(command: list[str]) -> dict[str, Any]:
    script_path, intake_request = command_signature(command)
    capture = bounded_subprocess_capture(
        ["ps", "-ww", "-eo", "pid=,args="],
    )
    pids: list[int] = []
    bindings_by_pid: dict[str, dict[str, str]] = {}
    stdout = capture.get("stdout")
    stdout_bytes = stdout if isinstance(stdout, bytes) else b""
    for raw_line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid_text, args_text = parts
        if script_path not in args_text:
            continue
        if "--intake-request" not in args_text:
            continue
        if intake_request and intake_request not in args_text:
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        if is_process_alive(pid):
            pids.append(pid)
            bindings_by_pid[str(pid)] = {
                "watcher_instance_id": command_option_value(
                    args_text,
                    "--watcher-instance-id",
                ),
                "watcher_process_started_at_utc": command_option_value(
                    args_text,
                    "--watcher-started-at-utc",
                ),
            }
    return {
        "pids": sorted(set(pids)),
        "bindings_by_pid": bindings_by_pid,
        "complete": bool(capture.get("complete")),
        "error_code": str(capture.get("error_code") or ""),
        "timed_out": bool(capture.get("timed_out")),
        "output_truncated": bool(capture.get("output_truncated")),
        "cleanup_complete": bool(capture.get("cleanup_complete")),
        "process_reaped": bool(capture.get("process_reaped")),
        "returncode": capture.get("returncode"),
    }


def list_matching_watcher_pids(command: list[str]) -> list[int]:
    return list(scan_matching_watcher_pids(command)["pids"])


def remove_pid_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def receipt_path_text(path: Path) -> str:
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name or "."


def receipt_command(command: list[str]) -> list[str]:
    result: list[str] = []
    for token in command:
        candidate = Path(token)
        result.append(receipt_path_text(candidate) if candidate.is_absolute() else token)
    return result


def parse_utc_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def intake_bindings_match(receipt_value: Any, expected: Path | None) -> bool:
    text = str(receipt_value or "").strip()
    if not text or expected is None:
        return False
    try:
        return Path(text).resolve() == expected.resolve()
    except OSError:
        return False


def heartbeat_binding_state(
    payload: dict[str, Any],
    *,
    generated_at: datetime | None,
    expected_pid: int | None,
    expected_intake_request: Path | None,
    expected_instance_id: str,
    expected_watcher_started_at_utc: str,
) -> str:
    contract_version = payload.get("contract_version")
    if (
        payload.get("contract_name") != AUTO_IMPORT_CONTRACT_NAME
        or not isinstance(contract_version, int)
        or isinstance(contract_version, bool)
        or contract_version != 2
        or payload.get("supersedes_contract_name") != AUTO_IMPORT_CONTRACT_NAME_V1
    ):
        return "receipt_contract_mismatch"
    if (
        expected_pid is None
        or expected_intake_request is None
        or not expected_instance_id
        or not expected_watcher_started_at_utc
    ):
        return "watcher_binding_unknown"
    runtime_binding = (
        payload.get("runtime_binding")
        if isinstance(payload.get("runtime_binding"), dict)
        else {}
    )
    runtime_pid = runtime_binding.get("pid")
    if not isinstance(runtime_pid, int) or isinstance(runtime_pid, bool):
        return "receipt_binding_missing"
    if runtime_pid != expected_pid:
        return "pid_mismatch"
    if str(runtime_binding.get("watcher_instance_id") or "") != expected_instance_id:
        return "instance_mismatch"
    if not intake_bindings_match(
        runtime_binding.get("intake_request"),
        expected_intake_request,
    ):
        return "intake_mismatch"
    expected_started_at = parse_utc_timestamp(expected_watcher_started_at_utc)
    receipt_watcher_started_at = parse_utc_timestamp(
        runtime_binding.get("watcher_started_at_utc")
    )
    runtime_started_at = parse_utc_timestamp(runtime_binding.get("started_at_utc"))
    if (
        expected_started_at is None
        or receipt_watcher_started_at is None
        or runtime_started_at is None
        or generated_at is None
    ):
        return "receipt_binding_missing"
    if receipt_watcher_started_at != expected_started_at:
        return "start_time_mismatch"
    if runtime_started_at < expected_started_at or generated_at < expected_started_at:
        return "receipt_predates_watcher"
    return "bound"


def auto_import_receipt_summary(
    path: Path,
    *,
    current_time: datetime | None = None,
    stale_after_seconds: int = AUTO_IMPORT_HEARTBEAT_MIN_STALE_SECONDS,
    expected_pid: int | None = None,
    expected_intake_request: Path | None = None,
    expected_instance_id: str = "",
    expected_watcher_started_at_utc: str = "",
) -> dict[str, Any]:
    exists = path.is_file()
    payload = load_json(path)
    generated_at_text = str(payload.get("generated_at_utc") or "").strip()
    generated_at = parse_utc_timestamp(generated_at_text)
    now = (current_time or datetime.now(UTC)).astimezone(UTC)
    stale_after = max(int(stale_after_seconds), 1)
    heartbeat_age_seconds: float | None = None
    if not exists:
        heartbeat_state = "missing"
    elif generated_at is None:
        heartbeat_state = "invalid"
    else:
        heartbeat_age_seconds = (now - generated_at).total_seconds()
        if heartbeat_age_seconds < -60.0:
            heartbeat_state = "invalid"
            heartbeat_age_seconds = None
        else:
            heartbeat_age_seconds = max(heartbeat_age_seconds, 0.0)
            heartbeat_state = (
                "stale"
                if heartbeat_age_seconds > stale_after
                else "fresh"
            )
    if not exists:
        binding_state = "missing_receipt"
    else:
        binding_state = heartbeat_binding_state(
            payload,
            generated_at=generated_at,
            expected_pid=expected_pid,
            expected_intake_request=expected_intake_request,
            expected_instance_id=expected_instance_id,
            expected_watcher_started_at_utc=expected_watcher_started_at_utc,
        )
    return {
        "auto_import_receipt_path": receipt_path_text(path),
        "auto_import_receipt_exists": exists,
        "auto_import_receipt_status": str(payload.get("status") or "").strip(),
        "auto_import_receipt_generated_at_utc": generated_at_text,
        "auto_import_heartbeat_state": heartbeat_state,
        "auto_import_heartbeat_age_seconds": heartbeat_age_seconds,
        "auto_import_heartbeat_stale_after_seconds": stale_after,
        "auto_import_heartbeat_fresh": heartbeat_state == "fresh",
        "auto_import_heartbeat_stale": heartbeat_state == "stale",
        "auto_import_heartbeat_binding_state": binding_state,
        "auto_import_heartbeat_bound": binding_state == "bound",
    }


def watcher_health(
    *,
    process_alive: bool,
    process_scan_complete: bool,
    heartbeat_state: str,
    launched_now: bool,
    heartbeat_bound: bool = False,
) -> str:
    if not process_scan_complete:
        return "unknown_process_state"
    if not process_alive:
        return "not_running"
    if heartbeat_state == "fresh" and heartbeat_bound:
        return "healthy"
    if launched_now:
        return "starting"
    if heartbeat_state == "fresh":
        return "degraded_unbound_heartbeat"
    if heartbeat_state == "missing":
        return "degraded_missing_heartbeat"
    if heartbeat_state == "stale":
        return "degraded_stale_heartbeat"
    return "degraded_invalid_heartbeat"


def build_payload(
    *,
    status: str,
    action: str,
    pid: int | None,
    process_alive: bool,
    matching_process_pids: list[int] | None,
    command: list[str],
    state_path: Path,
    pid_file: Path,
    log_file: Path,
    intake_request: Path,
    wait_seconds: float,
    poll_seconds: float,
    refresh_intake_request: bool,
    adopted_existing_process: bool = False,
    stop_signal: str = "",
    force_killed: bool = False,
    stopped_pids: list[int] | None = None,
    failed_stop_pids: list[int] | None = None,
    note: str = "",
    resolution: dict[str, Any] | None = None,
    launched_now: bool = False,
) -> dict[str, Any]:
    matching_pids = list(matching_process_pids or [])
    duplicate_pids = [item for item in matching_pids if item != pid]
    resolution_receipt = dict(resolution or {})
    process_scan_complete = bool(
        resolution_receipt.get("process_scan_complete", True)
    )
    heartbeat_stale_after = max(
        AUTO_IMPORT_HEARTBEAT_MIN_STALE_SECONDS,
        int(max(poll_seconds, 0.0) * AUTO_IMPORT_HEARTBEAT_POLL_MULTIPLIER),
    )
    heartbeat_receipt = auto_import_receipt_summary(
        DEFAULT_AUTO_IMPORT_OUTPUT,
        stale_after_seconds=heartbeat_stale_after,
        expected_pid=pid,
        expected_intake_request=intake_request,
        expected_instance_id=str(
            resolution_receipt.get("watcher_instance_id") or ""
        ),
        expected_watcher_started_at_utc=str(
            resolution_receipt.get("watcher_process_started_at_utc") or ""
        ),
    )
    command_receipt = receipt_command(command)
    health = watcher_health(
        process_alive=process_alive,
        process_scan_complete=process_scan_complete,
        heartbeat_state=str(heartbeat_receipt["auto_import_heartbeat_state"]),
        launched_now=launched_now,
        heartbeat_bound=bool(heartbeat_receipt["auto_import_heartbeat_bound"]),
    )
    return {
        "contract_name": WATCHER_CONTRACT_NAME,
        "contract_version": 2,
        "supersedes_contract_name": WATCHER_CONTRACT_NAME_V1,
        "generated_at_utc": now_iso(),
        "status": status,
        "action": action,
        "watcher_launch_mode": LAUNCH_MODE,
        "pid": pid,
        "process_alive": process_alive,
        "watcher_health": health,
        "watcher_instance_id": str(
            resolution_receipt.get("watcher_instance_id") or ""
        ),
        "watcher_process_started_at_utc": str(
            resolution_receipt.get("watcher_process_started_at_utc") or ""
        ),
        "adopted_existing_process": adopted_existing_process,
        "matching_process_pids": matching_pids,
        "matching_process_count": len(matching_pids),
        "duplicate_process_pids": duplicate_pids,
        "duplicate_process_count": len(duplicate_pids),
        "state_path": receipt_path_text(state_path),
        "pid_file": receipt_path_text(pid_file),
        "log_file": receipt_path_text(log_file),
        "intake_request": receipt_path_text(intake_request),
        "command": command_receipt,
        "command_text": " ".join(command_receipt),
        "wait_seconds": int(wait_seconds),
        "poll_seconds": int(poll_seconds),
        "refresh_intake_request": bool(refresh_intake_request),
        "stop_signal": stop_signal,
        "force_killed": force_killed,
        "stopped_pids": list(stopped_pids or []),
        "failed_stop_pids": list(failed_stop_pids or []),
        "note": note,
        "process_scan_complete": process_scan_complete,
        "process_scan_error_code": str(
            resolution_receipt.get("process_scan_error_code") or ""
        ),
        "process_scan_timed_out": bool(
            resolution_receipt.get("process_scan_timed_out", False)
        ),
        "process_scan_output_truncated": bool(
            resolution_receipt.get("process_scan_output_truncated", False)
        ),
        "process_scan_cleanup_complete": bool(
            resolution_receipt.get("process_scan_cleanup_complete", True)
        ),
        "process_scan_process_reaped": bool(
            resolution_receipt.get("process_scan_process_reaped", True)
        ),
        "pid_file_present_before_resolution": bool(
            resolution_receipt.get("pid_file_present_before_resolution", False)
        ),
        "pid_file_state_before_resolution": str(
            resolution_receipt.get("pid_file_state_before_resolution") or "missing"
        ),
        "pid_file_recorded_pid": resolution_receipt.get("pid_file_recorded_pid"),
        "stale_pid_detected": bool(
            resolution_receipt.get("stale_pid_detected", False)
        ),
        "stale_pid_reason": str(
            resolution_receipt.get("stale_pid_reason") or ""
        ),
        "stale_pid_file_removed": bool(
            resolution_receipt.get("stale_pid_file_removed", False)
        ),
        "stale_pid_file_repaired": bool(
            resolution_receipt.get("stale_pid_file_repaired", False)
        ),
        **heartbeat_receipt,
    }


def open_log_append(path: Path, *, binary: bool):
    ensure_durable_parent(path)
    validate_regular_target(path, target_name="watcher log")
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_APPEND
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("watcher log target must be a regular file")
        return os.fdopen(
            descriptor,
            "ab" if binary else "a",
            encoding=None if binary else "utf-8",
            buffering=0 if binary else -1,
        )
    except BaseException:
        os.close(descriptor)
        raise


def bounded_cleanup_launched_process(
    process: subprocess.Popen[bytes],
    *,
    cleanup_seconds: float = POST_LAUNCH_CLEANUP_SECONDS,
    term_seconds: float = POST_LAUNCH_TERM_SECONDS,
) -> bool:
    deadline = time.monotonic() + max(float(cleanup_seconds), 0.001)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.terminate()
        except (ProcessLookupError, OSError):
            pass
    remaining = max(deadline - time.monotonic(), 0.0)
    try:
        process.wait(timeout=max(min(remaining, max(float(term_seconds), 0.0)), 0.001))
        return True
    except subprocess.TimeoutExpired:
        pass
    except (ChildProcessError, OSError):
        if getattr(process, "returncode", None) is not None:
            return True

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass
    remaining = max(deadline - time.monotonic(), 0.0)
    try:
        process.wait(timeout=max(remaining, 0.001))
        return True
    except subprocess.TimeoutExpired:
        return False
    except (ChildProcessError, OSError):
        return getattr(process, "returncode", None) is not None


def launch_process(command: list[str], log_file: Path) -> subprocess.Popen[bytes]:
    with open_log_append(log_file, binary=False) as handle:
        handle.write(f"START {now_iso()}\n")
        handle.flush()
        os.fsync(handle.fileno())
    log_handle = open_log_append(log_file, binary=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=subprocess_env(workspace_root=ROOT.parent),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        try:
            log_handle.close()
        except BaseException:
            if process is not None:
                try:
                    bounded_cleanup_launched_process(process)
                except BaseException:
                    pass
            raise
    return process


def resolve_running_process_state(pid_file: Path, command: list[str]) -> dict[str, Any]:
    pid_state = read_pid_state(pid_file)
    recorded_pid = pid_state.get("pid")
    recorded_pid_alive = is_process_alive(recorded_pid)
    scan = scan_matching_watcher_pids(command)
    matches = list(scan.get("pids") or [])
    bindings_by_pid = (
        scan.get("bindings_by_pid")
        if isinstance(scan.get("bindings_by_pid"), dict)
        else {}
    )
    cleanup_complete = bool(scan.get("cleanup_complete", True))
    result = {
        "pid": recorded_pid if recorded_pid_alive else None,
        "matching_process_pids": matches,
        "adopted_existing_process": False,
        "process_scan_complete": bool(scan.get("complete")) and cleanup_complete,
        "process_scan_error_code": str(
            scan.get("error_code")
            or ("process_scan_cleanup_incomplete" if not cleanup_complete else "")
        ),
        "process_scan_timed_out": bool(scan.get("timed_out")),
        "process_scan_output_truncated": bool(scan.get("output_truncated")),
        "process_scan_cleanup_complete": cleanup_complete,
        "process_scan_process_reaped": bool(scan.get("process_reaped", True)),
        "watcher_instance_id": "",
        "watcher_process_started_at_utc": "",
        "pid_file_present_before_resolution": bool(pid_state.get("present")),
        "pid_file_state_before_resolution": str(pid_state.get("state") or "missing"),
        "pid_file_recorded_pid": recorded_pid,
        "recorded_pid_alive": recorded_pid_alive,
        "stale_pid_detected": False,
        "stale_pid_reason": "",
        "stale_pid_file_removed": False,
        "stale_pid_file_repaired": False,
    }
    if not result["process_scan_complete"]:
        return result

    if recorded_pid in matches and recorded_pid_alive:
        write_pid(pid_file, recorded_pid)
        result["pid"] = recorded_pid
        process_binding = bindings_by_pid.get(str(recorded_pid))
        if isinstance(process_binding, dict):
            result["watcher_instance_id"] = str(
                process_binding.get("watcher_instance_id") or ""
            )
            result["watcher_process_started_at_utc"] = str(
                process_binding.get("watcher_process_started_at_utc") or ""
            )
        return result

    if bool(pid_state.get("present")):
        result["stale_pid_detected"] = True
        pid_file_state = str(pid_state.get("state") or "invalid")
        if pid_file_state != "valid":
            result["stale_pid_reason"] = f"pid_file_{pid_file_state}"
        elif recorded_pid_alive:
            result["stale_pid_reason"] = "recorded_pid_command_mismatch"
        else:
            result["stale_pid_reason"] = "recorded_pid_not_alive"

    if matches:
        selected = matches[0]
        write_pid(pid_file, selected)
        result["pid"] = selected
        result["adopted_existing_process"] = True
        result["stale_pid_file_repaired"] = bool(pid_state.get("present"))
        process_binding = bindings_by_pid.get(str(selected))
        if isinstance(process_binding, dict):
            result["watcher_instance_id"] = str(
                process_binding.get("watcher_instance_id") or ""
            )
            result["watcher_process_started_at_utc"] = str(
                process_binding.get("watcher_process_started_at_utc") or ""
            )
        return result

    if bool(pid_state.get("present")):
        remove_pid_file(pid_file)
        result["stale_pid_file_removed"] = True
    result["pid"] = None
    return result


def resolve_running_processes(pid_file: Path, command: list[str]) -> tuple[int | None, list[int], bool]:
    resolution = resolve_running_process_state(pid_file, command)
    return (
        resolution.get("pid"),
        list(resolution.get("matching_process_pids") or []),
        bool(resolution.get("adopted_existing_process")),
    )


def restore_watcher_binding(
    resolution: dict[str, Any],
    state_path: Path,
    intake_request: Path,
) -> dict[str, Any]:
    restored = dict(resolution)
    observed_instance_id = str(
        restored.get("watcher_instance_id") or ""
    ).strip()
    observed_started_at = str(
        restored.get("watcher_process_started_at_utc") or ""
    ).strip()
    if (
        not observed_instance_id
        or parse_utc_timestamp(observed_started_at) is None
    ):
        return restored
    prior = load_json(state_path)
    if prior.get("contract_name") != WATCHER_CONTRACT_NAME:
        return restored
    if prior.get("pid") != restored.get("pid"):
        return restored
    if str(prior.get("intake_request") or "") != receipt_path_text(intake_request):
        return restored
    instance_id = str(prior.get("watcher_instance_id") or "").strip()
    started_at = str(prior.get("watcher_process_started_at_utc") or "").strip()
    if (
        instance_id != observed_instance_id
        or parse_utc_timestamp(started_at) is None
        or started_at != observed_started_at
    ):
        return restored
    return restored


def start(args: argparse.Namespace) -> int:
    command = watcher_command(
        args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
    )
    preflight_watcher_targets(
        state_path=args.state_path,
        pid_file=args.pid_file,
        log_file=args.log_file,
    )
    resolution = restore_watcher_binding(
        resolve_running_process_state(args.pid_file, command),
        args.state_path,
        args.intake_request,
    )
    running_pid = resolution.get("pid")
    matching_pids = list(resolution.get("matching_process_pids") or [])
    adopted = bool(resolution.get("adopted_existing_process"))
    if not bool(resolution.get("process_scan_complete")):
        payload = build_payload(
            status="process_state_unknown",
            action="start",
            pid=running_pid,
            process_alive=bool(resolution.get("recorded_pid_alive")),
            matching_process_pids=matching_pids,
            command=command,
            state_path=args.state_path,
            pid_file=args.pid_file,
            log_file=args.log_file,
            intake_request=args.intake_request,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            refresh_intake_request=args.refresh_intake_request,
            resolution=resolution,
            note="watcher start withheld because process discovery was incomplete",
        )
        write_json(args.state_path, payload)
        print(json.dumps(payload, indent=2))
        return 1
    if running_pid is not None:
        payload = build_payload(
            status="already_running",
            action="start",
            pid=running_pid,
            process_alive=True,
            matching_process_pids=matching_pids,
            command=command,
            state_path=args.state_path,
            pid_file=args.pid_file,
            log_file=args.log_file,
            intake_request=args.intake_request,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            refresh_intake_request=args.refresh_intake_request,
            adopted_existing_process=adopted,
            resolution=resolution,
            note="watcher already active" + ("; duplicate watchers detected" if len(matching_pids) > 1 else ""),
        )
        write_json(args.state_path, payload)
        print(json.dumps(payload, indent=2))
        return 0

    watcher_started_at = now_iso()
    watcher_instance_id = secrets.token_hex(16)
    launch_command = watcher_command(
        args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
        watcher_instance_id=watcher_instance_id,
        watcher_started_at_utc=watcher_started_at,
    )
    resolution = {
        **resolution,
        "watcher_instance_id": watcher_instance_id,
        "watcher_process_started_at_utc": watcher_started_at,
    }
    process = launch_process(launch_command, args.log_file)
    try:
        write_pid(args.pid_file, process.pid)
        alive = is_process_alive(process.pid)
        payload = build_payload(
            status="running" if alive else "launch_failed",
            action="start",
            pid=process.pid,
            process_alive=alive,
            matching_process_pids=[process.pid] if alive else [],
            command=launch_command,
            state_path=args.state_path,
            pid_file=args.pid_file,
            log_file=args.log_file,
            intake_request=args.intake_request,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            refresh_intake_request=args.refresh_intake_request,
            resolution=resolution,
            launched_now=True,
            note="watcher launched" if alive else "watcher exited immediately",
        )
        if not alive:
            remove_pid_file(args.pid_file)
        write_json(args.state_path, payload)
    except BaseException:
        try:
            bounded_cleanup_launched_process(process)
        except BaseException:
            pass
        try:
            if read_pid(args.pid_file) == process.pid:
                remove_pid_file(args.pid_file)
        except BaseException:
            pass
        raise
    print(json.dumps(payload, indent=2))
    return 0 if alive else 1


def status(args: argparse.Namespace) -> int:
    command = watcher_command(
        args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
    )
    resolution = restore_watcher_binding(
        resolve_running_process_state(args.pid_file, command),
        args.state_path,
        args.intake_request,
    )
    running_pid = resolution.get("pid")
    matching_pids = list(resolution.get("matching_process_pids") or [])
    adopted = bool(resolution.get("adopted_existing_process"))
    process_scan_complete = bool(resolution.get("process_scan_complete"))
    payload = build_payload(
        status=(
            "process_state_unknown"
            if not process_scan_complete
            else ("running" if running_pid is not None else "not_running")
        ),
        action="status",
        pid=running_pid,
        process_alive=(
            bool(resolution.get("recorded_pid_alive"))
            if not process_scan_complete
            else running_pid is not None
        ),
        matching_process_pids=matching_pids,
        command=command,
        state_path=args.state_path,
        pid_file=args.pid_file,
        log_file=args.log_file,
        intake_request=args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
        adopted_existing_process=adopted,
        resolution=resolution,
        note=(
            "watcher process state is unknown because discovery was incomplete"
            if not process_scan_complete
            else (
                "watcher discovered by pid file or process scan"
                + ("; duplicate watchers detected" if len(matching_pids) > 1 else "")
                if running_pid is not None
                else "no live watcher found"
            )
        ),
    )
    write_json(args.state_path, payload)
    print(json.dumps(payload, indent=2))
    return 0 if process_scan_complete else 1


def terminate_process_group(pid: int, grace_seconds: float) -> tuple[bool, bool]:
    force_killed = False
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False, force_killed

    deadline = time.monotonic() + max(grace_seconds, 0.0)
    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            return True, force_killed
        time.sleep(0.2)

    if not is_process_alive(pid):
        return True, force_killed

    force_killed = True
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True, force_killed
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            return True, force_killed
        time.sleep(0.2)
    return not is_process_alive(pid), force_killed


def stop(args: argparse.Namespace) -> int:
    command = watcher_command(
        args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
    )
    resolution = restore_watcher_binding(
        resolve_running_process_state(args.pid_file, command),
        args.state_path,
        args.intake_request,
    )
    running_pid = resolution.get("pid")
    matching_pids = list(resolution.get("matching_process_pids") or [])
    adopted = bool(resolution.get("adopted_existing_process"))
    if not bool(resolution.get("process_scan_complete")):
        payload = build_payload(
            status="process_state_unknown",
            action="stop",
            pid=running_pid,
            process_alive=bool(resolution.get("recorded_pid_alive")),
            matching_process_pids=matching_pids,
            command=command,
            state_path=args.state_path,
            pid_file=args.pid_file,
            log_file=args.log_file,
            intake_request=args.intake_request,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            refresh_intake_request=args.refresh_intake_request,
            resolution=resolution,
            note="watcher stop withheld because process discovery was incomplete",
        )
        write_json(args.state_path, payload)
        print(json.dumps(payload, indent=2))
        return 1
    if running_pid is None:
        payload = build_payload(
            status="not_running",
            action="stop",
            pid=None,
            process_alive=False,
            matching_process_pids=[],
            command=command,
            state_path=args.state_path,
            pid_file=args.pid_file,
            log_file=args.log_file,
            intake_request=args.intake_request,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            refresh_intake_request=args.refresh_intake_request,
            resolution=resolution,
            note="no live watcher found",
        )
        write_json(args.state_path, payload)
        print(json.dumps(payload, indent=2))
        return 0

    stopped_pids: list[int] = []
    failed_stop_pids: list[int] = []
    any_force_killed = False
    for pid in matching_pids or [running_pid]:
        stopped, force_killed = terminate_process_group(pid, args.stop_grace_seconds)
        any_force_killed = any_force_killed or force_killed
        if stopped:
            stopped_pids.append(pid)
        else:
            failed_stop_pids.append(pid)
    if not failed_stop_pids:
        remove_pid_file(args.pid_file)
    payload = build_payload(
        status="stopped" if not failed_stop_pids else "stop_failed",
        action="stop",
        pid=running_pid,
        process_alive=bool(failed_stop_pids),
        matching_process_pids=[pid for pid in matching_pids if pid not in stopped_pids] if failed_stop_pids else [],
        command=command,
        state_path=args.state_path,
        pid_file=args.pid_file,
        log_file=args.log_file,
        intake_request=args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
        adopted_existing_process=adopted,
        resolution=resolution,
        stop_signal="SIGTERM" if not any_force_killed else "SIGKILL",
        force_killed=any_force_killed,
        stopped_pids=stopped_pids,
        failed_stop_pids=failed_stop_pids,
        note="watcher terminated" if not failed_stop_pids else "watcher still alive after stop attempt",
    )
    write_json(args.state_path, payload)
    print(json.dumps(payload, indent=2))
    return 0 if not failed_stop_pids else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start, inspect, or stop the Windows installer gold-proof auto-import watcher.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    for action in ("start", "status", "stop"):
        subparser = subparsers.add_parser(action)
        subparser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
        subparser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
        subparser.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
        subparser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE)
        subparser.add_argument("--wait-seconds", type=float, default=DEFAULT_WAIT_SECONDS)
        subparser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
        subparser.add_argument("--refresh-intake-request", action="store_true", default=True)
        subparser.add_argument("--no-refresh-intake-request", action="store_false", dest="refresh_intake_request")
    subparsers.choices["stop"].add_argument("--stop-grace-seconds", type=float, default=DEFAULT_STOP_GRACE_SECONDS)
    return parser.parse_args([] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.action == "start":
        return start(args)
    if args.action == "status":
        return status(args)
    if args.action == "stop":
        return stop(args)
    raise SystemExit(f"unsupported action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
