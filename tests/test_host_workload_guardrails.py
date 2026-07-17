from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_host_workload_guardrails.py"


def run_repo_only() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--repo-only"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def test_repo_only_guardrail_verifier_passes() -> None:
    result = run_repo_only()
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    repo_paths = {entry["repo_path"] for entry in payload["repo_assets"]}
    assert "ops/host-workload/rclone-mount-watchdog.sh" in repo_paths
    assert "ops/host-workload/rclone-mount-pcloud-cache-tuning.conf" in repo_paths
    assert "ops/host-workload/media-cache-guard.service.d-10-budget.conf" in repo_paths
    assert "ops/host-workload/plex-internxt-mirror.sh" in repo_paths
    assert "ops/host-workload/qbittorrent-storage-watchdog.sh" in repo_paths
    assert "ops/host-workload/qbittorrent-staging-hygiene-watchdog.sh" in repo_paths
    assert "ops/host-workload/qbittorrent-staging-hygiene-watchdog.service" in repo_paths
    assert "ops/host-workload/qbittorrent-staging-hygiene-watchdog.timer" in repo_paths
    assert "ops/host-workload/qbittorrent-staging-hygiene-watchdog.default" in repo_paths


def test_repo_only_guardrail_verifier_reports_expected_snippets() -> None:
    result = run_repo_only()
    payload = json.loads(result.stdout)
    assets = {entry["repo_path"]: entry for entry in payload["repo_assets"]}

    assert assets["ops/host-workload/rclone-mount-internxt-cache-tuning.conf"]["expected_snippets_ok"] is True
    assert assets["ops/host-workload/rclone-mount-pcloud-cache-tuning.conf"]["expected_snippets_ok"] is True
    assert assets["ops/host-workload/rclone-mount-watchdog.sh"]["expected_snippets_ok"] is True


def test_repo_only_guardrail_verifier_tracks_stale_namespace_recovery_snippets() -> None:
    result = run_repo_only()
    payload = json.loads(result.stdout)
    watchdog_asset = next(
        entry for entry in payload["repo_assets"] if entry["repo_path"] == "ops/host-workload/rclone-mount-watchdog.sh"
    )

    assert watchdog_asset["exists"] is True
    assert watchdog_asset["expected_snippets_ok"] is True

    watchdog_text = (REPO_ROOT / "ops" / "host-workload" / "rclone-mount-watchdog.sh").read_text(encoding="utf-8")
    assert 'CONFIG_DRIFT_REMOTES_STR="${CONFIG_DRIFT_REMOTES:-internxt}"' in watchdog_text
    assert 'STALE_NAMESPACE_DOCKER_CONTAINERS="${STALE_NAMESPACE_DOCKER_CONTAINERS:-plex mymediaalexa sonarr_v2 radarr_v2 qbittorrent_pia}"' in watchdog_text
    assert 'CONTAINER_DEST_OVERRIDES="${CONTAINER_DEST_OVERRIDES:-mymediaalexa=/medialibrary}"' in watchdog_text
    assert 'CONTAINER_PROBE_OVERRIDES="${CONTAINER_PROBE_OVERRIDES:-mymediaalexa=/medialibrary}"' in watchdog_text
    assert 'CONFIG_DRIFT_BLOCKER_UNITS="${CONFIG_DRIFT_BLOCKER_UNITS:-internxt=plex-internxt-mirror.service}"' in watchdog_text
    assert 'STATE_DIR="${STATE_DIR:-/run/rclone-mount-watchdog}"' in watchdog_text
    assert 'LOCKFILE="${LOCKFILE:-/run/rclone-mount-watchdog.lock}"' in watchdog_text
    assert "restart_stale_namespace_containers()" in watchdog_text
    assert "container_mount_destination_for()" in watchdog_text
    assert "container_probe_target_for()" in watchdog_text
    assert "config_drift_blocker_active()" in watchdog_text
    assert "restart_mount_unit()" in watchdog_text
    assert "handle_runtime_config_drift()" in watchdog_text
    assert 'container_has_mount_destination "$container" "$container_destination"' in watchdog_text
    assert 'container_probe_ok "$container" "$container_probe_target"' in watchdog_text
    assert 'action_key="container.${container}"' in watchdog_text
    assert 'action_key="config_drift.${remote}"' in watchdog_text


def test_repo_only_guardrail_verifier_tracks_qbittorrent_storage_watchdog_snippets() -> None:
    result = run_repo_only()
    payload = json.loads(result.stdout)
    storage_asset = next(
        entry for entry in payload["repo_assets"] if entry["repo_path"] == "ops/host-workload/qbittorrent-storage-watchdog.sh"
    )

    assert storage_asset["exists"] is True
    assert storage_asset["expected_snippets_ok"] is True

    storage_text = (REPO_ROOT / "ops" / "host-workload" / "qbittorrent-storage-watchdog.sh").read_text(
        encoding="utf-8"
    )
    assert 'QBIT_CONTAINER="${QBIT_CONTAINER:-qbittorrent_pia}"' in storage_text
    assert "container_started_epoch()" in storage_text
    assert "configured_save_path()" in storage_text
    assert "last_storage_error_line()" in storage_text
    assert "container_write_probe_ok()" in storage_text
    assert 'systemctl start "$RCLONE_WATCHDOG_UNIT"' in storage_text


