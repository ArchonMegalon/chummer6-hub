from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import sys
import time
from pathlib import Path


MATERIALIZE = Path(__file__).resolve().parents[1] / "scripts" / "materialize_qbittorrent_staging_hygiene.py"
VERIFY = Path(__file__).resolve().parents[1] / "scripts" / "verify_qbittorrent_staging_hygiene.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_receipt_degrades_for_orphan_partials_and_dead_meta(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_degraded")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    orphan = staging_root / "Old.Show.S01E01.mkv.deadbeef.partial"
    orphan.write_bytes(b"x" * 1024)
    old_epoch = time.time() - (8 * 24 * 60 * 60)
    os.utime(orphan, (old_epoch, old_epoch))
    referenced_target = staging_root / "Live.Show.S01E02.mkv"
    referenced_partial = staging_root / "Live.Show.S01E02.mkv.1234abcd.partial"
    referenced_partial.write_bytes(b"y" * 512)
    os.utime(referenced_partial, (old_epoch, old_epoch))

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(module, "_fetch_preferences", lambda opener, base_url, timeout_seconds: {"queueing_enabled": True, "max_active_downloads": 2, "max_active_torrents": 3, "max_active_uploads": 3, "dont_count_slow_torrents": True})
    monkeypatch.setattr(
        module,
        "_fetch_torrents",
        lambda opener, base_url, timeout_seconds: [
            {
                "hash": "abc",
                "save_path": str(staging_root),
                "state": "downloading",
                "name": "Live Show",
                "added_on": int(time.time()) - 600,
                "last_activity": int(time.time()) - 60,
            },
            {
                "hash": "deadmeta",
                "save_path": str(staging_root),
                "state": "metaDL",
                "name": "Dead Meta",
                "added_on": int(time.time()) - 7200,
                "last_activity": int(time.time()) - 7200,
                "num_seeds": 0,
                "num_complete": 0,
            },
        ],
    )
    monkeypatch.setattr(
        module,
        "_referenced_file_paths",
        lambda opener, base_url, torrents, timeout_seconds, path_mappings: ({module._normalize_path(referenced_target)}, 1),
    )
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0, min_partial_age_days=7, sample_limit=5)

    assert receipt["status"] == "pass"
    assert receipt["runtime_status"] == "degraded"
    assert receipt["blocking_findings"] == []
    assert receipt["advisory_findings"] == [
        "qbittorrent_orphan_partials_present",
        "qbittorrent_dead_metadata_downloads_present",
    ]
    observation = receipt["runtime_observation"]
    assert observation["orphan_partial_file_count"] == 1
    assert observation["dead_meta_candidate_count"] == 1
    assert observation["referenced_file_count"] == 1


def test_build_receipt_blocks_when_api_and_staging_are_unavailable(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_blocked")
    missing_root = tmp_path / "missing-downloads"
    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "", "QBIT_PASS": "", "QBIT_SAVE_PATH": str(missing_root)})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (None, "missing_qbittorrent_credentials"))

    receipt = module.build_receipt(timeout_seconds=5.0)

    assert receipt["runtime_status"] == "blocked"
    assert receipt["blocking_findings"] == [
        "qbittorrent_api_unavailable",
        "qbittorrent_staging_root_unreadable",
    ]
    assert receipt["advisory_findings"] == []


def test_build_receipt_can_prune_orphan_partials(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_prune")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    orphan = staging_root / "Old.Show.S01E01.mkv.deadbeef.partial"
    orphan.write_bytes(b"x" * 2048)
    old_epoch = time.time() - (8 * 24 * 60 * 60)
    os.utime(orphan, (old_epoch, old_epoch))

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(module, "_fetch_preferences", lambda opener, base_url, timeout_seconds: {"queueing_enabled": True, "max_active_downloads": 2, "max_active_torrents": 3, "max_active_uploads": 3, "dont_count_slow_torrents": True})
    monkeypatch.setattr(module, "_fetch_torrents", lambda opener, base_url, timeout_seconds: [])
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0, min_partial_age_days=7, apply_prune_orphan_partials=True)

    assert orphan.exists() is False
    observation = receipt["runtime_observation"]
    assert observation["prune_orphan_partials_applied"] is True
    assert observation["pruned_orphan_partial_file_count"] == 1
    assert observation["orphan_partial_file_count"] == 0
    assert receipt["runtime_status"] == "ready"


