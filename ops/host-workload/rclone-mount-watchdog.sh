#!/usr/bin/env bash
set -euo pipefail

REMOTES_STR="${REMOTES:-pcloud internxt}"
IFS=' ' read -r -a REMOTES <<< "$REMOTES_STR"
CONFIG_DRIFT_REMOTES_STR="${CONFIG_DRIFT_REMOTES:-internxt}"
IFS=' ' read -r -a CONFIG_DRIFT_REMOTES <<< "$CONFIG_DRIFT_REMOTES_STR"
POST_REPAIR_DOCKER_CONTAINERS="${POST_REPAIR_DOCKER_CONTAINERS:-plex mymediaalexa}"
STALE_NAMESPACE_DOCKER_CONTAINERS="${STALE_NAMESPACE_DOCKER_CONTAINERS:-plex mymediaalexa sonarr_v2 radarr_v2 qbittorrent_pia}"
CONTAINER_DEST_OVERRIDES="${CONTAINER_DEST_OVERRIDES:-mymediaalexa=/medialibrary}"
CONTAINER_PROBE_OVERRIDES="${CONTAINER_PROBE_OVERRIDES:-mymediaalexa=/medialibrary}"
CONFIG_DRIFT_BLOCKER_UNITS="${CONFIG_DRIFT_BLOCKER_UNITS:-internxt=plex-internxt-mirror.service}"
NUMFMT_BIN="${NUMFMT_BIN:-/usr/bin/numfmt}"
RCLONE_BIN="${RCLONE_BIN:-/usr/bin/rclone}"

COOLDOWN_SECS="${COOLDOWN_SECS:-300}"   # seconds between *actions* per remote
LS_TIMEOUT="${LS_TIMEOUT:-20}"
FAILURE_THRESHOLD="${FAILURE_THRESHOLD:-3}"
MOUNT_PROBE_SUFFIX="${MOUNT_PROBE_SUFFIX:-/PLEX}"
DEFER_IF_PLEX_ACTIVE="${DEFER_IF_PLEX_ACTIVE:-1}"
PLEX_BASE_URL="${PLEX_BASE_URL:-http://127.0.0.1:32400}"
PLEX_TOKEN_FILE="${PLEX_TOKEN_FILE:-/docker/plex/config/plex/Library/Application Support/Plex Media Server/.LocalAdminToken}"

STATE_DIR="${STATE_DIR:-/run/rclone-mount-watchdog}"
LOCKFILE="${LOCKFILE:-/run/rclone-mount-watchdog.lock}"

mkdir -p "$STATE_DIR"

# Prevent overlapping runs
exec 9>"$LOCKFILE"
flock -n 9 || exit 0

plex_reprobe_required=0

log() {
  logger -t rclone-watchdog -- "$*"
  echo "[rclone-watchdog] $*"
}

now_epoch() { date +%s; }

last_action_file() { echo "$STATE_DIR/last_action.$1"; }
failure_count_file() { echo "$STATE_DIR/failure_count.$1"; }

last_action_age() {
  local f now last
  f="$(last_action_file "$1")"
  now="$(now_epoch)"
  last=0
  [[ -f "$f" ]] && last="$(cat "$f" 2>/dev/null || echo 0)"
  [[ "$last" =~ ^[0-9]+$ ]] || last=0
  echo $(( now - last ))
}

mark_action() { now_epoch > "$(last_action_file "$1")"; }

throttled() {
  local age
  age="$(last_action_age "$1")"
  (( age < COOLDOWN_SECS ))
}

failure_count() {
  local f value
  f="$(failure_count_file "$1")"
  value=0
  [[ -f "$f" ]] && value="$(cat "$f" 2>/dev/null || echo 0)"
  [[ "$value" =~ ^[0-9]+$ ]] || value=0
  echo "$value"
}

set_failure_count() {
  printf '%s\n' "$2" > "$(failure_count_file "$1")"
}

increment_failure_count() {
  local value
  value="$(( $(failure_count "$1") + 1 ))"
  set_failure_count "$1" "$value"
  echo "$value"
}

