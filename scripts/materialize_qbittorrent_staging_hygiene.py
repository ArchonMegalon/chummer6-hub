#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qbittorrent_staging_hygiene_contract as contract
from container_path_mapping import docker_container_mount_mappings, resolve_host_path
from ea_live_ops_receipt_hygiene import contains_secretish_key, public_source_ref, stderr_summary


DEFAULT_OUTPUT_PATH = REPO_ROOT / ".codex-studio" / "published" / "QBITTORRENT_STAGING_HYGIENE.generated.json"
CONTRACT_NAME = "chummer.qbittorrent_staging_hygiene.v1"
SOURCE_ID = "script:materialize_qbittorrent_staging_hygiene.py"
SOURCE_RUNTIME = "qbittorrent.staging_hygiene"
QBIT_ENV_PATH = Path("/docker/arr-v2/.env")
QBIT_CONTAINER_NAME = "qbittorrent_pia"
QBIT_URL_DEFAULT = "http://127.0.0.1:18083"
QBIT_SAVE_PATH_DEFAULT = "/mnt/pcloud/staging/downloads"
PARTIAL_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?:\.[0-9a-fA-F]{6,32})?\.partial$")
FORCED_DOWNLOAD_STATES = {"forcedDL", "forcedMetaDL"}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_value(values: dict[str, str], name: str, default: str = "") -> str:
    return os.environ.get(name, values.get(name, default))


def _env_int(values: dict[str, str], name: str, default: int) -> int:
    raw = os.environ.get(name, values.get(name, str(default)))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _age_minutes(epoch_seconds: int, now_epoch: float) -> int:
    if epoch_seconds <= 0:
        return 0
    return max(0, int((now_epoch - float(epoch_seconds)) / 60.0))


def _strip_partial_suffix(path: Path) -> Path:
    match = PARTIAL_SUFFIX_RE.match(path.as_posix())
    if not match:
        return path
    return Path(match.group("base"))


def _login(base_url: str, username: str, password: str, timeout_seconds: float) -> tuple[urllib.request.OpenerDirector | None, str]:
    if not username or not password:
        return None, "missing_qbittorrent_credentials"
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v2/auth/login",
        data=data,
        method="POST",
        headers={
            "Referer": base_url,
            "User-Agent": "qbittorrent-staging-hygiene/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", "ignore")
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        return None, f"login_failed:{type(exc).__name__}"
    if "Fails" in body:
        return None, "login_failed:invalid_credentials"
    return opener, ""


