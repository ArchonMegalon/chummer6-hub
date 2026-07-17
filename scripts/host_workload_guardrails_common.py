from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_ROOT = REPO_ROOT / "ops" / "host-workload"

ASSET_MAP = [
    ("ops/host-workload/media-cache-guard.sh", "/usr/local/sbin/media-cache-guard.sh"),
    ("ops/host-workload/media-cache-guard.service", "/etc/systemd/system/media-cache-guard.service"),
    ("ops/host-workload/media-cache-guard.timer", "/etc/systemd/system/media-cache-guard.timer"),
    (
        "ops/host-workload/media-cache-guard.service.d-10-budget.conf",
        "/etc/systemd/system/media-cache-guard.service.d/10-budget.conf",
    ),
    ("ops/host-workload/plex-stream-watchdog.sh", "/usr/local/sbin/plex-stream-watchdog.sh"),
    ("ops/host-workload/plex-stream-watchdog.service", "/etc/systemd/system/plex-stream-watchdog.service"),
    ("ops/host-workload/plex-stream-watchdog.timer", "/etc/systemd/system/plex-stream-watchdog.timer"),
    ("ops/host-workload/plex-stream-watchdog.default", "/etc/default/plex-stream-watchdog"),
    (
        "ops/host-workload/plex-stream-watchdog.timer.d-10-fast-container-check.conf",
        "/etc/systemd/system/plex-stream-watchdog.timer.d/10-fast-container-check.conf",
    ),
    (
        "ops/host-workload/rclone-mount-pcloud-cache-tuning.conf",
        "/etc/systemd/system/rclone-mount@pcloud.service.d/20-cache-tuning.conf",
    ),
    (
        "ops/host-workload/rclone-mount-internxt-cache-tuning.conf",
        "/etc/systemd/system/rclone-mount@internxt.service.d/zz-cache-budget.conf",
    ),
    (
        "ops/host-workload/rclone-mount@.service.d-80-media-priority.conf",
        "/etc/systemd/system/rclone-mount@.service.d/80-media-priority.conf",
    ),
    ("ops/host-workload/plex-internxt-mirror.sh", "/usr/local/sbin/plex-internxt-mirror.sh"),
    ("ops/host-workload/plex-internxt-mirror.service", "/etc/systemd/system/plex-internxt-mirror.service"),
    ("ops/host-workload/plex-internxt-mirror.timer", "/etc/systemd/system/plex-internxt-mirror.timer"),
    ("ops/host-workload/qbittorrent-storage-watchdog.sh", "/usr/local/sbin/qbittorrent-storage-watchdog.sh"),
    (
        "ops/host-workload/qbittorrent-storage-watchdog.service",
        "/etc/systemd/system/qbittorrent-storage-watchdog.service",
    ),
    ("ops/host-workload/qbittorrent-storage-watchdog.timer", "/etc/systemd/system/qbittorrent-storage-watchdog.timer"),
    (
        "ops/host-workload/qbittorrent-staging-hygiene-watchdog.sh",
        "/usr/local/sbin/qbittorrent-staging-hygiene-watchdog.sh",
    ),
    (
        "ops/host-workload/qbittorrent-staging-hygiene-watchdog.service",
        "/etc/systemd/system/qbittorrent-staging-hygiene-watchdog.service",
    ),
    ("ops/host-workload/qbittorrent-staging-hygiene-watchdog.timer", "/etc/systemd/system/qbittorrent-staging-hygiene-watchdog.timer"),
    (
        "ops/host-workload/qbittorrent-staging-hygiene-watchdog.default",
        "/etc/default/qbittorrent-staging-hygiene-watchdog",
    ),
    ("ops/host-workload/rclone-mount-watchdog.sh", "/usr/local/bin/rclone-mount-watchdog.sh"),
    ("ops/host-workload/rclone-mount-watchdog.service", "/etc/systemd/system/rclone-mount-watchdog.service"),
    ("ops/host-workload/rclone-mount-watchdog.timer", "/etc/systemd/system/rclone-mount-watchdog.timer"),
]

