#!/usr/bin/env bash
set -Eeuo pipefail

PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 022

LOCK_FILE="/run/plex-stream-watchdog.lock"

PCLOUD_MOUNT="${PCLOUD_MOUNT:-/mnt/pcloud}"
INTERNXT_MOUNT="${INTERNXT_MOUNT:-/mnt/internxt}"
PCLOUD_UNIT="${PCLOUD_UNIT:-pcloud}"
INTERNXT_UNIT="${INTERNXT_UNIT:-internxt}"
PCLOUD_PROBE_FILE="${PCLOUD_PROBE_FILE:-/mnt/pcloud/PLEX/Movies/11.14 (2003)/11.14 (2003).avi}"
INTERNXT_PROBE_FILE="${INTERNXT_PROBE_FILE:-/mnt/internxt/PLEX/Movies/0-9/11.14 (2003)/11.14 (2003).avi}"
STREAM_BYTES="${STREAM_BYTES:-16777216}"
STREAM_TIMEOUT="${STREAM_TIMEOUT:-45}"
MOUNT_TIMEOUT="${MOUNT_TIMEOUT:-15}"
RECOVERY_WAIT_SECONDS="${RECOVERY_WAIT_SECONDS:-10}"
RECOVERY_RETRIES="${RECOVERY_RETRIES:-6}"
PLEX_CONTAINER="${PLEX_CONTAINER:-plex}"
RESTART_PLEX_ON_MOUNT_RECOVERY="${RESTART_PLEX_ON_MOUNT_RECOVERY:-1}"
SKIP_PLEX_RESTART_IF_ACTIVE="${SKIP_PLEX_RESTART_IF_ACTIVE:-1}"
NOTIFY_USER="${NOTIFY_USER:-tibor}"
NOTIFY_UID="${NOTIFY_UID:-1000}"
NOTIFY_DESKTOP="${NOTIFY_DESKTOP:-1}"
NOTIFY_WALL="${NOTIFY_WALL:-1}"
NOTIFY_ON_RECOVERY="${NOTIFY_ON_RECOVERY:-1}"
NOTIFY_ON_FAILURE="${NOTIFY_ON_FAILURE:-1}"

if [[ -f /etc/default/plex-stream-watchdog ]]; then
  # shellcheck disable=SC1091
  source /etc/default/plex-stream-watchdog
fi

log() {
  local msg="[plex-watchdog] $*"
  echo "$msg"
  logger -t plex-stream-watchdog "$*"
}

fail() {
  log "fatal: $*"
  send_notification "failure" "$*"
  exit 1
}

