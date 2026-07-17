#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import host_workload_runtime_health_contract as contract
from ea_live_ops_receipt_hygiene import contains_secretish_key, json_from_text, stderr_summary


DEFAULT_OUTPUT_PATH = REPO_ROOT / ".codex-studio" / "published" / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json"
VERIFY_SCRIPT = SCRIPT_DIR / "verify_host_workload_guardrails.py"
QBIT_LOG_PATH = Path("/docker/arr-v2/qbittorrent-vpn/qBittorrent/logs/qbittorrent.log")
WATCHDOG_UNIT = "rclone-mount-watchdog.service"
RCLONE_RC_ADDR = "127.0.0.1:5572"
INTERNXT_RCLONE_RC_ADDR = "127.0.0.1:5574"
MEDIA_CACHE_BUDGET_PATH = Path("/etc/systemd/system/media-cache-guard.service.d/10-budget.conf")
PLEX_INTERNXT_MIRROR_UNIT = "plex-internxt-mirror.service"
PLEX_INTERNXT_MIRROR_STATUS_PATH = Path("/run/plex-internxt-mirror/status.json")
PLEX_INTERNXT_MIRROR_JOURNAL_LINES = 400
PLEX_INTERNXT_MIRROR_STALE_SECONDS = 1800
PLEX_INTERNXT_MIRROR_JOURNAL_ETA_SUPPRESS_SECONDS = 120
INTERNXT_CACHE_HEADROOM_GIB = 4.0
CONTRACT_NAME = "chummer.host_workload_runtime_health.v1"
SOURCE_ID = "script:materialize_host_workload_runtime_health.py"
SOURCE_RUNTIME = "host_workload.runtime_health"
CACHE_MODE_LABELS = {
    0: "off",
    1: "minimal",
    2: "writes",
    3: "full",
}
LOCAL_TZ = datetime.now().astimezone().tzinfo or UTC
PLEX_INTERNXT_MIRROR_PHASES: tuple[tuple[str, str, Path], ...] = (
    ("movies", "Movies", Path("/mnt/pcloud/PLEX/Movies")),
    ("tv", "TV", Path("/mnt/pcloud/PLEX/TV")),
    ("requested_movies", "Requested Movies", Path("/mnt/pcloud/PLEX/Requested/Movies")),
    ("requested_tv", "Requested TV", Path("/mnt/pcloud/PLEX/Requested/TV")),
    ("requested_unsorted", "Requested Unsorted", Path("/mnt/pcloud/PLEX/Requested/Unsorted")),
    ("requested_inbox", "Requested Inbox", Path("/mnt/pcloud/PLEX/Requested/_inbox")),
)
PLEX_INTERNXT_MIRROR_MOVIES_DEST_ROOT = Path("/mnt/internxt/PLEX/Movies")
PLEX_INTERNXT_MIRROR_TV_DEST_ROOT = Path("/mnt/internxt/PLEX/TV")
PLEX_INTERNXT_MIRROR_PROGRESS_RE = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}).*?"
    r"(?P<label>Movies|TV|Requested Movies|Requested TV|Requested Unsorted|Requested Inbox) "
    r"progress (?P<current>\d+)/(?P<total>\d+): (?P<name>.+?) -> (?P<detail>.+)$"
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(cmd: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


def _run_guardrail_verifier(timeout_seconds: float) -> tuple[int, dict[str, Any], str, str]:
    completed = _run([sys.executable, str(VERIFY_SCRIPT)], timeout_seconds)
    payload = json_from_text(completed.stdout)
    return completed.returncode, payload, completed.stdout, completed.stderr


def _run_rclone_vfs_stats(rc_addr: str, timeout_seconds: float) -> tuple[int, dict[str, Any], str, str]:
    completed = _run(["rclone", "rc", "--rc-addr", rc_addr, "vfs/stats"], timeout_seconds)
    payload = json_from_text(completed.stdout)
    return completed.returncode, payload, completed.stdout, completed.stderr


def _run_watchdog_journal(lines: int, timeout_seconds: float) -> tuple[int, str, str]:
    completed = _run(["journalctl", "-u", WATCHDOG_UNIT, "-n", str(lines), "--no-pager"], timeout_seconds)
    return completed.returncode, completed.stdout, completed.stderr


def _run_systemctl_show(unit: str, timeout_seconds: float) -> tuple[int, dict[str, str], str, str]:
    completed = _run(
        [
            "systemctl",
            "show",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "Result",
            "-p",
            "ExecMainStartTimestamp",
            "-p",
            "ExecMainExitTimestamp",
            "-p",
            "ExecMainStatus",
            unit,
        ],
        timeout_seconds,
    )
    payload: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return completed.returncode, payload, completed.stdout, completed.stderr


def _run_mirror_journal(lines: int, timeout_seconds: float) -> tuple[int, str, str]:
    completed = _run(["journalctl", "-u", PLEX_INTERNXT_MIRROR_UNIT, "-n", str(lines), "--no-pager"], timeout_seconds)
    return completed.returncode, completed.stdout, completed.stderr


def _read_qbittorrent_log_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "log_exists": False,
            "current_session_started_at": "",
            "fast_resume_rejected_count": 0,
            "recent_storage_error_count": 0,
            "restored_torrent_count": 0,
        }
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_index = 0
    for index, line in enumerate(lines):
        if "qBittorrent v" in line and " started. Process ID:" in line:
            start_index = index
    recent_lines = lines[start_index:] if lines else []
    current_session_started_at = ""
    if recent_lines:
        parts = recent_lines[0].split(" - ", 1)
        if parts:
            current_session_started_at = parts[0].split(") ", 1)[-1].strip()
    return {
        "log_exists": True,
        "current_session_started_at": current_session_started_at,
        "fast_resume_rejected_count": sum("fast resume rejected" in line for line in recent_lines),
        "recent_storage_error_count": sum("Socket not connected" in line for line in recent_lines),
        "restored_torrent_count": sum("Restored torrent." in line for line in recent_lines),
    }


