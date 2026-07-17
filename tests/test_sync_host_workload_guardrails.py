from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_host_workload_guardrails.py"


def test_sync_host_workload_guardrails_apply_populates_temp_root(tmp_path: Path) -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), "--apply", "--host-root", str(tmp_path)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["mode"] == "apply"
    assert payload["changed_count"] == len(payload["assets"])

    watchdog_path = tmp_path / "usr/local/bin/rclone-mount-watchdog.sh"
    plex_internxt_mirror_path = tmp_path / "usr/local/sbin/plex-internxt-mirror.sh"
    qbittorrent_watchdog_path = tmp_path / "usr/local/sbin/qbittorrent-storage-watchdog.sh"
    qbittorrent_staging_hygiene_path = tmp_path / "usr/local/sbin/qbittorrent-staging-hygiene-watchdog.sh"
    qbittorrent_staging_hygiene_service_path = tmp_path / "etc/systemd/system/qbittorrent-staging-hygiene-watchdog.service"
    qbittorrent_staging_hygiene_default_path = tmp_path / "etc/default/qbittorrent-staging-hygiene-watchdog"
    conf_path = tmp_path / "etc/systemd/system/media-cache-guard.service.d/10-budget.conf"
    plex_default_path = tmp_path / "etc/default/plex-stream-watchdog"

    assert watchdog_path.exists()
    assert plex_internxt_mirror_path.exists()
    assert qbittorrent_watchdog_path.exists()
    assert qbittorrent_staging_hygiene_path.exists()
    assert qbittorrent_staging_hygiene_service_path.exists()
    assert qbittorrent_staging_hygiene_default_path.exists()
    assert conf_path.exists()
    assert plex_default_path.exists()
    assert os.stat(watchdog_path).st_mode & 0o777 == 0o755
    assert os.stat(plex_internxt_mirror_path).st_mode & 0o777 == 0o755
    assert os.stat(qbittorrent_watchdog_path).st_mode & 0o777 == 0o755
    assert os.stat(qbittorrent_staging_hygiene_path).st_mode & 0o777 == 0o755
    assert os.stat(qbittorrent_staging_hygiene_service_path).st_mode & 0o777 == 0o644
    assert os.stat(qbittorrent_staging_hygiene_default_path).st_mode & 0o777 == 0o644
    assert os.stat(conf_path).st_mode & 0o777 == 0o644
    assert os.stat(plex_default_path).st_mode & 0o777 == 0o644
    watchdog_text = watchdog_path.read_text(encoding="utf-8")
    plex_internxt_mirror_text = plex_internxt_mirror_path.read_text(encoding="utf-8")
    qbittorrent_watchdog_text = qbittorrent_watchdog_path.read_text(encoding="utf-8")
    qbittorrent_staging_hygiene_service_text = qbittorrent_staging_hygiene_service_path.read_text(encoding="utf-8")
    qbittorrent_staging_hygiene_default_text = qbittorrent_staging_hygiene_default_path.read_text(encoding="utf-8")
    assert 'CONFIG_DRIFT_REMOTES_STR="${CONFIG_DRIFT_REMOTES:-internxt}"' in watchdog_text
    assert 'POST_REPAIR_DOCKER_CONTAINERS="${POST_REPAIR_DOCKER_CONTAINERS:-plex mymediaalexa}"' in watchdog_text
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
    assert 'REQUESTED_ROOT="${REQUESTED_ROOT:-$PCLOUD_ROOT/Requested}"' in plex_internxt_mirror_text
    assert 'REQUESTED_MOVIES_SOURCE="${REQUESTED_MOVIES_SOURCE:-$REQUESTED_ROOT/Movies}"' in plex_internxt_mirror_text
    assert 'REQUESTED_TV_SOURCE="${REQUESTED_TV_SOURCE:-$REQUESTED_ROOT/TV}"' in plex_internxt_mirror_text
    assert 'STATUS_FILE="$STATE_DIR/status.json"' in plex_internxt_mirror_text
    assert "write_status()" in plex_internxt_mirror_text
    assert "update_status()" in plex_internxt_mirror_text
    assert "handle_exit()" in plex_internxt_mirror_text
    assert '--inplace --partial --human-readable --info=stats1,name0' in plex_internxt_mirror_text
    assert 'sync_bucketed_tree "$TV_SOURCE" "$TV_DEST" "TV"' in plex_internxt_mirror_text
    assert "sync_requested_entries_from_root()" in plex_internxt_mirror_text
    assert "sync_requested_tree()" in plex_internxt_mirror_text
    assert 'QBIT_CONTAINER="${QBIT_CONTAINER:-qbittorrent_pia}"' in qbittorrent_watchdog_text
    assert 'systemctl start "$RCLONE_WATCHDOG_UNIT"' in qbittorrent_watchdog_text
    assert "EnvironmentFile=-/etc/default/qbittorrent-staging-hygiene-watchdog" in qbittorrent_staging_hygiene_service_text
    assert "QBIT_ENSURE_QUEUEING=1" in qbittorrent_staging_hygiene_default_text
    assert "QBIT_DELETE_DEAD_STALLED=1" in qbittorrent_staging_hygiene_default_text