def test_repo_only_guardrail_verifier_tracks_qbittorrent_staging_hygiene_snippets() -> None:
    result = run_repo_only()
    payload = json.loads(result.stdout)
    staging_hygiene_asset = next(
        entry
        for entry in payload["repo_assets"]
        if entry["repo_path"] == "ops/host-workload/qbittorrent-staging-hygiene-watchdog.sh"
    )

    assert staging_hygiene_asset["exists"] is True
    assert staging_hygiene_asset["expected_snippets_ok"] is True

    staging_hygiene_service_asset = next(
        entry
        for entry in payload["repo_assets"]
        if entry["repo_path"] == "ops/host-workload/qbittorrent-staging-hygiene-watchdog.service"
    )
    assert staging_hygiene_service_asset["exists"] is True
    assert staging_hygiene_service_asset["expected_snippets_ok"] is True

    staging_hygiene_default_asset = next(
        entry
        for entry in payload["repo_assets"]
        if entry["repo_path"] == "ops/host-workload/qbittorrent-staging-hygiene-watchdog.default"
    )
    assert staging_hygiene_default_asset["exists"] is True
    assert staging_hygiene_default_asset["expected_snippets_ok"] is True

    staging_hygiene_text = (
        REPO_ROOT / "ops" / "host-workload" / "qbittorrent-staging-hygiene-watchdog.sh"
    ).read_text(encoding="utf-8")
    staging_hygiene_service_text = (
        REPO_ROOT / "ops" / "host-workload" / "qbittorrent-staging-hygiene-watchdog.service"
    ).read_text(encoding="utf-8")
    staging_hygiene_default_text = (
        REPO_ROOT / "ops" / "host-workload" / "qbittorrent-staging-hygiene-watchdog.default"
    ).read_text(encoding="utf-8")
    assert (
        "QBIT_HYGIENE_SCRIPT=\"${QBIT_HYGIENE_SCRIPT:-$QBIT_REPO_ROOT/scripts/materialize_qbittorrent_staging_hygiene.py}\""
        in staging_hygiene_text
    )
    assert "--apply-requeue-dead-stalled-downloads" in staging_hygiene_text
    assert "flock -n 9 || exit 0" in staging_hygiene_text
    assert "EnvironmentFile=-/etc/default/qbittorrent-staging-hygiene-watchdog" in staging_hygiene_service_text
    assert "QBIT_MIN_DEAD_CHECKING_AGE_MINUTES=90" in staging_hygiene_default_text
    assert "QBIT_ENSURE_QUEUEING=1" in staging_hygiene_default_text


def test_repo_only_guardrail_verifier_tracks_plex_internxt_mirror_snippets() -> None:
    result = run_repo_only()
    payload = json.loads(result.stdout)
    mirror_asset = next(
        entry for entry in payload["repo_assets"] if entry["repo_path"] == "ops/host-workload/plex-internxt-mirror.sh"
    )

    assert mirror_asset["exists"] is True
    assert mirror_asset["expected_snippets_ok"] is True

    mirror_text = (REPO_ROOT / "ops" / "host-workload" / "plex-internxt-mirror.sh").read_text(encoding="utf-8")
    assert 'MOVIES_SOURCE="${MOVIES_SOURCE:-$PCLOUD_ROOT/Movies}"' in mirror_text
    assert 'REQUESTED_ROOT="${REQUESTED_ROOT:-$PCLOUD_ROOT/Requested}"' in mirror_text
    assert 'REQUESTED_MOVIES_SOURCE="${REQUESTED_MOVIES_SOURCE:-$REQUESTED_ROOT/Movies}"' in mirror_text
    assert 'REQUESTED_TV_SOURCE="${REQUESTED_TV_SOURCE:-$REQUESTED_ROOT/TV}"' in mirror_text
    assert 'STATUS_FILE="$STATE_DIR/status.json"' in mirror_text
    assert "write_status()" in mirror_text
    assert "update_status()" in mirror_text
    assert "handle_exit()" in mirror_text
    assert "bucket_for_name()" in mirror_text
    assert "requested_entry_type()" in mirror_text
    assert "requested_dest_entry()" in mirror_text
    assert "sync_bucketed_tree()" in mirror_text
    assert "sync_requested_entries_from_root()" in mirror_text
    assert "sync_requested_tree()" in mirror_text
    assert '--inplace --partial --human-readable --info=stats1,name0' in mirror_text
    assert 'sync_bucketed_tree "$MOVIES_SOURCE" "$MOVIES_DEST" "Movies"' in mirror_text
    assert 'sync_bucketed_tree "$TV_SOURCE" "$TV_DEST" "TV"' in mirror_text
