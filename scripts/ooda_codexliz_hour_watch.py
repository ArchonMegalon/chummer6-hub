#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/docker/chummercomplete/chummer.run-services")
OVERWATCH_ROOT = ROOT / ".codex-studio" / "out" / "absolute-audit-codexliz-overwatch"
WATCH_ROOT = ROOT / ".codex-studio" / "out" / "codexliz-ooda-hour-watch"
OVERWATCH_CURRENT_LINK = OVERWATCH_ROOT / "current"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = WATCH_ROOT / RUN_ID
CURRENT_LINK = WATCH_ROOT / "current"
OODA_JSONL = RUN_DIR / "ooda.jsonl"
WATCH_LOG = RUN_DIR / "watch.log"
STATUS_JSON = RUN_DIR / "status.json"
SUMMARY_JSON = RUN_DIR / "summary.json"

SYSTEMCTL = "/usr/bin/systemctl"
SERVICE = os.environ.get("CODEXLIZ_OODA_TARGET_SERVICE", "codexliz-absolute-audit-overwatch.service")
POLL_SECONDS = int(os.environ.get("CODEXLIZ_OODA_POLL_SECONDS", "60"))
DURATION_SECONDS = int(os.environ.get("CODEXLIZ_OODA_DURATION_SECONDS", "3600"))
HEALTH_STALE_SECONDS = int(os.environ.get("CODEXLIZ_OODA_HEALTH_STALE_SECONDS", "600"))
WORKER_MISSING_SECONDS = int(os.environ.get("CODEXLIZ_OODA_WORKER_MISSING_SECONDS", "120"))
RESTART_COOLDOWN_SECONDS = int(os.environ.get("CODEXLIZ_OODA_RESTART_COOLDOWN_SECONDS", "300"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    value = text.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def log(message: str) -> None:
    line = f"{now_iso()} {message}"
    with WATCH_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def ensure_dirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    WATCH_ROOT.mkdir(parents=True, exist_ok=True)
    if CURRENT_LINK.exists() or CURRENT_LINK.is_symlink():
        CURRENT_LINK.unlink()
    CURRENT_LINK.symlink_to(RUN_DIR)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def service_state() -> str:
    result = subprocess.run(
        [SYSTEMCTL, "--user", "is-active", SERVICE],
        text=True,
        capture_output=True,
        check=False,
    )
    return (result.stdout or result.stderr or "").strip() or "unknown"


def restart_service(reason: str) -> tuple[bool, str]:
    result = subprocess.run(
        [SYSTEMCTL, "--user", "restart", SERVICE],
        text=True,
        capture_output=True,
        check=False,
    )
    detail = (result.stderr or result.stdout or "").strip() or reason
    return result.returncode == 0, detail


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def snapshot() -> dict[str, Any]:
    health = load_json(OVERWATCH_ROOT / "health.json")
    current = OVERWATCH_CURRENT_LINK.resolve() if OVERWATCH_CURRENT_LINK.exists() else None
    closure = load_json(current / "closure-status.json") if current else None
    worker_pid = None
    if health:
        value = health.get("worker_pid")
        if isinstance(value, int):
            worker_pid = value
        elif isinstance(value, str) and value.isdigit():
            worker_pid = int(value)
    pending_count = None
    if closure:
        pending = closure.get("pending_check_keys")
        if isinstance(pending, list):
            pending_count = len(pending)
    return {
        "ts": now_iso(),
        "service_state": service_state(),
        "current_run_dir": str(current) if current else "",
        "health": health,
        "closure": closure,
        "worker_alive": pid_alive(worker_pid),
        "pending_count": pending_count,
    }


def summarize_orientation(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    health = current.get("health") or {}
    health_ts = parse_iso(str(health.get("ts") or ""))
    age_seconds = None
    if health_ts is not None:
        age_seconds = int((datetime.now(timezone.utc) - health_ts).total_seconds())
    result = {
        "run_id": health.get("run_id"),
        "loop_id": health.get("loop_id"),
        "status": health.get("status"),
        "failure_streak": health.get("failure_streak"),
        "pending_count": current.get("pending_count"),
        "worker_alive": current.get("worker_alive"),
        "health_age_seconds": age_seconds,
        "changed": {},
    }
    if previous:
        prev_health = previous.get("health") or {}
        result["changed"] = {
            "run_id": prev_health.get("run_id") != health.get("run_id"),
            "loop_id": prev_health.get("loop_id") != health.get("loop_id"),
            "status": prev_health.get("status") != health.get("status"),
            "pending_count": previous.get("pending_count") != current.get("pending_count"),
            "note": prev_health.get("note") != health.get("note"),
        }
    return result


def decide_action(current: dict[str, Any], previous_restart_ts: float | None) -> tuple[str, str]:
    health = current.get("health") or {}
    state = current.get("service_state")
    worker_alive = bool(current.get("worker_alive"))
    health_ts = parse_iso(str(health.get("ts") or ""))
    health_age_seconds = None
    if health_ts is not None:
        health_age_seconds = int((datetime.now(timezone.utc) - health_ts).total_seconds())
    cooldown_open = previous_restart_ts is not None and (time.time() - previous_restart_ts) < RESTART_COOLDOWN_SECONDS

    if state != "active":
        return ("restart", "service_inactive") if not cooldown_open else ("wait", "restart_cooldown_service_inactive")
    if not health:
        return ("restart", "health_missing") if not cooldown_open else ("wait", "restart_cooldown_health_missing")
    if health_age_seconds is not None and health_age_seconds > HEALTH_STALE_SECONDS:
        return ("restart", f"health_stale_{health_age_seconds}s") if not cooldown_open else ("wait", "restart_cooldown_health_stale")
    if str(health.get("status") or "") in {"running", "launching", "prelaunch"} and not worker_alive:
        if health_age_seconds is None or health_age_seconds > WORKER_MISSING_SECONDS:
            return ("restart", "worker_missing_while_running") if not cooldown_open else ("wait", "restart_cooldown_worker_missing")
    return ("none", "healthy_or_supervised")


def main() -> int:
    ensure_dirs()
    start = time.time()
    end = start + DURATION_SECONDS
    iteration = 0
    restarts = 0
    previous: dict[str, Any] | None = None
    last_restart_ts: float | None = None

    while True:
        current = snapshot()
        orient = summarize_orientation(current, previous)
        action, reason = decide_action(current, last_restart_ts)
        act_result = {"action": action, "reason": reason, "ok": True, "detail": ""}
        if action == "restart":
            ok, detail = restart_service(reason)
            act_result["ok"] = ok
            act_result["detail"] = detail
            restarts += 1 if ok else 0
            last_restart_ts = time.time() if ok else last_restart_ts
        record = {
            "ts": now_iso(),
            "iteration": iteration,
            "observe": {
                "service_state": current.get("service_state"),
                "current_run_dir": current.get("current_run_dir"),
                "worker_alive": current.get("worker_alive"),
                "pending_count": current.get("pending_count"),
            },
            "orient": orient,
            "decide": {"action": action, "reason": reason},
            "act": act_result,
        }
        append_jsonl(OODA_JSONL, record)
        log(f"iteration={iteration} service={current.get('service_state')} worker_alive={current.get('worker_alive')} pending={current.get('pending_count')} action={action} reason={reason}")
        write_json(
            STATUS_JSON,
            {
                "ts": now_iso(),
                "iteration": iteration,
                "restarts": restarts,
                "service_state": current.get("service_state"),
                "current_run_dir": current.get("current_run_dir"),
                "worker_alive": current.get("worker_alive"),
                "pending_count": current.get("pending_count"),
                "last_action": action,
                "last_reason": reason,
            },
        )

        previous = current
        iteration += 1
        if time.time() >= end:
            break
        sleep_for = min(POLL_SECONDS, max(1, int(end - time.time())))
        time.sleep(sleep_for)

    write_json(
        SUMMARY_JSON,
        {
            "ts": now_iso(),
            "duration_seconds": DURATION_SECONDS,
            "poll_seconds": POLL_SECONDS,
            "iterations": iteration,
            "restarts": restarts,
            "final_snapshot": previous or {},
        },
    )
    log(f"completed duration_seconds={DURATION_SECONDS} iterations={iteration} restarts={restarts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
