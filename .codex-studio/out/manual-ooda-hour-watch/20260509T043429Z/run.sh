#!/usr/bin/env bash
set -euo pipefail
RUN_DIR="$1"
SERVICE="codexliz-absolute-audit-overwatch.service"
HEALTH="/docker/chummercomplete/chummer.run-services/.codex-studio/out/absolute-audit-codexliz-overwatch/health.json"
CURRENT_LINK="/docker/chummercomplete/chummer.run-services/.codex-studio/out/absolute-audit-codexliz-overwatch/current"
python3 - "$RUN_DIR" "$SERVICE" "$HEALTH" "$CURRENT_LINK" <<'PY'
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
run_dir = Path(sys.argv[1])
service = sys.argv[2]
health_path = Path(sys.argv[3])
current_link = Path(sys.argv[4])
ooda = run_dir / ooda.jsonl
status = run_dir / status.json
summary = run_dir / summary.json
watch_log = run_dir / watch.log
start = time.time()
end = start + 3600
poll = 60
last_restart = 0.0
restarts = 0
stale_threshold = 600
worker_missing_threshold = 120
restart_cooldown = 300
prev = {}

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace(+00:00,Z)

def parse_iso(text):
    if not text: return None
    try:
        if text.endswith(Z): text = text[:-1] + +00:00
        return datetime.fromisoformat(text)
    except Exception:
        return None

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2) + n, encoding=utf-8)

def append_jsonl(path, payload):
    with path.open(a, encoding=utf-8) as h:
        h.write(json.dumps(payload) + n)

def log(msg):
    with watch_log.open(a, encoding=utf-8) as h:
        h.write(f"{now_iso()} {msg}\n")

def service_state():
    r = subprocess.run([/usr/bin/systemctl,--user,is-active,service], text=True, capture_output=True, check=False)
    return (r.stdout or r.stderr or ).strip() or unknown

def load_json(path):
    if not path.is_file(): return None
    try:
        obj = json.loads(path.read_text(encoding=utf-8))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None

def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

def restart(reason):
    global last_restart, restarts
    r = subprocess.run([/usr/bin/systemctl,--user,restart,service], text=True, capture_output=True, check=False)
    ok = r.returncode == 0
    if ok:
        last_restart = time.time()
        restarts += 1
    detail = (r.stderr or r.stdout or ).strip() or reason
    return ok, detail

iteration = 0
while True:
    health = load_json(health_path) or {}
    closure = load_json(current_link / closure-status.json) if current_link.exists() else None
    state = service_state()
    worker_pid = health.get(worker_pid)
    worker_alive = pid_alive(worker_pid)
    pending_count = None
    if isinstance(closure, dict) and isinstance(closure.get(pending_check_keys), list):
        pending_count = len(closure[pending_check_keys])
    health_ts = parse_iso(str(health.get(ts) or ))
    health_age = int((datetime.now(timezone.utc) - health_ts).total_seconds()) if health_ts else None
    action = none
    reason = healthy_or_supervised
    act_ok = True
    detail = 
    cooldown_open = (time.time() - last_restart) < restart_cooldown if last_restart else False
    if state != active:
        if cooldown_open:
            action, reason = wait, restart_cooldown_service_inactive
        else:
            action, reason = restart, service_inactive
    elif not health:
        if cooldown_open:
            action, reason = wait, restart_cooldown_health_missing
        else:
            action, reason = restart, health_missing
    elif health_age is not None and health_age > stale_threshold:
        if cooldown_open:
            action, reason = wait, restart_cooldown_health_stale
        else:
            action, reason = restart, fhealth_stale_{health_age}s
    elif str(health.get(status) or ) in {running,launching,prelaunch} and not worker_alive:
        if health_age is None or health_age > worker_missing_threshold:
            if cooldown_open:
                action, reason = wait, restart_cooldown_worker_missing
            else:
                action, reason = restart, worker_missing_while_running
    if action == restart:
        act_ok, detail = restart(reason)
    record = {
        ts: now_iso(),
        iteration: iteration,
        observe: {
            service_state: state,
            worker_alive: worker_alive,
            run_id: health.get(run_id),
            loop_id: health.get(loop_id),
            pending_count: pending_count,
            health_status: health.get(status),
            health_age_seconds: health_age,
        },
        orient: {
            changed_run_id: prev.get(run_id) != health.get(run_id),
            changed_loop_id: prev.get(loop_id) != health.get(loop_id),
            changed_pending_count: prev.get(pending_count) != pending_count,
            changed_note: prev.get(note) != health.get(note),
            failure_streak: health.get(failure_streak),
        },
        decide: {action: action, reason: reason},
        act: {ok: act_ok, detail: detail},
    }
    append_jsonl(ooda, record)
    write_json(status, {
        ts: now_iso(),
        iteration: iteration,
        service_state: state,
        worker_alive: worker_alive,
        run_id: health.get(run_id),
        loop_id: health.get(loop_id),
        pending_count: pending_count,
        health_status: health.get(status),
        failure_streak: health.get(failure_streak),
        last_action: action,
        last_reason: reason,
        restarts: restarts,
    })
    log(f"iteration={iteration} state={state} worker_alive={worker_alive} pending={pending_count} action={action} reason={reason}")
    prev = {run_id: health.get(run_id), loop_id: health.get(loop_id), pending_count: pending_count, note: health.get(note)}
    iteration += 1
    if time.time() >= end:
        break
    time.sleep(poll)
write_json(summary, {
    ts: now_iso(),
    duration_seconds: int(time.time() - start),
    iterations: iteration,
    restarts: restarts,
    final_status: load_json(status),
})
log(f"completed iterations={iteration} restarts={restarts}")
PY