EXPECTED_SNIPPETS = {
    "ops/host-workload/media-cache-guard.service.d-10-budget.conf": ["MEDIA_CACHE_MIN_FREE_GIB=20"],
    "ops/host-workload/rclone-mount-pcloud-cache-tuning.conf": [
        "--vfs-cache-mode writes",
        "--vfs-cache-max-size 12G",
        "--vfs-cache-min-free-space 8G",
        "--vfs-read-chunk-size 64M",
    ],
    "ops/host-workload/rclone-mount-internxt-cache-tuning.conf": [
        "--vfs-cache-max-size 4G",
        "--vfs-cache-min-free-space 8G",
    ],
    "ops/host-workload/rclone-mount@.service.d-80-media-priority.conf": [
        "Nice=0",
        "IOSchedulingClass=best-effort",
    ],
    "ops/host-workload/plex-internxt-mirror.sh": [
        'MOVIES_SOURCE="${MOVIES_SOURCE:-$PCLOUD_ROOT/Movies}"',
        'TV_SOURCE="${TV_SOURCE:-$PCLOUD_ROOT/TV}"',
        'REQUESTED_ROOT="${REQUESTED_ROOT:-$PCLOUD_ROOT/Requested}"',
        'REQUESTED_MOVIES_SOURCE="${REQUESTED_MOVIES_SOURCE:-$REQUESTED_ROOT/Movies}"',
        'REQUESTED_TV_SOURCE="${REQUESTED_TV_SOURCE:-$REQUESTED_ROOT/TV}"',
        'STATUS_FILE="$STATE_DIR/status.json"',
        "write_status()",
        "update_status()",
        "handle_exit()",
        "bucket_for_name()",
        "requested_entry_type()",
        "requested_dest_entry()",
        "sync_bucketed_tree()",
        "sync_requested_entries_from_root()",
        "sync_requested_tree()",
        '"$RSYNC_BIN" -a --inplace --partial --human-readable --info=stats1,name0',
        'sync_bucketed_tree "$MOVIES_SOURCE" "$MOVIES_DEST" "Movies"',
        'sync_bucketed_tree "$TV_SOURCE" "$TV_DEST" "TV"',
        "sync_requested_tree",
    ],
    "ops/host-workload/qbittorrent-storage-watchdog.sh": [
        'QBIT_CONTAINER="${QBIT_CONTAINER:-qbittorrent_pia}"',
        'QBIT_ERROR_LOOKBACK_SECS="${QBIT_ERROR_LOOKBACK_SECS:-1800}"',
        'RCLONE_WATCHDOG_UNIT="${RCLONE_WATCHDOG_UNIT:-rclone-mount-watchdog.service}"',
        "container_started_epoch()",
        "configured_save_path()",
        "last_storage_error_line()",
        "container_write_probe_ok()",
        'write_epoch_file "$LAST_HANDLED_FILE" "$error_epoch"',
        'systemctl start "$RCLONE_WATCHDOG_UNIT"',
        'docker restart "$QBIT_CONTAINER"',
    ],
    "ops/host-workload/qbittorrent-staging-hygiene-watchdog.sh": [
        "QBIT_REPO_ROOT=\"${QBIT_REPO_ROOT:-/docker/chummercomplete/chummer.run-services}\"",
        "QBIT_HYGIENE_SCRIPT=\"${QBIT_HYGIENE_SCRIPT:-$QBIT_REPO_ROOT/scripts/materialize_qbittorrent_staging_hygiene.py}\"",
        "QBIT_HYGIENE_OUTPUT=\"${QBIT_HYGIENE_OUTPUT:-/run/QBITTORRENT_STAGING_HYGIENE.generated.json}\"",
        "flock -n 9 || exit 0",
        'args=(',
        '"$QBIT_PYTHON_BIN" "$QBIT_HYGIENE_SCRIPT" "${args[@]}"',
    ],
    "ops/host-workload/qbittorrent-staging-hygiene-watchdog.service": [
        "EnvironmentFile=-/etc/default/qbittorrent-staging-hygiene-watchdog",
        "ExecStart=/usr/local/sbin/qbittorrent-staging-hygiene-watchdog.sh",
    ],
    "ops/host-workload/qbittorrent-staging-hygiene-watchdog.default": [
        "QBIT_MIN_DEAD_STALLED_AGE_MINUTES=5",
        "QBIT_MIN_DEAD_META_AGE_MINUTES=45",
        "QBIT_MIN_DEAD_CHECKING_AGE_MINUTES=90",
        "QBIT_DELETE_DEAD_STALLED=1",
        "QBIT_ENSURE_QUEUEING=1",
    ],
    "ops/host-workload/rclone-mount-watchdog.sh": [
        "plex_reprobe_required=0",
        'CONFIG_DRIFT_REMOTES_STR="${CONFIG_DRIFT_REMOTES:-internxt}"',
        "POST_REPAIR_DOCKER_CONTAINERS",
        "STALE_NAMESPACE_DOCKER_CONTAINERS",
        'CONTAINER_DEST_OVERRIDES="${CONTAINER_DEST_OVERRIDES:-mymediaalexa=/medialibrary}"',
        'CONTAINER_PROBE_OVERRIDES="${CONTAINER_PROBE_OVERRIDES:-mymediaalexa=/medialibrary}"',
        'CONFIG_DRIFT_BLOCKER_UNITS="${CONFIG_DRIFT_BLOCKER_UNITS:-internxt=plex-internxt-mirror.service}"',
        'NUMFMT_BIN="${NUMFMT_BIN:-/usr/bin/numfmt}"',
        'RCLONE_BIN="${RCLONE_BIN:-/usr/bin/rclone}"',
        'FAILURE_THRESHOLD="${FAILURE_THRESHOLD:-3}"',
        'DEFER_IF_PLEX_ACTIVE="${DEFER_IF_PLEX_ACTIVE:-1}"',
        'STATE_DIR="${STATE_DIR:-/run/rclone-mount-watchdog}"',
        'LOCKFILE="${LOCKFILE:-/run/rclone-mount-watchdog.lock}"',
        'probe_target="$(probe_target_for_mount "$mp")"',
        "config_drift_blocker_active()",
        "restart_mount_unit()",
        "unit_cache_max_size_bytes()",
        "remote_runtime_cache_max_size_bytes()",
        'should_defer_for_active_plex()',
        "restart_post_repair_containers()",
        "restart_stale_namespace_containers()",
        "container_mount_destination_for()",
        "container_probe_target_for()",
        "handle_runtime_config_drift()",
        'action_key="container.${container}"',
        'action_key="config_drift.${remote}"',
        'container_has_mount_destination "$container" "$container_destination"',
        'container_probe_ok "$container" "$container_probe_target"',
        "wait_for_mount_ready()",
        'docker restart "$container"',
        'systemctl start plex-stream-watchdog.service',
    ],
    "ops/host-workload/plex-stream-watchdog.default": ["SKIP_PLEX_RESTART_IF_ACTIVE=1"],
}

WATCHDOG_TIMERS = [
    "plex-stream-watchdog.timer",
    "plex-internxt-mirror.timer",
    "qbittorrent-storage-watchdog.timer",
    "qbittorrent-staging-hygiene-watchdog.timer",
    "rclone-mount-watchdog.timer",
    "media-cache-guard.timer",
]

CONTAINER_PROBES = {
    "pcloud_stream": '/mnt/pcloud/PLEX/Movies/11.14 (2003)/11.14 (2003).avi',
    "internxt_stream": '/mnt/internxt/PLEX/Movies/0-9/11.14 (2003)/11.14 (2003).avi',
}

CONTAINER_ALIAS_PATHS = [
    "/media/Movies",
    "/media/TV Shows",
    "/media/Requested",
]

HOST_ALIAS_PATHS = [
    "/docker/plex/media/Movies",
    "/docker/plex/media/TV Shows",
    "/docker/plex/media/Requested",
]
