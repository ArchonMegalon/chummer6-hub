#!/usr/bin/env bash
set -euo pipefail

QBIT_CONTAINER="${QBIT_CONTAINER:-qbittorrent_pia}"
QBIT_CONFIG_ROOT="${QBIT_CONFIG_ROOT:-/docker/arr-v2/qbittorrent-vpn/qBittorrent}"
QBIT_CONF_FILE="${QBIT_CONF_FILE:-$QBIT_CONFIG_ROOT/qBittorrent.conf}"
QBIT_LOG_FILE="${QBIT_LOG_FILE:-$QBIT_CONFIG_ROOT/logs/qbittorrent.log}"
QBIT_STORAGE_ERROR_PATTERN="${QBIT_STORAGE_ERROR_PATTERN:-Socket not connected|Transport endpoint is not connected}"
QBIT_ERROR_LOOKBACK_SECS="${QBIT_ERROR_LOOKBACK_SECS:-1800}"
QBIT_RECOVERY_COOLDOWN_SECS="${QBIT_RECOVERY_COOLDOWN_SECS:-300}"
QBIT_WRITE_PROBE_TIMEOUT="${QBIT_WRITE_PROBE_TIMEOUT:-20}"
RCLONE_WATCHDOG_UNIT="${RCLONE_WATCHDOG_UNIT:-rclone-mount-watchdog.service}"

STATE_DIR="/run/qbittorrent-storage-watchdog"
LOCKFILE="/run/qbittorrent-storage-watchdog.lock"
LAST_HANDLED_FILE="$STATE_DIR/last_handled_error_epoch"
LAST_RESTART_FILE="$STATE_DIR/last_restart_epoch"

mkdir -p "$STATE_DIR"

exec 9>"$LOCKFILE"
flock -n 9 || exit 0

log() {
  logger -t qbittorrent-storage-watchdog -- "$*"
  echo "[qbittorrent-storage-watchdog] $*"
}

now_epoch() {
  date +%s
}

read_epoch_file() {
  local file="$1" value=0
  [[ -f "$file" ]] && value="$(cat "$file" 2>/dev/null || echo 0)"
  [[ "$value" =~ ^[0-9]+$ ]] || value=0
  printf '%s\n' "$value"
}

write_epoch_file() {
  printf '%s\n' "$2" > "$1"
}

restart_age() {
  echo $(( $(now_epoch) - $(read_epoch_file "$LAST_RESTART_FILE") ))
}

restart_throttled() {
  (( $(restart_age) < QBIT_RECOVERY_COOLDOWN_SECS ))
}

container_running() {
  docker ps --format '{{.Names}}' | grep -qx "$QBIT_CONTAINER"
}

container_started_epoch() {
  local started_at
  started_at="$(docker inspect -f '{{.State.StartedAt}}' "$QBIT_CONTAINER" 2>/dev/null || true)"
  [[ -n "$started_at" ]] || {
    printf '0\n'
    return 0
  }
  date -d "$started_at" +%s 2>/dev/null || printf '0\n'
}

configured_save_path() {
  [[ -r "$QBIT_CONF_FILE" ]] || return 0
  sed -n \
    -e 's/^Downloads\\SavePath=//p' \
    -e 's/^Session\\DefaultSavePath=//p' \
    "$QBIT_CONF_FILE" \
    | sed '/^$/d' \
    | head -n 1 \
    | sed 's#/*$##'
}

last_storage_error_line() {
  [[ -r "$QBIT_LOG_FILE" ]] || return 0
  grep -E "File error alert\..*(${QBIT_STORAGE_ERROR_PATTERN})" "$QBIT_LOG_FILE" | tail -n 1 || true
}

error_epoch_from_line() {
  local line="$1"
  if [[ "$line" =~ ^\([A-Z]\)\ ([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})\ -\  ]]; then
    date -d "${BASH_REMATCH[1]}" +%s 2>/dev/null || printf '0\n'
    return 0
  fi
  printf '0\n'
}

container_write_probe_ok() {
  local target_dir="$1" probe_name
  probe_name=".qbittorrent-storage-watchdog.$(now_epoch).$$"
  timeout "$QBIT_WRITE_PROBE_TIMEOUT" docker exec "$QBIT_CONTAINER" sh -lc \
    'd="$1"; f="$d/$2"; ls -1A "$d" >/dev/null 2>&1; : > "$f"; rm -f "$f"' \
    sh "$target_dir" "$probe_name" >/dev/null 2>&1
}

if ! container_running; then
  exit 0
fi

save_path="$(configured_save_path)"
if [[ -z "$save_path" ]]; then
  log "unable to resolve qBittorrent save path from $QBIT_CONF_FILE"
  exit 1
fi

error_line="$(last_storage_error_line)"
[[ -n "$error_line" ]] || exit 0

error_epoch="$(error_epoch_from_line "$error_line")"
if ! [[ "$error_epoch" =~ ^[0-9]+$ ]] || (( error_epoch == 0 )); then
  log "unable to parse qBittorrent storage error timestamp from log line"
  exit 1
fi

if (( error_epoch <= $(read_epoch_file "$LAST_HANDLED_FILE") )); then
  exit 0
fi

if (( $(now_epoch) - error_epoch > QBIT_ERROR_LOOKBACK_SECS )); then
  exit 0
fi

started_epoch="$(container_started_epoch)"
if (( started_epoch > error_epoch )); then
  write_epoch_file "$LAST_HANDLED_FILE" "$error_epoch"
  exit 0
fi

if [[ "$error_line" != *"$save_path"* ]]; then
  log "recent qBittorrent storage error did not target configured save path $save_path -> skipping"
  write_epoch_file "$LAST_HANDLED_FILE" "$error_epoch"
  exit 0
fi

if ! container_write_probe_ok "$save_path"; then
  log "$QBIT_CONTAINER: recent storage error on $save_path and container write probe still fails -> triggering $RCLONE_WATCHDOG_UNIT"
  systemctl start "$RCLONE_WATCHDOG_UNIT" >/dev/null 2>&1 || log "failed to trigger $RCLONE_WATCHDOG_UNIT"
  exit 0
fi

if restart_throttled; then
  log "$QBIT_CONTAINER: recent storage error on $save_path but restart is throttled (<${QBIT_RECOVERY_COOLDOWN_SECS}s) -> skipping"
  exit 0
fi

write_epoch_file "$LAST_RESTART_FILE" "$(now_epoch)"
log "$QBIT_CONTAINER: recent storage error on $save_path while the path is healthy again -> restarting qBittorrent"
docker restart "$QBIT_CONTAINER" >/dev/null 2>&1
write_epoch_file "$LAST_HANDLED_FILE" "$error_epoch"
