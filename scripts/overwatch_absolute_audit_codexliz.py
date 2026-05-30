#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


ROOT = Path("/docker/chummercomplete/chummer.run-services")
PLAN_FILE = Path(os.environ.get("CODEXLIZ_OVERWATCH_PLAN_FILE", str(ROOT / "ABSOLUTE_AUDIT_EXECUTION_PLAN_20260508.md")))
TASK_FILE = Path(os.environ.get("CODEXLIZ_OVERWATCH_TASK_FILE", str(ROOT / "ABSOLUTE_AUDIT_CODEXLIZ_TASK_20260508.md")))
CLOSURE_SCRIPT = Path(os.environ.get("CODEXLIZ_OVERWATCH_CLOSURE_SCRIPT", str(ROOT / "scripts" / "check_absolute_audit_closure.py")))
OUT_ROOT = ROOT / ".codex-studio" / "out" / "absolute-audit-codexliz-overwatch"
COMPLETION_ROOT = ROOT.parent / "_completion" / "chummer6_absolute_completion"
RUN_ID = os.environ.get("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = OUT_ROOT / RUN_ID
CURRENT_LINK = OUT_ROOT / "current"
PID_FILE = OUT_ROOT / "overwatch.pid"
SUPERVISOR_LOG = RUN_DIR / "supervisor.log"
STATE_JSON = RUN_DIR / "closure-status.json"
OODA_JSONL = RUN_DIR / "ooda.jsonl"
RUN_HEALTH_JSON = RUN_DIR / "health.json"
HEALTH_JSON = OUT_ROOT / "health.json"
LOOP_HISTORY_JSONL = OUT_ROOT / "loop-history.jsonl"
SLEEP_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_SLEEP_SECONDS", "30"))
HEARTBEAT_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_HEARTBEAT_SECONDS", "30"))
STALL_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_STALL_SECONDS", "600"))
ITERATION_TIMEOUT_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_ITERATION_TIMEOUT_SECONDS", "14400"))
MIDLOOP_CLOSURE_POLL_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_MIDLOOP_CLOSURE_POLL_SECONDS", "60"))
PASS0_START_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_PASS0_START_SECONDS", "180"))
MATERIAL_PROGRESS_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_MATERIAL_PROGRESS_SECONDS", "600"))
PASS0_DEADLINE_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_PASS0_DEADLINE_SECONDS", "420"))
LAUNCH_BACKOFF_BASE_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_BACKOFF_BASE_SECONDS", "30"))
LAUNCH_BACKOFF_MAX_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_BACKOFF_MAX_SECONDS", "1800"))
RUN_DIR_RETENTION_COUNT = int(os.environ.get("CODEXLIZ_OVERWATCH_RUN_DIR_RETENTION_COUNT", "56"))
LOOP_RETENTION_COUNT = int(os.environ.get("CODEXLIZ_OVERWATCH_LOOP_RETENTION_COUNT", "48"))
ACTIVE_ARTIFACT_MAX_BYTES = int(os.environ.get("CODEXLIZ_OVERWATCH_ACTIVE_ARTIFACT_MAX_BYTES", str(8 * 1024 * 1024)))
SUPERVISOR_LOG_MAX_BYTES = int(os.environ.get("CODEXLIZ_OVERWATCH_SUPERVISOR_LOG_MAX_BYTES", str(4 * 1024 * 1024)))
OODA_LOG_MAX_BYTES = int(os.environ.get("CODEXLIZ_OVERWATCH_OODA_LOG_MAX_BYTES", str(4 * 1024 * 1024)))
LOOP_HISTORY_MAX_BYTES = int(os.environ.get("CODEXLIZ_OVERWATCH_LOOP_HISTORY_MAX_BYTES", str(4 * 1024 * 1024)))
PROVIDER_MODELS_URL = os.environ.get("CODEXLIZ_OVERWATCH_PROVIDER_MODELS_URL", "http://127.0.0.1:33531/v1/models")
PROVIDER_TIMEOUT_SECONDS = int(os.environ.get("CODEXLIZ_OVERWATCH_PROVIDER_TIMEOUT_SECONDS", "15"))
CODEXLIZ_BIN = os.environ.get("CODEXLIZ_OVERWATCH_CODEXLIZ_BIN") or shutil.which("codexliz") or "/home/tibor/.local/bin/codexliz"
PYTHON_BIN = shutil.which("python3") or "/usr/bin/python3"
GIT_BIN = shutil.which("git") or "/usr/bin/git"
PS_BIN = shutil.which("ps") or "/usr/bin/ps"
TIMEOUT_BIN = shutil.which("timeout") or "/usr/bin/timeout"
BASELINE_FILE = RUN_DIR / "estate-git-baseline.json"
LOCK_FILE = OUT_ROOT / "overwatch.lock"
PASS0_ARTIFACTS = [
    "REPO_INVENTORY.yaml",
    "CANON_TRUTH_MAP.md",
    "OWNERSHIP_TRUTH_MAP.yaml",
    "FALSE_COMPLETE_REGISTER.yaml",
    "BUG_AND_GAP_REGISTER.yaml",
    "ABSOLUTE_COMPLETION_VERDICT.md",
]
PASS0_START_ARTIFACTS = [
    "REPO_INVENTORY.yaml",
    "CANON_TRUTH_MAP.md",
    "FALSE_COMPLETE_REGISTER.yaml",
]
PASS0_START_SUBSTANCE_KEYS = {
    "run_ledger",
    "repo_inventory",
    "repo_inventory_live_reconciliation",
    "canon_truth_map_semantics",
    "false_complete_seed_coverage",
}
PASS0_SUBSTANCE_KEYS = {
    "pass0_control_plane",
    "run_ledger",
    "repo_inventory",
    "repo_inventory_live_reconciliation",
    "ownership_truth_map_semantics",
    "canon_truth_map_semantics",
    "false_complete_seed_coverage",
    "bug_register_semantics",
    "completion_verdict_semantics",
}
BASELINE_REPOS = [
    "/docker/chummercomplete/Chummer6",
    "/docker/EA",
    "/docker/fleet",
    "/docker/chummercomplete/chummer.run-services",
    "/docker/chummercomplete/chummer-core-engine",
    "/docker/chummercomplete/chummer-presentation",
    "/docker/chummercomplete/chummer-design",
    "/docker/chummercomplete/chummer-hub-registry",
    "/docker/chummercomplete/chummer-play",
    "/docker/chummercomplete/chummer-ui-kit",
    "/docker/fleet/repos/chummer-media-factory",
    "/docker/chummer5a",
    "/docker/fleet/repos/chummer4",
]
LOCK_HANDLE: Any | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_capped_line(path: Path, line: str, max_bytes: int) -> None:
    if path.exists():
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > max_bytes:
            keep_bytes = max(1024, max_bytes // 2)
            tail = b""
            with path.open("rb") as handle:
                if size > keep_bytes:
                    handle.seek(-keep_bytes, os.SEEK_END)
                tail = handle.read()
            marker = f"[truncated {now_iso()}]\n".encode("utf-8")
            path.write_bytes(marker + tail)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_dirs() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    global LOCK_HANDLE
    LOCK_HANDLE = LOCK_FILE.open("a+", encoding="utf-8")
    try:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        owner_pid = PID_FILE.read_text(encoding="utf-8").strip() if PID_FILE.exists() else "unknown"
        raise RuntimeError(f"another overwatch supervisor already owns {LOCK_FILE} pid={owner_pid}") from exc
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if CURRENT_LINK.exists() or CURRENT_LINK.is_symlink():
        CURRENT_LINK.unlink()
    CURRENT_LINK.symlink_to(RUN_DIR)
    PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")


def capture_git_baseline() -> None:
    repos: list[dict[str, Any]] = []
    for raw_path in BASELINE_REPOS:
        path = Path(raw_path)
        if not path.exists():
            continue
        dirty = subprocess.run([GIT_BIN, "status", "--porcelain"], cwd=path, text=True, capture_output=True, check=False)
        branch = subprocess.run([GIT_BIN, "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, text=True, capture_output=True, check=False)
        sha = subprocess.run([GIT_BIN, "rev-parse", "HEAD"], cwd=path, text=True, capture_output=True, check=False)
        upstream = subprocess.run(
            [GIT_BIN, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd=path,
            text=True,
            capture_output=True,
            check=False,
        )
        ahead = behind = None
        if upstream.returncode == 0 and upstream.stdout.strip():
            counts = subprocess.run(
                [GIT_BIN, "rev-list", "--left-right", "--count", f"HEAD...{upstream.stdout.strip()}"],
                cwd=path,
                text=True,
                capture_output=True,
                check=False,
            )
            if counts.returncode == 0 and counts.stdout.strip():
                parts = counts.stdout.strip().split()
                if len(parts) == 2:
                    ahead, behind = parts
        repos.append(
            {
                "path": raw_path,
                "dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
                "branch": branch.stdout.strip() if branch.returncode == 0 else None,
                "head_sha": sha.stdout.strip() if sha.returncode == 0 else None,
                "upstream": upstream.stdout.strip() if upstream.returncode == 0 else None,
                "ahead": ahead,
                "behind": behind,
            }
        )
    BASELINE_FILE.write_text(
        json.dumps({"generated_at": now_iso(), "repos": repos}, indent=2) + "\n",
        encoding="utf-8",
    )


def log(message: str) -> None:
    line = f"{now_iso()} {message}"
    append_capped_line(SUPERVISOR_LOG, line, SUPERVISOR_LOG_MAX_BYTES)
    print(line, file=sys.stderr, flush=True)


def write_ooda(phase: str, note: str) -> None:
    payload = {"ts": now_iso(), "phase": phase, "note": note}
    append_capped_line(OODA_JSONL, json.dumps(payload), OODA_LOG_MAX_BYTES)


def append_loop_history(payload: dict[str, Any]) -> None:
    append_capped_line(LOOP_HISTORY_JSONL, json.dumps(payload), LOOP_HISTORY_MAX_BYTES)


def write_health(
    status: str,
    loop_id: int,
    state: dict[str, Any] | None = None,
    *,
    worker_pid: int | None = None,
    last_exit: int | None = None,
    failure_streak: int = 0,
    note: str = "",
) -> None:
    payload = {
        "ts": now_iso(),
        "run_id": RUN_ID,
        "status": status,
        "supervisor_pid": os.getpid(),
        "loop_id": loop_id,
        "worker_pid": worker_pid,
        "last_exit": last_exit,
        "failure_streak": failure_streak,
        "provider_models_url": PROVIDER_MODELS_URL,
        "completion_root": str(COMPLETION_ROOT),
        "run_dir": str(RUN_DIR),
        "note": note,
    }
    if state:
        payload["closure_done"] = bool(state.get("closure_done"))
        payload["pending_abs_ids"] = list(state.get("pending_abs_ids") or [])
        payload["pending_check_keys"] = list(state.get("pending_check_keys") or [])
        payload["pending_count"] = len(payload["pending_check_keys"])
    write_json(RUN_HEALTH_JSON, payload)
    write_json(HEALTH_JSON, payload)


def backoff_seconds(failure_streak: int) -> int:
    if failure_streak <= 0:
        return SLEEP_SECONDS
    exponent = min(failure_streak - 1, 6)
    return max(SLEEP_SECONDS, min(LAUNCH_BACKOFF_MAX_SECONDS, LAUNCH_BACKOFF_BASE_SECONDS * (2**exponent)))


def prune_old_run_dirs() -> list[str]:
    if not OUT_ROOT.exists():
        return []
    run_dirs = [
        path
        for path in OUT_ROOT.iterdir()
        if path.is_dir() and not path.is_symlink() and path.name not in {RUN_ID}
    ]
    run_dirs.sort(key=lambda item: item.stat().st_mtime)
    removed: list[str] = []
    while len(run_dirs) > RUN_DIR_RETENTION_COUNT:
        victim = run_dirs.pop(0)
        try:
            shutil.rmtree(victim)
        except FileNotFoundError:
            continue
        removed.append(victim.name)
    return removed


def prune_old_loop_artifacts() -> list[str]:
    pattern = re.compile(r"^loop-(\d+)\.(jsonl|stderr\.log|prompt\.md|last\.txt)$")
    by_loop: dict[int, list[Path]] = {}
    for path in RUN_DIR.iterdir():
        match = pattern.match(path.name)
        if not match:
            continue
        loop_number = int(match.group(1))
        by_loop.setdefault(loop_number, []).append(path)
    keep = set(sorted(by_loop.keys())[-LOOP_RETENTION_COUNT:])
    removed: list[str] = []
    for loop_number, paths in by_loop.items():
        if loop_number in keep:
            continue
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            removed.append(path.name)
    return removed


def probe_provider() -> tuple[bool, str]:
    request = urllib_request.Request(PROVIDER_MODELS_URL, headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return True, "reachable-non-json"
    ids: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        for item in payload["data"]:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
    if ids and "qwen3-coder-next:q8_0" not in ids:
        return False, "model_missing:qwen3-coder-next:q8_0"
    return True, f"reachable models={len(ids) if ids else 'unknown'}"


def observe_closure() -> dict[str, Any]:
    result = subprocess.run(
        [PYTHON_BIN, str(CLOSURE_SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout.strip():
        STATE_JSON.write_text(result.stdout, encoding="utf-8")
    if not STATE_JSON.is_file():
        raise RuntimeError(f"closure gate did not emit state (exit={result.returncode} stderr={result.stderr.strip()!r})")
    payload = json.loads(STATE_JSON.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("closure state is not a JSON object")
    return payload


def render_prompt(loop_id: int, last_exit: int, state: dict[str, Any]) -> Path:
    prompt_path = RUN_DIR / f"loop-{loop_id}.prompt.md"
    task = TASK_FILE.read_text(encoding="utf-8")
    plan = PLAN_FILE.read_text(encoding="utf-8")
    pending = state.get("pending_abs_ids") or []
    checks = state.get("checks") or []
    pending_lines = []
    for check in checks:
        if check.get("ok"):
            continue
        pending_lines.append(
            f"- {check.get('label')}: {check.get('detail')} ({check.get('path')})"
        )

    text = "\n".join(
        [
            task.rstrip(),
            "",
            "Supervisor context:",
            f"- overwatch loop: {loop_id}",
            f"- previous codexliz exit code: {last_exit}",
            f"- closure gate script: {CLOSURE_SCRIPT}",
            "- pending ABS ids: " + (", ".join(str(item) for item in pending) if pending else "none"),
            f"- completion root: {COMPLETION_ROOT}",
            "",
            "Current pending checks:",
            "\n".join(pending_lines) if pending_lines else "- none",
            "",
            "Execution plan:",
            plan.rstrip(),
            "",
            f"Before you claim completion, rerun `python3 {CLOSURE_SCRIPT}` and verify `closure_done` is true.",
            "",
        ]
    )
    prompt_path.write_text(text, encoding="utf-8")
    return prompt_path


def stat_snapshot(paths: list[Path]) -> dict[str, tuple[int, int]]:
    snap: dict[str, tuple[int, int]] = {}
    for path in paths:
        if path.exists():
            stat = path.stat()
            snap[str(path)] = (int(stat.st_size), int(stat.st_mtime))
    return snap


def completion_snapshot() -> dict[str, tuple[int, int]]:
    paths: list[Path] = []
    if COMPLETION_ROOT.exists():
        for path in sorted(COMPLETION_ROOT.iterdir()):
            if path.name == "_inputs":
                continue
            if path.is_file():
                paths.append(path)
    return stat_snapshot(paths)


def pass0_missing() -> list[str]:
    return [name for name in PASS0_ARTIFACTS if not (COMPLETION_ROOT / name).is_file()]


def pass0_start_missing() -> list[str]:
    return [name for name in PASS0_START_ARTIFACTS if not (COMPLETION_ROOT / name).is_file()]


def state_signature(state: dict[str, Any]) -> str:
    payload = {
        "closure_done": bool(state.get("closure_done")),
        "pending_abs_ids": list(state.get("pending_abs_ids") or []),
        "pending_check_keys": list(state.get("pending_check_keys") or []),
        "checks": [
            {
                "key": str(check.get("key") or ""),
                "ok": bool(check.get("ok")),
                "detail": str(check.get("detail") or ""),
            }
            for check in (state.get("checks") or [])
            if isinstance(check, dict)
        ],
    }
    return json.dumps(payload, sort_keys=True)


def pass0_substance_pending(state: dict[str, Any]) -> list[str]:
    pending: list[str] = []
    for check in (state.get("checks") or []):
        if not isinstance(check, dict):
            continue
        key = str(check.get("key") or "")
        if key in PASS0_SUBSTANCE_KEYS and not bool(check.get("ok")):
            pending.append(key)
    return pending


def pass0_start_substance_pending(state: dict[str, Any]) -> list[str]:
    pending: list[str] = []
    for check in (state.get("checks") or []):
        if not isinstance(check, dict):
            continue
        key = str(check.get("key") or "")
        if key in PASS0_START_SUBSTANCE_KEYS and not bool(check.get("ok")):
            pending.append(key)
    return pending


def sweep_stale_worker_groups() -> list[str]:
    result = subprocess.run(
        [PS_BIN, "-eo", "pid,pgid,args"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    stale: list[str] = []
    killed_pgids: set[int] = set()
    pattern = re.compile(r"absolute-audit-codexliz-overwatch/([^/]+)/loop-\d+\.last\.txt")
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        _pid_text, pgid_text, args = parts
        if "codexliz exec" not in args or "absolute-audit-codexliz-overwatch/" not in args:
            continue
        match = pattern.search(args)
        if not match:
            continue
        run_id = match.group(1)
        if run_id == RUN_ID:
            continue
        try:
            pgid = int(pgid_text)
        except ValueError:
            continue
        if pgid in killed_pgids or pgid == os.getpid():
            continue
        kill_process_group(pgid)
        killed_pgids.add(pgid)
        stale.append(f"{run_id}:{pgid}")
    return stale


def kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGINT)
    except ProcessLookupError:
        return
    except PermissionError:
        return
    time.sleep(2)
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        return
    time.sleep(5)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def launch_worker(loop_id: int, prompt_path: Path) -> tuple[subprocess.Popen[str], Path, Path, Path]:
    jsonl_path = RUN_DIR / f"loop-{loop_id}.jsonl"
    stderr_path = RUN_DIR / f"loop-{loop_id}.stderr.log"
    last_path = RUN_DIR / f"loop-{loop_id}.last.txt"

    env = os.environ.copy()
    env["CODEXLIZ_MODEL"] = "qwen3-coder-next:q8_0"
    env["CODEXLIZ_MODEL_GENERAL"] = "qwen3-coder-next:q8_0"
    env["CODEXLIZ_MODEL_CODER"] = "qwen3-coder-next:q8_0"
    env["CODEXLIZ_COMPLETION_POLICY_ENABLED"] = "0"
    env["CODEXLIZ_TRANSPORT_TRACE_INTERVAL_SECONDS"] = os.environ.get("CODEXLIZ_TRANSPORT_TRACE_INTERVAL_SECONDS", "15")
    env["CODEXLIZ_TRANSPORT_RETRY_INTERVAL_SECONDS"] = os.environ.get("CODEXLIZ_TRANSPORT_RETRY_INTERVAL_SECONDS", "15")

    stdin_handle = prompt_path.open("r", encoding="utf-8")
    stdout_handle = jsonl_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")

    command = [
        TIMEOUT_BIN,
        "--signal=INT",
        "--kill-after=60s",
        f"{ITERATION_TIMEOUT_SECONDS}s",
        CODEXLIZ_BIN,
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "-s",
        "danger-full-access",
        "-C",
        str(ROOT),
        "--add-dir",
        "/docker/chummercomplete",
        "--add-dir",
        "/docker/EA",
        "--add-dir",
        "/docker/chummer5a",
        "--add-dir",
        "/docker/fleet",
        "--add-dir",
        "/docker/fleet/repos",
        "--add-dir",
        "/home/tibor",
        "-o",
        str(last_path),
        "-",
    ]

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=stdin_handle,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        start_new_session=True,
        env=env,
    )

    stdin_handle.close()
    stdout_handle.close()
    stderr_handle.close()
    return process, jsonl_path, stderr_path, last_path


def supervise_worker(loop_id: int, process: subprocess.Popen[str], jsonl_path: Path, stderr_path: Path, last_path: Path) -> int:
    watched_paths = [jsonl_path, stderr_path, last_path]
    last_snapshot = stat_snapshot(watched_paths)
    last_change_time = time.time()
    last_observe_time = 0.0
    loop_start = time.time()
    last_material_progress_time = loop_start
    last_completion_snapshot = completion_snapshot()
    last_state_signature = ""
    last_closure_poll_time = 0.0

    while True:
        exit_code = process.poll()
        if exit_code is not None:
            return exit_code

        now = time.time()
        current_snapshot = stat_snapshot(watched_paths)
        if current_snapshot != last_snapshot:
            last_snapshot = current_snapshot
            last_change_time = now

        if now - last_observe_time >= HEARTBEAT_SECONDS:
            summary = ", ".join(
                f"{Path(path).name}:{size}"
                for path, (size, _mtime) in sorted(current_snapshot.items())
            ) or "no-artifacts-yet"
            write_ooda("observe", f"loop={loop_id} worker_alive artifacts={summary}")
            log(f"loop={loop_id} worker_alive artifacts={summary}")
            write_health("running", loop_id, worker_pid=process.pid, note=summary)
            last_observe_time = now

        oversized = [
            f"{Path(path).name}:{size}"
            for path, (size, _mtime) in sorted(current_snapshot.items())
            if size > ACTIVE_ARTIFACT_MAX_BYTES
        ]
        if oversized:
            detail = ",".join(oversized)
            write_ooda("act", f"loop={loop_id} artifact_growth_exceeded files={detail}; terminating worker")
            log(f"loop={loop_id} artifact_growth_exceeded files={detail}; terminating worker")
            kill_process_group(process.pid)
            return process.wait(timeout=90)

        if now - last_closure_poll_time >= MIDLOOP_CLOSURE_POLL_SECONDS:
            state = observe_closure()
            current_state_signature = state_signature(state)
            current_completion_snapshot = completion_snapshot()
            if current_state_signature != last_state_signature or current_completion_snapshot != last_completion_snapshot:
                last_material_progress_time = now
                last_state_signature = current_state_signature
                last_completion_snapshot = current_completion_snapshot
            if state.get("closure_done"):
                write_ooda("act", f"loop={loop_id} closure_done=true midloop; terminating worker")
                log(f"loop={loop_id} closure_done=true midloop; terminating worker")
                kill_process_group(process.pid)
                return process.wait(timeout=90)
            last_closure_poll_time = now

        if now - loop_start >= PASS0_START_SECONDS:
            state = observe_closure()
            missing_start = pass0_start_missing()
            pending_start = pass0_start_substance_pending(state)
            if missing_start or pending_start:
                detail_parts: list[str] = []
                if missing_start:
                    detail_parts.append(f"missing={','.join(missing_start)}")
                if pending_start:
                    detail_parts.append(f"pending={','.join(pending_start)}")
                detail = " ".join(detail_parts)
                write_ooda("act", f"loop={loop_id} pass0_start_missed {detail}; terminating worker")
                log(f"loop={loop_id} pass0_start_missed {detail}; terminating worker")
                kill_process_group(process.pid)
                return process.wait(timeout=90)

        if now - loop_start >= PASS0_DEADLINE_SECONDS:
            state = observe_closure()
            missing_pass0 = pass0_missing()
            pending_substance = pass0_substance_pending(state)
            if missing_pass0 or pending_substance:
                detail_parts: list[str] = []
                if missing_pass0:
                    detail_parts.append(f"missing={','.join(missing_pass0)}")
                if pending_substance:
                    detail_parts.append(f"pending={','.join(pending_substance)}")
                detail = " ".join(detail_parts)
                write_ooda("act", f"loop={loop_id} pass0_deadline_missed {detail}; terminating worker")
                log(f"loop={loop_id} pass0_deadline_missed {detail}; terminating worker")
                kill_process_group(process.pid)
                return process.wait(timeout=90)

        if now - last_material_progress_time >= MATERIAL_PROGRESS_SECONDS:
            write_ooda("act", f"loop={loop_id} material_progress_stalled seconds={MATERIAL_PROGRESS_SECONDS}; terminating worker")
            log(f"loop={loop_id} material_progress_stalled seconds={MATERIAL_PROGRESS_SECONDS}; terminating worker")
            kill_process_group(process.pid)
            return process.wait(timeout=90)

        if now - last_change_time >= STALL_SECONDS:
            write_ooda("act", f"loop={loop_id} stall_detected seconds={STALL_SECONDS}; terminating worker")
            log(f"loop={loop_id} stall_detected seconds={STALL_SECONDS}; terminating worker")
            kill_process_group(process.pid)
            return process.wait(timeout=90)

        time.sleep(5)


def main() -> int:
    ensure_dirs()
    stale = sweep_stale_worker_groups()
    pruned_runs = prune_old_run_dirs()
    capture_git_baseline()
    log(f"starting absolute-audit codexliz overwatch run_id={RUN_ID}")
    write_ooda("observe", "supervisor started")
    write_health("starting", 0, failure_streak=0, note="supervisor started")
    if stale:
        log(f"swept stale codexliz workers before start: {', '.join(stale)}")
        write_ooda("act", f"swept stale codexliz workers before start: {', '.join(stale)}")
    if pruned_runs:
        log(f"pruned old run dirs before start: {', '.join(pruned_runs)}")
        write_ooda("act", f"pruned old run dirs before start: {', '.join(pruned_runs)}")

    loop_id = 0
    last_exit = 0
    failure_streak = 0

    while True:
        write_ooda("observe", "refreshing absolute-audit closure state")
        state = observe_closure()
        if state.get("closure_done"):
            log("closure gate is green; stopping overwatch")
            write_ooda("observe", "closure_done=true")
            write_health("complete", loop_id, state, last_exit=last_exit, failure_streak=failure_streak, note="closure gate green")
            return 0

        pending = state.get("pending_abs_ids") or []
        write_ooda("orient", "reviewed pending ABS ids and failing closure checks")
        log(f"pending closure remains; preparing codexliz loop={loop_id} pending={','.join(str(item) for item in pending)}")
        write_health("prelaunch", loop_id, state, last_exit=last_exit, failure_streak=failure_streak, note="preparing worker loop")
        stale = sweep_stale_worker_groups()
        if stale:
            log(f"swept stale codexliz workers before launch: {', '.join(stale)}")
            write_ooda("act", f"swept stale codexliz workers before launch: {', '.join(stale)}")
        provider_ok, provider_detail = probe_provider()
        if not provider_ok:
            failure_streak += 1
            backoff = backoff_seconds(failure_streak)
            log(f"provider preflight failed loop={loop_id} detail={provider_detail} backoff={backoff}s")
            write_ooda("decide", f"provider_preflight_failed detail={provider_detail} backoff={backoff}s")
            write_health("provider-unhealthy", loop_id, state, last_exit=98, failure_streak=failure_streak, note=provider_detail)
            time.sleep(backoff)
            continue

        prompt_path = render_prompt(loop_id, last_exit, state)
        pre_state_signature = state_signature(state)
        pre_completion_snapshot = completion_snapshot()

        write_ooda("decide", "launch codexliz exec with JSON logging and qwen3-coder-next:q8_0 preference")
        log(f"launching codexliz loop={loop_id} timeout={ITERATION_TIMEOUT_SECONDS}s")
        process, jsonl_path, stderr_path, last_path = launch_worker(loop_id, prompt_path)
        write_health("launching", loop_id, state, worker_pid=process.pid, last_exit=last_exit, failure_streak=failure_streak, note="worker launched")
        last_exit = supervise_worker(loop_id, process, jsonl_path, stderr_path, last_path)
        write_ooda("act", f"codexliz loop exited with code {last_exit}")
        log(f"codexliz loop={loop_id} exited code={last_exit}")

        post_state = observe_closure()
        post_state_signature = state_signature(post_state)
        post_completion_snapshot = completion_snapshot()
        made_progress = pre_state_signature != post_state_signature or pre_completion_snapshot != post_completion_snapshot
        if (
            last_exit == 0
            and not post_state.get("closure_done")
            and not made_progress
        ):
            last_exit = 90
            write_ooda("act", f"loop={loop_id} no_machine_state_progress detected; escalating as failure")
            log(f"loop={loop_id} no_machine_state_progress detected; escalating as failure")
        if made_progress:
            failure_streak = 0
        else:
            failure_streak += 1
        append_loop_history(
            {
                "ts": now_iso(),
                "run_id": RUN_ID,
                "loop_id": loop_id,
                "exit_code": last_exit,
                "made_progress": made_progress,
                "failure_streak": failure_streak,
                "pending_count": len(post_state.get("pending_check_keys") or []),
                "closure_done": bool(post_state.get("closure_done")),
            }
        )
        pruned_loop_files = prune_old_loop_artifacts()
        if pruned_loop_files:
            log(f"pruned old loop artifacts after loop={loop_id}: {', '.join(pruned_loop_files[:12])}{'...' if len(pruned_loop_files) > 12 else ''}")
            write_ooda("act", f"pruned old loop artifacts after loop={loop_id}: count={len(pruned_loop_files)}")
        pruned_runs = prune_old_run_dirs()
        if pruned_runs:
            log(f"pruned old run dirs after loop={loop_id}: {', '.join(pruned_runs)}")
            write_ooda("act", f"pruned old run dirs after loop={loop_id}: {', '.join(pruned_runs)}")
        if post_state.get("closure_done"):
            log("closure gate is green after loop exit; stopping overwatch")
            write_ooda("observe", "closure_done=true after loop exit")
            write_health("complete", loop_id, post_state, last_exit=last_exit, failure_streak=failure_streak, note="closure gate green after loop exit")
            return 0
        sleep_seconds = SLEEP_SECONDS if made_progress else backoff_seconds(failure_streak)
        write_health("sleeping", loop_id, post_state, last_exit=last_exit, failure_streak=failure_streak, note=f"sleep={sleep_seconds}s progress={made_progress}")

        loop_id += 1
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