def _recent_download_activity_count(save_path: str, lookback_minutes: int, timeout_seconds: float) -> int | None:
    path = Path(str(save_path or "").strip())
    if not path.exists():
        return None
    completed = _run(
        [
            "find",
            str(path),
            "-maxdepth",
            "2",
            "-type",
            "f",
            "-mmin",
            f"-{int(lookback_minutes)}",
            "-printf",
            ".",
        ],
        timeout_seconds,
    )
    if completed.returncode != 0:
        return None
    return len(completed.stdout)


def _watchdog_state(lines: str) -> dict[str, Any]:
    journal_lines = [line.strip() for line in str(lines or "").splitlines() if line.strip()]
    deferred_lines = [
        line
        for line in journal_lines
        if "mount namespace for /mnt/pcloud/PLEX is stale but Plex has active sessions -> deferring container restart" in line
    ]
    restart_lines = [
        line
        for line in journal_lines
        if "restarting stale namespace container plex" in line or "docker restart \"plex\"" in line
    ]
    return {
        "plex_restart_deferred": bool(deferred_lines),
        "last_deferred_line": deferred_lines[-1] if deferred_lines else "",
        "last_restart_line": restart_lines[-1] if restart_lines else "",
    }


def _cache_mode_label(value: Any) -> str:
    if isinstance(value, bool):
        return "unknown"
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return CACHE_MODE_LABELS.get(integer, str(integer))