def test_build_receipt_surfaces_queueing_drift_and_can_apply_guardrails(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_queueing")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    prefs_state = {
        "queueing_enabled": False,
        "max_active_downloads": 2,
        "max_active_torrents": 3,
        "max_active_uploads": 3,
        "dont_count_slow_torrents": False,
    }

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(module, "_fetch_preferences", lambda opener, base_url, timeout_seconds: dict(prefs_state))
    monkeypatch.setattr(
        module,
        "_set_preferences",
        lambda opener, base_url, timeout_seconds, changes: prefs_state.update(changes) or "Ok.",
    )
    monkeypatch.setattr(
        module,
        "_fetch_torrents",
        lambda opener, base_url, timeout_seconds: [
            {
                "hash": "a",
                "save_path": str(staging_root),
                "state": "downloading",
                "name": "A",
                "added_on": int(time.time()) - 60,
                "last_activity": int(time.time()) - 10,
            }
        ],
    )
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    degraded = module.build_receipt(timeout_seconds=5.0)
    assert degraded["advisory_findings"] == ["qbittorrent_queueing_disabled"]

    ready = module.build_receipt(timeout_seconds=5.0, apply_enable_queueing=True)
    assert ready["runtime_status"] == "ready"
    assert ready["runtime_observation"]["queueing_enabled"] is True
    assert ready["runtime_observation"]["runtime_guardrail_changes_applied"] == {
        "queueing_enabled": True,
        "dont_count_slow_torrents": True,
    }


def test_build_receipt_can_clear_forced_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_clear_forced")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrents_state = [
        {
            "hash": "forced-dl",
            "save_path": str(staging_root),
            "state": "forcedDL",
            "force_start": True,
            "name": "Forced Download",
            "added_on": int(time.time()) - 600,
            "last_activity": int(time.time()) - 30,
        },
        {
            "hash": "forced-meta",
            "save_path": str(staging_root),
            "state": "forcedMetaDL",
            "force_start": True,
            "name": "Forced Metadata",
            "added_on": int(time.time()) - 600,
            "last_activity": int(time.time()) - 30,
        },
        {
            "hash": "download-a",
            "save_path": str(staging_root),
            "state": "downloading",
            "force_start": False,
            "name": "Download A",
            "added_on": int(time.time()) - 600,
            "last_activity": int(time.time()) - 30,
        },
        {
            "hash": "download-b",
            "save_path": str(staging_root),
            "state": "downloading",
            "force_start": False,
            "name": "Download B",
            "added_on": int(time.time()) - 600,
            "last_activity": int(time.time()) - 30,
        },
    ]

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(
        module,
        "_fetch_torrents",
        lambda opener, base_url, timeout_seconds: [dict(item) for item in torrents_state],
    )

    def fake_set_force_start(opener, base_url, timeout_seconds, hashes, value):
        assert value is False
        for item in torrents_state:
            if item["hash"] in hashes:
                item["force_start"] = False
                item["state"] = "queuedDL"
        return "Ok."

    monkeypatch.setattr(module, "_set_force_start", fake_set_force_start)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    degraded = module.build_receipt(timeout_seconds=5.0)
    assert degraded["advisory_findings"] == [
        "qbittorrent_active_download_count_exceeds_limit",
        "qbittorrent_forced_downloads_present",
    ]

    ready = module.build_receipt(timeout_seconds=5.0, apply_clear_forced_downloads=True)
    assert ready["runtime_status"] == "ready"
    assert ready["runtime_observation"]["forced_download_count"] == 0
    assert ready["runtime_observation"]["forced_download_hashes_cleared"] == ["forced-dl", "forced-meta"]


