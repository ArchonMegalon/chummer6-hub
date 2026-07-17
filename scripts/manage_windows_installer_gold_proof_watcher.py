#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


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
    return command


def command_signature(command: list[str]) -> tuple[str, str]:
    script_path = str(AUTO_IMPORT_SCRIPT.resolve())
    intake_request = ""
    for index, token in enumerate(command):
        if token == "--intake-request" and index + 1 < len(command):
            intake_request = command[index + 1]
            break
    return script_path, intake_request


def list_matching_watcher_pids(command: list[str]) -> list[int]:
    script_path, intake_request = command_signature(command)
    completed = subprocess.run(
        ["ps", "-ww", "-eo", "pid=,args="],
        env=subprocess_env(workspace_root=ROOT.parent),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    pids: list[int] = []
    for raw_line in completed.stdout.splitlines():
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
    return sorted(set(pids))


def remove_pid_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def auto_import_receipt_summary(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    return {
        "auto_import_receipt_path": str(path),
        "auto_import_receipt_exists": path.is_file(),
        "auto_import_receipt_status": str(payload.get("status") or "").strip(),
        "auto_import_receipt_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
    }


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
) -> dict[str, Any]:
    matching_pids = list(matching_process_pids or [])
    duplicate_pids = [item for item in matching_pids if item != pid]
    return {
        "contract_name": "chummer.windows_installer_gold_proof_watcher.v1",
        "generated_at_utc": now_iso(),
        "status": status,
        "action": action,
        "watcher_launch_mode": LAUNCH_MODE,
        "pid": pid,
        "process_alive": process_alive,
        "adopted_existing_process": adopted_existing_process,
        "matching_process_pids": matching_pids,
        "matching_process_count": len(matching_pids),
        "duplicate_process_pids": duplicate_pids,
        "duplicate_process_count": len(duplicate_pids),
        "state_path": str(state_path),
        "pid_file": str(pid_file),
        "log_file": str(log_file),
        "intake_request": str(intake_request),
        "command": command,
        "command_text": " ".join(command),
        "wait_seconds": int(wait_seconds),
        "poll_seconds": int(poll_seconds),
        "refresh_intake_request": bool(refresh_intake_request),
        "stop_signal": stop_signal,
        "force_killed": force_killed,
        "stopped_pids": list(stopped_pids or []),
        "failed_stop_pids": list(failed_stop_pids or []),
        "note": note,
        **auto_import_receipt_summary(DEFAULT_AUTO_IMPORT_OUTPUT),
    }


def launch_process(command: list[str], log_file: Path) -> subprocess.Popen[bytes]:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"START {now_iso()}\n")
    log_handle = log_file.open("ab", buffering=0)
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
        log_handle.close()
    return process


def resolve_running_processes(pid_file: Path, command: list[str]) -> tuple[int | None, list[int], bool]:
    pid = read_pid(pid_file)
    matches = list_matching_watcher_pids(command)
    if pid in matches and is_process_alive(pid):
        write_pid(pid_file, pid)
        return pid, matches, False
    if matches:
        selected = matches[0]
        write_pid(pid_file, selected)
        return selected, matches, True
    if pid is not None:
        remove_pid_file(pid_file)
    return None, [], False


def start(args: argparse.Namespace) -> int:
    command = watcher_command(
        args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
    )
    running_pid, matching_pids, adopted = resolve_running_processes(args.pid_file, command)
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
            note="watcher already active" + ("; duplicate watchers detected" if len(matching_pids) > 1 else ""),
        )
        write_json(args.state_path, payload)
        print(json.dumps(payload, indent=2))
        return 0

    process = launch_process(command, args.log_file)
    write_pid(args.pid_file, process.pid)
    alive = is_process_alive(process.pid)
    payload = build_payload(
        status="running" if alive else "launch_failed",
        action="start",
        pid=process.pid,
        process_alive=alive,
        matching_process_pids=[process.pid] if alive else [],
        command=command,
        state_path=args.state_path,
        pid_file=args.pid_file,
        log_file=args.log_file,
        intake_request=args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
        note="watcher launched" if alive else "watcher exited immediately",
    )
    if not alive:
        remove_pid_file(args.pid_file)
    write_json(args.state_path, payload)
    print(json.dumps(payload, indent=2))
    return 0 if alive else 1


def status(args: argparse.Namespace) -> int:
    command = watcher_command(
        args.intake_request,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        refresh_intake_request=args.refresh_intake_request,
    )
    running_pid, matching_pids, adopted = resolve_running_processes(args.pid_file, command)
    payload = build_payload(
        status="running" if running_pid is not None else "not_running",
        action="status",
        pid=running_pid,
        process_alive=running_pid is not None,
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
        note=(
            "watcher discovered by pid file or process scan"
            + ("; duplicate watchers detected" if len(matching_pids) > 1 else "")
            if running_pid is not None
            else "no live watcher found"
        ),
    )
    write_json(args.state_path, payload)
    print(json.dumps(payload, indent=2))
    return 0


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
    running_pid, matching_pids, adopted = resolve_running_processes(args.pid_file, command)
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