def _media_cache_reserve_target_gib(path: Path) -> int | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Environment=MEDIA_CACHE_MIN_FREE_GIB="):
            raw = line.split("=", 2)[-1].strip()
            try:
                return int(raw)
            except ValueError:
                return None
    return None


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _parse_systemd_timestamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    parts = raw.split()
    if len(parts) < 3:
        return None
    try:
        return datetime.strptime(" ".join(parts[1:3]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def _parse_journal_timestamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(f"{datetime.now(LOCAL_TZ).year} {raw}", "%Y %b %d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def _is_datetime_like(value: Any) -> bool:
    return hasattr(value, "astimezone") and callable(getattr(value, "astimezone", None))


def _count_top_level_entries(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for child in path.iterdir() if child.is_dir() or child.is_file())
    except OSError:
        return 0


def _mirror_phase_totals() -> tuple[dict[str, int], int]:
    totals = {phase_key: _count_top_level_entries(path) for phase_key, _label, path in PLEX_INTERNXT_MIRROR_PHASES}
    return totals, sum(totals.values())


def _path_size_bytes(path: Path, timeout_seconds: float) -> int | None:
    if not path.exists():
        return None
    completed = _run(["du", "-sb", str(path)], timeout_seconds)
    if completed.returncode != 0:
        return None
    first_line = next((line for line in completed.stdout.splitlines() if line.strip()), "")
    if not first_line:
        return None
    raw = first_line.split("\t", 1)[0].strip().split(maxsplit=1)[0]
    try:
        return int(raw)
    except ValueError:
        return None


def _mirror_entry_paths(phase_key: str, current_name: str, current_detail: str) -> tuple[Path | None, Path | None]:
    name = str(current_name or "").strip()
    bucket = str(current_detail or "").strip()
    if not name:
        return None, None
    if phase_key == "movies":
        return Path("/mnt/pcloud/PLEX/Movies") / name, PLEX_INTERNXT_MIRROR_MOVIES_DEST_ROOT / bucket / name
    if phase_key == "tv":
        return Path("/mnt/pcloud/PLEX/TV") / name, PLEX_INTERNXT_MIRROR_TV_DEST_ROOT / bucket / name
    if phase_key == "requested_movies":
        return Path("/mnt/pcloud/PLEX/Requested/Movies") / name, PLEX_INTERNXT_MIRROR_MOVIES_DEST_ROOT / bucket / name
    if phase_key == "requested_tv":
        return Path("/mnt/pcloud/PLEX/Requested/TV") / name, PLEX_INTERNXT_MIRROR_TV_DEST_ROOT / bucket / name
    return None, None


def _load_status_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_invalid": True}
    return payload if isinstance(payload, dict) else {"_invalid": True}


def _build_plex_internxt_mirror_observation(timeout_seconds: float) -> dict[str, Any]:
    systemctl_returncode, systemctl_payload, _systemctl_stdout, systemctl_stderr = _run_systemctl_show(
        PLEX_INTERNXT_MIRROR_UNIT, timeout_seconds
    )
    journal_returncode, journal_stdout, journal_stderr = _run_mirror_journal(
        PLEX_INTERNXT_MIRROR_JOURNAL_LINES, timeout_seconds
    )
    status_payload = _load_status_json(PLEX_INTERNXT_MIRROR_STATUS_PATH)
    phase_totals, filesystem_overall_total = _mirror_phase_totals()
    phase_offsets: dict[str, int] = {}
    offset = 0
    for phase_key, _label, _path in PLEX_INTERNXT_MIRROR_PHASES:
        phase_offsets[phase_key] = offset
        offset += phase_totals.get(phase_key, 0)

    service_active_state = str(systemctl_payload.get("ActiveState") or "").strip().lower()
    service_sub_state = str(systemctl_payload.get("SubState") or "").strip().lower()
    service_result = str(systemctl_payload.get("Result") or "").strip().lower()
    service_start_dt = _parse_systemd_timestamp(systemctl_payload.get("ExecMainStartTimestamp", ""))
    service_exit_dt = _parse_systemd_timestamp(systemctl_payload.get("ExecMainExitTimestamp", ""))
    now_dt = datetime.now(UTC)
    progress_rows: list[dict[str, Any]] = []
    observation: dict[str, Any] = {
        "service_probe_status": "pass" if systemctl_returncode == 0 else "fail",
        "service_active_state": service_active_state or "unknown",
        "service_sub_state": service_sub_state or "unknown",
        "service_result": service_result or "unknown",
        "service_exec_main_status": str(systemctl_payload.get("ExecMainStatus") or "").strip(),
        "service_started_at": service_start_dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if service_start_dt
        else "",
        "service_exited_at": service_exit_dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if service_exit_dt
        else "",
        "status_file_path": str(PLEX_INTERNXT_MIRROR_STATUS_PATH),
        "status_file_present": bool(status_payload) and not bool(status_payload.get("_invalid")),
        "status_source": "none",
        "status": "unknown",
        "phase": "",
        "phase_label": "",
        "phase_current": 0,
        "phase_total": 0,
        "overall_current": 0,
        "overall_total": filesystem_overall_total,
        "current_name": "",
        "current_detail": "",
        "run_started_at": "",
        "updated_at": "",
        "note": "",
        "last_error": "",
        "exit_code": 0,
        "items_per_minute": None,
        "items_per_minute_source": "",
        "eta_seconds": None,
        "eta_at": "",
        "eta_suppressed_reason": "",
        "stale_seconds": None,
        "current_entry_source_bytes": None,
        "current_entry_dest_bytes": None,
        "current_entry_progress_ratio": None,
        "journal_accessible": journal_returncode == 0,
        "journal_progress_found": False,
        "phase_totals": phase_totals,
        "stderr_summary": stderr_summary("\n".join(item for item in (systemctl_stderr, journal_stderr) if str(item).strip())),
    }

    if status_payload.get("_invalid"):
        observation["status_source"] = "status_file_invalid"
        observation["note"] = "status_file_invalid"

    if observation["status_file_present"]:
        phase_key = str(status_payload.get("phase") or "").strip()
        phase_total = int(status_payload.get("phase_total") or 0)
        overall_total = int(status_payload.get("overall_total") or 0) or filesystem_overall_total
        observation.update(
            {
                "status_source": "status_file",
                "status": str(status_payload.get("status") or "").strip().lower() or "unknown",
                "phase": phase_key,
                "phase_label": str(status_payload.get("phase_label") or "").strip(),
                "phase_current": int(status_payload.get("phase_current") or 0),
                "phase_total": phase_total or phase_totals.get(phase_key, 0),
                "overall_current": int(status_payload.get("overall_current") or 0),
                "overall_total": overall_total,
                "current_name": str(status_payload.get("current_name") or "").strip(),
                "current_detail": str(status_payload.get("current_detail") or "").strip(),
                "run_started_at": str(status_payload.get("run_started_at") or "").strip(),
                "updated_at": str(status_payload.get("updated_at") or "").strip(),
                "note": str(status_payload.get("note") or "").strip(),
                "last_error": str(status_payload.get("last_error") or "").strip(),
                "exit_code": int(status_payload.get("exit_code") or 0),
            }
        )
    elif journal_returncode == 0:
        seen: set[tuple[str, str, int, int, str]] = set()
        for line in journal_stdout.splitlines():
            match = PLEX_INTERNXT_MIRROR_PROGRESS_RE.search(line)
            if not match:
                continue
            label = str(match.group("label")).strip()
            phase_key = next((key for key, known_label, _path in PLEX_INTERNXT_MIRROR_PHASES if known_label == label), "")
            timestamp_text = str(match.group("ts") or "").strip()
            row_key = (
                timestamp_text,
                label,
                int(match.group("current")),
                int(match.group("total")),
                str(match.group("name")).strip(),
            )
            if row_key in seen:
                continue
            seen.add(row_key)
            progress_rows.append(
                {
                    "timestamp": _parse_journal_timestamp(timestamp_text),
                    "phase": phase_key,
                    "phase_label": label,
                    "phase_current": int(match.group("current")),
                    "phase_total": int(match.group("total")),
                    "current_name": str(match.group("name")).strip(),
                    "current_detail": str(match.group("detail")).strip(),
                }
            )
        observation["journal_progress_found"] = bool(progress_rows)
        completion_seen = "plex internxt mirror run completed" in journal_stdout.lower()
        if progress_rows:
            first = progress_rows[0]
            last = progress_rows[-1]
            phase_key = str(last.get("phase") or "").strip()
            phase_offset = phase_offsets.get(phase_key, 0)
            overall_total = filesystem_overall_total
            run_started_at = (
                first["timestamp"].astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                if _is_datetime_like(first.get("timestamp"))
                else ""
            )
            updated_at = (
                last["timestamp"].astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                if _is_datetime_like(last.get("timestamp"))
                else ""
            )
            observation.update(
                {
                    "status_source": "journal",
                    "status": "running"
                    if service_active_state in {"activating", "active"}
                    else ("completed" if completion_seen else "unknown"),
                    "phase": phase_key,
                    "phase_label": str(last.get("phase_label") or "").strip(),
                    "phase_current": int(last.get("phase_current") or 0),
                    "phase_total": int(last.get("phase_total") or 0) or phase_totals.get(phase_key, 0),
                    "overall_current": phase_offset + int(last.get("phase_current") or 0),
                    "overall_total": overall_total,
                    "current_name": str(last.get("current_name") or "").strip(),
                    "current_detail": str(last.get("current_detail") or "").strip(),
                    "run_started_at": run_started_at,
                    "updated_at": updated_at,
                    "note": "journal_fallback",
                    "exit_code": 0,
                }
            )
        elif completion_seen:
            observation.update(
                {
                    "status_source": "journal",
                    "status": "completed",
                    "phase": "complete",
                    "phase_label": "Completed",
                    "phase_current": filesystem_overall_total,
                    "phase_total": filesystem_overall_total,
                    "overall_current": filesystem_overall_total,
                    "overall_total": filesystem_overall_total,
                    "run_started_at": observation.get("service_started_at") or "",
                    "updated_at": observation.get("service_exited_at") or observation.get("service_started_at") or "",
                    "note": "journal_completion",
                }
            )

    if observation["status"] == "unknown":
        if service_active_state == "failed" or service_result == "failed":
            observation["status"] = "failed"
        elif service_active_state in {"activating", "active"} and service_sub_state in {"start", "running"}:
            observation["status"] = "running"
        elif observation["service_exited_at"]:
            observation["status"] = "completed" if service_result in {"success", ""} else "failed"

    if observation["status"] == "failed" and not observation.get("last_error"):
        observation["last_error"] = service_result or observation.get("note") or "service_failed"

    run_started_dt = _parse_iso(str(observation.get("run_started_at") or ""))
    updated_dt = _parse_iso(str(observation.get("updated_at") or ""))
    if updated_dt:
        observation["stale_seconds"] = max(int((now_dt - updated_dt.astimezone(UTC)).total_seconds()), 0)
    if observation.get("status_source") == "journal" and observation.get("status") == "running":
        src_entry, dst_entry = _mirror_entry_paths(
            str(observation.get("phase") or "").strip(),
            str(observation.get("current_name") or "").strip(),
            str(observation.get("current_detail") or "").strip(),
        )
        src_bytes = _path_size_bytes(src_entry, timeout_seconds) if isinstance(src_entry, Path) else None
        dst_bytes = _path_size_bytes(dst_entry, timeout_seconds) if isinstance(dst_entry, Path) else None
        observation["current_entry_source_bytes"] = src_bytes
        observation["current_entry_dest_bytes"] = dst_bytes
        if isinstance(src_bytes, int) and src_bytes > 0 and isinstance(dst_bytes, int) and dst_bytes >= 0:
            observation["current_entry_progress_ratio"] = round(min(max(dst_bytes / src_bytes, 0.0), 1.0), 4)
    current_phase_rows = [
        row
        for row in progress_rows
        if str(row.get("phase") or "").strip() == str(observation.get("phase") or "").strip()
        and _is_datetime_like(row.get("timestamp"))
    ]
    items_per_minute: float | None = None
    if len(current_phase_rows) >= 2:
        phase_first = current_phase_rows[0]
        phase_last = current_phase_rows[-1]
        phase_first_ts = phase_first.get("timestamp")
        phase_last_ts = phase_last.get("timestamp")
        phase_elapsed_seconds = max(
            (phase_last_ts.astimezone(UTC) - phase_first_ts.astimezone(UTC)).total_seconds()
            if _is_datetime_like(phase_first_ts) and _is_datetime_like(phase_last_ts)
            else 0.0,
            0.0,
        )
        phase_delta = int(phase_last.get("phase_current") or 0) - int(phase_first.get("phase_current") or 0)
        if phase_elapsed_seconds > 0 and phase_delta > 0:
            items_per_minute = (float(phase_delta) / phase_elapsed_seconds) * 60.0
            observation["items_per_minute_source"] = "current_phase"
    elif (
        run_started_dt
        and updated_dt
        and str(observation.get("phase") or "").strip() == PLEX_INTERNXT_MIRROR_PHASES[0][0]
        and int(observation.get("overall_current") or 0) > 0
    ):
        elapsed_seconds = max((updated_dt.astimezone(UTC) - run_started_dt.astimezone(UTC)).total_seconds(), 0.0)
        if elapsed_seconds > 0:
            items_per_minute = (float(observation.get("overall_current") or 0) / elapsed_seconds) * 60.0
            observation["items_per_minute_source"] = "overall_from_start"

    if (
        items_per_minute is not None
        and int(observation.get("overall_total") or 0) >= int(observation.get("overall_current") or 0)
    ):
        observation["items_per_minute"] = round(items_per_minute, 2)
        remaining = int(observation.get("overall_total") or 0) - int(observation.get("overall_current") or 0)
        if remaining > 0 and items_per_minute > 0:
            eta_seconds = int(round((remaining / items_per_minute) * 60.0))
            observation["eta_seconds"] = eta_seconds
            eta_at = now_dt + timedelta(seconds=eta_seconds)
            observation["eta_at"] = eta_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if (
        observation.get("status_source") == "journal"
        and observation.get("status") == "running"
        and int(observation.get("stale_seconds") or 0) >= PLEX_INTERNXT_MIRROR_JOURNAL_ETA_SUPPRESS_SECONDS
        and isinstance(observation.get("current_entry_progress_ratio"), float)
        and float(observation.get("current_entry_progress_ratio") or 0.0) < 0.95
    ):
        observation["eta_seconds"] = None
        observation["eta_at"] = ""
        observation["eta_suppressed_reason"] = "journal_current_entry_long_running"

    return observation


def _runtime_observation(
    verifier_payload: dict[str, Any],
    verifier_returncode: int,
    rclone_payload: dict[str, Any],
    internxt_rclone_payload: dict[str, Any],
    watchdog: dict[str, Any],
    qbit_log: dict[str, Any],
    recent_download_activity_count: int | None,
    plex_internxt_mirror: dict[str, Any],
) -> dict[str, Any]:
    runtime = verifier_payload.get("runtime") if isinstance(verifier_payload.get("runtime"), dict) else {}
    container_probes = runtime.get("container_probes") if isinstance(runtime.get("container_probes"), dict) else {}
    qbittorrent_storage = (
        runtime.get("qbittorrent_storage") if isinstance(runtime.get("qbittorrent_storage"), dict) else {}
    )
    pcloud_probe = container_probes.get("pcloud_stream") if isinstance(container_probes.get("pcloud_stream"), dict) else {}
    internxt_probe = (
        container_probes.get("internxt_stream") if isinstance(container_probes.get("internxt_stream"), dict) else {}
    )
    qbit_write_probe = (
        qbittorrent_storage.get("write_probe") if isinstance(qbittorrent_storage.get("write_probe"), dict) else {}
    )
    rclone_opt = rclone_payload.get("opt") if isinstance(rclone_payload.get("opt"), dict) else {}
    rclone_disk = rclone_payload.get("diskCache") if isinstance(rclone_payload.get("diskCache"), dict) else {}
    internxt_rclone_opt = internxt_rclone_payload.get("opt") if isinstance(internxt_rclone_payload.get("opt"), dict) else {}
    internxt_rclone_disk = (
        internxt_rclone_payload.get("diskCache") if isinstance(internxt_rclone_payload.get("diskCache"), dict) else {}
    )
    disk_free = runtime.get("disk_free_gib") if isinstance(runtime.get("disk_free_gib"), dict) else {}
    guardrail_failures = verifier_payload.get("failures") if isinstance(verifier_payload.get("failures"), list) else []

    return {
        "guardrail_verifier_status": str(verifier_payload.get("status") or "").strip() or ("pass" if verifier_returncode == 0 else "fail"),
        "guardrail_verifier_returncode": verifier_returncode,
        "guardrail_failures": [str(item).strip() for item in guardrail_failures if str(item).strip()],
        "disk_free_gib_root": disk_free.get("/") if isinstance(disk_free.get("/"), (int, float)) else None,
        "disk_free_gib_cache": disk_free.get("/var/cache/rclone") if isinstance(disk_free.get("/var/cache/rclone"), (int, float)) else None,
        "cache_reserve_target_gib": _media_cache_reserve_target_gib(MEDIA_CACHE_BUDGET_PATH),
        "plex_pcloud_container_probe_ok": bool(pcloud_probe.get("ok")),
        "internxt_container_probe_ok": bool(internxt_probe.get("ok")),
        "plex_alias_probe_ok": bool(runtime.get("container_alias_probe", {}).get("ok")) if isinstance(runtime.get("container_alias_probe"), dict) else False,
        "plex_restart_deferred": bool(watchdog.get("plex_restart_deferred")),
        "plex_last_deferred_line": str(watchdog.get("last_deferred_line") or "").strip(),
        "qbittorrent_container_status": str(qbittorrent_storage.get("container_status") or "").strip(),
        "qbittorrent_save_path": str(qbittorrent_storage.get("save_path") or "").strip(),
        "qbittorrent_write_probe_ok": bool(qbit_write_probe.get("ok")),
        "qbittorrent_log_exists": bool(qbit_log.get("log_exists")),
        "qbittorrent_current_session_started_at": str(qbit_log.get("current_session_started_at") or "").strip(),
        "qbittorrent_fast_resume_rejected_count": int(qbit_log.get("fast_resume_rejected_count") or 0),
        "qbittorrent_recent_storage_error_count": int(qbit_log.get("recent_storage_error_count") or 0),
        "qbittorrent_restored_torrent_count": int(qbit_log.get("restored_torrent_count") or 0),
        "qbittorrent_recent_download_activity_count": recent_download_activity_count,
        "pcloud_cache_mode": _cache_mode_label(rclone_opt.get("CacheMode")),
        "pcloud_cache_bytes_used": int(rclone_disk.get("bytesUsed") or 0),
        "pcloud_cache_uploads_in_progress": int(rclone_disk.get("uploadsInProgress") or 0),
        "pcloud_cache_uploads_queued": int(rclone_disk.get("uploadsQueued") or 0),
        "internxt_cache_mode": _cache_mode_label(internxt_rclone_opt.get("CacheMode")),
        "internxt_cache_bytes_used": int(internxt_rclone_disk.get("bytesUsed") or 0),
        "internxt_cache_uploads_in_progress": int(internxt_rclone_disk.get("uploadsInProgress") or 0),
        "internxt_cache_uploads_queued": int(internxt_rclone_disk.get("uploadsQueued") or 0),
        "internxt_cache_max_size_bytes": int(internxt_rclone_opt.get("CacheMaxSize") or 0),
        "internxt_cache_min_free_space_bytes": int(internxt_rclone_opt.get("CacheMinFreeSpace") or 0),
        "plex_internxt_mirror": plex_internxt_mirror,
    }


def _classify_findings(observation: dict[str, Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    advisory: list[str] = []
    guardrail_failures = [str(item).strip() for item in observation.get("guardrail_failures") or [] if str(item).strip()]

    if not observation.get("guardrail_verifier_status"):
        blocking.append("host_workload_guardrails_probe_failed")
        return blocking, advisory

    if observation.get("pcloud_cache_mode") not in {"unknown", "writes"}:
        blocking.append("pcloud_cache_mode_not_writes")
    if observation.get("qbittorrent_write_probe_ok") is not True:
        blocking.append("qbittorrent_write_probe_failed")

    pcloud_probe_ok = observation.get("plex_pcloud_container_probe_ok") is True
    alias_probe_ok = observation.get("plex_alias_probe_ok") is True
    deferred = observation.get("plex_restart_deferred") is True

    if not pcloud_probe_ok:
        if deferred:
            advisory.append("plex_namespace_restart_deferred_until_idle")
        else:
            blocking.append("plex_pcloud_namespace_stale")
    if not alias_probe_ok and pcloud_probe_ok:
        blocking.append("plex_alias_paths_unavailable")
    if observation.get("internxt_container_probe_ok") is not True:
        advisory.append("internxt_container_probe_failed")

    if int(observation.get("qbittorrent_fast_resume_rejected_count") or 0) > 0:
        advisory.append("qbittorrent_fast_resume_mismatches_present")
    if int(observation.get("qbittorrent_recent_storage_error_count") or 0) > 0:
        advisory.append("recent_qbittorrent_storage_errors_present")
    cache_free = observation.get("disk_free_gib_cache")
    cache_target = observation.get("cache_reserve_target_gib")
    internxt_cache_bytes_used = float(observation.get("internxt_cache_bytes_used") or 0)
    internxt_uploads_in_progress = int(observation.get("internxt_cache_uploads_in_progress") or 0)
    internxt_uploads_queued = int(observation.get("internxt_cache_uploads_queued") or 0)
    if isinstance(cache_free, (int, float)) and isinstance(cache_target, int) and cache_free < cache_target:
        if (
            internxt_cache_bytes_used >= INTERNXT_CACHE_HEADROOM_GIB * (1024 ** 3)
            and internxt_uploads_in_progress == 0
            and internxt_uploads_queued == 0
        ):
            advisory.append("internxt_cache_budget_exceeds_host_headroom")
        else:
            advisory.append("cache_filesystem_below_reserve_threshold")

    mirror = observation.get("plex_internxt_mirror") if isinstance(observation.get("plex_internxt_mirror"), dict) else {}
    mirror_status = str(mirror.get("status") or "").strip().lower()
    mirror_active_state = str(mirror.get("service_active_state") or "").strip().lower()
    mirror_result = str(mirror.get("service_result") or "").strip().lower()
    stale_seconds = mirror.get("stale_seconds")
    if mirror_status == "failed" or mirror_active_state == "failed" or mirror_result == "failed":
        advisory.append("plex_internxt_mirror_failed")
    elif mirror_status == "running" and isinstance(stale_seconds, (int, float)) and stale_seconds > PLEX_INTERNXT_MIRROR_STALE_SECONDS:
        if str(mirror.get("eta_suppressed_reason") or "").strip() != "journal_current_entry_long_running":
            advisory.append("plex_internxt_mirror_progress_stale")
    elif (
        mirror_active_state in {"activating", "active"}
        and mirror_status in {"", "unknown"}
        and str(mirror.get("status_source") or "").strip().lower() == "none"
    ):
        advisory.append("plex_internxt_mirror_status_unavailable")

    handled_failures = {
        "container probe failed: pcloud_stream",
        "container alias probe failed",
        "qbittorrent write probe failed",
        "container probe failed: internxt_stream",
    }
    extra_failures = [item for item in guardrail_failures if item not in handled_failures]
    if extra_failures:
        advisory.append("host_workload_guardrail_failures_present")

    return blocking, advisory


def _stdout_summary(
    *,
    verifier_returncode: int,
    verifier_status: str,
    runtime_status: str,
    observation: dict[str, Any],
) -> str:
    parts = [
        f"verifier_returncode={verifier_returncode}",
        f"verifier_status={verifier_status or 'missing'}",
        f"runtime_status={runtime_status}",
        f"pcloud_cache_mode={observation.get('pcloud_cache_mode') or 'unknown'}",
        f"qbit_write_probe={str(bool(observation.get('qbittorrent_write_probe_ok'))).lower()}",
        f"qbit_fast_resume_rejected={int(observation.get('qbittorrent_fast_resume_rejected_count') or 0)}",
        f"qbit_storage_errors={int(observation.get('qbittorrent_recent_storage_error_count') or 0)}",
        f"plex_pcloud_probe={str(bool(observation.get('plex_pcloud_container_probe_ok'))).lower()}",
        f"plex_deferred={str(bool(observation.get('plex_restart_deferred'))).lower()}",
        f"internxt_cache_bytes={int(observation.get('internxt_cache_bytes_used') or 0)}",
    ]
    mirror = observation.get("plex_internxt_mirror") if isinstance(observation.get("plex_internxt_mirror"), dict) else {}
    parts.extend(
        [
            f"mirror_status={mirror.get('status') or 'unknown'}",
            f"mirror_phase={mirror.get('phase') or 'unknown'}",
            f"mirror_progress={int(mirror.get('overall_current') or 0)}/{int(mirror.get('overall_total') or 0)}",
        ]
    )
    if isinstance(mirror.get("eta_seconds"), int):
        parts.append(f"mirror_eta_seconds={int(mirror.get('eta_seconds') or 0)}")
    return " ".join(parts)


def build_receipt(*, timeout_seconds: float, watchdog_journal_lines: int, recent_activity_minutes: int) -> dict[str, Any]:
    receipt_updated_at = now_iso()
    verifier_returncode, verifier_payload, verifier_stdout, verifier_stderr = _run_guardrail_verifier(timeout_seconds)
    rclone_returncode, rclone_payload, _rclone_stdout, rclone_stderr = _run_rclone_vfs_stats(RCLONE_RC_ADDR, timeout_seconds)
    internxt_rclone_returncode, internxt_rclone_payload, _internxt_rclone_stdout, internxt_rclone_stderr = _run_rclone_vfs_stats(
        INTERNXT_RCLONE_RC_ADDR,
        timeout_seconds,
    )
    journal_returncode, journal_stdout, journal_stderr = _run_watchdog_journal(watchdog_journal_lines, timeout_seconds)
    qbit_log = _read_qbittorrent_log_state(QBIT_LOG_PATH)

    verifier_runtime = verifier_payload.get("runtime") if isinstance(verifier_payload.get("runtime"), dict) else {}
    qbittorrent_storage = (
        verifier_runtime.get("qbittorrent_storage")
        if isinstance(verifier_runtime.get("qbittorrent_storage"), dict)
        else {}
    )
    recent_download_activity_count = _recent_download_activity_count(
        str(qbittorrent_storage.get("host_save_path") or qbittorrent_storage.get("save_path") or "").strip(),
        recent_activity_minutes,
        timeout_seconds,
    )
    watchdog = _watchdog_state(journal_stdout if journal_returncode == 0 else "")
    plex_internxt_mirror = _build_plex_internxt_mirror_observation(timeout_seconds)
    observation = _runtime_observation(
        verifier_payload,
        verifier_returncode,
        rclone_payload if rclone_returncode == 0 else {},
        internxt_rclone_payload if internxt_rclone_returncode == 0 else {},
        watchdog,
        qbit_log,
        recent_download_activity_count,
        plex_internxt_mirror,
    )

    blocking_findings, advisory_findings = _classify_findings(observation)
    runtime_status = contract.runtime_status(blocking_findings, advisory_findings)
    runtime_ready = contract.runtime_ready(blocking_findings, advisory_findings)
    next_actions = contract.next_actions(blocking_findings)
    advisory_actions = contract.advisory_actions(advisory_findings)
    secret_leak_detected = contains_secretish_key(
        {
            "verifier": verifier_payload,
            "rclone_vfs_stats": rclone_payload if rclone_returncode == 0 else {},
            "observation": observation,
        }
    )

    structural_failures: list[str] = []
    if not isinstance(verifier_payload, dict) or not verifier_payload:
        structural_failures.append("host_workload_guardrails_probe_failed")
    if rclone_returncode != 0:
        structural_failures.append("pcloud_vfs_stats_unavailable")
    if journal_returncode != 0:
        structural_failures.append("watchdog_journal_unavailable")
    if secret_leak_detected:
        structural_failures.append("secret_leak_detected")

    structural_status = "pass" if not structural_failures else "fail"

    stderr_sources = "\n".join(
        item
        for item in (verifier_stderr, rclone_stderr, internxt_rclone_stderr, journal_stderr)
        if str(item or "").strip()
    )
    return {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": receipt_updated_at,
        "updated_at": receipt_updated_at,
        "status": structural_status,
        "structural_status": structural_status,
        "effective_status": runtime_status,
        "runtime_status": runtime_status,
        "runtime_ready": runtime_ready,
        "source": SOURCE_ID,
        "source_runtime": SOURCE_RUNTIME,
        "observed_at": str(verifier_payload.get("checked_at") or receipt_updated_at),
        "blocking_count": len(blocking_findings),
        "advisory_count": len(advisory_findings),
        "blocking_findings": blocking_findings,
        "advisory_findings": advisory_findings,
        "next_action_component_keys": [
            str(item.get("component_key") or "").strip()
            for item in next_actions
            if str(item.get("component_key") or "").strip()
        ],
        "advisory_action_component_keys": [
            str(item.get("component_key") or "").strip()
            for item in advisory_actions
            if str(item.get("component_key") or "").strip()
        ],
        "next_actions": next_actions,
        "advisory_actions": advisory_actions,
        "runtime_observation": observation,
        "secret_leak_detected": secret_leak_detected,
        "failures": structural_failures,
        "stdout_tail": _stdout_summary(
            verifier_returncode=verifier_returncode,
            verifier_status=str(verifier_payload.get("status") or "").strip(),
            runtime_status=runtime_status,
            observation=observation,
        ),
        "stderr_tail": stderr_summary(stderr_sources),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a host workload runtime-health receipt for EA/operator dashboards.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--watchdog-journal-lines", type=int, default=200)
    parser.add_argument("--recent-activity-minutes", type=int, default=20)
    args = parser.parse_args()

    payload = build_receipt(
        timeout_seconds=float(args.timeout_seconds),
        watchdog_journal_lines=int(args.watchdog_journal_lines),
        recent_activity_minutes=int(args.recent_activity_minutes),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