def test_build_receipt_can_requeue_dead_stalled_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_requeue")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "stalled-a",
            "save_path": str(staging_root),
            "state": "stalledDL",
            "name": "Old Stalled A",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
        },
        {
            "hash": "stalled-b",
            "save_path": str(staging_root),
            "state": "stalledDL",
            "name": "Old Stalled B",
            "added_on": int(time.time()) - 4000,
            "last_activity": int(time.time()) - 4000,
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        assert state in {"pause", "resume"}
        if state != "resume":
            return "Ok."
        for item in torrent_states:
            if item["hash"] in hashes:
                item["state"] = "downloading"
        return "Ok."

    action_calls: list[tuple[str, str]] = []

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        action_calls.append((str(action), next(iter(hashes)) if hashes else ""))
        assert action in {"reannounce", "recheck"}
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    degraded = module.build_receipt(timeout_seconds=5.0, min_dead_stalled_age_minutes=30)
    assert degraded["runtime_status"] == "degraded"
    assert degraded["advisory_findings"] == ["qbittorrent_dead_stalled_downloads_present"]

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_stalled_age_minutes=30,
        apply_requeue_dead_stalled_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_stalled_requeue_count"] == 2
    assert observation["dead_stalled_hashes_requeued"] == ["stalled-a", "stalled-b"]
    assert observation["dead_stalled_requeue_errors"] == []
    assert observation["dead_stalled_candidate_count"] == 0
    assert sorted({action for action, _ in action_calls}) == ["reannounce", "recheck"]


def test_build_receipt_treats_zero_speed_old_downloading_as_stalled(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_requeue_downloading_zero_speed")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "zero-speed-down",
            "save_path": str(staging_root),
            "state": "downloading",
            "name": "Frozen Download",
            "progress": 0.74,
            "dlspeed": 0,
            "upspeed": 0,
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        assert state in {"pause", "resume"}
        if state == "resume":
            for item in torrent_states:
                if item["hash"] in hashes:
                    item["state"] = "downloading"
                    item["dlspeed"] = 12
        return "Ok."

    action_calls: list[tuple[str, str]] = []

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        action_calls.append((str(action), next(iter(hashes)) if hashes else ""))
        assert action in {"reannounce", "recheck"}
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_stalled_age_minutes=30,
        apply_requeue_dead_stalled_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_stalled_requeue_count"] == 1
    assert observation["dead_stalled_hashes_requeued"] == ["zero-speed-down"]
    assert sorted({action for action, _ in action_calls}) == ["reannounce", "recheck"]


def test_build_receipt_excludes_zero_speed_candidates_with_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_downloading_active")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "active-down",
            "save_path": str(staging_root),
            "state": "downloading",
            "name": "Live Download",
            "progress": 1.0,
            "dlspeed": 0,
            "upspeed": 0,
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 2,
            "num_complete": 1,
        }
    ]

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", lambda opener, base_url, timeout_seconds: [dict(item) for item in torrent_states])
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(timeout_seconds=5.0, min_dead_stalled_age_minutes=30)
    assert ready["runtime_status"] == "ready"
    assert ready["runtime_observation"]["dead_stalled_candidate_count"] == 0


