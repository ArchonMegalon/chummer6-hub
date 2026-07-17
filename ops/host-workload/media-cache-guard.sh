#!/usr/bin/env bash
set -Eeuo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

CACHE_PATH="${MEDIA_CACHE_PATH:-/var/cache/rclone}"
MIN_FREE_GIB="${MEDIA_CACHE_MIN_FREE_GIB:-80}"
DOCKER_PRUNE_UNTIL="${MEDIA_CACHE_DOCKER_PRUNE_UNTIL:-2h}"
LOCK_PATH="${MEDIA_CACHE_LOCK_PATH:-/run/media-cache-guard.lock}"

log() {
  local message="$*"
  echo "[media-cache-guard] ${message}"
  logger -t media-cache-guard -- "${message}" || true
}

available_gib() {
  df -BG --output=avail "$CACHE_PATH" | awk 'NR == 2 { gsub(/G/, "", $1); print $1 }'
}

main() {
  mkdir -p "$(dirname "$LOCK_PATH")"
  exec 9>"$LOCK_PATH"
  if ! flock -n 9; then
    log "another guard run is active; skipping"
    return 0
  fi

  if [ ! -d "$CACHE_PATH" ]; then
    log "cache path missing: $CACHE_PATH"
    return 0
  fi

  local before
  before="$(available_gib)"
  log "cache filesystem free=${before}GiB threshold=${MIN_FREE_GIB}GiB"

  if [ "$before" -ge "$MIN_FREE_GIB" ]; then
    return 0
  fi

  log "free space below threshold; pruning rebuildable Docker cache older than ${DOCKER_PRUNE_UNTIL}"
  docker builder prune -af --filter "until=${DOCKER_PRUNE_UNTIL}" || true
  docker image prune -f || true
  apt-get clean || true
  journalctl --vacuum-size=512M >/dev/null || true

  local after
  after="$(available_gib)"
  log "cache filesystem free_after=${after}GiB"

  if [ "$after" -lt "$MIN_FREE_GIB" ]; then
    log "WARNING: media cache reserve still below threshold after cleanup"
  fi
}

main "$@"