clear_failure_count() {
  rm -f "$(failure_count_file "$1")"
}

unit_prop() {
  local unit="$1" prop="$2"
  systemctl show -p "$prop" --value "$unit" 2>/dev/null || true
}

string_array_contains() {
  local needle="$1"
  shift || true
  local value
  for value in "$@"; do
    [[ "$value" == "$needle" ]] && return 0
  done
  return 1
}

map_lookup() {
  local key="$1" mapping="$2" entry
  for entry in $mapping; do
    case "$entry" in
      "$key"=*)
        printf '%s\n' "${entry#*=}"
        return 0
        ;;
    esac
  done
  return 1
}

unit_needs_daemon_reload() {
  [[ "$(unit_prop "$1" NeedDaemonReload)" == "yes" ]]
}

unit_cat() {
  systemctl cat "$1" 2>/dev/null || true
}

unit_flag_value() {
  local unit="$1" flag="$2" flattened
  flattened="$(unit_cat "$unit" | tr '\n' ' ' | tr '\\' ' ')"
  sed -n "s/.*${flag}[[:space:]]\\([^[:space:]]\\+\\).*/\\1/p" <<<"$flattened" | head -n 1
}

size_to_bytes() {
  local value="$1"
  [[ -n "$value" ]] || return 1
  "$NUMFMT_BIN" --from=iec "$value" 2>/dev/null | head -n 1
}

unit_rc_addr_from_service() {
  unit_flag_value "$1" "--rc-addr"
}

unit_cache_max_size_bytes() {
  local raw
  raw="$(unit_flag_value "$1" "--vfs-cache-max-size")"
  size_to_bytes "$raw"
}

remote_runtime_cache_max_size_bytes() {
  local rc_addr="$1"
  [[ -n "$rc_addr" ]] || return 1
  "$RCLONE_BIN" rc --rc-addr "$rc_addr" vfs/stats 2>/dev/null \
    | sed -n 's/.*"CacheMaxSize":[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
    | head -n 1
}