def test_build_receipt_requeues_stalled_downloads_until_clear(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_requeue_cycles")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    state_steps = [["stalledDL"], ["stalledDL"], ["downloading"]]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        state = state_steps.pop(0) if state_steps else ["downloading"]
        return [
            {
                "hash": "stalled-a",
                "save_path": str(staging_root),
                "state": state[0],
                "name": "Old Stalled A",
                "added_on": int(time.time()) - 7200,
                "last_activity": int(time.time()) - 7200,
                "num_seeds": 0,
                "num_complete": 0,
            }
        ]

    state_calls: list[str] = []

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        state_calls.append(str(state))
        return "Ok."

    action_calls: list[str] = []

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        action_calls.append(str(action))
        return "Ok."

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(float(seconds))

    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_stalled_age_minutes=30,
        max_recovery_cycles=5,
        recovery_wait_seconds=7.5,
        apply_requeue_dead_stalled_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_stalled_requeue_count"] == 1
    assert observation["dead_stalled_recovery_cycles"] == 2
    assert sleep_calls == [7.5, 7.5]
    assert state_calls.count("pause") == 2
    assert state_calls.count("resume") == 2
    assert sorted(set(action_calls)) == ["reannounce", "recheck"]


def test_build_receipt_never_deletes_stubborn_started_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_delete")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "stalled-a",
            "save_path": str(staging_root),
            "state": "stalledDL",
            "name": "Old Stalled A",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
            "downloaded": 512 * 1024 * 1024,
            "completed": 512 * 1024 * 1024,
            "amount_left": 512 * 1024 * 1024,
            "total_size": 1024 * 1024 * 1024,
            "progress": 0.5,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    def fake_delete_torrents(opener, base_url, timeout_seconds, hashes):
        raise AssertionError("stalled payload deletion must stay unreachable")

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        return "Ok."

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_delete_torrents", fake_delete_torrents)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_stalled_age_minutes=30,
        max_recovery_cycles=1,
        recovery_wait_seconds=0,
        apply_requeue_dead_stalled_downloads=True,
        apply_delete_dead_stalled_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "degraded"
    assert observation["dead_stalled_requeue_count"] == 1
    assert observation["dead_stalled_delete_count"] == 0
    assert observation["dead_stalled_hashes_deleted"] == []
    assert observation["dead_stalled_delete_errors"] == ["started_torrent_preservation_policy"]
    assert [item["hash"] for item in torrent_states] == ["stalled-a"]


def test_build_receipt_continues_if_reannounce_fails(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_requeue_reannounce_failure")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "stalled-a",
            "save_path": str(staging_root),
            "state": "stalledDL",
            "name": "Old Stalled A",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        if state == "resume":
            for item in torrent_states:
                if item["hash"] in hashes:
                    item["state"] = "downloading"
        return "Ok."

    calls: list[str] = []

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        calls.append(str(action))
        if action == "reannounce":
            raise urllib.error.URLError("reannounce unavailable")
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_stalled_age_minutes=30,
        apply_requeue_dead_stalled_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_stalled_requeue_count"] == 1
    assert observation["dead_stalled_hashes_requeued"] == ["stalled-a"]
    assert observation["dead_stalled_requeue_errors"] == ["stalled-a:reannounce:URLError"]
    assert sorted(set(calls)) == ["reannounce", "recheck"]


def test_build_receipt_can_requeue_dead_meta_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_requeue_meta")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "meta-a",
            "save_path": str(staging_root),
            "state": "metaDL",
            "name": "Old Metadata A",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
        },
        {
            "hash": "meta-b",
            "save_path": str(staging_root),
            "state": "forcedMetaDL",
            "name": "Old Metadata B",
            "added_on": int(time.time()) - 4000,
            "last_activity": int(time.time()) - 4000,
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    action_calls: list[tuple[str, str]] = []

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        assert state in {"pause", "resume"}
        if state != "resume":
            return "Ok."
        for item in torrent_states:
            if item["hash"] in hashes:
                item["state"] = "downloading"
        return "Ok."

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        action_calls.append((str(action), next(iter(hashes)) if hashes else ""))
        assert action in {"reannounce", "recheck"}
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_meta_age_minutes=30,
        apply_requeue_dead_meta_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_meta_requeue_count"] == 2
    assert observation["dead_meta_hashes_requeued"] == ["meta-a", "meta-b"]
    assert observation["dead_meta_requeue_errors"] == []
    assert observation["dead_meta_candidate_count"] == 0
    assert sorted({action for action, _ in action_calls}) == ["reannounce", "recheck"]


def test_build_receipt_can_delete_stubborn_dead_meta_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_delete_meta")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "meta-a",
            "save_path": str(staging_root),
            "state": "metaDL",
            "name": "Old Metadata A",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    delete_calls: list[tuple[str, str]] = []

    def fake_delete_torrents(opener, base_url, timeout_seconds, hashes):
        delete_calls.append((base_url, "|".join(sorted(hashes))))
        torrent_states.clear()

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        return "Ok."

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_delete_torrents", fake_delete_torrents)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_meta_age_minutes=30,
        max_recovery_cycles=1,
        recovery_wait_seconds=0,
        apply_requeue_dead_meta_downloads=True,
        apply_delete_dead_meta_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_meta_requeue_count"] == 1
    assert observation["dead_meta_delete_count"] == 1
    assert observation["dead_meta_hashes_deleted"] == ["meta-a"]
    assert delete_calls == [("http://127.0.0.1:18083", "meta-a")]


def test_dead_meta_candidates_exclude_complete_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_meta_filtering")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    now = int(time.time())
    torrent_states = [
        {
            "hash": "meta-active",
            "save_path": str(staging_root),
            "state": "metaDL",
            "name": "Fresh Metadata",
            "added_on": now - (5 * 60),
            "last_activity": now - (2 * 60),
            "num_seeds": 0,
            "num_complete": 0,
        },
        {
            "hash": "meta-complete",
            "save_path": str(staging_root),
            "state": "metaDL",
            "name": "Completed Metadata",
            "added_on": now - (2 * 60 * 60),
            "last_activity": now - (40 * 60),
            "num_seeds": 0,
            "num_complete": 1,
            "is_complete": True,
        },
        {
            "hash": "meta-valid",
            "save_path": str(staging_root),
            "state": "metaDL",
            "name": "Stale Metadata",
            "added_on": now - (2 * 60 * 60),
            "last_activity": now - (40 * 60),
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", lambda opener, base_url, timeout_seconds: [dict(item) for item in torrent_states])
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0, min_dead_meta_age_minutes=30)

    assert receipt["runtime_observation"]["dead_meta_candidate_count"] == 1
    assert receipt["runtime_observation"]["dead_meta_candidate_names"] == ["Stale Metadata"]


def test_build_receipt_can_requeue_dead_checking_downloads(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_requeue_checking")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    torrent_states = [
        {
            "hash": "checking-a",
            "save_path": str(staging_root),
            "state": "checkingDL",
            "name": "Old Checking A",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 0,
            "dlspeed": 0,
        },
        {
            "hash": "checking-b",
            "save_path": str(staging_root),
            "state": "checkingDL",
            "name": "Old Checking B (complete)",
            "added_on": int(time.time()) - 7200,
            "last_activity": int(time.time()) - 7200,
            "num_seeds": 0,
            "num_complete": 1,
            "dlspeed": 0,
        },
    ]

    def fake_fetch_torrents(opener, base_url, timeout_seconds):
        return [dict(item) for item in torrent_states]

    def fake_set_torrent_state(opener, base_url, timeout_seconds, hashes, state):
        assert state in {"pause", "resume"}
        if state != "resume":
            return "Ok."
        for item in torrent_states:
            if item["hash"] in hashes:
                item["state"] = "downloading"
        return "Ok."

    calls: list[str] = []

    def fake_set_torrent_action(opener, base_url, timeout_seconds, hashes, action):
        calls.append(str(action))
        assert action in {"reannounce", "recheck"}
        return "Ok."

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", fake_fetch_torrents)
    monkeypatch.setattr(module, "_set_torrent_state", fake_set_torrent_state)
    monkeypatch.setattr(module, "_set_torrent_action", fake_set_torrent_action)
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    degraded = module.build_receipt(timeout_seconds=5.0, min_dead_checking_age_minutes=30)
    assert degraded["advisory_findings"] == ["qbittorrent_long_checking_downloads_present"]

    ready = module.build_receipt(
        timeout_seconds=5.0,
        min_dead_checking_age_minutes=30,
        apply_requeue_dead_checking_downloads=True,
    )
    observation = ready["runtime_observation"]
    assert ready["runtime_status"] == "ready"
    assert observation["dead_checking_requeue_count"] == 2
    assert observation["dead_checking_hashes_requeued"] == ["checking-a", "checking-b"]
    assert observation["dead_checking_requeue_errors"] == []
    assert observation["dead_checking_candidate_count"] == 0
    assert sorted(set(calls)) == ["reannounce", "recheck"]


def test_dead_stalled_candidates_respect_inactivity_window(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_inactive_stalled")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    now = int(time.time())
    torrent_states = [
        {
            "hash": "active-stalled",
            "save_path": str(staging_root),
            "state": "stalledDL",
            "name": "Active Stalled",
            "added_on": now - (2 * 60 * 60),
            "last_activity": now - (2 * 60),
            "num_seeds": 0,
            "num_complete": 0,
        },
        {
            "hash": "quiet-stalled",
            "save_path": str(staging_root),
            "state": "stalledDL",
            "name": "Quiet Stalled",
            "added_on": now - (2 * 60 * 60),
            "last_activity": now - (40 * 60),
            "num_seeds": 0,
            "num_complete": 0,
        },
    ]

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", lambda opener, base_url, timeout_seconds: [dict(item) for item in torrent_states])
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0, min_dead_stalled_age_minutes=30)

    assert receipt["runtime_observation"]["dead_stalled_candidate_count"] == 1
    assert receipt["runtime_observation"]["dead_stalled_candidate_names"] == ["Quiet Stalled"]


def test_dead_checking_candidates_respect_inactivity_window(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_inactive_checking")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    now = int(time.time())
    torrent_states = [
        {
            "hash": "active-checking",
            "save_path": str(staging_root),
            "state": "checkingDL",
            "name": "Active Checking",
            "added_on": now - (2 * 60 * 60),
            "last_activity": now - (2 * 60),
            "num_seeds": 0,
            "num_complete": 0,
            "dlspeed": 0,
        },
        {
            "hash": "quiet-checking",
            "save_path": str(staging_root),
            "state": "checkingDL",
            "name": "Quiet Checking",
            "added_on": now - (2 * 60 * 60),
            "last_activity": now - (40 * 60),
            "num_seeds": 0,
            "num_complete": 0,
            "dlspeed": 0,
        },
        {
            "hash": "checking-fresh",
            "save_path": str(staging_root),
            "state": "checkingDL",
            "name": "Freshly Added",
            "added_on": now - (5 * 60),
            "last_activity": now - (40 * 60),
            "num_seeds": 0,
            "num_complete": 0,
            "dlspeed": 0,
        },
    ]

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", lambda opener, base_url, timeout_seconds: [dict(item) for item in torrent_states])
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0, min_dead_checking_age_minutes=30)

    assert receipt["runtime_observation"]["dead_checking_candidate_count"] == 1
    assert receipt["runtime_observation"]["dead_checking_candidate_names"] == ["Quiet Checking"]


def test_env_int_reads_values_and_falls_back_on_bad_input(monkeypatch) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_env_int")
    monkeypatch.setenv("QB_ENV_SAMPLE_INT", "17")
    assert module._env_int({}, "QB_ENV_SAMPLE_INT", 11) == 17
    monkeypatch.setenv("QB_ENV_SAMPLE_INT", "not-int")
    assert module._env_int({}, "QB_ENV_SAMPLE_INT", 11) == 11


def test_build_receipt_excludes_slow_downloads_from_effective_queue_pressure(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_slow_exempt")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
            "slow_torrent_dl_rate_threshold": 2,
            "slow_torrent_ul_rate_threshold": 2,
            "slow_torrent_inactive_timer": 60,
        },
    )
    monkeypatch.setattr(
        module,
        "_fetch_torrents",
        lambda opener, base_url, timeout_seconds: [
            {
                "hash": "download-a",
                "save_path": str(staging_root),
                "state": "downloading",
                "force_start": False,
                "name": "Download A",
                "added_on": int(time.time()) - 600,
                "last_activity": int(time.time()) - 30,
                "dlspeed": 400000,
                "upspeed": 0,
            },
            {
                "hash": "download-b",
                "save_path": str(staging_root),
                "state": "downloading",
                "force_start": False,
                "name": "Download B",
                "added_on": int(time.time()) - 600,
                "last_activity": int(time.time()) - 30,
                "dlspeed": 250000,
                "upspeed": 0,
            },
            {
                "hash": "download-slow",
                "save_path": str(staging_root),
                "state": "downloading",
                "force_start": False,
                "name": "Download Slow",
                "added_on": int(time.time()) - 600,
                "last_activity": int(time.time()) - 30,
                "dlspeed": 288,
                "upspeed": 0,
            },
        ],
    )
    monkeypatch.setattr(module, "_referenced_file_paths", lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0))
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0)

    assert receipt["runtime_status"] == "ready"
    assert receipt["runtime_observation"]["downloading_state_count"] == 3
    assert receipt["runtime_observation"]["effective_downloading_state_count"] == 2


