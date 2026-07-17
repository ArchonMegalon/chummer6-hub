from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path


MATERIALIZE = Path(__file__).resolve().parents[1] / "scripts" / "materialize_host_workload_runtime_health.py"
VERIFY = Path(__file__).resolve().parents[1] / "scripts" / "verify_host_workload_runtime_health.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def degraded_guardrail_payload() -> dict[str, object]:
    return {
        "checked_at": "2026-07-05T17:18:54Z",
        "status": "fail",
        "failures": [
            "container probe failed: pcloud_stream",
            "container alias probe failed",
        ],
        "runtime": {
            "disk_free_gib": {
                "/": 21.1,
                "/var/cache/rclone": 21.1,
            },
            "container_probes": {
                "pcloud_stream": {"ok": False},
                "internxt_stream": {"ok": True},
            },
            "container_alias_probe": {"ok": False},
            "qbittorrent_storage": {
                "container_status": "Up About a minute",
                "save_path": "/mnt/pcloud/staging/downloads",
                "write_probe": {"ok": True},
            },
        },
    }


def running_mirror_payload() -> dict[str, object]:
    return {
        "status": "running",
        "status_source": "journal",
        "service_active_state": "activating",
        "service_sub_state": "start",
        "service_result": "success",
        "phase": "movies",
        "phase_label": "Movies",
        "phase_current": 325,
        "phase_total": 1555,
        "overall_current": 325,
        "overall_total": 2180,
        "eta_seconds": 1800,
        "items_per_minute": 63.7,
        "stale_seconds": 12,
        "current_name": "Chasing Coral (2017)",
        "current_detail": "C",
    }


def rclone_vfs_payload(*, cache_mode: int = 2, bytes_used: int = 0, uploads_in_progress: int = 0, uploads_queued: int = 0, cache_max_size: int = 0, cache_min_free_space: int = 0) -> dict[str, object]:
    return {
        "opt": {
            "CacheMode": cache_mode,
            "CacheMaxSize": cache_max_size,
            "CacheMinFreeSpace": cache_min_free_space,
        },
        "diskCache": {
            "bytesUsed": bytes_used,
            "uploadsInProgress": uploads_in_progress,
            "uploadsQueued": uploads_queued,
        },
    }