config_drift_blocker_active() {
  local remote="$1" units unit active
  units="$(map_lookup "$remote" "$CONFIG_DRIFT_BLOCKER_UNITS" || true)"
  [[ -n "$units" ]] || return 1
  for unit in ${units//,/ }; do
    [[ -n "$unit" ]] || continue
    active="$(unit_prop "$unit" ActiveState)"
    [[ "$active" == "active" || "$active" == "activating" ]] && return 0
  done
  return 1
}

detach_mount() {
  local mp="$1"
  fusermount3 -uz "$mp" 2>/dev/null || true
  fusermount  -uz "$mp" 2>/dev/null || true
  umount -l "$mp" 2>/dev/null || true
}

probe_target_for_mount() {
  printf '%s%s' "$1" "$MOUNT_PROBE_SUFFIX"
}

wait_for_mount_ready() {
  local mp="$1" probe_target="$2" i
  for ((i=0; i<15; i++)); do
    if mountpoint -q "$mp" && timeout "$LS_TIMEOUT" ls -1A "$probe_target" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

restart_mount_unit() {
  local unit="$1"
  if unit_needs_daemon_reload "$unit"; then
    log "$unit: systemd reports NeedDaemonReload=yes -> reloading units before restart"
    systemctl daemon-reload
  fi
  systemctl restart "$unit" 2>/dev/null || systemctl start "$unit" 2>/dev/null
}

get_local_plex_token() {
  [[ -r "$PLEX_TOKEN_FILE" ]] || return 0
  cat "$PLEX_TOKEN_FILE" 2>/dev/null || true
}

plex_has_active_sessions() {
  local token xml
  token="$(get_local_plex_token)"
  [[ -n "$token" ]] || return 1
  xml="$(curl -fsS --max-time 10 -H "X-Plex-Token: ${token}" "${PLEX_BASE_URL}/status/sessions" 2>/dev/null || true)"
  [[ "$xml" == *"<Video "* || "$xml" == *"<Track "* || "$xml" == *"<Photo "* ]]
}

should_defer_for_active_plex() {
  [[ "$DEFER_IF_PLEX_ACTIVE" == "1" ]] || return 1
  plex_has_active_sessions
}

restart_post_repair_containers() {
  local container
  for container in $POST_REPAIR_DOCKER_CONTAINERS; do
    [[ -n "$container" ]] || continue
    if docker ps --format '{{.Names}}' | grep -qx "$container"; then
      log "restarting container $container after mount repair"
      docker restart "$container" >/dev/null 2>&1 || log "$container: restart failed after mount repair"
    fi
  done
}

container_is_running() {
  docker ps --format '{{.Names}}' | grep -qx "$1"
}

container_has_mount_destination() {
  docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$1" 2>/dev/null | grep -qx "$2"
}

container_mount_destination_for() {
  local container="$1" default_destination="$2" override
  override="$(map_lookup "$container" "$CONTAINER_DEST_OVERRIDES" || true)"
  printf '%s\n' "${override:-$default_destination}"
}

container_probe_target_for() {
  local container="$1" default_probe_target="$2" override
  override="$(map_lookup "$container" "$CONTAINER_PROBE_OVERRIDES" || true)"
  printf '%s\n' "${override:-$default_probe_target}"
}

container_probe_ok() {
  local container="$1" probe_target="$2"
  timeout "$LS_TIMEOUT" docker exec "$container" sh -lc \
    "stat '$probe_target' >/dev/null 2>&1 && ls -1A '$probe_target' >/dev/null 2>&1"
}

restart_stale_namespace_containers() {
  local mp="$1" probe_target="$2" container action_key container_destination container_probe_target

  for container in $STALE_NAMESPACE_DOCKER_CONTAINERS; do
    [[ -n "$container" ]] || continue
    container_is_running "$container" || continue
    container_destination="$(container_mount_destination_for "$container" "$mp")"
    container_probe_target="$(container_probe_target_for "$container" "$probe_target")"
    container_has_mount_destination "$container" "$container_destination" || continue

    if container_probe_ok "$container" "$container_probe_target"; then
      continue
    fi

    action_key="container.${container}"
    if [[ "$container" == "plex" ]] && should_defer_for_active_plex; then
      log "$container: mount namespace for $container_probe_target is stale but Plex has active sessions -> deferring container restart"
      continue
    fi

    if throttled "$action_key"; then
      log "$container: mount namespace for $container_probe_target is stale; action throttled (<${COOLDOWN_SECS}s) -> skipping"
      continue
    fi

    mark_action "$action_key"
    log "$container: mount namespace for $container_probe_target is stale -> restarting container"
    docker restart "$container" >/dev/null 2>&1 || log "$container: restart failed after stale mount detection"
  done
}

handle_runtime_config_drift() {
  local remote="$1" mp="$2" probe_target="$3" unit="$4"
  local rc_addr expected_bytes live_bytes action_key

  string_array_contains "$remote" "${CONFIG_DRIFT_REMOTES[@]}" || return 1

  rc_addr="$(unit_rc_addr_from_service "$unit")"
  expected_bytes="$(unit_cache_max_size_bytes "$unit")"
  live_bytes="$(remote_runtime_cache_max_size_bytes "$rc_addr")"

  [[ "$expected_bytes" =~ ^[0-9]+$ ]] || return 1
  [[ "$live_bytes" =~ ^[0-9]+$ ]] || return 1
  [[ "$expected_bytes" == "$live_bytes" ]] && return 1

  if config_drift_blocker_active "$remote"; then
    log "$remote: runtime cache max size ${live_bytes} != configured ${expected_bytes}, but blocker units are active -> deferring mount restart"
    return 0
  fi

  if should_defer_for_active_plex; then
    log "$remote: runtime cache max size ${live_bytes} != configured ${expected_bytes}, and Plex has active sessions -> deferring mount restart"
    return 0
  fi

  action_key="config_drift.${remote}"
  if throttled "$action_key"; then
    log "$remote: runtime cache max size ${live_bytes} != configured ${expected_bytes}; action throttled (<${COOLDOWN_SECS}s) -> skipping"
    return 0
  fi

  log "$remote: runtime cache max size ${live_bytes} != configured ${expected_bytes} -> restarting unit to apply config drift"
  mark_action "$action_key"
  if restart_mount_unit "$unit"; then
    if wait_for_mount_ready "$mp" "$probe_target"; then
      clear_failure_count "$remote"
      plex_reprobe_required=1
    else
      log "$remote: restart issued for config drift, but $mp is not ready yet"
    fi
  fi
  return 0
}

main() {
  local r mp unit probe_target sub act failures

  for r in "${REMOTES[@]}"; do
    mp="/mnt/$r"
    unit="rclone-mount@$r.service"
    probe_target="$(probe_target_for_mount "$mp")"

    mkdir -p "$mp" 2>/dev/null || true

    sub="$(unit_prop "$unit" SubState)"
    act="$(unit_prop "$unit" ActiveState)"

    # If systemd is already applying RestartSec backoff, don't fight it.
    if [[ "$sub" == "auto-restart" ]]; then
      log "$r: unit is in auto-restart backoff (RestartSec applies) -> skipping"
      continue
    fi

    if mountpoint -q "$mp"; then
      # Mounted: must be listable quickly, otherwise treat as stale/hung
      if timeout "$LS_TIMEOUT" ls -1A "$probe_target" >/dev/null 2>&1; then
        clear_failure_count "$r"
        restart_stale_namespace_containers "$mp" "$probe_target"
        if handle_runtime_config_drift "$r" "$mp" "$probe_target" "$unit"; then
          continue
        fi
        continue
      fi

      failures="$(increment_failure_count "$r")"
      if (( failures < FAILURE_THRESHOLD )); then
        log "$r: probe $probe_target is slow/unresponsive; failure ${failures}/${FAILURE_THRESHOLD} -> waiting"
        continue
      fi

      if should_defer_for_active_plex; then
        log "$r: probe $probe_target is failing and Plex has active sessions -> deferring mount restart"
        continue
      fi

      if throttled "$r"; then
        log "$r: mounted but unresponsive; action throttled (<${COOLDOWN_SECS}s) -> skipping"
        continue
      fi

      log "$r: probe $probe_target failed ${failures} consecutive times -> detaching and restarting unit"
      mark_action "$r"
      detach_mount "$mp"
      if restart_mount_unit "$unit"; then
        if wait_for_mount_ready "$mp" "$probe_target"; then
          clear_failure_count "$r"
          plex_reprobe_required=1
        else
          log "$r: mount restart issued, but $mp is not ready yet"
        fi
      fi
      continue
    fi

    # Not mounted:
    # If unit is active but mount is missing -> restart (throttled)
    # Otherwise leave it to systemd retries (especially during upstream outage)
    if [[ "$act" == "active" ]]; then
      failures="$(increment_failure_count "$r")"
      if (( failures < FAILURE_THRESHOLD )); then
        log "$r: unit active but $mp not mounted; failure ${failures}/${FAILURE_THRESHOLD} -> waiting"
        continue
      fi

      if should_defer_for_active_plex; then
        log "$r: unit active but $mp not mounted, and Plex has active sessions -> deferring mount restart"
        continue
      fi

      if throttled "$r"; then
        log "$r: unit active but $mp not mounted; action throttled (<${COOLDOWN_SECS}s) -> skipping"
        continue
      fi
      log "$r: unit active but $mp not mounted -> restarting unit"
      mark_action "$r"
      if restart_mount_unit "$unit"; then
        if wait_for_mount_ready "$mp" "$probe_target"; then
          clear_failure_count "$r"
          plex_reprobe_required=1
        else
          log "$r: restart issued, but $mp is not ready yet"
        fi
      fi
    else
      log "$r: not mounted; unit ActiveState=$act SubState=$sub -> leaving to systemd"
    fi
  done

  if (( plex_reprobe_required )); then
    restart_post_repair_containers
    log "one or more mounts were repaired -> triggering plex stream watchdog"
    systemctl start plex-stream-watchdog.service 2>/dev/null || true
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