def test_build_receipt_maps_container_download_path_back_to_host_staging_root(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_mapped_paths")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()
    referenced_partial = staging_root / "Mapped.Show.S01E01.mkv.abcdef.partial"
    referenced_partial.write_bytes(b"z" * 512)
    old_epoch = time.time() - (8 * 24 * 60 * 60)
    os.utime(referenced_partial, (old_epoch, old_epoch))

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "docker_container_mount_mappings", lambda container_name, timeout_seconds=15.0: [("/downloads", str(staging_root))])
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
            "save_path": "/downloads",
        },
    )
    monkeypatch.setattr(
        module,
        "_fetch_torrents",
        lambda opener, base_url, timeout_seconds: [
            {
                "hash": "mapped",
                "save_path": "/downloads",
                "state": "downloading",
                "name": "Mapped Show",
                "added_on": int(time.time()) - 600,
                "last_activity": int(time.time()) - 30,
            }
        ],
    )
    monkeypatch.setattr(
        module,
        "_fetch_torrent_files",
        lambda opener, base_url, torrent_hash, timeout_seconds: [{"name": "Mapped.Show.S01E01.mkv"}],
    )

    receipt = module.build_receipt(timeout_seconds=5.0, min_partial_age_days=7)

    assert receipt["runtime_status"] == "ready"
    assert receipt["runtime_observation"]["staging_root"] == str(staging_root)
    assert receipt["runtime_observation"]["referenced_file_count"] == 1
    assert receipt["runtime_observation"]["orphan_partial_file_count"] == 0