def test_build_receipt_surfaces_deferred_plex_namespace_and_resume_drift(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_degraded")
    guardrail_payload = degraded_guardrail_payload()
    monkeypatch.setattr(
        module,
        "_run_guardrail_verifier",
        lambda timeout_seconds: (1, guardrail_payload, json.dumps(guardrail_payload), ""),
    )
    monkeypatch.setattr(
        module,
        "_run_rclone_vfs_stats",
        lambda rc_addr, timeout_seconds: (
            0,
            rclone_vfs_payload(
                cache_mode=2,
                bytes_used=0,
                uploads_in_progress=0,
                uploads_queued=0,
                cache_max_size=8589934592,
                cache_min_free_space=8589934592,
            ),
            "{}",
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_run_watchdog_journal",
        lambda lines, timeout_seconds: (
            0,
            "Jul 05 19:18:43 ubuntu rclone-watchdog[158391]: plex: mount namespace for /mnt/pcloud/PLEX is stale but Plex has active sessions -> deferring container restart\n",
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_read_qbittorrent_log_state",
        lambda path: {
            "log_exists": True,
            "current_session_started_at": "2026-07-05T19:17:07",
            "fast_resume_rejected_count": 6,
            "recent_storage_error_count": 0,
            "restored_torrent_count": 42,
        },
    )
    monkeypatch.setattr(module, "_recent_download_activity_count", lambda save_path, lookback_minutes, timeout_seconds: 12)
    monkeypatch.setattr(module, "_build_plex_internxt_mirror_observation", lambda timeout_seconds: running_mirror_payload())

    receipt = module.build_receipt(timeout_seconds=5.0, watchdog_journal_lines=50, recent_activity_minutes=20)

    assert receipt["updated_at"]
    assert receipt["status"] == "pass"
    assert receipt["structural_status"] == "pass"
    assert receipt["effective_status"] == "degraded"
    assert receipt["runtime_ready"] is False
    assert receipt["blocking_findings"] == []
    assert receipt["advisory_findings"] == [
        "plex_namespace_restart_deferred_until_idle",
        "qbittorrent_fast_resume_mismatches_present",
    ]
    assert receipt["next_action_component_keys"] == []
    assert receipt["advisory_action_component_keys"] == ["plex", "qbittorrent"]
    assert receipt["runtime_observation"]["pcloud_cache_mode"] == "writes"
    assert receipt["runtime_observation"]["internxt_cache_mode"] == "writes"
    assert receipt["runtime_observation"]["qbittorrent_recent_download_activity_count"] == 12
    assert receipt["runtime_observation"]["plex_internxt_mirror"]["status"] == "running"
    assert receipt["runtime_observation"]["plex_internxt_mirror"]["eta_seconds"] == 1800
    assert "mirror_status=running" in receipt["stdout_tail"]
    assert "pcloud_cache_mode=writes" in receipt["stdout_tail"]


def test_build_receipt_blocks_when_qbittorrent_write_probe_fails(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_blocked")
    guardrail_payload = degraded_guardrail_payload()
    guardrail_payload["failures"] = ["qbittorrent write probe failed"]
    guardrail_payload["runtime"]["container_probes"]["pcloud_stream"] = {"ok": True}
    guardrail_payload["runtime"]["container_alias_probe"] = {"ok": True}
    guardrail_payload["runtime"]["qbittorrent_storage"]["write_probe"] = {"ok": False}
    monkeypatch.setattr(
        module,
        "_run_guardrail_verifier",
        lambda timeout_seconds: (1, guardrail_payload, json.dumps(guardrail_payload), ""),
    )
    monkeypatch.setattr(
        module,
        "_run_rclone_vfs_stats",
        lambda rc_addr, timeout_seconds: (
            0,
            rclone_vfs_payload(
                cache_mode=3 if rc_addr == module.RCLONE_RC_ADDR else 2,
                bytes_used=9 if rc_addr == module.RCLONE_RC_ADDR else 0,
                uploads_in_progress=0,
                uploads_queued=0,
                cache_max_size=8589934592,
                cache_min_free_space=8589934592,
            ),
            "{}",
            "",
        ),
    )
    monkeypatch.setattr(module, "_run_watchdog_journal", lambda lines, timeout_seconds: (0, "", ""))
    monkeypatch.setattr(
        module,
        "_read_qbittorrent_log_state",
        lambda path: {
            "log_exists": True,
            "current_session_started_at": "2026-07-05T19:17:07",
            "fast_resume_rejected_count": 0,
            "recent_storage_error_count": 0,
            "restored_torrent_count": 0,
        },
    )
    monkeypatch.setattr(module, "_recent_download_activity_count", lambda save_path, lookback_minutes, timeout_seconds: 0)
    monkeypatch.setattr(module, "_build_plex_internxt_mirror_observation", lambda timeout_seconds: running_mirror_payload())

    receipt = module.build_receipt(timeout_seconds=5.0, watchdog_journal_lines=50, recent_activity_minutes=20)

    assert receipt["effective_status"] == "blocked"
    assert receipt["blocking_findings"] == [
        "pcloud_cache_mode_not_writes",
        "qbittorrent_write_probe_failed",
    ]
    assert receipt["next_action_component_keys"] == ["pcloud_mount", "qbittorrent"]
    assert receipt["advisory_action_component_keys"] == []


def test_build_receipt_identifies_internxt_cache_pressure_as_specific_advisory(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_internxt_pressure")
    guardrail_payload = degraded_guardrail_payload()
    guardrail_payload["status"] = "pass"
    guardrail_payload["failures"] = []
    guardrail_payload["runtime"]["disk_free_gib"] = {"/": 18.7, "/var/cache/rclone": 18.7}
    guardrail_payload["runtime"]["container_probes"]["pcloud_stream"] = {"ok": True}
    guardrail_payload["runtime"]["container_alias_probe"] = {"ok": True}
    monkeypatch.setattr(
        module,
        "_run_guardrail_verifier",
        lambda timeout_seconds: (0, guardrail_payload, json.dumps(guardrail_payload), ""),
    )
    monkeypatch.setattr(
        module,
        "_run_rclone_vfs_stats",
        lambda rc_addr, timeout_seconds: (
            0,
            (
                rclone_vfs_payload(
                    cache_mode=2,
                    bytes_used=12 * 1024**3,
                    uploads_in_progress=0,
                    uploads_queued=0,
                    cache_max_size=12 * 1024**3,
                    cache_min_free_space=8 * 1024**3,
                )
                if rc_addr == module.RCLONE_RC_ADDR
                else rclone_vfs_payload(
                    cache_mode=3,
                    bytes_used=6 * 1024**3,
                    uploads_in_progress=0,
                    uploads_queued=0,
                    cache_max_size=8 * 1024**3,
                    cache_min_free_space=8 * 1024**3,
                )
            ),
            "{}",
            "",
        ),
    )
    monkeypatch.setattr(module, "_run_watchdog_journal", lambda lines, timeout_seconds: (0, "", ""))
    monkeypatch.setattr(
        module,
        "_read_qbittorrent_log_state",
        lambda path: {
            "log_exists": True,
            "current_session_started_at": "2026-07-05T19:17:07",
            "fast_resume_rejected_count": 0,
            "recent_storage_error_count": 0,
            "restored_torrent_count": 0,
        },
    )
    monkeypatch.setattr(module, "_recent_download_activity_count", lambda save_path, lookback_minutes, timeout_seconds: 0)
    monkeypatch.setattr(module, "_build_plex_internxt_mirror_observation", lambda timeout_seconds: running_mirror_payload())

    receipt = module.build_receipt(timeout_seconds=5.0, watchdog_journal_lines=50, recent_activity_minutes=20)

    assert receipt["effective_status"] == "degraded"
    assert receipt["blocking_findings"] == []
    assert receipt["advisory_findings"] == ["internxt_cache_budget_exceeds_host_headroom"]
    assert receipt["advisory_action_component_keys"] == ["internxt"]


def test_build_receipt_marks_failed_mirror_as_advisory(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_mirror_failed")
    guardrail_payload = degraded_guardrail_payload()
    guardrail_payload["status"] = "pass"
    guardrail_payload["failures"] = []
    guardrail_payload["runtime"]["container_probes"]["pcloud_stream"] = {"ok": True}
    guardrail_payload["runtime"]["container_alias_probe"] = {"ok": True}
    monkeypatch.setattr(
        module,
        "_run_guardrail_verifier",
        lambda timeout_seconds: (0, guardrail_payload, json.dumps(guardrail_payload), ""),
    )
    monkeypatch.setattr(
        module,
        "_run_rclone_vfs_stats",
        lambda rc_addr, timeout_seconds: (
            0,
            rclone_vfs_payload(
                cache_mode=2,
                bytes_used=0,
                uploads_in_progress=0,
                uploads_queued=0,
                cache_max_size=8589934592,
                cache_min_free_space=8589934592,
            ),
            "{}",
            "",
        ),
    )
    monkeypatch.setattr(module, "_run_watchdog_journal", lambda lines, timeout_seconds: (0, "", ""))
    monkeypatch.setattr(
        module,
        "_read_qbittorrent_log_state",
        lambda path: {
            "log_exists": True,
            "current_session_started_at": "2026-07-05T19:17:07",
            "fast_resume_rejected_count": 0,
            "recent_storage_error_count": 0,
            "restored_torrent_count": 0,
        },
    )
    monkeypatch.setattr(module, "_recent_download_activity_count", lambda save_path, lookback_minutes, timeout_seconds: 0)
    monkeypatch.setattr(
        module,
        "_build_plex_internxt_mirror_observation",
        lambda timeout_seconds: {
            "status": "failed",
            "status_source": "status_file",
            "service_active_state": "failed",
            "service_sub_state": "failed",
            "service_result": "failed",
            "phase": "movies",
            "phase_label": "Movies",
            "phase_current": 125,
            "phase_total": 1555,
            "overall_current": 125,
            "overall_total": 2180,
            "stale_seconds": 300,
            "last_error": "internxt_write_failed",
        },
    )

    receipt = module.build_receipt(timeout_seconds=5.0, watchdog_journal_lines=50, recent_activity_minutes=20)

    assert receipt["effective_status"] == "degraded"
    assert receipt["blocking_findings"] == []
    assert receipt["advisory_findings"] == ["plex_internxt_mirror_failed"]
    assert receipt["advisory_action_component_keys"] == ["internxt_mirror"]


def test_build_receipt_does_not_mark_long_running_journal_entry_as_stale_progress(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_mirror_long_entry_not_stale")
    guardrail_payload = degraded_guardrail_payload()
    guardrail_payload["status"] = "pass"
    guardrail_payload["failures"] = []
    guardrail_payload["runtime"]["container_probes"]["pcloud_stream"] = {"ok": True}
    guardrail_payload["runtime"]["container_alias_probe"] = {"ok": True}
    monkeypatch.setattr(
        module,
        "_run_guardrail_verifier",
        lambda timeout_seconds: (0, guardrail_payload, json.dumps(guardrail_payload), ""),
    )
    monkeypatch.setattr(
        module,
        "_run_rclone_vfs_stats",
        lambda rc_addr, timeout_seconds: (
            0,
            rclone_vfs_payload(
                cache_mode=2 if rc_addr == module.RCLONE_RC_ADDR else 3,
                bytes_used=0,
                uploads_in_progress=0,
                uploads_queued=0,
                cache_max_size=8589934592,
                cache_min_free_space=8589934592,
            ),
            "{}",
            "",
        ),
    )
    monkeypatch.setattr(module, "_run_watchdog_journal", lambda lines, timeout_seconds: (0, "", ""))
    monkeypatch.setattr(
        module,
        "_read_qbittorrent_log_state",
        lambda path: {
            "log_exists": True,
            "current_session_started_at": "2026-07-05T19:17:07",
            "fast_resume_rejected_count": 0,
            "recent_storage_error_count": 0,
            "restored_torrent_count": 0,
        },
    )
    monkeypatch.setattr(module, "_recent_download_activity_count", lambda save_path, lookback_minutes, timeout_seconds: 0)
    monkeypatch.setattr(
        module,
        "_build_plex_internxt_mirror_observation",
        lambda timeout_seconds: {
            "status": "running",
            "status_source": "journal",
            "service_active_state": "activating",
            "service_sub_state": "start",
            "service_result": "success",
            "phase": "tv",
            "phase_label": "TV",
            "phase_current": 100,
            "phase_total": 496,
            "overall_current": 1655,
            "overall_total": 2235,
            "stale_seconds": 2400,
            "eta_seconds": None,
            "eta_suppressed_reason": "journal_current_entry_long_running",
            "current_name": "Grey's Anatomy {tmdb-1416}",
            "current_detail": "G",
            "current_entry_progress_ratio": 0.0504,
        },
    )

    receipt = module.build_receipt(timeout_seconds=5.0, watchdog_journal_lines=50, recent_activity_minutes=20)

    assert "plex_internxt_mirror_progress_stale" not in receipt["advisory_findings"]


def test_build_plex_internxt_mirror_observation_estimates_eta_from_journal(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_mirror_journal")
    monkeypatch.setattr(module, "PLEX_INTERNXT_MIRROR_STATUS_PATH", tmp_path / "missing-status.json")
    monkeypatch.setattr(
        module,
        "_run_systemctl_show",
        lambda unit, timeout_seconds: (
            0,
            {
                "ActiveState": "activating",
                "SubState": "start",
                "Result": "success",
                "ExecMainStartTimestamp": "Mon 2026-07-06 05:10:28 CEST",
                "ExecMainExitTimestamp": "",
                "ExecMainStatus": "0",
            },
            "",
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_run_mirror_journal",
        lambda lines, timeout_seconds: (
            0,
            "\n".join(
                [
                    "Jul 06 05:10:28 ubuntu plex-internxt-mirror[2638254]: Movies progress 1/1555: '71 (2014) -> #",
                    "Jul 06 05:15:34 ubuntu plex-internxt-mirror[2665530]: Movies progress 325/1555: Chasing Coral (2017) -> C",
                ]
            ),
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_mirror_phase_totals",
        lambda: (
            {
                "movies": 1555,
                "tv": 496,
                "requested_movies": 88,
                "requested_tv": 37,
                "requested_unsorted": 1,
                "requested_inbox": 58,
            },
            2235,
        ),
    )

    observation = module._build_plex_internxt_mirror_observation(timeout_seconds=5.0)

    assert observation["status"] == "running"
    assert observation["status_source"] == "journal"
    assert observation["phase"] == "movies"
    assert observation["phase_current"] == 325
    assert observation["overall_current"] == 325
    assert observation["overall_total"] == 2235
    assert observation["current_name"] == "Chasing Coral (2017)"
    assert observation["current_detail"] == "C"
    assert isinstance(observation["eta_seconds"], int)
    assert observation["eta_seconds"] > 0
    assert observation["items_per_minute"] is not None
    assert observation["items_per_minute_source"] == "current_phase"


def test_build_plex_internxt_mirror_observation_uses_current_phase_rate_after_transition(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_mirror_phase_rate")
    monkeypatch.setattr(module, "PLEX_INTERNXT_MIRROR_STATUS_PATH", tmp_path / "missing-status.json")
    monkeypatch.setattr(
        module,
        "_run_systemctl_show",
        lambda unit, timeout_seconds: (
            0,
            {
                "ActiveState": "activating",
                "SubState": "start",
                "Result": "success",
                "ExecMainStartTimestamp": "Mon 2026-07-06 05:10:28 CEST",
                "ExecMainExitTimestamp": "",
                "ExecMainStatus": "0",
            },
            "",
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_run_mirror_journal",
        lambda lines, timeout_seconds: (
            0,
            "\n".join(
                [
                    "Jul 06 05:45:52 ubuntu plex-internxt-mirror[2817754]: Movies progress 1375/1555: The Empire Strikes Back (1980) -> T",
                    "Jul 06 05:48:11 ubuntu plex-internxt-mirror[2829985]: Movies progress 1400/1555: The Fly (1986) -> T",
                    "Jul 06 05:54:11 ubuntu plex-internxt-mirror[2862931]: TV progress 75/496: Fixer Upper -> F",
                    "Jul 06 05:54:59 ubuntu plex-internxt-mirror[2866846]: TV progress 100/496: Grey's Anatomy {tmdb-1416} -> G",
                ]
            ),
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_mirror_phase_totals",
        lambda: (
            {
                "movies": 1555,
                "tv": 496,
                "requested_movies": 88,
                "requested_tv": 37,
                "requested_unsorted": 1,
                "requested_inbox": 58,
            },
            2235,
        ),
    )
    monkeypatch.setattr(module, "_path_size_bytes", lambda path, timeout_seconds: None)

    observation = module._build_plex_internxt_mirror_observation(timeout_seconds=5.0)

    assert observation["phase"] == "tv"
    assert observation["overall_current"] == 1655
    assert observation["items_per_minute_source"] == "current_phase"
    assert observation["items_per_minute"] is not None
    assert 30.0 <= observation["items_per_minute"] <= 32.0
    assert isinstance(observation["eta_seconds"], int)
    assert 1000 <= observation["eta_seconds"] <= 1200


def test_build_plex_internxt_mirror_observation_suppresses_eta_until_new_phase_has_two_markers(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_mirror_phase_warmup")
    monkeypatch.setattr(module, "PLEX_INTERNXT_MIRROR_STATUS_PATH", tmp_path / "missing-status.json")
    monkeypatch.setattr(
        module,
        "_run_systemctl_show",
        lambda unit, timeout_seconds: (
            0,
            {
                "ActiveState": "activating",
                "SubState": "start",
                "Result": "success",
                "ExecMainStartTimestamp": "Mon 2026-07-06 05:10:28 CEST",
                "ExecMainExitTimestamp": "",
                "ExecMainStatus": "0",
            },
            "",
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_run_mirror_journal",
        lambda lines, timeout_seconds: (
            0,
            "\n".join(
                [
                    "Jul 06 05:45:52 ubuntu plex-internxt-mirror[2817754]: Movies progress 1375/1555: The Empire Strikes Back (1980) -> T",
                    "Jul 06 05:48:11 ubuntu plex-internxt-mirror[2829985]: Movies progress 1400/1555: The Fly (1986) -> T",
                    "Jul 06 05:54:11 ubuntu plex-internxt-mirror[2862931]: TV progress 75/496: Fixer Upper -> F",
                ]
            ),
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_mirror_phase_totals",
        lambda: (
            {
                "movies": 1555,
                "tv": 496,
                "requested_movies": 88,
                "requested_tv": 37,
                "requested_unsorted": 1,
                "requested_inbox": 58,
            },
            2235,
        ),
    )

    observation = module._build_plex_internxt_mirror_observation(timeout_seconds=5.0)

    assert observation["phase"] == "tv"
    assert observation["overall_current"] == 1630
    assert observation["items_per_minute"] is None
    assert observation["items_per_minute_source"] == ""
    assert observation["eta_seconds"] is None


def test_build_plex_internxt_mirror_observation_suppresses_eta_for_long_running_current_entry(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_host_workload_runtime_health_mirror_long_entry")
    monkeypatch.setattr(module, "PLEX_INTERNXT_MIRROR_STATUS_PATH", tmp_path / "missing-status.json")
    monkeypatch.setattr(module, "PLEX_INTERNXT_MIRROR_JOURNAL_ETA_SUPPRESS_SECONDS", 120)
    monkeypatch.setattr(
        module,
        "_run_systemctl_show",
        lambda unit, timeout_seconds: (
            0,
            {
                "ActiveState": "activating",
                "SubState": "start",
                "Result": "success",
                "ExecMainStartTimestamp": "Mon 2026-07-06 05:10:28 CEST",
                "ExecMainExitTimestamp": "",
                "ExecMainStatus": "0",
            },
            "",
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_run_mirror_journal",
        lambda lines, timeout_seconds: (
            0,
            "\n".join(
                [
                    "Jul 06 05:54:11 ubuntu plex-internxt-mirror[2862931]: TV progress 75/496: Fixer Upper -> F",
                    "Jul 06 05:54:59 ubuntu plex-internxt-mirror[2866846]: TV progress 100/496: Grey's Anatomy {tmdb-1416} -> G",
                ]
            ),
            "",
        ),
    )
    monkeypatch.setattr(
        module,
        "_mirror_phase_totals",
        lambda: (
            {
                "movies": 1555,
                "tv": 496,
                "requested_movies": 88,
                "requested_tv": 37,
                "requested_unsorted": 1,
                "requested_inbox": 58,
            },
            2235,
        ),
    )
    original_parse_iso = module._parse_iso
    monkeypatch.setattr(
        module,
        "_parse_iso",
        lambda value: (
            datetime.fromisoformat("2026-07-06T03:54:59+00:00")
            if str(value) == "2026-07-06T03:54:59Z"
            else original_parse_iso(value)
        ),
    )
    monkeypatch.setattr(
        module,
        "_parse_journal_timestamp",
        lambda value: (
            datetime.fromisoformat("2026-07-06T03:54:11+00:00")
            if "05:54:11" in str(value)
            else datetime.fromisoformat("2026-07-06T03:54:59+00:00")
        ),
    )
    real_datetime = module.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime.fromisoformat("2026-07-06T04:00:30+00:00")
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        module,
        "_path_size_bytes",
        lambda path, timeout_seconds: (
            916_924_061_767 if path and "pcloud/PLEX/TV/Grey's Anatomy" in str(path) else 22_801_542_729
        ),
    )

    observation = module._build_plex_internxt_mirror_observation(timeout_seconds=5.0)

    assert observation["phase"] == "tv"
    assert observation["current_entry_source_bytes"] == 916_924_061_767
    assert observation["current_entry_dest_bytes"] == 22_801_542_729
    assert observation["current_entry_progress_ratio"] is not None
    assert observation["current_entry_progress_ratio"] < 0.95
    assert observation["items_per_minute"] is not None
    assert observation["eta_seconds"] is None
    assert observation["eta_suppressed_reason"] == "journal_current_entry_long_running"


def test_verify_receipt_passes_for_coherent_receipt(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_host_workload_runtime_health")
    receipt_path = tmp_path / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-05T17:18:54Z",
        "updated_at": "2026-07-05T17:18:54Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "degraded",
        "runtime_status": "degraded",
        "runtime_ready": False,
        "source": "script:materialize_host_workload_runtime_health.py",
        "source_runtime": "host_workload.runtime_health",
        "observed_at": "2026-07-05T17:18:54Z",
        "blocking_count": 0,
        "advisory_count": 2,
        "blocking_findings": [],
        "advisory_findings": [
            "plex_namespace_restart_deferred_until_idle",
            "qbittorrent_fast_resume_mismatches_present",
        ],
        "next_action_component_keys": [],
        "advisory_action_component_keys": ["plex", "qbittorrent"],
        "next_actions": [],
        "advisory_actions": [
            {
                "component_key": "plex",
                "component_label": "Plex pCloud namespace",
                "action": "restart_plex_when_idle",
                "reason": "plex_namespace_restart_deferred_until_idle",
                "href": "",
                "label": "Restart Plex after active sessions end",
                "method": "manual",
            },
            {
                "component_key": "qbittorrent",
                "component_label": "qBittorrent resume state",
                "action": "recheck_or_requeue_mismatched_torrents",
                "reason": "qbittorrent_fast_resume_mismatches_present",
                "href": "",
                "label": "Recheck or requeue mismatched torrents",
                "method": "manual",
            },
        ],
        "runtime_observation": {
            "guardrail_verifier_status": "fail",
            "qbittorrent_write_probe_ok": True,
            "pcloud_cache_mode": "writes",
            "internxt_cache_mode": "writes",
            "internxt_cache_bytes_used": 0,
            "plex_internxt_mirror": {
                "status": "running",
                "status_source": "journal",
                "service_active_state": "activating",
                "service_result": "success",
            },
        },
        "secret_leak_detected": False,
        "failures": [],
        "stdout_tail": "verifier_returncode=1 verifier_status=fail runtime_status=degraded",
        "stderr_tail": "",
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is True
    assert verified["status"] == "pass"
    assert verified["effective_status"] == "degraded"
    assert verified["runtime_status"] == "degraded"


def test_verify_receipt_fails_when_actions_are_stale(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_host_workload_runtime_health_stale")
    receipt_path = tmp_path / "HOST_WORKLOAD_RUNTIME_HEALTH.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-05T17:18:54Z",
        "updated_at": "2026-07-05T17:18:54Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready",
        "runtime_status": "ready",
        "runtime_ready": True,
        "source": "script:materialize_host_workload_runtime_health.py",
        "source_runtime": "host_workload.runtime_health",
        "observed_at": "2026-07-05T17:18:54Z",
        "blocking_count": 0,
        "advisory_count": 1,
        "blocking_findings": [],
        "advisory_findings": ["qbittorrent_fast_resume_mismatches_present"],
        "next_action_component_keys": [],
        "advisory_action_component_keys": [],
        "next_actions": [],
        "advisory_actions": [],
        "runtime_observation": {"plex_internxt_mirror": {}},
        "secret_leak_detected": False,
        "failures": [],
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is False
    assert "runtime_status_mismatch" in verified["failures"]
    assert "runtime_ready_mismatch" in verified["failures"]
    assert "advisory_action_component_keys_mismatch" in verified["failures"]
    assert "advisory_actions_mismatch" in verified["failures"]