def _request_json(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    timeout_seconds: float,
) -> Any:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers={
            "Referer": base_url,
            "User-Agent": "qbittorrent-staging-hygiene/1.0",
        },
    )
    with opener.open(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", "ignore")
    return json.loads(raw) if raw.strip() else None


def _request_text(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    timeout_seconds: float,
    *,
    form: dict[str, Any] | None = None,
    method: str = "GET",
) -> str:
    headers = {
        "Referer": base_url,
        "User-Agent": "qbittorrent-staging-hygiene/1.0",
    }
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    with opener.open(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", "ignore")


def _fetch_torrents(opener: urllib.request.OpenerDirector, base_url: str, timeout_seconds: float) -> list[dict[str, Any]]:
    payload = _request_json(opener, base_url, "/api/v2/torrents/info", timeout_seconds)
    return [dict(item) for item in payload] if isinstance(payload, list) else []


def _fetch_preferences(opener: urllib.request.OpenerDirector, base_url: str, timeout_seconds: float) -> dict[str, Any]:
    payload = _request_json(opener, base_url, "/api/v2/app/preferences", timeout_seconds)
    return dict(payload) if isinstance(payload, dict) else {}


def _set_preferences(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    changes: dict[str, Any],
) -> str:
    return _request_text(
        opener,
        base_url,
        "/api/v2/app/setPreferences",
        timeout_seconds,
        form={"json": json.dumps(changes)},
        method="POST",
    )


def _set_force_start(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    hashes: list[str],
    value: bool,
) -> str:
    cleaned = sorted({str(item).strip() for item in hashes if str(item).strip()})
    if not cleaned:
        return ""
    return _request_text(
        opener,
        base_url,
        "/api/v2/torrents/setForceStart",
        timeout_seconds,
        form={"hashes": "|".join(cleaned), "value": "true" if value else "false"},
        method="POST",
    )


def _set_torrent_state(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    hashes: list[str],
    state: str,
) -> str:
    normalized_state = str(state or "").strip().lower()
    candidates = []
    if normalized_state == "pause":
        candidates = ["stop", "pause"]
    elif normalized_state == "resume":
        candidates = ["start", "resume"]
    else:
        raise ValueError(f"unsupported_torrent_state:{state}")
    cleaned = sorted({str(item).strip() for item in hashes if str(item).strip()})
    if not cleaned:
        return ""
    request_error: Exception | None = None
    for candidate in candidates:
        try:
            return _set_torrent_action(
                opener=opener,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                hashes=["|".join(cleaned)],
                action=candidate,
            )
        except urllib.error.HTTPError as exc:
            request_error = exc
            if exc.code != 404:
                raise
            continue
    if request_error is None:
        raise RuntimeError("torrent_state_transition_failed")
    raise request_error


def _set_torrent_action(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    hashes: list[str],
    action: str,
) -> str:
    normalized_action = str(action or "").strip()
    if not normalized_action:
        raise ValueError(f"unsupported_torrent_action:{action}")
    cleaned = sorted({str(item).strip() for item in hashes if str(item).strip()})
    if not cleaned:
        return ""
    return _request_text(
        opener,
        base_url,
        f"/api/v2/torrents/{normalized_action}",
        timeout_seconds,
        form={"hashes": "|".join(cleaned)},
        method="POST",
    )


def _delete_torrents(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    hashes: list[str],
) -> str:
    cleaned = sorted({str(item).strip() for item in hashes if str(item).strip()})
    if not cleaned:
        return ""
    return _request_text(
        opener,
        base_url,
        "/api/v2/torrents/delete",
        timeout_seconds,
        form={"hashes": "|".join(cleaned), "deleteFiles": "true"},
        method="POST",
    )


def _fetch_torrent_files(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    torrent_hash: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    if not torrent_hash.strip():
        return []
    quoted_hash = urllib.parse.quote(torrent_hash.strip())
    payload = _request_json(opener, base_url, f"/api/v2/torrents/files?hash={quoted_hash}", timeout_seconds)
    return [dict(item) for item in payload] if isinstance(payload, list) else []


def _staging_root_from_preferences(
    env_values: dict[str, str],
    configured_container_save_path: str,
    path_mappings: list[tuple[str, str]],
) -> Path:
    configured_host_path = _env_value(env_values, "QBIT_SAVE_PATH", "").strip()
    if configured_host_path:
        return Path(configured_host_path).expanduser().resolve(strict=False)
    resolved = resolve_host_path(configured_container_save_path or QBIT_SAVE_PATH_DEFAULT, path_mappings)
    return Path(resolved)


def _referenced_file_paths(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    torrents: list[dict[str, Any]],
    timeout_seconds: float,
    path_mappings: list[tuple[str, str]],
) -> tuple[set[str], int]:
    referenced: set[str] = set()
    fetched = 0
    for torrent in torrents:
        save_path = str(torrent.get("save_path") or "").strip()
        torrent_hash = str(torrent.get("hash") or torrent.get("infohash_v1") or "").strip()
        if not save_path or not torrent_hash:
            continue
        try:
            files = _fetch_torrent_files(opener, base_url, torrent_hash, timeout_seconds)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
            continue
        fetched += 1
        for file_row in files:
            relative_name = str(file_row.get("name") or "").strip()
            if not relative_name:
                continue
            host_save_path = resolve_host_path(save_path, path_mappings)
            referenced.add(_normalize_path(Path(host_save_path) / relative_name))
    return referenced, fetched


def _scan_orphan_partials(
    staging_root: Path,
    referenced_paths: set[str],
    min_age_minutes: int,
    now_epoch: float,
    sample_limit: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    file_count = 0
    total_bytes = 0
    oldest_age_minutes = 0
    for path in staging_root.rglob("*.partial"):
        if not path.is_file():
            continue
        stat = path.stat()
        age_minutes = _age_minutes(int(stat.st_mtime), now_epoch)
        if age_minutes < min_age_minutes:
            continue
        target_path = _strip_partial_suffix(path)
        normalized_target = _normalize_path(target_path)
        if normalized_target in referenced_paths:
            continue
        file_count += 1
        total_bytes += int(stat.st_size)
        oldest_age_minutes = max(oldest_age_minutes, age_minutes)
        candidates.append(
            {
                "path": str(path),
                "bytes": int(stat.st_size),
                "age_minutes": age_minutes,
                "target_path": str(target_path),
            }
        )
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "total_gib": round(total_bytes / (1024**3), 2),
        "oldest_age_minutes": oldest_age_minutes,
        "samples": candidates[:sample_limit],
        "candidates": candidates,
    }


def _dead_meta_candidates(torrents: list[dict[str, Any]], min_age_minutes: int, now_epoch: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for torrent in torrents:
        state = str(torrent.get("state") or "").strip()
        if state not in {"metaDL", "forcedMetaDL"}:
            continue
        added_age = _age_minutes(int(torrent.get("added_on") or 0), now_epoch)
        inactive_age = _age_minutes(int(torrent.get("last_activity") or 0) or int(torrent.get("added_on") or 0), now_epoch)
        if added_age < min_age_minutes:
            continue
        if int(torrent.get("num_seeds") or 0) > 0 or int(torrent.get("num_complete") or 0) > 0:
            continue
        candidates.append(
            {
                "hash": str(torrent.get("hash") or torrent.get("infohash_v1") or "").strip(),
                "name": str(torrent.get("name") or "").strip(),
                "state": state,
                "added_age_minutes": added_age,
                "inactive_age_minutes": inactive_age,
            }
        )
    return candidates


def _dead_stalled_candidates(torrents: list[dict[str, Any]], min_age_minutes: int, now_epoch: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for torrent in torrents:
        state = str(torrent.get("state") or "").strip()
        if state != "stalledDL" and state not in {"downloading", "forcedDL"}:
            continue
        added_age = _age_minutes(int(torrent.get("added_on") or 0), now_epoch)
        inactive_age = _age_minutes(int(torrent.get("last_activity") or 0) or int(torrent.get("added_on") or 0), now_epoch)
        if state in {"downloading", "forcedDL"}:
            dlspeed = max(0, int(torrent.get("dlspeed") or 0))
            progress = float(torrent.get("progress") or 0.0)
            if dlspeed > 0 or progress >= 1.0:
                continue
        if added_age < min_age_minutes or inactive_age < min_age_minutes:
            continue
        candidates.append(
            {
                "hash": str(torrent.get("hash") or torrent.get("infohash_v1") or "").strip(),
                "name": str(torrent.get("name") or "").strip(),
                "state": state,
                "added_age_minutes": added_age,
                "inactive_age_minutes": inactive_age,
            }
        )
    return candidates


def _dead_checking_candidates(torrents: list[dict[str, Any]], min_age_minutes: int, now_epoch: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for torrent in torrents:
        state = str(torrent.get("state") or "").strip()
        if state not in {"checkingDL", "checkingResumeData"}:
            continue
        added_age = _age_minutes(int(torrent.get("added_on") or 0), now_epoch)
        inactive_age = _age_minutes(int(torrent.get("last_activity") or 0) or int(torrent.get("added_on") or 0), now_epoch)
        if added_age < min_age_minutes or inactive_age < min_age_minutes:
            continue
        candidates.append(
            {
                "hash": str(torrent.get("hash") or torrent.get("infohash_v1") or "").strip(),
                "name": str(torrent.get("name") or "").strip(),
                "state": state,
                "added_age_minutes": added_age,
                "inactive_age_minutes": inactive_age,
            }
        )
    return candidates


def _recover_dead_stalled_torrent(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    stalled_hash: str,
) -> list[str]:
    errors: list[str] = []
    _set_torrent_state(
        opener,
        base_url,
        timeout_seconds,
        [stalled_hash],
        "pause",
    )
    # Re-announce to refresh peer/trackers before resuming and rechecking.
    # This can help stalled downloads where the tracker session has drifted stale.
    try:
        _set_torrent_action(
            opener=opener,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            hashes=[stalled_hash],
            action="reannounce",
        )
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        errors.append(f"{stalled_hash}:reannounce:{type(exc).__name__}")
    _set_torrent_state(
        opener,
        base_url,
        timeout_seconds,
        [stalled_hash],
        "resume",
    )
    _set_torrent_action(
        opener=opener,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        hashes=[stalled_hash],
        action="recheck",
    )
    return errors


def _recover_stuck_torrents(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    timeout_seconds: float,
    torrents: list[dict[str, Any]],
    min_age_minutes: int,
    now_epoch: float,
    max_recovery_cycles: int,
    wait_seconds: float,
    candidate_fn: Callable[[list[dict[str, Any]], int, float], list[dict[str, Any]]],
    sleep_fn: Callable[[float], Any] = time.sleep,
) -> tuple[list[str], list[str], list[str], int, list[dict[str, Any]]]:
    if max_recovery_cycles < 1:
        max_recovery_cycles = 1
    if wait_seconds < 0:
        wait_seconds = 0.0

    requeued: list[str] = []
    requeue_errors: list[str] = []
    candidates_now = candidate_fn(torrents, min_age_minutes, now_epoch)
    current_hashes = sorted(
        {
            item["hash"]
            for item in candidates_now
            if isinstance(item.get("hash"), str) and item.get("hash").strip()
        }
    )
    if not current_hashes:
        return requeued, requeue_errors, [], 0, torrents

    remaining_hashes = list(current_hashes)
    recovery_cycles = 0

    for cycle in range(1, max_recovery_cycles + 1):
        if not current_hashes:
            break
        recovery_cycles = cycle
        for torrent_hash in current_hashes:
            try:
                errors = _recover_dead_stalled_torrent(opener, base_url, timeout_seconds, torrent_hash)
                requeue_errors.extend(errors)
                if torrent_hash not in requeued:
                    requeued.append(torrent_hash)
            except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                requeue_errors.append(f"{torrent_hash}:{type(exc).__name__}")
        if cycle < max_recovery_cycles:
            if wait_seconds > 0:
                sleep_fn(wait_seconds)
            try:
                torrents = _fetch_torrents(opener, base_url, timeout_seconds)
            except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
                break
            candidates_now = [
                item
                for item in candidate_fn(torrents, min_age_minutes, time.time())
                if not (
                    str(item.get("state") or "").strip() in {"downloading", "forcedDL"}
                    and str(item.get("hash") or "").strip() in requeued
                )
            ]
            current_hashes = sorted(
                {
                    item["hash"]
                    for item in candidates_now
                    if isinstance(item.get("hash"), str) and item.get("hash").strip()
                }
            )

    remaining_torrents = candidate_fn(torrents, min_age_minutes, time.time())
    if requeued:
        remaining_torrents = [
            item
            for item in remaining_torrents
            if not (
                str(item.get("state") or "").strip() in {"downloading", "forcedDL"}
                and str(item.get("hash") or "").strip() in requeued
            )
        ]
    remaining_hashes = sorted(
        {
            item["hash"]
            for item in remaining_torrents
            if isinstance(item.get("hash"), str) and item.get("hash").strip()
        }
    )

    return requeued, requeue_errors, remaining_hashes, recovery_cycles, torrents


def _download_speed_threshold_bytes(preferences: dict[str, Any]) -> int:
    return max(0, int(preferences.get("slow_torrent_dl_rate_threshold") or 0)) * 1024


def _upload_speed_threshold_bytes(preferences: dict[str, Any]) -> int:
    return max(0, int(preferences.get("slow_torrent_ul_rate_threshold") or 0)) * 1024


def _torrent_is_slow_queue_exempt(torrent: dict[str, Any], preferences: dict[str, Any]) -> bool:
    if preferences.get("dont_count_slow_torrents") is not True:
        return False
    state = str(torrent.get("state") or "").strip()
    if state not in {"downloading", "forcedDL"}:
        return False
    download_threshold = _download_speed_threshold_bytes(preferences)
    upload_threshold = _upload_speed_threshold_bytes(preferences)
    if download_threshold <= 0 and upload_threshold <= 0:
        return False
    download_speed = max(0, int(torrent.get("dlspeed") or 0))
    upload_speed = max(0, int(torrent.get("upspeed") or 0))
    return download_speed <= download_threshold and upload_speed <= upload_threshold


def _classify_findings(observation: dict[str, Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    advisory: list[str] = []
    if observation.get("qbittorrent_api_ok") is not True:
        blocking.append("qbittorrent_api_unavailable")
    if observation.get("staging_root_ok") is not True:
        blocking.append("qbittorrent_staging_root_unreadable")
    if observation.get("queueing_enabled") is False:
        advisory.append("qbittorrent_queueing_disabled")
    active_download_count = int(observation.get("effective_downloading_state_count") or 0)
    max_active_downloads = int(observation.get("max_active_downloads") or 0)
    if observation.get("queueing_enabled") is True and max_active_downloads > 0 and active_download_count > max_active_downloads:
        advisory.append("qbittorrent_active_download_count_exceeds_limit")
    if int(observation.get("forced_download_count") or 0) > 0:
        advisory.append("qbittorrent_forced_downloads_present")
    if int(observation.get("orphan_partial_file_count") or 0) > 0:
        advisory.append("qbittorrent_orphan_partials_present")
    if int(observation.get("dead_meta_candidate_count") or 0) > 0:
        advisory.append("qbittorrent_dead_metadata_downloads_present")
    if int(observation.get("dead_stalled_candidate_count") or 0) > 0:
        advisory.append("qbittorrent_dead_stalled_downloads_present")
    if int(observation.get("dead_checking_candidate_count") or 0) > 0:
        advisory.append("qbittorrent_long_checking_downloads_present")
    return blocking, advisory


def build_receipt(
    *,
    timeout_seconds: float = 30.0,
    min_partial_age_days: int = 7,
    min_dead_meta_age_minutes: int = 120,
    min_dead_stalled_age_minutes: int = 120,
    min_dead_checking_age_minutes: int = 120,
    max_recovery_cycles: int = 3,
    recovery_wait_seconds: float = 5.0,
    sample_limit: int = 20,
    apply_prune_orphan_partials: bool = False,
    apply_enable_queueing: bool = False,
    apply_clear_forced_downloads: bool = False,
    apply_requeue_dead_stalled_downloads: bool = False,
    apply_requeue_dead_meta_downloads: bool = False,
    apply_requeue_dead_checking_downloads: bool = False,
    apply_delete_dead_stalled_downloads: bool = False,
    apply_delete_dead_meta_downloads: bool = False,
    apply_delete_dead_checking_downloads: bool = False,
    guardrail_max_active_downloads: int = 2,
    guardrail_max_active_torrents: int = 3,
    guardrail_max_active_uploads: int = 3,
) -> dict[str, Any]:
    observed_at = now_iso()
    env_values = _load_env(QBIT_ENV_PATH)
    base_url = _env_value(env_values, "QBIT_URL", QBIT_URL_DEFAULT).rstrip("/")
    username = _env_value(env_values, "QBIT_USER", "")
    password = _env_value(env_values, "QBIT_PASS", "")
    path_mappings = docker_container_mount_mappings(QBIT_CONTAINER_NAME, timeout_seconds=timeout_seconds)
    staging_root = Path(_env_value(env_values, "QBIT_SAVE_PATH", QBIT_SAVE_PATH_DEFAULT))
    now_epoch = time.time()

    structural_failures: list[str] = []
    stderr_notes: list[str] = []
    torrents: list[dict[str, Any]] = []
    referenced_paths: set[str] = set()
    files_api_calls = 0
    prefs_before: dict[str, Any] = {}
    prefs_after: dict[str, Any] = {}
    runtime_guardrail_changes_applied: dict[str, Any] = {}
    forced_download_hashes_cleared: list[str] = []
    dead_stalled_hashes_requeued: list[str] = []
    dead_stalled_requeue_errors: list[str] = []
    dead_checking_hashes_requeued: list[str] = []
    dead_checking_requeue_errors: list[str] = []
    dead_meta_hashes_requeued: list[str] = []
    dead_meta_requeue_errors: list[str] = []
    dead_stalled_hashes_deleted: list[str] = []
    dead_stalled_delete_errors: list[str] = []
    dead_checking_hashes_deleted: list[str] = []
    dead_checking_delete_errors: list[str] = []
    dead_meta_hashes_deleted: list[str] = []
    dead_meta_delete_errors: list[str] = []
    dead_stalled_recovery_cycles: int = 0
    dead_checking_recovery_cycles: int = 0
    dead_meta_recovery_cycles: int = 0
    opener, login_error = _login(base_url, username, password, timeout_seconds)
    if opener is None:
        structural_failures.append("qbittorrent_api_unavailable")
        stderr_notes.append(login_error or "login_failed")
    else:
        try:
            prefs_before = _fetch_preferences(opener, base_url, timeout_seconds)
            prefs_after = dict(prefs_before)
            configured_container_save_path = str(prefs_after.get("save_path") or "").strip()
            staging_root = _staging_root_from_preferences(env_values, configured_container_save_path, path_mappings)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
            structural_failures.append("qbittorrent_api_unavailable")
            stderr_notes.append(f"preferences_failed:{type(exc).__name__}")
        if apply_enable_queueing and not structural_failures:
            desired_prefs = {
                "queueing_enabled": True,
                "max_active_downloads": int(guardrail_max_active_downloads),
                "max_active_torrents": int(guardrail_max_active_torrents),
                "max_active_uploads": int(guardrail_max_active_uploads),
                "dont_count_slow_torrents": True,
            }
            runtime_guardrail_changes_applied = {
                key: value for key, value in desired_prefs.items() if prefs_before.get(key) != value
            }
            if runtime_guardrail_changes_applied:
                try:
                    _set_preferences(opener, base_url, timeout_seconds, runtime_guardrail_changes_applied)
                    prefs_after = _fetch_preferences(opener, base_url, timeout_seconds)
                    configured_container_save_path = str(prefs_after.get("save_path") or "").strip()
                    staging_root = _staging_root_from_preferences(env_values, configured_container_save_path, path_mappings)
                except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                    stderr_notes.append(f"set_preferences_failed:{type(exc).__name__}")
        try:
            torrents = _fetch_torrents(opener, base_url, timeout_seconds)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
            structural_failures.append("qbittorrent_api_unavailable")
            stderr_notes.append(f"torrents_info_failed:{type(exc).__name__}")
            torrents = []
        if apply_clear_forced_downloads and torrents and prefs_after.get("queueing_enabled") is True:
            forced_download_hashes_cleared = sorted(
                {
                    str(item.get("hash") or item.get("infohash_v1") or "").strip()
                    for item in torrents
                    if bool(item.get("force_start")) and str(item.get("state") or "").strip() in FORCED_DOWNLOAD_STATES
                }
            )
            if forced_download_hashes_cleared:
                try:
                    _set_force_start(opener, base_url, timeout_seconds, forced_download_hashes_cleared, False)
                    torrents = _fetch_torrents(opener, base_url, timeout_seconds)
                except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                    stderr_notes.append(f"clear_force_start_failed:{type(exc).__name__}")
        if apply_requeue_dead_stalled_downloads and torrents:
            dead_stalled_hashes_requeued, dead_stalled_requeue_errors, dead_stalled_remaining_hashes, dead_stalled_recovery_cycles, torrents = _recover_stuck_torrents(
                opener=opener,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                torrents=torrents,
                min_age_minutes=min_dead_stalled_age_minutes,
                now_epoch=now_epoch,
                max_recovery_cycles=max_recovery_cycles,
                wait_seconds=recovery_wait_seconds,
                candidate_fn=_dead_stalled_candidates,
                sleep_fn=time.sleep,
            )
            if dead_stalled_remaining_hashes and apply_delete_dead_stalled_downloads:
                # A stalled row may already contain irreplaceable payload bytes. Keep
                # the legacy switch fail-closed so configuration drift can request a
                # retry, but can never turn stalled-download recovery into deletion.
                dead_stalled_delete_errors.append("started_torrent_preservation_policy")

        if apply_requeue_dead_meta_downloads and torrents:
            dead_meta_hashes_requeued, dead_meta_requeue_errors, dead_meta_remaining_hashes, dead_meta_recovery_cycles, torrents = _recover_stuck_torrents(
                opener=opener,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                torrents=torrents,
                min_age_minutes=min_dead_meta_age_minutes,
                now_epoch=now_epoch,
                max_recovery_cycles=max_recovery_cycles,
                wait_seconds=recovery_wait_seconds,
                candidate_fn=_dead_meta_candidates,
                sleep_fn=time.sleep,
            )
            if dead_meta_remaining_hashes and apply_delete_dead_meta_downloads:
                try:
                    _delete_torrents(opener, base_url, timeout_seconds, dead_meta_remaining_hashes)
                    dead_meta_hashes_deleted = list(dead_meta_remaining_hashes)
                    try:
                        torrents = _fetch_torrents(opener, base_url, timeout_seconds)
                    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                        structural_failures.append("qbittorrent_api_unavailable")
                        stderr_notes.append(f"torrents_info_failed:{type(exc).__name__}")
                        torrents = []
                except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                    dead_meta_delete_errors.append(type(exc).__name__)
        if apply_requeue_dead_checking_downloads and torrents:
            dead_checking_hashes_requeued, dead_checking_requeue_errors, dead_checking_remaining_hashes, dead_checking_recovery_cycles, torrents = _recover_stuck_torrents(
                opener=opener,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                torrents=torrents,
                min_age_minutes=min_dead_checking_age_minutes,
                now_epoch=now_epoch,
                max_recovery_cycles=max_recovery_cycles,
                wait_seconds=recovery_wait_seconds,
                candidate_fn=_dead_checking_candidates,
                sleep_fn=time.sleep,
            )
            if dead_checking_remaining_hashes and apply_delete_dead_checking_downloads:
                try:
                    _delete_torrents(opener, base_url, timeout_seconds, dead_checking_remaining_hashes)
                    dead_checking_hashes_deleted = list(dead_checking_remaining_hashes)
                    try:
                        torrents = _fetch_torrents(opener, base_url, timeout_seconds)
                    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                        structural_failures.append("qbittorrent_api_unavailable")
                        stderr_notes.append(f"torrents_info_failed:{type(exc).__name__}")
                        torrents = []
                except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
                    dead_checking_delete_errors.append(type(exc).__name__)
        if torrents:
            referenced_paths, files_api_calls = _referenced_file_paths(
                opener,
                base_url,
                torrents,
                timeout_seconds,
                path_mappings,
            )

    staging_root_ok = staging_root.exists() and staging_root.is_dir()
    if not staging_root_ok:
        structural_failures.append("qbittorrent_staging_root_unreadable")

    orphan_summary = {
        "file_count": 0,
        "total_bytes": 0,
        "total_gib": 0.0,
        "oldest_age_minutes": 0,
        "samples": [],
    }
    if staging_root_ok:
        orphan_summary = _scan_orphan_partials(
            staging_root,
            referenced_paths,
            min_partial_age_days * 24 * 60,
            now_epoch,
            sample_limit,
        )
    prune_result = {
        "applied": False,
        "pruned_file_count": 0,
        "pruned_bytes": 0,
        "pruned_gib": 0.0,
    }
    if apply_prune_orphan_partials and staging_root_ok and orphan_summary["candidates"]:
        pruned_count = 0
        pruned_bytes = 0
        for candidate in orphan_summary["candidates"]:
            candidate_path = Path(str(candidate.get("path") or ""))
            if not candidate_path.is_file():
                continue
            pruned_count += 1
            pruned_bytes += int(candidate.get("bytes") or 0)
            candidate_path.unlink(missing_ok=True)
        prune_result = {
            "applied": True,
            "pruned_file_count": pruned_count,
            "pruned_bytes": pruned_bytes,
            "pruned_gib": round(pruned_bytes / (1024**3), 2),
        }
        orphan_summary = _scan_orphan_partials(
            staging_root,
            referenced_paths,
            min_partial_age_days * 24 * 60,
            time.time(),
            sample_limit,
        )

    dead_meta = _dead_meta_candidates(torrents, min_dead_meta_age_minutes, now_epoch)
    dead_stalled = _dead_stalled_candidates(torrents, min_dead_stalled_age_minutes, now_epoch)
    dead_checking = _dead_checking_candidates(torrents, min_dead_checking_age_minutes, now_epoch)
    recently_recovered_hashes = {str(item) for item in dead_stalled_hashes_requeued + dead_meta_hashes_requeued + dead_checking_hashes_requeued}
    if recently_recovered_hashes:
        dead_stalled = [
            item
            for item in dead_stalled
            if not (
                str(item.get("state") or "").strip() in {"downloading", "forcedDL"}
                and str(item.get("hash") or "").strip() in recently_recovered_hashes
            )
        ]
    state_counts = dict(sorted(Counter(str(item.get("state") or "unknown") for item in torrents).items()))
    active_download_count = sum(
        1
        for item in torrents
        if str(item.get("state") or "") in {"downloading", "forcedDL", "stalledDL", "metaDL", "forcedMetaDL"}
    )
    downloading_state_count = int(state_counts.get("downloading") or 0) + int(state_counts.get("forcedDL") or 0)
    effective_downloading_state_count = sum(
        1
        for item in torrents
        if str(item.get("state") or "").strip() in {"downloading", "forcedDL"}
        and not _torrent_is_slow_queue_exempt(item, prefs_after)
    )
    forced_download_count = sum(int(state_counts.get(state) or 0) for state in FORCED_DOWNLOAD_STATES)

    observation = {
        "qbittorrent_api_ok": "qbittorrent_api_unavailable" not in structural_failures,
        "qbittorrent_url": base_url,
        "qbittorrent_container_name": QBIT_CONTAINER_NAME,
        "qbittorrent_container_save_path": str(prefs_after.get("save_path") or "").strip(),
        "staging_root": str(staging_root),
        "staging_root_ok": staging_root_ok,
        "container_path_mappings": [
            {"container_path": container_path, "host_path": host_path}
            for container_path, host_path in path_mappings[:10]
        ],
        "min_partial_age_days": int(min_partial_age_days),
        "min_dead_meta_age_minutes": int(min_dead_meta_age_minutes),
        "min_dead_stalled_age_minutes": int(min_dead_stalled_age_minutes),
        "min_dead_checking_age_minutes": int(min_dead_checking_age_minutes),
        "torrent_count": len(torrents),
        "active_download_count": active_download_count,
        "downloading_state_count": downloading_state_count,
        "effective_downloading_state_count": effective_downloading_state_count,
        "forced_download_count": forced_download_count,
        "state_counts": state_counts,
        "referenced_file_count": len(referenced_paths),
        "files_api_calls": files_api_calls,
        "queueing_enabled": prefs_after.get("queueing_enabled"),
        "max_active_downloads": prefs_after.get("max_active_downloads"),
        "max_active_torrents": prefs_after.get("max_active_torrents"),
        "max_active_uploads": prefs_after.get("max_active_uploads"),
        "dont_count_slow_torrents": prefs_after.get("dont_count_slow_torrents"),
        "slow_torrent_dl_rate_threshold_kib": prefs_after.get("slow_torrent_dl_rate_threshold"),
        "slow_torrent_ul_rate_threshold_kib": prefs_after.get("slow_torrent_ul_rate_threshold"),
        "slow_torrent_inactive_timer_seconds": prefs_after.get("slow_torrent_inactive_timer"),
        "runtime_guardrail_changes_applied": runtime_guardrail_changes_applied,
        "forced_download_hashes_cleared": forced_download_hashes_cleared,
        "dead_stalled_hashes_requeued": dead_stalled_hashes_requeued,
        "dead_stalled_requeue_count": len(dead_stalled_hashes_requeued),
        "dead_stalled_requeue_errors": dead_stalled_requeue_errors,
        "dead_meta_hashes_requeued": dead_meta_hashes_requeued,
        "dead_meta_requeue_count": len(dead_meta_hashes_requeued),
        "dead_meta_requeue_errors": dead_meta_requeue_errors,
        "dead_checking_hashes_requeued": dead_checking_hashes_requeued,
        "dead_checking_requeue_count": len(dead_checking_hashes_requeued),
        "dead_checking_requeue_errors": dead_checking_requeue_errors,
        "orphan_partial_file_count": int(orphan_summary["file_count"]),
        "orphan_partial_bytes": int(orphan_summary["total_bytes"]),
        "orphan_partial_gib": float(orphan_summary["total_gib"]),
        "orphan_partial_oldest_age_minutes": int(orphan_summary["oldest_age_minutes"]),
        "orphan_partial_samples": orphan_summary["samples"],
        "orphan_partial_file_count_before_prune": int(
            len(orphan_summary["candidates"]) + prune_result["pruned_file_count"]
            if prune_result["applied"]
            else orphan_summary["file_count"]
        ),
        "orphan_partial_gib_before_prune": (
            round(float(orphan_summary["total_gib"]) + float(prune_result["pruned_gib"]), 2)
            if prune_result["applied"]
            else float(orphan_summary["total_gib"])
        ),
        "prune_orphan_partials_applied": bool(prune_result["applied"]),
        "pruned_orphan_partial_file_count": int(prune_result["pruned_file_count"]),
        "pruned_orphan_partial_bytes": int(prune_result["pruned_bytes"]),
        "pruned_orphan_partial_gib": float(prune_result["pruned_gib"]),
        "max_recovery_cycles": max_recovery_cycles,
        "recovery_wait_seconds": float(recovery_wait_seconds),
        "dead_stalled_recovery_cycles": int(dead_stalled_recovery_cycles),
        "dead_checking_recovery_cycles": int(dead_checking_recovery_cycles),
        "dead_meta_recovery_cycles": int(dead_meta_recovery_cycles),
        "dead_stalled_hashes_deleted": dead_stalled_hashes_deleted,
        "dead_stalled_delete_count": len(dead_stalled_hashes_deleted),
        "dead_stalled_delete_errors": dead_stalled_delete_errors,
        "dead_checking_hashes_deleted": dead_checking_hashes_deleted,
        "dead_checking_delete_count": len(dead_checking_hashes_deleted),
        "dead_checking_delete_errors": dead_checking_delete_errors,
        "dead_meta_hashes_deleted": dead_meta_hashes_deleted,
        "dead_meta_delete_count": len(dead_meta_hashes_deleted),
        "dead_meta_delete_errors": dead_meta_delete_errors,
        "dead_meta_candidate_count": len(dead_meta),
        "dead_meta_candidate_names": [item["name"] for item in dead_meta[:sample_limit] if item.get("name")],
        "dead_meta_candidates": dead_meta[:sample_limit],
        "dead_stalled_candidate_count": len(dead_stalled),
        "dead_stalled_candidate_names": [item["name"] for item in dead_stalled[:sample_limit] if item.get("name")],
        "dead_stalled_candidates": dead_stalled[:sample_limit],
        "dead_checking_candidate_count": len(dead_checking),
        "dead_checking_candidate_names": [item["name"] for item in dead_checking[:sample_limit] if item.get("name")],
        "dead_checking_candidates": dead_checking[:sample_limit],
    }

    blocking_findings, advisory_findings = _classify_findings(observation)
    runtime_status = contract.runtime_status(blocking_findings, advisory_findings)
    runtime_ready = contract.runtime_ready(blocking_findings, advisory_findings)
    next_actions = contract.next_actions(blocking_findings)
    advisory_actions = contract.advisory_actions(advisory_findings)

    receipt = {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": observed_at,
        "updated_at": observed_at,
        "observed_at": observed_at,
        "status": "pass",
        "structural_status": "pass",
        "effective_status": runtime_status,
        "runtime_status": runtime_status,
        "runtime_ready": runtime_ready,
        "source": SOURCE_ID,
        "source_runtime": SOURCE_RUNTIME,
        "blocking_count": len(blocking_findings),
        "advisory_count": len(advisory_findings),
        "blocking_findings": blocking_findings,
        "advisory_findings": advisory_findings,
        "next_action_component_keys": [item["component_key"] for item in next_actions],
        "advisory_action_component_keys": [item["component_key"] for item in advisory_actions],
        "next_actions": next_actions,
        "advisory_actions": advisory_actions,
        "runtime_observation": observation,
        "failures": structural_failures,
        "stdout_tail": (
            f"observed_at={observed_at} "
            f"source={public_source_ref(SOURCE_ID) or SOURCE_ID} "
            f"runtime_status={runtime_status} "
            f"orphan_partials={int(orphan_summary['file_count'])} "
            f"orphan_partial_gib={float(orphan_summary['total_gib'])} "
            f"pruned_orphan_partials={int(prune_result['pruned_file_count'])} "
            f"queueing_enabled={str(bool(prefs_after.get('queueing_enabled'))).lower()} "
            f"downloading_state_count={downloading_state_count} "
            f"effective_downloading_state_count={effective_downloading_state_count} "
            f"dead_meta={len(dead_meta)} "
            f"dead_stalled={len(dead_stalled)} "
            f"dead_checking={len(dead_checking)} "
            f"dead_meta_requeued={len(dead_meta_hashes_requeued)} "
            f"dead_meta_recovery_cycles={dead_meta_recovery_cycles} "
            f"dead_stalled_requeued={len(dead_stalled_hashes_requeued)} "
            f"dead_stalled_recovery_cycles={dead_stalled_recovery_cycles} "
            f"dead_checking_requeued={len(dead_checking_hashes_requeued)} "
            f"dead_checking_recovery_cycles={dead_checking_recovery_cycles} "
            f"torrent_count={len(torrents)}"
        ),
        "stderr_tail": stderr_summary("\n".join(note for note in stderr_notes if note)),
    }
    receipt["secret_leak_detected"] = contains_secretish_key(receipt)
    return receipt


def main() -> int:
    env_values = _load_env(QBIT_ENV_PATH)
    parser = argparse.ArgumentParser(description="Materialize a qBittorrent staging-hygiene runtime receipt.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--min-partial-age-days", type=int, default=7)
    parser.add_argument(
        "--min-dead-meta-age-minutes",
        type=int,
        default=_env_int(env_values, "META_MIN_AGE_MINUTES", 120),
    )
    parser.add_argument(
        "--min-dead-stalled-age-minutes",
        type=int,
        default=_env_int(env_values, "STALL_MIN_AGE_MINUTES", 120),
    )
    parser.add_argument(
        "--min-dead-checking-age-minutes",
        type=int,
        default=_env_int(env_values, "CHECKING_MIN_AGE_MINUTES", 120),
    )
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument(
        "--apply-prune-orphan-partials",
        action="store_true",
        help="Delete orphan partial files older than the configured age threshold after verifying they are not referenced by live qBittorrent torrents.",
    )
    parser.add_argument(
        "--apply-enable-queueing",
        action="store_true",
        help="Enable qBittorrent queueing and re-apply the runtime download limits through the WebUI API.",
    )
    parser.add_argument(
        "--apply-clear-forced-downloads",
        action="store_true",
        help="If queueing is enabled but active downloads still exceed the limit, clear force-start on active forced downloads so qBittorrent can schedule them normally again.",
    )
    parser.add_argument(
        "--apply-requeue-dead-stalled-downloads",
        action="store_true",
        help="For old stalled torrents, pause, reannounce, resume, and recheck each one to force a fresh scheduler slot and peer refresh.",
    )
    parser.add_argument(
        "--apply-requeue-dead-meta-downloads",
        action="store_true",
        help="For old metadata torrents, pause, reannounce, resume, and recheck each one to force a fresh metadata lookup state.",
    )
    parser.add_argument(
        "--apply-requeue-dead-checking-downloads",
        action="store_true",
        help="For old long-checking torrents, pause, reannounce, resume, and recheck each one to force a fresh scheduler slot and peer refresh.",
    )
    parser.add_argument(
        "--apply-delete-dead-stalled-downloads",
        action="store_true",
        help="Legacy compatibility switch; stalled-download deletion is blocked by the started-torrent preservation policy.",
    )
    parser.add_argument(
        "--apply-delete-dead-meta-downloads",
        action="store_true",
        help="After requeue attempts, delete old metadata torrents that remain stalled beyond the recovery cycles.",
    )
    parser.add_argument(
        "--apply-delete-dead-checking-downloads",
        action="store_true",
        help="After requeue attempts, delete old checking torrents that remain checking beyond the recovery cycles.",
    )
    parser.add_argument(
        "--max-recovery-cycles",
        type=int,
        default=_env_int(env_values, "QBIT_RECOVERY_MAX_CYCLES", 3),
    )
    parser.add_argument(
        "--recovery-wait-seconds",
        type=float,
        default=float(_env_int(env_values, "QBIT_RECOVERY_WAIT_SECONDS", 5)),
    )
    parser.add_argument(
        "--guardrail-max-active-downloads",
        type=int,
        default=_env_int(env_values, "QBIT_MAX_ACTIVE_DOWNLOADS", 2),
    )
    parser.add_argument(
        "--guardrail-max-active-torrents",
        type=int,
        default=_env_int(env_values, "QBIT_MAX_ACTIVE_TORRENTS", 3),
    )
    parser.add_argument(
        "--guardrail-max-active-uploads",
        type=int,
        default=_env_int(env_values, "QBIT_MAX_ACTIVE_UPLOADS", 3),
    )
    args = parser.parse_args()

    receipt = build_receipt(
        timeout_seconds=args.timeout_seconds,
        min_partial_age_days=args.min_partial_age_days,
        min_dead_meta_age_minutes=args.min_dead_meta_age_minutes,
        min_dead_stalled_age_minutes=args.min_dead_stalled_age_minutes,
        min_dead_checking_age_minutes=args.min_dead_checking_age_minutes,
        max_recovery_cycles=args.max_recovery_cycles,
        recovery_wait_seconds=args.recovery_wait_seconds,
        sample_limit=args.sample_limit,
        apply_prune_orphan_partials=args.apply_prune_orphan_partials,
        apply_enable_queueing=args.apply_enable_queueing,
        apply_clear_forced_downloads=args.apply_clear_forced_downloads,
        apply_requeue_dead_stalled_downloads=args.apply_requeue_dead_stalled_downloads,
        apply_requeue_dead_meta_downloads=args.apply_requeue_dead_meta_downloads,
        apply_requeue_dead_checking_downloads=args.apply_requeue_dead_checking_downloads,
        apply_delete_dead_stalled_downloads=args.apply_delete_dead_stalled_downloads,
        apply_delete_dead_meta_downloads=args.apply_delete_dead_meta_downloads,
        apply_delete_dead_checking_downloads=args.apply_delete_dead_checking_downloads,
        guardrail_max_active_downloads=args.guardrail_max_active_downloads,
        guardrail_max_active_torrents=args.guardrail_max_active_torrents,
        guardrail_max_active_uploads=args.guardrail_max_active_uploads,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