def test_verify_receipt_passes_for_coherent_payload(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_qbittorrent_staging_hygiene")
    receipt_path = tmp_path / "QBITTORRENT_STAGING_HYGIENE.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-05T17:18:54Z",
        "updated_at": "2026-07-05T17:18:54Z",
        "observed_at": "2026-07-05T17:18:54Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "degraded",
        "runtime_status": "degraded",
        "runtime_ready": False,
        "source": "script:materialize_qbittorrent_staging_hygiene.py",
        "source_runtime": "qbittorrent.staging_hygiene",
        "blocking_count": 0,
        "advisory_count": 1,
        "blocking_findings": [],
        "advisory_findings": ["qbittorrent_orphan_partials_present"],
        "next_action_component_keys": [],
        "advisory_action_component_keys": ["qbittorrent_staging"],
        "next_actions": [],
        "advisory_actions": [
            {
                "component_key": "qbittorrent_staging",
                "component_label": "qBittorrent staging hygiene",
                "action": "prune_orphan_partial_files",
                "reason": "qbittorrent_orphan_partials_present",
                "href": "",
                "label": "Prune orphan partial files",
                "method": "manual",
            }
        ],
        "runtime_observation": {
            "qbittorrent_api_ok": True,
            "staging_root_ok": True,
            "orphan_partial_file_count": 41,
        },
        "failures": [],
        "secret_leak_detected": False,
        "stdout_tail": "observed_at=2026-07-05T17:18:54Z source=script:materialize_qbittorrent_staging_hygiene.py runtime_status=degraded orphan_partials=41",
        "stderr_tail": "",
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is True
    assert verified["status"] == "pass"
    assert verified["runtime_status"] == "degraded"


def test_verify_receipt_fails_for_unsafe_stdout_tail_source(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_qbittorrent_staging_hygiene_stdout_source")
    receipt_path = tmp_path / "QBITTORRENT_STAGING_HYGIENE.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-05T17:18:54Z",
        "updated_at": "2026-07-05T17:18:54Z",
        "observed_at": "2026-07-05T17:18:54Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready",
        "runtime_status": "ready",
        "runtime_ready": True,
        "source": "script:materialize_qbittorrent_staging_hygiene.py",
        "source_runtime": "qbittorrent.staging_hygiene",
        "blocking_count": 0,
        "advisory_count": 0,
        "blocking_findings": [],
        "advisory_findings": [],
        "next_action_component_keys": [],
        "advisory_action_component_keys": [],
        "next_actions": [],
        "advisory_actions": [],
        "runtime_observation": {"qbittorrent_api_ok": True, "staging_root_ok": True},
        "failures": [],
        "secret_leak_detected": False,
        "stdout_tail": "observed_at=2026-07-05T17:18:54Z source=/docker/chummercomplete/chummer.run-services/scripts/materialize_qbittorrent_staging_hygiene.py runtime_status=ready",
        "stderr_tail": "",
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is False
    assert "unsafe_stdout_tail_source" in verified["failures"]


def test_verify_receipt_fails_when_actions_do_not_match_findings(tmp_path: Path) -> None:
    module = _load(VERIFY, "verify_qbittorrent_staging_hygiene_stale")
    receipt_path = tmp_path / "QBITTORRENT_STAGING_HYGIENE.generated.json"
    payload = {
        "contract_name": module.CONTRACT_NAME,
        "generated_at_utc": "2026-07-05T17:18:54Z",
        "updated_at": "2026-07-05T17:18:54Z",
        "observed_at": "2026-07-05T17:18:54Z",
        "status": "pass",
        "structural_status": "pass",
        "effective_status": "ready",
        "runtime_status": "ready",
        "runtime_ready": True,
        "source": "script:materialize_qbittorrent_staging_hygiene.py",
        "source_runtime": "qbittorrent.staging_hygiene",
        "blocking_count": 0,
        "advisory_count": 1,
        "blocking_findings": [],
        "advisory_findings": ["qbittorrent_orphan_partials_present"],
        "next_action_component_keys": [],
        "advisory_action_component_keys": [],
        "next_actions": [],
        "advisory_actions": [],
        "runtime_observation": {},
        "failures": [],
        "secret_leak_detected": False,
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verified, passed = module.verify_receipt(receipt_path)

    assert passed is False
    assert "runtime_status_mismatch" in verified["failures"]
    assert "runtime_ready_mismatch" in verified["failures"]
    assert "advisory_actions_mismatch" in verified["failures"]


def test_build_receipt_stdout_tail_uses_public_source_label(monkeypatch, tmp_path: Path) -> None:
    module = _load(MATERIALIZE, "materialize_qbittorrent_staging_hygiene_stdout_source")
    staging_root = tmp_path / "downloads"
    staging_root.mkdir()

    monkeypatch.setattr(module, "_load_env", lambda path: {"QBIT_USER": "tibor", "QBIT_PASS": "pw"})
    monkeypatch.setattr(module, "_login", lambda base_url, username, password, timeout_seconds: (object(), ""))
    monkeypatch.setattr(
        module,
        "_fetch_preferences",
        lambda opener, base_url, timeout_seconds: {
            "queueing_enabled": True,
            "max_active_downloads": 2,
            "max_active_torrents": 3,
            "max_active_uploads": 3,
            "dont_count_slow_torrents": True,
        },
    )
    monkeypatch.setattr(module, "_fetch_torrents", lambda opener, base_url, timeout_seconds: [])
    monkeypatch.setattr(
        module,
        "_referenced_file_paths",
        lambda opener, base_url, torrents, timeout_seconds, path_mappings: (set(), 0),
    )
    monkeypatch.setattr(module, "QBIT_SAVE_PATH_DEFAULT", str(staging_root))

    receipt = module.build_receipt(timeout_seconds=5.0)

    assert "source=script:materialize_qbittorrent_staging_hygiene.py" in receipt["stdout_tail"]
    assert "/docker/chummercomplete" not in receipt["stdout_tail"]