validate_abs_path() {
  local value="$1"
  [[ "$value" == /* ]]
}

validate_unit_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9_.@:-]+$ ]]
}

validate_numeric() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]]
}

desktop_notify() {
  local urgency="$1"
  local title="$2"
  local body="$3"
  local bus="/run/user/${NOTIFY_UID}/bus"

  [[ "$NOTIFY_DESKTOP" == "1" ]] || return 0
  [[ -S "$bus" ]] || return 0
  command -v notify-send >/dev/null 2>&1 || return 0

  runuser -u "$NOTIFY_USER" -- \
    env DBUS_SESSION_BUS_ADDRESS="unix:path=${bus}" \
    notify-send --urgency="$urgency" "$title" "$body" >/dev/null 2>&1 || true
}

send_notification() {
  local kind="$1"
  local body="$2"
  local title="Plex Watchdog"
  local urgency="normal"

  case "$kind" in
    failure)
      [[ "$NOTIFY_ON_FAILURE" == "1" ]] || return 0
      title="Plex Watchdog Failure"
      urgency="critical"
      ;;
    recovery)
      [[ "$NOTIFY_ON_RECOVERY" == "1" ]] || return 0
      title="Plex Watchdog Recovery"
      ;;
  esac

  desktop_notify "$urgency" "$title" "$body"

  if [[ "$NOTIFY_WALL" == "1" ]] && command -v wall >/dev/null 2>&1; then
    printf '%s\n' "[plex-watchdog] ${title}: ${body}" | wall >/dev/null 2>&1 || true
  fi
}

with_timeout() {
  timeout --foreground "$1" "${@:2}"
}

stream_probe() {
  local file="$1"
  [[ -f "$file" ]] || return 10
  with_timeout "$STREAM_TIMEOUT" head -c "$STREAM_BYTES" -- "$file" >/dev/null
}

container_stream_probe() {
  local file="$1"

  docker ps --format '{{.Names}}' | grep -qx "$PLEX_CONTAINER" || return 20
  with_timeout "$STREAM_TIMEOUT" docker exec "$PLEX_CONTAINER" sh -lc '
    file="$1"
    bytes="$2"
    [ -f "$file" ] || exit 10
    head -c "$bytes" -- "$file" >/dev/null
  ' sh "$file" "$STREAM_BYTES"
}

mount_probe() {
  local mount_path="$1"
  with_timeout "$MOUNT_TIMEOUT" ls -1A "$mount_path/PLEX" >/dev/null
}

get_local_plex_token() {
  docker exec "$PLEX_CONTAINER" sh -lc 'cat /config/Library/Application\ Support/Plex\ Media\ Server/.LocalAdminToken 2>/dev/null' 2>/dev/null || true
}

plex_has_active_sessions() {
  local token xml
  token="$(get_local_plex_token)"
  [[ -n "$token" ]] || return 1
  xml="$(curl -fsS --max-time 10 -H "X-Plex-Token: ${token}" http://127.0.0.1:32400/status/sessions 2>/dev/null || true)"
  [[ "$xml" == *"<Video "* || "$xml" == *"<Track "* || "$xml" == *"<Photo "* ]]
}

restart_mount() {
  local unit_name="$1"
  log "restarting mount unit rclone-mount@${unit_name}.service"
  systemctl restart "rclone-mount@${unit_name}.service"
}

restart_plex_if_needed() {
  [[ "$RESTART_PLEX_ON_MOUNT_RECOVERY" == "1" ]] || return 0

  if ! docker ps --format '{{.Names}}' | grep -qx "$PLEX_CONTAINER"; then
    log "plex container ${PLEX_CONTAINER} is not running; skipping restart"
    return 0
  fi

  if [[ "$SKIP_PLEX_RESTART_IF_ACTIVE" == "1" ]] && plex_has_active_sessions; then
    log "active plex sessions detected; skipping plex restart after mount recovery"
    send_notification "recovery" "Mount recovered, but Plex restart was skipped because active playback was detected."
    return 0
  fi

  log "restarting plex container ${PLEX_CONTAINER} after mount recovery"
  docker restart "$PLEX_CONTAINER" >/dev/null
}

restart_plex_for_container_mount() {
  [[ "$RESTART_PLEX_ON_MOUNT_RECOVERY" == "1" ]] || return 1

  if ! docker ps --format '{{.Names}}' | grep -qx "$PLEX_CONTAINER"; then
    log "plex container ${PLEX_CONTAINER} is not running; cannot refresh container mount"
    return 1
  fi

  log "restarting plex container ${PLEX_CONTAINER} to refresh stale container mount"
  docker restart "$PLEX_CONTAINER" >/dev/null
}

check_storage() {
  local name="$1"
  local mount_path="$2"
  local probe_file="$3"
  local unit_name="$4"
  local attempt

  if stream_probe "$probe_file"; then
    if container_stream_probe "$probe_file"; then
      log "${name}: host and plex-container stream probes ok"
      return 0
    fi

    log "${name}: host stream probe ok, but plex-container stream probe failed for ${probe_file}"
    if restart_plex_for_container_mount; then
      sleep "$RECOVERY_WAIT_SECONDS"
      if container_stream_probe "$probe_file"; then
        log "${name}: plex-container stream probe recovered after plex restart"
        send_notification "recovery" "${name} was readable on the host but stale inside Plex; Plex was restarted and the container mount recovered."
        return 0
      fi
    fi

    log "${name}: plex-container stream probe is still failing after plex restart"
    send_notification "failure" "${name} is readable on the host but not inside the Plex container."
    return 1
  fi

  local probe_rc=$?
  log "${name}: stream probe failed for ${probe_file}"

  if ! mountpoint -q "$mount_path"; then
    log "${name}: mountpoint ${mount_path} is not mounted"
  elif ! mount_probe "$mount_path"; then
    log "${name}: mount probe failed for ${mount_path}"
  elif [[ "$probe_rc" -eq 10 ]]; then
    log "${name}: probe file is missing while mount is present"
  else
    log "${name}: mount probe passed but stream probe failed"
  fi

  restart_mount "$unit_name"

  for attempt in $(seq 1 "$RECOVERY_RETRIES"); do
    sleep "$RECOVERY_WAIT_SECONDS"
    if mountpoint -q "$mount_path" && mount_probe "$mount_path" && stream_probe "$probe_file"; then
      log "${name}: recovery succeeded on attempt ${attempt}"
      send_notification "recovery" "${name} mount recovered on attempt ${attempt}."
      restart_plex_if_needed
      return 0
    fi
    log "${name}: recovery attempt ${attempt}/${RECOVERY_RETRIES} still failing"
  done

  log "${name}: recovery failed after ${RECOVERY_RETRIES} attempts"
  send_notification "failure" "${name} mount/stream probe failed and recovery did not succeed after ${RECOVERY_RETRIES} attempts."
  return 1
}

validate_config() {
  validate_abs_path "$PCLOUD_MOUNT" || fail "invalid PCLOUD_MOUNT: ${PCLOUD_MOUNT}"
  validate_abs_path "$INTERNXT_MOUNT" || fail "invalid INTERNXT_MOUNT: ${INTERNXT_MOUNT}"
  validate_abs_path "$PCLOUD_PROBE_FILE" || fail "invalid PCLOUD_PROBE_FILE: ${PCLOUD_PROBE_FILE}"
  validate_abs_path "$INTERNXT_PROBE_FILE" || fail "invalid INTERNXT_PROBE_FILE: ${INTERNXT_PROBE_FILE}"
  validate_unit_name "$PCLOUD_UNIT" || fail "invalid PCLOUD_UNIT: ${PCLOUD_UNIT}"
  validate_unit_name "$INTERNXT_UNIT" || fail "invalid INTERNXT_UNIT: ${INTERNXT_UNIT}"
  validate_unit_name "$PLEX_CONTAINER" || fail "invalid PLEX_CONTAINER: ${PLEX_CONTAINER}"
  validate_numeric "$STREAM_BYTES" || fail "invalid STREAM_BYTES: ${STREAM_BYTES}"
  validate_numeric "$STREAM_TIMEOUT" || fail "invalid STREAM_TIMEOUT: ${STREAM_TIMEOUT}"
  validate_numeric "$MOUNT_TIMEOUT" || fail "invalid MOUNT_TIMEOUT: ${MOUNT_TIMEOUT}"
  validate_numeric "$RECOVERY_WAIT_SECONDS" || fail "invalid RECOVERY_WAIT_SECONDS: ${RECOVERY_WAIT_SECONDS}"
  validate_numeric "$RECOVERY_RETRIES" || fail "invalid RECOVERY_RETRIES: ${RECOVERY_RETRIES}"
  validate_numeric "$NOTIFY_UID" || fail "invalid NOTIFY_UID: ${NOTIFY_UID}"
}

main() {
  mkdir -p "$(dirname "$LOCK_FILE")"
  exec 9>"$LOCK_FILE"
  flock -n 9 || {
    log "another watchdog run is already active"
    exit 0
  }

  validate_config

  local rc=0

  check_storage "pcloud" "$PCLOUD_MOUNT" "$PCLOUD_PROBE_FILE" "$PCLOUD_UNIT" || rc=1
  check_storage "internxt" "$INTERNXT_MOUNT" "$INTERNXT_PROBE_FILE" "$INTERNXT_UNIT" || rc=1

  exit "$rc"
}

main "$@"
